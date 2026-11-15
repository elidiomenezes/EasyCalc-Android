#include "logger.hpp"

#include <iostream>
#include <mutex>

namespace payment_gateway {
namespace {
// This is the ONLY shared state required by the reference gateway.
std::mutex log_mutex;
}

void log(const std::string& message) {
    std::lock_guard<std::mutex> guard(log_mutex);
    std::cerr << "[gateway] " << message << '\n';
}

} // namespace payment_gateway
