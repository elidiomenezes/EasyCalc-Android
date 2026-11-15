#pragma once

#include <boost/asio.hpp>

namespace course {

// Accepts incoming connections and starts one independent worker per client.
// It does not know anything about ISO 8583 fields or transaction boundaries.
class Gateway {
public:
    using tcp = boost::asio::ip::tcp;

    Gateway(tcp::endpoint listen_address, tcp::endpoint authorizer_address);
    void run(); // Run the listener until the process is stopped.

private:
    boost::asio::io_context io_;
    tcp::acceptor acceptor_;
    tcp::endpoint authorizer_address_;
};

} // namespace course
