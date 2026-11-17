#include "iso8583_parser.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using payment_gateway::FieldFormat;
using payment_gateway::Iso8583Parser;
using payment_gateway::ParseError;

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

template <typename F> void must_reject(F action) {
    try {
        action();
    } catch (const ParseError&) {
        return;
    }
    throw std::runtime_error("required ParseError was not thrown");
}

// Fixture construction is independent of the parser being assessed.
std::string bitmap_for(const std::vector<unsigned>& fields) {
    std::array<bool, 129> set{};
    for (unsigned de : fields) {
        require(de >= 2 && de <= 128, "invalid fixture field");
        set[de] = true;
        if (de > 64) set[1] = true;
    }
    std::string hex;
    const char digits[] = "0123456789ABCDEF";
    const unsigned high = set[1] ? 128U : 64U;
    for (unsigned first = 1; first <= high; first += 4) {
        unsigned nibble = 0;
        for (unsigned bit = 0; bit < 4; ++bit) {
            if (set[first + bit]) nibble |= 8U >> bit;
        }
        hex.push_back(digits[nibble]);
    }
    return hex;
}

std::string message_with(const std::string& mti,
                         const std::vector<std::pair<unsigned, std::string>>& values) {
    std::vector<unsigned> de_numbers;
    for (const auto& field : values) de_numbers.push_back(field.first);
    require(std::is_sorted(de_numbers.begin(), de_numbers.end()),
            "fixture fields must be sorted");
    std::string result = mti + bitmap_for(de_numbers);
    for (const auto& field : values) result += field.second;
    return result;
}

void fixed_exact_end() {
    std::size_t pos = 1;
    require(Iso8583Parser::parse_fixed("XAB", pos, 2) == "AB", "wrong FIXED value");
    require(pos == 3, "cursor failed to reach exact end");
}
void fixed_truncated() {
    std::size_t pos = 1;
    must_reject([&] { (void)Iso8583Parser::parse_fixed("AB", pos, 2); });
}
void fixed_past_end() {
    std::size_t pos = 10;
    must_reject([&] { (void)Iso8583Parser::parse_fixed("AB", pos, 1); });
}
void fixed_integer_overflow() {
    std::size_t pos = 1;
    must_reject([&] {
        (void)Iso8583Parser::parse_fixed("AB", pos,
                                        std::numeric_limits<std::size_t>::max());
    });
}

void llvar_zero_length() {
    std::size_t pos = 0;
    require(Iso8583Parser::parse_llvar("00", pos, 19).empty(), "zero LLVAR value");
    require(pos == 2, "zero LLVAR cursor");
}
void llvar_bad_digit() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_llvar("0XABC", pos, 19); });
}
void llvar_short_prefix() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_llvar("1", pos, 19); });
}
void llvar_above_spec_max() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_llvar("04ABCD", pos, 3); });
}
void llvar_truncated_data() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_llvar("05ABC", pos, 19); });
}
void lllvar_max_length() {
    std::size_t pos = 0;
    const std::string wire = "510" + std::string(510, 'X');
    require(Iso8583Parser::parse_lllvar(wire, pos, 510) == std::string(510, 'X'),
            "maximum LLLVAR value");
    require(pos == wire.size(), "maximum LLLVAR cursor");
}
void lllvar_bad_sign() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_lllvar("-01A", pos, 100); });
}
void lllvar_short_data() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_lllvar("006AB", pos, 30); });
}

void bitmap_last_primary_bit() {
    std::size_t pos = 0;
    auto flags = Iso8583Parser::parse_bitmaps("0000000000000001", pos);
    require(pos == 16 && flags[64] && !flags[63], "DE64 mapping");
}
void bitmap_first_secondary_bit() {
    std::size_t pos = 0;
    auto flags = Iso8583Parser::parse_bitmaps(
        "80000000000000008000000000000000", pos);
    require(pos == 32 && flags[65] && !flags[1], "DE65 mapping");
}
void bitmap_missing_secondary() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_bitmaps("8000000000000000", pos); });
}
void bitmap_bad_hex() {
    std::size_t pos = 0;
    must_reject([&] { (void)Iso8583Parser::parse_bitmaps("G000000000000000", pos); });
}
void bitmap_lowercase_hex() {
    std::size_t pos = 0;
    auto flags = Iso8583Parser::parse_bitmaps("a000000000000000" 
                                              "0000000000000000", pos);
    require(pos == 32 && flags[3] && !flags[2], "lowercase bitmap hex");
}

void message_three_fields() {
    Iso8583Parser::FieldTable table{};
    table[2] = {FieldFormat::llvar, 19};
    table[3] = {FieldFormat::fixed, 6};
    table[41] = {FieldFormat::fixed, 8};
    Iso8583Parser parser(table);
    const auto wire = message_with("0200", {
        {2, "04ABCD"}, {3, "000000"}, {41, "TERM0001"}
    });
    auto result = parser.parse(wire);
    require(result.mti == "0200", "MTI mismatch");
    require(result.present[2] && result.present[3] && result.present[41],
            "field presence mismatch");
    require(result.fields[2] == "ABCD" && result.fields[3] == "000000" &&
            result.fields[41] == "TERM0001", "field value mismatch");
}
void message_present_empty_field() {
    Iso8583Parser::FieldTable table{};
    table[2] = {FieldFormat::llvar, 19};
    auto parsed = Iso8583Parser(table).parse(message_with("0200", {{2, "00"}}));
    require(parsed.present[2] && parsed.fields[2].empty() && !parsed.present[3],
            "empty field presence not preserved");
}
void message_unsupported_field() {
    Iso8583Parser::FieldTable table{};
    must_reject([&] {
        (void)Iso8583Parser(table).parse(message_with("0200", {{3, "000000"}}));
    });
}
void message_trailing_bytes() {
    Iso8583Parser::FieldTable table{};
    table[3] = {FieldFormat::fixed, 6};
    must_reject([&] {
        (void)Iso8583Parser(table).parse(message_with("0200", {{3, "000000"}}) + "X");
    });
}
void message_invalid_mti() {
    Iso8583Parser::FieldTable table{};
    must_reject([&] { (void)Iso8583Parser(table).parse("02X0" + bitmap_for({})); });
}
void message_secondary_de123() {
    Iso8583Parser::FieldTable table{};
    table[3] = {FieldFormat::fixed, 6};
    table[123] = {FieldFormat::lllvar, 15};
    auto parsed = Iso8583Parser(table).parse(message_with("0100", {
        {3, "123456"}, {123, "003XYZ"}
    }));
    require(parsed.present[123] && parsed.fields[123] == "XYZ", "DE123 parse");
}

void nibss_table_twenty_fields() {
    const auto table = Iso8583Parser::nibss_fields();
    using F = FieldFormat;
    const struct { unsigned de; F format; std::size_t max; } expected[] = {
        {2,F::llvar,19}, {3,F::fixed,6}, {4,F::fixed,12}, {7,F::fixed,10},
        {11,F::fixed,6}, {12,F::fixed,6}, {13,F::fixed,4}, {14,F::fixed,4},
        {18,F::fixed,4}, {22,F::fixed,3}, {25,F::fixed,2}, {32,F::llvar,11},
        {35,F::llvar,37}, {37,F::fixed,12}, {39,F::fixed,2}, {41,F::fixed,8},
        {42,F::fixed,15}, {49,F::fixed,3}, {55,F::lllvar,510},
        {123,F::lllvar,15}
    };
    for (const auto& e : expected) {
        require(table[e.de].format == e.format && table[e.de].maximum == e.max,
                "incorrect NIBSS field specification DE" + std::to_string(e.de));
    }
    require(table[0].format == F::unused && table[1].format == F::unused,
            "indexes 0 and 1 must not be normal DEs");
}

using NamedTest = std::pair<std::string, std::function<void()>>;
const std::vector<NamedTest>& cases() {
    static const std::vector<NamedTest> all = {
        {"fixed_exact_end", fixed_exact_end},
        {"fixed_truncated", fixed_truncated},
        {"fixed_past_end", fixed_past_end},
        {"fixed_integer_overflow", fixed_integer_overflow},
        {"llvar_zero_length", llvar_zero_length},
        {"llvar_bad_digit", llvar_bad_digit},
        {"llvar_short_prefix", llvar_short_prefix},
        {"llvar_above_spec_max", llvar_above_spec_max},
        {"llvar_truncated_data", llvar_truncated_data},
        {"lllvar_max_length", lllvar_max_length},
        {"lllvar_bad_sign", lllvar_bad_sign},
        {"lllvar_short_data", lllvar_short_data},
        {"bitmap_last_primary_bit", bitmap_last_primary_bit},
        {"bitmap_first_secondary_bit", bitmap_first_secondary_bit},
        {"bitmap_missing_secondary", bitmap_missing_secondary},
        {"bitmap_bad_hex", bitmap_bad_hex},
        {"bitmap_lowercase_hex", bitmap_lowercase_hex},
        {"message_three_fields", message_three_fields},
        {"message_present_empty_field", message_present_empty_field},
        {"message_unsupported_field", message_unsupported_field},
        {"message_trailing_bytes", message_trailing_bytes},
        {"message_invalid_mti", message_invalid_mti},
        {"message_secondary_de123", message_secondary_de123},
        {"nibss_table_twenty_fields", nibss_table_twenty_fields},
    };
    return all;
}

} // namespace

int main(int argc, char** argv) {
    bool matched = false;
    int failures = 0;
    for (const auto& item : cases()) {
        if (argc > 1 && item.first != argv[1]) continue;
        matched = true;
        try {
            item.second();
            std::cout << "PASS " << item.first << '\n';
        } catch (const std::exception& e) {
            ++failures;
            std::cerr << "FAIL " << item.first << ": " << e.what() << '\n';
        }
    }
    return matched && failures == 0 ? 0 : 1;
}
