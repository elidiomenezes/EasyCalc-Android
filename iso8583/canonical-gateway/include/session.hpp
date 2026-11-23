#pragma once
#include <boost/asio.hpp>
#include <array>
#include <cstddef>
#include <memory>
#include <string>
#include <memory>
#include "database.hpp"
namespace payment_gateway {
namespace asio = boost::asio;
using tcp = asio::ip::tcp;
struct ParsedMessage;
class Session : public std::enable_shared_from_this<Session> {
public:
    Session(asio::io_context& io, tcp::endpoint destination);
    tcp::socket& client();
    void start();
private:
    void record_transaction(const ParsedMessage& msg, const char* direction);
    void read_client();
    void read_authorizer();
    static void half_close(tcp::socket& socket);
    void finish_if_done();
    void stop();
    void observe_frames(std::string& pending, const char* data, std::size_t size, const char* direction);
    std::unique_ptr<Database> database_;
    tcp::socket client_;
    tcp::socket authorizer_;
    tcp::endpoint destination_;
    std::array<char,16384> to_authorizer_{};
    std::array<char,16384> to_client_{};
    std::string pending_requests_;
    std::string pending_responses_;
    bool client_eof_ = false;
    bool authorizer_eof_ = false;
    bool stopped_ = false;
};
void serve_client(tcp::socket::native_handle_type fd, tcp::endpoint destination);
}
