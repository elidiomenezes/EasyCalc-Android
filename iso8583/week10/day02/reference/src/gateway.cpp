// Week 10 / Day 2: transparent TCP gateway using C++17 and Boost.Asio.
// The proxy treats messages as opaque bytes. ISO 8583 parsing comes on Day 3.
#include <boost/asio.hpp>
#include <array>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>

namespace asio = boost::asio;
using tcp = asio::ip::tcp;
using error_code = boost::system::error_code;

namespace {

std::mutex log_mutex; // Only logs are shared between threads.
void log(const std::string& text) {
    std::lock_guard<std::mutex> guard(log_mutex);
    std::cerr << "[gateway] " << text << '\n';
}

// Turn "127.0.0.1:8500" into a Boost.Asio endpoint.
tcp::endpoint parse_endpoint(const std::string& text) {
    const auto colon = text.find(':');
    if (colon == std::string::npos || text.find(':', colon + 1) != std::string::npos)
        throw std::runtime_error("Expected IPv4:port: " + text);
    const auto ip_text = text.substr(0, colon);
    const auto port_text = text.substr(colon + 1);
    if (port_text.empty() || port_text.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("Invalid port: " + port_text);
    unsigned long port = 0;
    try { port = std::stoul(port_text); }
    catch (const std::exception&) { throw std::runtime_error("Invalid port: " + port_text); }
    if (port == 0 || port > 65535) throw std::runtime_error("Port out of range");
    error_code ec;
    const auto ip = asio::ip::make_address_v4(ip_text, ec);
    if (ec) throw std::runtime_error("Invalid IPv4: " + ip_text);
    return {ip, static_cast<unsigned short>(port)};
}

// One Session owns two sockets and two buffers. It exists until callbacks end.
// shared_from_this() guarantees that asynchronous callbacks cannot access
// already-destroyed Session data. The sockets close automatically (RAII).
class Session : public std::enable_shared_from_this<Session> {
public:
    Session(asio::io_context& io, tcp::endpoint authorizer)
        : client_(io), authorizer_(io), destination_(authorizer) {}

    tcp::socket& client() { return client_; }

    void start() {
        error_code ec;
        authorizer_.connect(destination_, ec);
        if (ec) { log("Authorizer connection failed: " + ec.message()); stop(); return; }
        read_client();
        read_authorizer();
    }

private:
    tcp::socket client_;
    tcp::socket authorizer_;
    tcp::endpoint destination_;
    std::array<char, 16384> to_authorizer_{};
    std::array<char, 16384> to_client_{};
    bool client_eof_ = false;
    bool authorizer_eof_ = false;
    bool stopped_ = false;

    // Read from client, write all received bytes to authorizer, repeat.
    // async_write handles partial TCP writes. Waiting for its completion
    // before reading again gives us bounded memory and backpressure.
    void read_client() {
        auto self = shared_from_this();
        client_.async_read_some(asio::buffer(to_authorizer_),
            [self](const error_code& ec, std::size_t n) {
                if (self->stopped_) return;
                if (ec == asio::error::eof) {
                    self->client_eof_ = true;
                    self->half_close(self->authorizer_);
                    self->finish_if_done();
                } else if (ec) self->stop();
                else {
                    asio::async_write(self->authorizer_,
                        asio::buffer(self->to_authorizer_.data(), n),
                        [self](const error_code& write_ec, std::size_t) {
                            if (write_ec) self->stop();
                            else if (!self->stopped_) self->read_client();
                        });
                }
            });
    }

    // Exactly the same mechanism in the opposite direction.
    void read_authorizer() {
        auto self = shared_from_this();
        authorizer_.async_read_some(asio::buffer(to_client_),
            [self](const error_code& ec, std::size_t n) {
                if (self->stopped_) return;
                if (ec == asio::error::eof) {
                    self->authorizer_eof_ = true;
                    self->half_close(self->client_);
                    self->finish_if_done();
                } else if (ec) self->stop();
                else {
                    asio::async_write(self->client_, asio::buffer(self->to_client_.data(), n),
                        [self](const error_code& write_ec, std::size_t) {
                            if (write_ec) self->stop();
                            else if (!self->stopped_) self->read_authorizer();
                        });
                }
            });
    }

    // A TCP half-close says "done sending" without preventing reception.
    static void half_close(tcp::socket& socket) {
        error_code ignored;
        socket.shutdown(tcp::socket::shutdown_send, ignored);
    }
    void finish_if_done() { if (client_eof_ && authorizer_eof_) stop(); }
    void stop() {
        if (stopped_) return;
        stopped_ = true;
        error_code ignored;
        client_.close(ignored);
        authorizer_.close(ignored);
    }
};

// This worker owns its own Asio event loop and one dedicated authorizer socket.
// An individual failure is isolated from the listener and other clients.
void serve_client(tcp::socket::native_handle_type fd, tcp::endpoint destination) {
    try {
        asio::io_context io;
        auto session = std::make_shared<Session>(io, destination);
        error_code ec;
        session->client().assign(tcp::v4(), fd, ec);
        if (ec) { ::close(fd); throw std::runtime_error(ec.message()); }
        session->start();
        io.run(); // Executes asynchronous callbacks for this session.
    } catch (const std::exception& e) { log(std::string("Session: ") + e.what()); }
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: gateway LISTEN_IPV4:PORT AUTHORIZER_IPV4:PORT\n";
        return 2;
    }
    try {
        auto listen_at = parse_endpoint(argv[1]);
        auto authorizer = parse_endpoint(argv[2]);
        asio::io_context io;
        tcp::acceptor acceptor(io);
        acceptor.open(tcp::v4());
        acceptor.set_option(tcp::acceptor::reuse_address(true));
        acceptor.bind(listen_at);
        acceptor.listen();
        log("Listening on " + listen_at.address().to_string() + ":" +
            std::to_string(listen_at.port()));
        for (;;) {
            tcp::socket incoming(io);
            error_code ec;
            acceptor.accept(incoming, ec);
            if (ec) { log("Accept: " + ec.message()); continue; }
            // Transfer the native socket to the thread's independent io_context.
            auto fd = incoming.release(ec);
            if (ec) { log("Socket transfer: " + ec.message()); continue; }
            try { std::thread(serve_client, fd, authorizer).detach(); }
            catch (...) { ::close(fd); throw; }
        }
    } catch (const std::exception& e) {
        std::cerr << "gateway: " << e.what() << '\n';
        return 1;
    }
}
