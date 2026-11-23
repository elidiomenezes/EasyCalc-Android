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
headers = '#include <poll.h>\n#include <sys/socket.h>\n#include <cerrno>\n#include <chrono>\n#include <string_view>\n'
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
                boost::system::error_code error;
                authorizer_.connect(destination_,error);
                if(error){log("Upstream unavailable: "+error.message());break;}
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
