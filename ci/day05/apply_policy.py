#!/usr/bin/env python3
"""Apply Day 5 gateway policy on top of the canonical Day 4 instructor reference."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
source = root / "src/session.cpp"
code = source.read_text()
anchor = "void Session::start() {"
assert code.count(anchor) == 1, "Day 4 API changed: review the upstream source"
insertion = r'''
namespace {
// Synchronous framed transport scoped to the existing one-thread-per-client worker.
// Waiting is bounded and no response is ever interpreted as an approval.
int timeout_ms(const char* name, int fallback) {
    const char* v=std::getenv(name);
    if (!v || !*v) return fallback;
    try { auto n=std::stol(v); return n>0 && n<=600000 ? static_cast<int>(n) : fallback; }
    catch (...) { return fallback; }
}
bool wait_fd(int fd, short events, int ms) {
    pollfd p{}; p.fd=fd; p.events=events;
    int rc;
    do { rc=::poll(&p, 1, ms); } while(rc<0 && errno==EINTR);
    if (rc<=0) return false;
    return (p.revents & events)!=0 && !(p.revents & (POLLERR|POLLNVAL));
}
bool connect_bounded(tcp::socket& socket,const tcp::endpoint& endpoint,int ms) {
    boost::system::error_code ec;
    socket.open(tcp::v4(),ec);
    if(ec)return false;
    socket.non_blocking(true,ec);
    if(ec)return false;
    socket.connect(endpoint,ec);
    if(ec && ec!=asio::error::in_progress && ec!=asio::error::would_block)return false;
    if(ec) {
        if(!wait_fd(socket.native_handle(),POLLOUT,ms))return false;
        int so_error=0;
        socklen_t len=sizeof(so_error);
        if(::getsockopt(socket.native_handle(),SOL_SOCKET,SO_ERROR,&so_error,&len)<0 || so_error!=0)return false;
    }
    socket.non_blocking(false,ec);
    return !ec;
}
bool read_exact(int fd, char* data, std::size_t n, int timeout) {
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(timeout);
    std::size_t done=0;
    while(done<n) {
        auto left=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
        if(left<=0 || !wait_fd(fd,POLLIN,static_cast<int>(left)))return false;
        ssize_t count=::recv(fd,data+done,n-done,0);
        if(count<0 && errno==EINTR)continue;
        if(count<=0)return false;
        done+=static_cast<std::size_t>(count);
    }
    return true;
}
bool write_exact(int fd, const std::string& frame, int timeout) {
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(timeout);
    std::size_t pos=0;
    while(pos<frame.size()) {
        auto left=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
        if(left<=0 || !wait_fd(fd,POLLOUT,static_cast<int>(left)))return false;
        ssize_t count=::send(fd,frame.data()+pos,frame.size()-pos,MSG_NOSIGNAL);
        if(count<0 && errno==EINTR)continue;
        if(count<=0)return false;
        pos+=static_cast<std::size_t>(count);
    }
    return true;
}
bool read_frame(int fd, std::string& frame, int timeout) {
    char header[2];
    if(!read_exact(fd,header,2,timeout))return false;
    std::size_t n=(static_cast<unsigned char>(header[0])<<8U)|static_cast<unsigned char>(header[1]);
    if(n==0)throw std::runtime_error("zero-length TCP frame");
    frame.assign(header,2);
    std::string body(n,'\0');
    if(!read_exact(fd,body.data(),n,timeout))return false;
    frame+=body;
    return true;
}
std::string framed(const std::string& payload) {
    if(payload.empty() || payload.size()>65535)throw std::runtime_error("bad payload length");
    auto n=static_cast<unsigned>(payload.size());
    std::string result;
    result.push_back(static_cast<char>(n>>8));
    result.push_back(static_cast<char>(n&255));
    result+=payload;
    return result;
}
bool digits(const std::string& s) {
    return !s.empty() && std::all_of(s.begin(),s.end(),[](unsigned char c){return c>='0' && c<='9';});
}
bool valid_luhn(const std::string& pan) {
    if(pan.size()<12 || pan.size()>19 || !digits(pan))return false;
    int sum=0; bool double_it=false;
    for(auto it=pan.rbegin();it!=pan.rend();++it) {
        int n=*it-'0';
        if(double_it){n*=2;if(n>9)n-=9;}
        sum+=n; double_it=!double_it;
    }
    return sum%10==0;
}
std::string decision(const ParsedMessage& request, Database* db) {
    for(int de : {2,4,11,13,37,42})if(!request.present[de])return "30";
    if(!digits(request.fields[4]) || request.fields[4].size()!=12)return "30";
    if(!digits(request.fields[11]) || request.fields[11].size()!=6 ||
       request.fields[13].size()!=4 || !digits(request.fields[13]) ||
       request.fields[37].size()!=12 || request.fields[42].size()!=15)return "30";
    if(std::stoll(request.fields[4])>=1000000)return "61";
    if(!valid_luhn(request.fields[2]))return "14";
    if(!db)return "96";
    try {
        auto stmt=db->prepare("SELECT 1 FROM authorized_merchants WHERE merchant_id=:merchant LIMIT 1");
        stmt.bind(":merchant",std::string_view(request.fields[42]));
        return stmt.step() ? "" : "03";
    } catch(const std::exception& error) {
        log(std::string("Merchant database error: ")+error.what());
        return "96";
    }
}
ParsedMessage make_decline(const ParsedMessage& request, const std::string& code) {
    ParsedMessage response{};
    response.mti=request.mti=="0100" ? "0110" : "0210";
    for(int de : {11,13,37,41}) {
        if(request.present[de]) {
            response.present[de]=true;
            response.fields[de]=request.fields[de];
        }
    }
    response.present[39]=true;
    response.fields[39]=code;
    return response;
}
} // namespace
'''
headers = '#include <poll.h>\n#include <sys/socket.h>\n#include <netinet/in.h>\n#include <cerrno>\n#include <chrono>\n#include <string_view>\n'
code=code.replace('#include "session.hpp"', '#include "session.hpp"\n'+headers,1)
start=code.index(anchor)
end=code.index("\nvoid Session::read_client()",start)
replacement=r'''void Session::start() {
    static const Iso8583Parser parser{};
    const int idle_timeout=timeout_ms("ISO8583_IDLE_TIMEOUT_MS",300000);
    const int upstream_timeout=timeout_ms("ISO8583_UPSTREAM_TIMEOUT_MS",3000);
    const int client_timeout=timeout_ms("ISO8583_CLIENT_WRITE_TIMEOUT_MS",3000);
    try {
        for(;;) {
            std::string input;
            if(!read_frame(client_.native_handle(),input,idle_timeout))break;
            auto started=std::chrono::steady_clock::now();
            ParsedMessage request{};
            try {request=parser.parse(input.substr(2));}
            catch(const ParseError& e) {
                log(std::string("Malformed ISO payload, session closed: ")+e.what());
                break;
            }
            bool local=(request.mti=="0100" || request.mti=="0200");
            std::string reason=local ? decision(request,database_.get()) : "";
            if(!reason.empty()) {
                const auto response=make_decline(request,reason);
                std::string output=framed(parser.compose(response));
                try {
                    record_transaction(request,"request");
                    record_transaction(response,"response");
                } catch(const std::exception& e) {
                    log(std::string("Decline persistence error: ")+e.what());
                }
                if(!write_exact(client_.native_handle(),output,client_timeout))break;
                auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now()-started).count();
                log("local decline MTI="+request.mti+" code="+reason+" elapsed_ms="+std::to_string(ms));
                continue;
            }
            if(!authorizer_.is_open()) {
                if(!connect_bounded(authorizer_,destination_,upstream_timeout)) {
                    log("Upstream connect failed or timed out");break;
                }
            }
            try { record_transaction(request,"request"); }
            catch(const std::exception& e){log(std::string("Request persistence error: ")+e.what());}
            if(!write_exact(authorizer_.native_handle(),input,upstream_timeout)) {
                log("Upstream send failed or timed out");break;
            }
            std::string output;
            if(!read_frame(authorizer_.native_handle(),output,upstream_timeout)) {
                log("Upstream response timed out or disconnected");break;
            }
            try {
                auto response=parser.parse(output.substr(2));
                record_transaction(response,"response");
            } catch(const std::exception& e) {
                log(std::string("Upstream response error: ")+e.what());
                break;
            }
            if(!write_exact(client_.native_handle(),output,client_timeout))break;
            auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now()-started).count();
            log("forwarded MTI="+request.mti+" elapsed_ms="+std::to_string(ms));
        }
    } catch(const std::exception& e) {
        log(std::string("Session stopped: ")+e.what());
    }
    stop();
}
'''
code=code[:start]+insertion+replacement+code[end:]
source.write_text(code)
schema=root/"schema.sql"
s=schema.read_text()
s+='''
CREATE TABLE IF NOT EXISTS authorized_merchants (
    merchant_id TEXT PRIMARY KEY NOT NULL
);
'''
for i in range(1,11):
    s+=f"INSERT OR IGNORE INTO authorized_merchants(merchant_id) VALUES('MERCHANT{i:07d}');\n"
schema.write_text(s)
print("Day 5 policy installed into Day 4 source")

# Preserve the complete Day 4 codec, including LLLLVAR, and add compose in place.
hpp=root/"include/iso8583_parser.hpp"
h=hpp.read_text()
if "class ComposeError" not in h:
    h=h.replace("class Iso8583Parser", "class ComposeError : public std::runtime_error {\npublic:\n    using std::runtime_error::runtime_error;\n};\n\nclass Iso8583Parser",1)
if "compose(const ParsedMessage&" not in h:
    h=h.replace("private:\n    FieldTable fields_", "    std::string compose(const ParsedMessage& message) const;\n\nprivate:\n    FieldTable fields_",1)
    assert "compose(const ParsedMessage&" in h, "missing codec insertion"
hpp.write_text(h)
cpp=root/"src/iso8583_parser.cpp"
s=cpp.read_text()
if "Iso8583Parser::compose(" not in s:
    extra=r'''
namespace {
bool day05_digits(const std::string& s) {
    return std::all_of(s.begin(),s.end(),[](unsigned char c){return c>='0' && c<='9';});
}
std::string day05_bitmap(const Iso8583Parser::PresenceMap& present,unsigned first) {
    static const char hex[]="0123456789ABCDEF";
    std::string s;
    for(unsigned n=0;n<16;++n) {
        unsigned bits=0;
        for(unsigned b=0;b<4;++b)if(present[first+n*4+b])bits|=(8U>>b);
        s+=hex[bits];
    }
    return s;
}
void day05_length(std::string& output,std::size_t length,unsigned width) {
    const std::string decimal=std::to_string(length);
    output.append(width-decimal.size(),'0');
    output+=decimal;
}
}
std::string Iso8583Parser::compose(const ParsedMessage& msg) const {
    if(msg.mti.size()!=4 || !day05_digits(msg.mti))throw ComposeError("invalid MTI");
    if(msg.present[0] || msg.present[1])throw ComposeError("reserved data element");
    auto bitmap=msg.present;
    bool secondary=false;
    for(unsigned de=2;de<=128;++de) {
        if(!msg.present[de])continue;
        const auto spec=fields_[de];
        const std::size_t n=msg.fields[de].size();
        if(spec.format==FieldFormat::unused)throw ComposeError("unsupported data element");
        if(spec.format==FieldFormat::fixed && n!=spec.maximum)throw ComposeError("fixed length mismatch");
        if(spec.format!=FieldFormat::fixed && n>spec.maximum)throw ComposeError("variable length too long");
        if(spec.format==FieldFormat::llvar && n>99)throw ComposeError("LLVAR prefix overflow");
        if(spec.format==FieldFormat::lllvar && n>999)throw ComposeError("LLLVAR prefix overflow");
        if(spec.format==FieldFormat::llllvar && n>9999)throw ComposeError("LLLLVAR prefix overflow");
        if(de>64)secondary=true;
    }
    bitmap[1]=secondary;
    std::string output=msg.mti+day05_bitmap(bitmap,1);
    if(secondary)output+=day05_bitmap(bitmap,65);
    for(unsigned de=2;de<=128;++de) {
        if(!msg.present[de])continue;
        auto format=fields_[de].format;
        if(format==FieldFormat::llvar)day05_length(output,msg.fields[de].size(),2);
        else if(format==FieldFormat::lllvar)day05_length(output,msg.fields[de].size(),3);
        else if(format==FieldFormat::llllvar)day05_length(output,msg.fields[de].size(),4);
        output+=msg.fields[de];
    }
    return output;
}
'''
    pos=s.rfind("} // namespace payment_gateway")
    assert pos>0, "unexpected codec namespace layout"
    s=s[:pos]+extra+s[pos:]
cpp.write_text(s)
