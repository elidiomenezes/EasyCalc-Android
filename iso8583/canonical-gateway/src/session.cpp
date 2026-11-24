#include "session.hpp"
#include <poll.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <cerrno>
#include <chrono>
#include <string_view>

#include "logger.hpp"
#include "iso8583_parser.hpp"
#include <stdexcept>
#include <string>
#include <algorithm>
#include <unistd.h>
#include <ctime>
#include <cstdlib>
#include <cstdint>
#include <memory>
namespace payment_gateway {
namespace {
std::string now_utc() {
    const auto t=std::time(nullptr);
    std::tm tm{};
    gmtime_r(&t,&tm);
    char buffer[32];
    std::strftime(buffer,sizeof(buffer),"%Y-%m-%dT%H:%M:%SZ",&tm);
    return buffer;
}
std::string transaction_date(const std::string& mmdd) {
    if(mmdd.size()!=4 || mmdd.find_first_not_of("0123456789")!=std::string::npos)
        throw DatabaseError("invalid transaction date");
    const int mm=std::stoi(mmdd.substr(0,2)),dd=std::stoi(mmdd.substr(2,2));
    if(mm<1||mm>12||dd<1||dd>31)throw DatabaseError("invalid transaction date");
    std::time_t current=std::time(nullptr);
    std::tm now{};gmtime_r(&current,&now);
    std::tm candidate=now;
    candidate.tm_mon=mm-1;candidate.tm_mday=dd;
    candidate.tm_hour=12;candidate.tm_min=0;candidate.tm_sec=0;
    candidate.tm_isdst=0;
    std::time_t timestamp=timegm(&candidate);
    if(timestamp>current+15552000) candidate.tm_year-=1;
    else if(timestamp<current-15552000)candidate.tm_year+=1;
    candidate.tm_hour=12;
    timestamp=timegm(&candidate);
    std::tm checked{};gmtime_r(&timestamp,&checked);
    if(checked.tm_mon!=mm-1||checked.tm_mday!=dd)throw DatabaseError("invalid transaction date");
    char result[11];std::strftime(result,sizeof(result),"%Y-%m-%d",&checked);
    return result;
}
std::string right_trim(std::string v) {
    while(!v.empty() && v.back()==' ')v.pop_back();
    return v;
}
}
void Session::record_transaction(const ParsedMessage& msg, const char* direction) {
    if(!database_)return;
    static constexpr struct {const char* req;const char* response;const char* op;} types[]={
        {"0100","0110","AUTHORIZATION"},
        {"0200","0210","FINANCIAL"},
        {"0220","0230","ADVICE"},
        {"0420","0430","REVERSAL"}
    };
    const bool is_request=std::string(direction)=="request";
    const char* operation=nullptr;
    for(const auto& type:types){
        if(msg.mti==(is_request?type.req:type.response)) {operation=type.op;break;}
    }
    if(!operation)return;
    if(!msg.present[11]||!msg.present[37]||!msg.present[13])return;
    const std::string& stan=msg.fields[11];
    const std::string& rrn=msg.fields[37];
    const std::string day=transaction_date(msg.fields[13]);
    auto tx=database_->begin_transaction();
    if(is_request){
        auto existing=database_->prepare(
            "SELECT id FROM transactions WHERE stan=:stan AND rrn=:rrn "
            "AND transaction_date=:day AND operation=:operation LIMIT 1");
        existing.bind(":stan",std::string_view(stan));
        existing.bind(":rrn",std::string_view(rrn));
        existing.bind(":day",std::string_view(day));
        existing.bind(":operation",std::string_view(operation));
        if(existing.step()) {tx.commit();return;}
        if(!msg.present[4])return;
        const auto amount=static_cast<std::int64_t>(std::stoll(msg.fields[4]));
        auto insert=database_->prepare(
            "INSERT INTO transactions(stan,rrn,transaction_date,cardholder_ref,merchant_ref,"
            "operation,amount_minor,currency,status,outcome_code,created_at,completed_at) "
            "VALUES(:stan,:rrn,:day,NULL,:merchant,:op,:amount,:currency,'PENDING',NULL,:created,NULL)");
        insert.bind(":stan",std::string_view(stan));
        insert.bind(":rrn",std::string_view(rrn));
        insert.bind(":day",std::string_view(day));
        insert.bind(":merchant",std::string_view(msg.present[42]?right_trim(msg.fields[42]):""));
        insert.bind(":op",std::string_view(operation));
        insert.bind(":amount",amount);
        insert.bind(":currency",std::string_view(msg.present[49]?msg.fields[49]:""));
        const std::string received=now_utc();
        insert.bind(":created",std::string_view(received));
        (void)insert.step();
    } else {
        if(!msg.present[39])return;
        auto update=database_->prepare(
            "UPDATE transactions SET status=:status, outcome_code=:code,completed_at=:completed "
            "WHERE id=(SELECT id FROM transactions WHERE stan=:stan AND rrn=:rrn "
            "AND transaction_date=:day AND operation=:operation ORDER BY id DESC LIMIT 1) "
            "AND status='PENDING'");
        const std::string status=msg.fields[39]=="00"?"APPROVED":"DECLINED";
        update.bind(":status",std::string_view(status));
        update.bind(":code",std::string_view(msg.fields[39]));
        const std::string completed=now_utc();
        update.bind(":completed",std::string_view(completed));
        update.bind(":stan",std::string_view(stan));
        update.bind(":rrn",std::string_view(rrn));
        update.bind(":day",std::string_view(day));
        update.bind(":operation",std::string_view(operation));
        (void)update.step();
    }
    tx.commit();
}

void Session::observe_frames(std::string& pending,const char* data,std::size_t size,const char* direction) {
    constexpr std::size_t header_size=2;
    constexpr std::size_t max_frame_size=65535;
    pending.append(data,size);
    static const Iso8583Parser parser{};
    while(pending.size()>=header_size) {
        const auto b0=static_cast<unsigned char>(pending[0]);
        const auto b1=static_cast<unsigned char>(pending[1]);
        const std::size_t length=(static_cast<std::size_t>(b0)<<8U)|b1;
        if(length==0 || length>max_frame_size){log(std::string(direction)+" invalid frame length");pending.clear();return;}
        if(pending.size()-header_size<length)return;
        const std::string payload=pending.substr(header_size,length);
        try {
            const auto message=parser.parse(payload);
            // DAY 4 TODO: persist request/response business data here.
            // Read ISO8583_DB_PATH (same file across workers), own a per-worker
            // Database, and correlate by STAN + RRN + transaction_date.
            // Never block forwarding on SQLite failure or log sensitive fields.
            try { record_transaction(message,direction); }
            catch(const std::exception& error){log(std::string("Database persistence failed: ")+error.what());}
            const auto count=std::count(message.present.begin(),message.present.end(),true);
            log(std::string(direction)+" ISO8583 MTI="+message.mti+" fields="+std::to_string(count));
        } catch(const ParseError& error) {log(std::string(direction)+" unparsed ISO8583 frame: "+error.what());}
        pending.erase(0,header_size+length);
    }
}
Session::Session(asio::io_context& io,tcp::endpoint destination)
    : client_(io),authorizer_(io),destination_(destination) {
    const char* path=std::getenv("ISO8583_DB_PATH");
    if(path && *path) {
        try {database_=std::make_unique<Database>(path);}
        catch(const std::exception& error){log(std::string("Database unavailable: ")+error.what());}
    }
}
tcp::socket& Session::client(){return client_;}

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
        auto stmt=db->prepare("SELECT 1 FROM authorized_merchants WHERE merchant_ref=:merchant LIMIT 1");
        stmt.bind(":merchant",std::string_view(right_trim(request.fields[42])));
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
void Session::start() {
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
            std::string upstream_frame=input;
            const auto length=static_cast<unsigned>(upstream_frame.size());
            upstream_frame[0]=static_cast<char>(length>>8U);
            upstream_frame[1]=static_cast<char>(length&255U);
            if(!write_exact(authorizer_.native_handle(),upstream_frame,upstream_timeout)) {
                log("Upstream send failed or timed out");break;
            }
            std::string output;
            if(!read_frame(authorizer_.native_handle(),output,upstream_timeout)) {
                log("Upstream response timed out or disconnected");break;
            }
            try {
                auto response=parser.parse(output.substr(2));
                std::string expected_mti=request.mti;
                if(expected_mti.size()!=4 || expected_mti[2]<'0' || expected_mti[2]>'8')
                    throw std::runtime_error("unsupported request MTI response pair");
                ++expected_mti[2];
                if(response.mti!=expected_mti)
                    throw std::runtime_error("upstream response MTI mismatch");
                for(int de : {11,13,37}) {
                    if(request.present[de] &&
                       (!response.present[de] || request.fields[de]!=response.fields[de]))
                        throw std::runtime_error("upstream response correlation mismatch");
                }
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

void Session::read_client() {
    auto self=shared_from_this();
    client_.async_read_some(asio::buffer(to_authorizer_),[self](const boost::system::error_code& error,std::size_t bytes){
        if(self->stopped_)return;
        if(error==asio::error::eof){self->client_eof_=true;self->half_close(self->authorizer_);self->finish_if_done();}
        else if(error){self->stop();}
        else {
            self->observe_frames(self->pending_requests_,self->to_authorizer_.data(),bytes,"request");
            asio::async_write(self->authorizer_,asio::buffer(self->to_authorizer_.data(),bytes),[self](const boost::system::error_code& write_error,std::size_t){
                if(write_error)self->stop();
                else if(!self->stopped_)self->read_client();
            });
        }
    });
}
void Session::read_authorizer() {
    auto self=shared_from_this();
    authorizer_.async_read_some(asio::buffer(to_client_),[self](const boost::system::error_code& error,std::size_t bytes){
        if(self->stopped_)return;
        if(error==asio::error::eof){self->authorizer_eof_=true;self->half_close(self->client_);self->finish_if_done();}
        else if(error){self->stop();}
        else {
            self->observe_frames(self->pending_responses_,self->to_client_.data(),bytes,"response");
            asio::async_write(self->client_,asio::buffer(self->to_client_.data(),bytes),[self](const boost::system::error_code& write_error,std::size_t){
                if(write_error)self->stop();
                else if(!self->stopped_)self->read_authorizer();
            });
        }
    });
}
void Session::half_close(tcp::socket& socket) {
    boost::system::error_code ignored;
    socket.shutdown(tcp::socket::shutdown_send,ignored);
}
void Session::finish_if_done(){if(client_eof_ && authorizer_eof_)stop();}
void Session::stop(){
    if(stopped_)return;
    stopped_=true;
    boost::system::error_code ignored;
    client_.close(ignored);
    authorizer_.close(ignored);
}
void serve_client(tcp::socket::native_handle_type fd,tcp::endpoint destination){
    try {
        asio::io_context io;
        auto session=std::make_shared<Session>(io,destination);
        boost::system::error_code error;
        session->client().assign(tcp::v4(),fd,error);
        if(error){::close(fd);throw std::runtime_error("Socket assignment: "+error.message());}
        session->start();io.run();
    }catch(const std::exception& error){log(std::string("Session failure: ")+error.what());}
}
}
