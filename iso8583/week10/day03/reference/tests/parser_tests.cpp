#include "iso8583_parser.hpp"

#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using payment_gateway::Iso8583Parser;
using payment_gateway::ParseError;
using payment_gateway::FieldFormat;

static void require(bool condition, const std::string& explanation) {
    if (!condition) throw std::runtime_error(explanation);
}

static void fixed() {
    std::size_t pos = 2;
    require(Iso8583Parser::parse_fixed("xxABCz", pos, 3) == "ABC",
            "FIXED value mismatch");
    require(pos == 5, "FIXED cursor mismatch");
    try {
        (void)Iso8583Parser::parse_fixed("AB", pos, 3);
    } catch (const ParseError&) {
        return;
    }
    throw std::runtime_error("truncated FIXED field was accepted");
}

static void llvar() {
    std::size_t pos = 0;
    require(Iso8583Parser::parse_llvar("03ABC!", pos, 5) == "ABC",
            "LLVAR value mismatch");
    require(pos == 5, "LLVAR cursor mismatch");
    pos = 0;
    try {
        (void)Iso8583Parser::parse_llvar("A3ABC", pos, 10);
    } catch (const ParseError&) {
        return;
    }
    throw std::runtime_error("nondigit LLVAR prefix was accepted");
}

static void lllvar() {
    std::size_t pos = 0;
    require(Iso8583Parser::parse_lllvar("005HELLO", pos, 15) == "HELLO",
            "LLLVAR value mismatch");
    require(pos == 8, "LLLVAR cursor mismatch");
    pos = 0;
    try {
        (void)Iso8583Parser::parse_lllvar("016HELLO", pos, 15);
    } catch (const ParseError&) {
        return;
    }
    throw std::runtime_error("oversized LLLVAR field was accepted");
}

static void bitmap() {
    std::size_t pos = 0;
    auto primary = Iso8583Parser::parse_bitmaps("4000000000000000", pos);
    require(pos == 16 && primary[2] && !primary[3],
            "primary bitmap decoded incorrectly");
    pos = 0;
    auto both = Iso8583Parser::parse_bitmaps(
        "80000000000000004000000000000000", pos);
    require(pos == 32 && both[66] && !both[1],
            "secondary bitmap decoded incorrectly");
}

static void message() {
    Iso8583Parser::FieldTable fields{};
    fields[3] = {FieldFormat::fixed, 6};
    Iso8583Parser parser(fields);
    auto parsed = parser.parse("02002000000000000000000000");
    require(parsed.mti == "0200", "MTI mismatch");
    require(parsed.present[3], "DE3 missing");
    require(parsed.fields[3] == "000000", "DE3 value mismatch");
}

int main(int argc, char** argv) {
    const std::vector<std::pair<std::string, std::function<void()>>> cases = {
        {"fixed", fixed}, {"llvar", llvar}, {"lllvar", lllvar},
        {"bitmap", bitmap}, {"message", message}
    };
    int failures = 0;
    bool selected = false;
    for (const auto& test : cases) {
        if (argc > 1 && test.first != argv[1]) continue;
        selected = true;
        try {
            test.second();
            std::cout << "PASS " << test.first << '\n';
        } catch (const std::exception& error) {
            std::cerr << "FAIL " << test.first << ": " << error.what() << '\n';
            ++failures;
        }
    }
    return selected && failures == 0 ? 0 : 1;
}
