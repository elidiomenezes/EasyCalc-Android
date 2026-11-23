#include "logger.hpp"
#include <iostream>
#include <mutex>
namespace payment_gateway {
namespace { std::mutex log_mutex; }
void log(const std::string& message) {
    std::lock_guard<std::mutex> guard(log_mutex);
    std::cerr << "[gateway] " << message << '\n';
}
}
