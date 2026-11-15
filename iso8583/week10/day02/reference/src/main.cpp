#include "gateway.hpp"

#include <boost/asio.hpp>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

// Convert an IPv4:port command-line argument into an Asio endpoint.
course::Gateway::tcp::endpoint parse_endpoint(const std::string& text) {
    const auto colon = text.find(':');
    if (colon == std::string::npos || text.find(':', colon + 1) != std::string::npos)
        throw std::runtime_error("Expected IPv4:port: " + text);

    const auto host = text.substr(0, colon);
    const auto port_text = text.substr(colon + 1);
    if (port_text.empty() || port_text.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("Invalid port: " + port_text);

    unsigned long port = 0;
    try { port = std::stoul(port_text); }
    catch (const std::exception&) { throw std::runtime_error("Invalid port: " + port_text); }
    if (port == 0 || port > 65535) throw std::runtime_error("Port out of range");

    boost::system::error_code error;
    const auto address = boost::asio::ip::make_address_v4(host, error);
    if (error) throw std::runtime_error("Invalid IPv4 address: " + host);
    return {address, static_cast<unsigned short>(port)};
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: gateway LISTEN_IPV4:PORT AUTHORIZER_IPV4:PORT\n";
        return 2;
    }

    try {
        course::Gateway gateway(parse_endpoint(argv[1]), parse_endpoint(argv[2]));
        gateway.run();
    } catch (const std::exception& error) {
        std::cerr << "gateway: " << error.what() << '\n';
        return 1;
    }
}
