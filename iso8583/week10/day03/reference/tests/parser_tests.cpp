#include "iso8583_parser.hpp"

#include <array>
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


static void extended_nibss() {
    using F = FieldFormat;
    const struct { unsigned de; F format; std::size_t maximum; } expected[] = {
        {2, F::llvar, 19},
        {3, F::fixed, 6},
        {4, F::fixed, 12},
        {5, F::fixed, 12},
        {7, F::fixed, 10},
        {9, F::fixed, 8},
        {11, F::fixed, 6},
        {12, F::fixed, 6},
        {13, F::fixed, 4},
        {14, F::fixed, 4},
        {15, F::fixed, 4},
        {16, F::fixed, 4},
        {18, F::fixed, 4},
        {22, F::fixed, 3},
        {23, F::fixed, 3},
        {25, F::fixed, 2},
        {26, F::fixed, 2},
        {28, F::fixed, 9},
        {29, F::fixed, 9},
        {30, F::fixed, 9},
        {31, F::fixed, 9},
        {32, F::llvar, 11},
        {33, F::llvar, 11},
        {35, F::llvar, 37},
        {37, F::fixed, 12},
        {38, F::fixed, 6},
        {39, F::fixed, 2},
        {40, F::fixed, 3},
        {41, F::fixed, 8},
        {42, F::fixed, 15},
        {43, F::fixed, 40},
        {44, F::llvar, 25},
        {45, F::llvar, 76},
        {48, F::lllvar, 999},
        {49, F::fixed, 3},
        {50, F::fixed, 3},
        {52, F::fixed, 16},
        {53, F::fixed, 96},
        {54, F::lllvar, 120},
        {55, F::lllvar, 510},
        {56, F::lllvar, 4},
        {58, F::lllvar, 11},
        {59, F::lllvar, 255},
        {60, F::lllvar, 999},
        {62, F::lllvar, 999},
        {63, F::llllvar, 9999},
        {64, F::fixed, 64},
        {67, F::fixed, 2},
        {90, F::fixed, 42},
        {95, F::fixed, 42},
        {98, F::fixed, 25},
        {100, F::llvar, 11},
        {102, F::llvar, 28},
        {103, F::llvar, 28},
        {123, F::lllvar, 15},
        {124, F::llllvar, 9999},
        {128, F::fixed, 64}
    };
    const auto table = Iso8583Parser::nibss_fields();
    std::array<bool,129> bits{};
    bits[1] = true;
    for (const auto& e : expected) {
        require(table[e.de].format == e.format &&
                table[e.de].maximum == e.maximum,
                "incorrect DE specification " + std::to_string(e.de));
        bits[e.de] = true;
    }
    std::size_t configured = 0;
    for (const auto& e : table) {
        if (e.format != F::unused) ++configured;
    }
    require(configured == 57, "expected exactly 57 NIBSS layout fields");
    require(table[70].format == F::unused, "DE70 must not be supported");

    // Build an independent wire fixture containing all 57 fields.
    std::string wire = "0200";
    constexpr char hex[] = "0123456789ABCDEF";
    for (unsigned de = 1; de <= 128; de += 4) {
        unsigned nibble = 0;
        for (unsigned bit = 0; bit < 4; ++bit) {
            if (bits[de + bit]) nibble |= 8U >> bit;
        }
        wire += hex[nibble];
    }
    for (const auto& e : expected) {
        const std::string value(e.format == F::fixed ? e.maximum : 3U,
                                static_cast<char>('A' + (e.de % 26U)));
        if (e.format == F::llvar) wire += "03";
        if (e.format == F::lllvar) wire += "003";
        if (e.format == F::llllvar) wire += "0003";
        wire += value;
    }
    const auto parsed = Iso8583Parser().parse(wire);
    require(parsed.mti == "0200", "complete MTI incorrect");
    for (const auto& e : expected) {
        const std::string value(e.format == F::fixed ? e.maximum : 3U,
                                static_cast<char>('A' + (e.de % 26U)));
        require(parsed.present[e.de] && parsed.fields[e.de] == value,
                "complete fixture DE" + std::to_string(e.de));
    }
    std::size_t offset = 0;
    const std::string binary("0003A\0B", 7);
    require(Iso8583Parser::parse_llllvar(binary, offset, 9999).size() == 3U &&
            offset == 7U, "LLLLVAR binary safety");

    // An otherwise well-formed message with unsupported DE70 must fail.
    bits = {};
    bits[1] = true;
    bits[70] = true;
    std::string unsupported = "0800";
    for (unsigned de = 1; de <= 128; de += 4) {
        unsigned nibble = 0;
        for (unsigned bit = 0; bit < 4; ++bit) {
            if (bits[de + bit]) nibble |= 8U >> bit;
        }
        unsupported += hex[nibble];
    }
    unsupported += "001";
    try {
        (void)Iso8583Parser().parse(unsupported);
    } catch (const ParseError&) {
        return;
    }
    throw std::runtime_error("DE70 was incorrectly accepted");
}

int main(int argc, char** argv) {
    const std::vector<std::pair<std::string, std::function<void()>>> cases = {
        {"fixed", fixed}, {"llvar", llvar}, {"lllvar", lllvar},
        {"bitmap", bitmap}, {"message", message},
        {"extended_nibss", extended_nibss}
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
