#include "gateway.hpp"
#include "logger.hpp"
#include "session.hpp"

#include <string>
#include <thread>
#include <unistd.h> // close() if creating a worker thread fails

namespace course {

Gateway::Gateway(tcp::endpoint listen_address, tcp::endpoint authorizer_address)
    : acceptor_(io_), authorizer_address_(authorizer_address) {
    acceptor_.open(tcp::v4());
    acceptor_.set_option(tcp::acceptor::reuse_address(true));
    acceptor_.bind(listen_address);
    acceptor_.listen();
    log("Listening on " + listen_address.address().to_string() + ":" +
        std::to_string(listen_address.port()));
}

void Gateway::run() {
    for (;;) {
        // accept() blocks until a client arrives. That is fine: only the
        // listener waits here. Existing clients run in their own threads.
        tcp::socket incoming(io_);
        boost::system::error_code error;
        acceptor_.accept(incoming, error);
        if (error) {
            log("Accept failed: " + error.message());
            continue;
        }

        // Each worker needs its own io_context. release() transfers ownership
        // of the accepted native descriptor to serve_client(), which adopts it.
        auto fd = incoming.release(error);
        if (error) {
            log("Socket transfer failed: " + error.message());
            continue;
        }
        try {
            std::thread(serve_client, fd, authorizer_address_).detach();
        } catch (...) {
            ::close(fd); // No worker exists to own this descriptor.
            throw;
        }
    }
}

} // namespace course
