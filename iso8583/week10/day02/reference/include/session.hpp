#pragma once

#include <boost/asio.hpp>
#include <array>
#include <cstddef>
#include <memory>

namespace payment_gateway {

namespace asio = boost::asio;
using tcp = asio::ip::tcp;

// A session owns two TCP sockets: one client and one dedicated authorizer.
// Only its own worker thread runs its Asio callbacks; no network mutex needed.
class Session : public std::enable_shared_from_this<Session> {
public:
    Session(asio::io_context& io, tcp::endpoint destination);

    tcp::socket& client(); // Used once to adopt the accepted client socket.
    void start();          // Connect to authorizer and start both read loops.

private:
    void read_client();
    void read_authorizer();
    static void half_close(tcp::socket& socket);
    void finish_if_done();
    void stop();

    tcp::socket client_;
    tcp::socket authorizer_;
    tcp::endpoint destination_;

    // Different buffers prevent a write in one direction from overwriting
    // the bytes still being sent in the opposite direction.
    std::array<char, 16384> to_authorizer_{};
    std::array<char, 16384> to_client_{};
    bool client_eof_ = false;
    bool authorizer_eof_ = false;
    bool stopped_ = false;
};

// Worker entry point: owns a new Asio event loop and a single Session.
// fd is a native descriptor transferred from Gateway::run().
void serve_client(tcp::socket::native_handle_type fd, tcp::endpoint destination);

} // namespace payment_gateway
