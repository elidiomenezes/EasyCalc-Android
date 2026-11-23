#pragma once
#include <boost/asio.hpp>
namespace payment_gateway {
class Gateway {
public:
    using tcp = boost::asio::ip::tcp;
    Gateway(tcp::endpoint listen_address, tcp::endpoint authorizer_address);
    void run();
private:
    boost::asio::io_context io_;
    tcp::acceptor acceptor_;
    tcp::endpoint authorizer_address_;
};
}
