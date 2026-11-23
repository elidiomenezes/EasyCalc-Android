#include "gateway.hpp"
#include "logger.hpp"
#include "session.hpp"
#include <string>
#include <thread>
#include <unistd.h>
namespace payment_gateway {
Gateway::Gateway(tcp::endpoint listen_address, tcp::endpoint authorizer_address)
    : acceptor_(io_), authorizer_address_(authorizer_address) {
    acceptor_.open(tcp::v4());
    acceptor_.set_option(tcp::acceptor::reuse_address(true));
    acceptor_.bind(listen_address);
    acceptor_.listen();
    log("Listening on " + listen_address.address().to_string() + ":" + std::to_string(listen_address.port()));
}
void Gateway::run() {
    for (;;) {
        tcp::socket incoming(io_);
        boost::system::error_code error;
        acceptor_.accept(incoming,error);
        if(error){log("Accept failed: " + error.message());continue;}
        auto fd=incoming.release(error);
        if(error){log("Socket transfer failed: " + error.message());continue;}
        try {std::thread(serve_client,fd,authorizer_address_).detach();}
        catch(...){::close(fd);throw;}
    }
}
}
