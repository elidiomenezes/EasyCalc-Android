#pragma once

#include <array>
#include <cstddef>
#include <stdexcept>
#include <string>

namespace payment_gateway {

// The three wire formats covered in this assignment.
// 'unused' means that this project has no definition for the DE.
enum class FieldFormat { unused, fixed, llvar, lllvar };

struct FieldSpec {
    FieldFormat format = FieldFormat::unused;
    std::size_t maximum = 0;
};

// A successfully parsed ISO 8583 payload (without its 2-byte TCP header).
// Array indexes match Data Element numbers: fields[41] stores DE41.
// A present zero-length field is different from an absent field. Check
// present[de] before reading fields[de].
struct ParsedMessage {
    std::string mti;
    std::array<bool, 129> present{};
    std::array<std::string, 129> fields{};
};

class ParseError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Iso8583Parser {
public:
    using FieldTable = std::array<FieldSpec, 129>;
    using PresenceMap = std::array<bool, 129>;

    // Task 4: construct the supported part of the NIBSS POS v1.16 table.
    // Index 0 is unused. Bit 1 signals a secondary bitmap, rather than DE1
    // carrying an ordinary field value.
    static FieldTable nibss_fields();

    explicit Iso8583Parser(FieldTable fields = nibss_fields());

    // Task 1: read exactly 'length' bytes and advance 'offset'.
    // Throw ParseError if there are not enough bytes. A read of exactly the
    // remaining bytes is valid. Never perform unchecked buffer indexing.
    static std::string parse_fixed(const std::string& wire,
                                   std::size_t& offset,
                                   std::size_t length);

    // Task 2: read two decimal length digits, then exactly that many bytes.
    // The declared size must be <= maximum and <= available data bytes.
    static std::string parse_llvar(const std::string& wire,
                                   std::size_t& offset,
                                   std::size_t maximum);

    // Task 2: same rule as LLVAR, but with three decimal length digits.
    static std::string parse_lllvar(const std::string& wire,
                                    std::size_t& offset,
                                    std::size_t maximum);

    // Task 3: decode a 16-character ASCII-hex primary bitmap. When its
    // first bit is set, read and decode a 16-character secondary bitmap.
    // Update offset past all consumed bitmap characters. Bits are numbered
    // MSB first. present[1] stays false because DE1 is the indicator.
    static PresenceMap parse_bitmaps(const std::string& wire,
                                     std::size_t& offset);

    // Task 5: parse a COMPLETE ISO payload, beginning with its 4-byte MTI.
    // Use the table, bitmap and field helpers. Consume fields in ascending
    // DE order. Reject unconfigured fields and extra trailing bytes.
    // Return a complete ParsedMessage or throw ParseError; never return a
    // partially parsed message.
    ParsedMessage parse(const std::string& payload) const;

private:
    FieldTable fields_;
};

} // namespace payment_gateway
