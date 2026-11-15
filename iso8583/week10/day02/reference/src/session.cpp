#include "session.hpp"
#include "logger.hpp"

#include <stdexcept>
#include <string>
#include <unistd.h> // close() only if adopting a descriptor fails

namespace course {

Session::Session(asio::io_context& io, tcp::endpoint destination)
    : client_(io), authorizer_(io), destination_(destination) {}

tcp::socket& Session::client() { return client_; }

void Session::start() {
    boost::system::error_code error;
    authorizer_.connect(destination_, error);
    if (error) {
        log("Authorizer connection failed: " + error.message());
        stop();
        return;
    }

    // Both directions are active at the same time in one Asio event loop.
    read_client();
    read_authorizer();
}

void Session::read_client() {
    // The callback might execute after this function returns. Holding self
    // keeps the Session (including sockets and buffers) alive until then.
    auto self = shared_from_this();
    client_.async_read_some(asio::buffer(to_authorizer_),
        [self](const boost::system::error_code& error, std::size_t bytes) {
            if (self->stopped_) return;
            if (error == asio::error::eof) {
                self->client_eof_ = true;
                self->half_close(self->authorizer_);
                self->finish_if_done();
            } else if (error) {
                self->stop();
            } else {
                // Unlike a single send(), async_write keeps going until all
                // 'bytes' have been written or an error occurs.
                asio::async_write(self->authorizer_,
                    asio::buffer(self->to_authorizer_.data(), bytes),
                    [self](const boost::system::error_code& write_error, std::size_t) {
                        if (write_error) self->stop();
                        else if (!self->stopped_) self->read_client();
                    });
                // Wait for that write before reading again. This prevents
                // overwriting the buffer and provides simple backpressure.
            }
        });
}

void Session::read_authorizer() {
    // Same algorithm, but for bytes travelling toward the client.
    auto self = shared_from_this();
    authorizer_.async_read_some(asio::buffer(to_client_),
        [self](const boost::system::error_code& error, std::size_t bytes) {
            if (self->stopped_) return;
            if (error == asio::error::eof) {
                self->authorizer_eof_ = true;
                self->half_close(self->client_);
                self->finish_if_done();
            } else if (error) {
                self->stop();
            } else {
                asio::async_write(self->client_,
                    asio::buffer(self->to_client_.data(), bytes),
                    [self](const boost::system::error_code& write_error, std::size_t) {
                        if (write_error) self->stop();
                        else if (!self->stopped_) self->read_authorizer();
                    });
            }
        });
}

void Session::half_close(tcp::socket& socket) {
    // TCP supports shutting down only the sending half of a connection.
    // The other peer may still need to send its final response.
    boost::system::error_code ignored;
    socket.shutdown(tcp::socket::shutdown_send, ignored);
}

void Session::finish_if_done() {
    if (client_eof_ && authorizer_eof_) stop();
}

void Session::stop() {
    if (stopped_) return;
    stopped_ = true;
    boost::system::error_code ignored;
    client_.close(ignored);
    authorizer_.close(ignored);
    // RAII: Session and its sockets are destroyed after the last callback.
}

void serve_client(tcp::socket::native_handle_type fd, tcp::endpoint destination) {
    try {
        // This event loop belongs to ONE client. Other client sessions do
        // not share it, so callbacks do not need locks for socket access.
        asio::io_context io;
        auto session = std::make_shared<Session>(io, destination);

        boost::system::error_code error;
        session->client().assign(tcp::v4(), fd, error);
        if (error) {
            ::close(fd); // assign() did not assume ownership on failure.
            throw std::runtime_error("Socket assignment: " + error.message());
        }

        session->start();
        io.run(); // Execute asynchronous callbacks until the session ends.
    } catch (const std::exception& error) {
        log(std::string("Session failure: ") + error.what());
    }
}

} // namespace course
