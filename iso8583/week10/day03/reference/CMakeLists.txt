cmake_minimum_required(VERSION 3.16)
project(iso8583_day03_gateway LANGUAGES CXX)

add_library(iso8583_parser STATIC src/iso8583_parser.cpp)
target_compile_features(iso8583_parser PUBLIC cxx_std_17)
target_compile_options(iso8583_parser PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
target_include_directories(iso8583_parser PUBLIC include)

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

# The gateway remains the working Day 2 reference. The new parser is a
# separate component until the student completes Task 5 integration.
target_link_libraries(gateway PRIVATE iso8583_parser)

include(CTest)
if(BUILD_TESTING)
    add_executable(parser_tests tests/parser_tests.cpp)
    target_compile_features(parser_tests PRIVATE cxx_std_17)
    target_compile_options(parser_tests PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
    target_link_libraries(parser_tests PRIVATE iso8583_parser)
    foreach(name fixed llvar lllvar bitmap message extended_nibss)
        add_test(NAME parser_${name} COMMAND parser_tests ${name})
    endforeach()
    # Independent field-by-field NIBSS v1.16 reference tests:
    # every DE gets its own CTest case, including malformed/truncated input.
    add_executable(nibss_per_de_tests tests/nibss_per_de_tests.cpp)
    target_compile_features(nibss_per_de_tests PRIVATE cxx_std_17)
    target_compile_options(nibss_per_de_tests PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
    target_link_libraries(nibss_per_de_tests PRIVATE iso8583_parser)
    foreach(de 2 3 4 5 7 9 11 12 13 14 15 16 18 22 23 25 26 28 29 30 31 32 33 35 37 38 39 40 41 42 43 44 45 48 49 50 52 53 54 55 56 58 59 60 62 63 64 67 90 95 98 100 102 103 123 124 128)
        add_test(NAME nibss_de_${de} COMMAND nibss_per_de_tests ${de})
    endforeach()

endif()
