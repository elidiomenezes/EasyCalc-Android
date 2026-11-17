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
    const auto table = Iso8583Parser::nibss_fields();
    const struct { unsigned de; F format; std::size_t maximum; } extra[] = {
        {23,F::fixed,3}, {28,F::fixed,9}, {38,F::fixed,6},
        {43,F::fixed,40}, {48,F::lllvar,999}, {52,F::fixed,16},
        {53,F::fixed,96}, {59,F::lllvar,255}, {62,F::lllvar,999},
        {63,F::llllvar,9999}, {90,F::fixed,42}, {95,F::fixed,42},
        {124,F::llllvar,9999}, {128,F::fixed,64}
    };
    std::size_t configured = 0;
    for (const auto& e : table) {
        if (e.format != F::unused) ++configured;
    }
    require(configured == 34, "expected 34 configured fields (20 + 14)");
    for (const auto& e : extra) {
        require(table[e.de].format == e.format &&
                table[e.de].maximum == e.maximum,
                "incorrect extended DE definition: " + std::to_string(e.de));
    }
    std::array<bool,129> bits{};
    std::vector<std::pair<unsigned,std::string>> values = {
        {23,"001"}, {28,"C00000001"}, {38,"123456"},
        {43,std::string(40,'A')}, {48,"004DATA"},
        {52,"0123456789ABCDEF"}, {53,std::string(96,'F')},
        {59,"003ECO"}, {62,"005HELLO"}, {63,"0004ABCD"},
        {90,std::string(42,'0')}, {95,std::string(42,'1')},
        {124,"0003NFC"}, {128,std::string(64,'A')}
    };
    bits[1] = true;
    for (const auto& p : values) bits[p.first] = true;
    std::string wire = "0800";
    constexpr char hex[] = "0123456789ABCDEF";
    for (unsigned de = 1; de <= 128; de += 4) {
        unsigned nibble = 0;
        for (unsigned bit = 0; bit < 4; ++bit) {
            if (bits[de + bit]) nibble |= (8U >> bit);
        }
        wire += hex[nibble];
    }
    for (const auto& p : values) wire += p.second;
    const auto parsed = Iso8583Parser().parse(wire);
    require(parsed.mti == "0800", "extended MTI mismatch");
    for (const auto& p : values) {
        require(parsed.present[p.first], "missing DE" + std::to_string(p.first));
    }
    require(parsed.fields[48] == "DATA", "DE48 must be LLLVAR");
    require(parsed.fields[63] == "ABCD", "DE63 must be LLLLVAR");
    require(parsed.fields[124] == "NFC", "DE124 must be LLLLVAR");
    require(parsed.fields[128] == std::string(64,'A'), "DE128 mismatch");
    std::size_t pos = 0;
    require(Iso8583Parser::parse_llllvar(std::string("0003A\0B",7),pos,9999).size() == 3,
            "binary-safe LLLLVAR read failed");
    require(pos == 7, "LLLLVAR offset mismatch");
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
