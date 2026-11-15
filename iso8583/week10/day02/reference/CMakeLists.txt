cmake_minimum_required(VERSION 3.16)
project(iso8583_day02_gateway LANGUAGES CXX)

add_executable(gateway
    src/main.cpp
    src/gateway.cpp
    src/session.cpp
    src/logger.cpp
)
target_compile_features(gateway PRIVATE cxx_std_17)
target_compile_options(gateway PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
target_include_directories(gateway PRIVATE include)
find_package(Threads REQUIRED)
find_package(Boost REQUIRED COMPONENTS system)
target_link_libraries(gateway PRIVATE Threads::Threads Boost::system)
