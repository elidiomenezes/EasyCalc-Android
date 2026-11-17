#include "iso8583_parser.hpp"

#include <array>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using payment_gateway::Iso8583Parser;
using payment_gateway::ParseError;

namespace {
struct Expected { unsigned de; unsigned prefix; std::size_t maximum; };

// Independently maintained test oracle, not read from parser.nibss_fields().
// prefix = 0 FIXED, 1 LLVAR, 2 LLLVAR, 3 LLLLVAR.
constexpr Expected specifications[] = {
    {2, 1, 19},
    {3, 0, 6},
    {4, 0, 12},
    {5, 0, 12},
    {7, 0, 10},
    {9, 0, 8},
    {11, 0, 6},
    {12, 0, 6},
    {13, 0, 4},
    {14, 0, 4},
    {15, 0, 4},
    {16, 0, 4},
    {18, 0, 4},
    {22, 0, 3},
    {23, 0, 3},
    {25, 0, 2},
    {26, 0, 2},
    {28, 0, 9},
    {29, 0, 9},
    {30, 0, 9},
    {31, 0, 9},
    {32, 1, 11},
    {33, 1, 11},
    {35, 1, 37},
    {37, 0, 12},
    {38, 0, 6},
    {39, 0, 2},
    {40, 0, 3},
    {41, 0, 8},
    {42, 0, 15},
    {43, 0, 40},
    {44, 1, 25},
    {45, 1, 76},
    {48, 2, 999},
    {49, 0, 3},
    {50, 0, 3},
    {52, 0, 16},
    {53, 0, 96},
    {54, 2, 120},
    {55, 2, 510},
    {56, 2, 4},
    {58, 2, 11},
    {59, 2, 255},
    {60, 2, 999},
    {62, 2, 999},
    {63, 3, 9999},
    {64, 0, 64},
    {67, 0, 2},
    {90, 0, 42},
    {95, 0, 42},
    {98, 0, 25},
    {100, 1, 11},
    {102, 1, 28},
    {103, 1, 28},
    {123, 2, 15},
    {124, 3, 9999},
    {128, 0, 64}
};

void check(bool condition, const std::string& description) {
    if (!condition) throw std::runtime_error(description);
}

template <class Action>
void reject(Action action, const std::string& description) {
    try { action(); } catch (const ParseError&) { return; }
    throw std::runtime_error("accepted invalid message: " + description);
}

std::string decimal(std::size_t number, unsigned width) {
    std::string result(width, '0');
    for (unsigned i = 0; i < width; ++i) {
        result[width - 1 - i] = static_cast<char>('0' + number % 10);
        number /= 10;
    }
    check(number == 0, "length prefix cannot represent the value");
    return result;
}

std::string bitmap(unsigned de) {
    std::array<bool,129> bits{};
    bits[de] = true;
    if (de > 64) bits[1] = true;
    std::string result;
    constexpr char hex[] = "0123456789ABCDEF";
    for (unsigned first = 1; first <= (de > 64 ? 128U : 64U); first += 4) {
        unsigned n = 0;
        for (unsigned offset = 0; offset < 4; ++offset) {
            if (bits[first + offset]) n |= 8U >> offset;
        }
        result += hex[n];
    }
    return result;
}

std::string message(const Expected& item, const std::string& value,
                    const std::string& prefix_override = "") {
    const auto prefix = item.prefix == 0 ? std::string{} :
        (prefix_override.empty() ? decimal(value.size(), item.prefix + 1) :
                                   prefix_override);
    return "0200" + bitmap(item.de) + prefix + value;
}

void test_one(const Expected& item) {
    const Iso8583Parser parser;
    const std::string tag = "DE" + std::to_string(item.de);
    const auto field = Iso8583Parser::nibss_fields()[item.de];
    check(static_cast<unsigned>(field.format) == item.prefix + 1 &&
          field.maximum == item.maximum, tag + " configuration wrong");

    // 1. Exactly one field: its own bitmap must select only that field.
    const auto middle = item.prefix == 0 ? item.maximum : std::size_t{3};
    const std::string value(middle, static_cast<char>('A' + item.de % 26));
    const auto good = message(item, value);
    auto parsed = parser.parse(good);
    check(parsed.fields[item.de] == value && parsed.present[item.de],
          tag + " value differs from actual transmitted bytes");
    for (unsigned i = 2; i <= 128; ++i) {
        if (i != item.de) check(!parsed.present[i], tag + " false bitmap bit");
    }
    // 2. Append byte: message must be fully consumed.
    reject([&] { parser.parse(good + "!"); }, tag + " trailing byte");
    // 3. Truncate by one byte: must throw, never partially return.
    reject([&] { parser.parse(good.substr(0, good.size() - 1)); },
           tag + " truncated data");

    if (item.prefix != 0) {
        // 4. Zero-length variable field must be distinguished from absent.
        const auto empty = parser.parse(message(item, ""));
        check(empty.present[item.de] && empty.fields[item.de].empty(),
              tag + " zero-length value");
        // 5. Maximal valid value.
        const std::string max_value(item.maximum, 'M');
        const auto at_max = parser.parse(message(item, max_value));
        check(at_max.fields[item.de] == max_value, tag + " maximum length");
        // 6. Length beyond per-field max must fail, when representable.
        const std::size_t prefix_limit =
            item.prefix == 1 ? 99U : item.prefix == 2 ? 999U : 9999U;
        if (item.maximum < prefix_limit) {
            reject([&] { parser.parse(message(item, std::string(item.maximum + 1, 'X'))); },
                   tag + " above maximum");
        }
        // 7. A nondecimal prefix must fail.
        reject([&] { parser.parse(message(item, "X", std::string(item.prefix + 1, 'X'))); },
               tag + " nondigit prefix");
        // 8. Declared data length longer than received bytes.
        reject([&] { parser.parse(message(item, "X", decimal(2, item.prefix + 1))); },
               tag + " missing value bytes");
        // 9. Binary-safe extraction must preserve embedded zero bytes.
        const std::string binary("A\0B", 3);
        check(parser.parse(message(item, binary)).fields[item.de] == binary,
              tag + " binary preservation");
    }
    std::cout << "PASS " << tag << '\n';
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: nibss_per_de_tests DE_NUMBER\n";
        return 2;
    }
    const auto requested = static_cast<unsigned>(std::strtoul(argv[1], nullptr, 10));
    for (const auto& item : specifications) {
        if (item.de != requested) continue;
        try { test_one(item); return 0; }
        catch (const std::exception& error) {
            std::cerr << "FAIL DE" << requested << ": " << error.what() << '\n';
            return 1;
        }
    }
    std::cerr << "unknown DE" << requested << '\n';
    return 2;
}
