#include "iso8583_parser.hpp"

#include <algorithm>
#include <utility>

namespace payment_gateway {

namespace {

// Decode one ASCII hex character. Do not pass a possibly negative 'char'
// directly to the <cctype> functions.
unsigned hex_value(char c) {
    if (c >= '0' && c <= '9') return static_cast<unsigned>(c - '0');
    if (c >= 'A' && c <= 'F') return static_cast<unsigned>(c - 'A') + 10U;
    if (c >= 'a' && c <= 'f') return static_cast<unsigned>(c - 'a') + 10U;
    throw ParseError("invalid bitmap hex digit");
}

std::string parse_variable(const std::string& wire, std::size_t& offset,
                           std::size_t prefix_size, std::size_t maximum) {
    // Work with a tentative cursor so failures do not change the caller's
    // position. In particular, a valid prefix with a truncated value fails.
    std::size_t cursor = offset;
    auto prefix = Iso8583Parser::parse_fixed(wire, cursor, prefix_size);
    std::size_t length = 0;
    for (char digit : prefix) {
        if (digit < '0' || digit > '9') {
            throw ParseError("nondecimal variable-length prefix");
        }
        length = length * 10U + static_cast<std::size_t>(digit - '0');
    }
    if (length > maximum) throw ParseError("field exceeds specified maximum");
    auto value = Iso8583Parser::parse_fixed(wire, cursor, length);
    offset = cursor;
    return value;
}

void decode_hex_bitmap(const std::string& wire, std::size_t& cursor,
                       Iso8583Parser::PresenceMap& present,
                       unsigned first_de) {
    auto bitmap = Iso8583Parser::parse_fixed(wire, cursor, 16);
    for (std::size_t i = 0; i < bitmap.size(); ++i) {
        unsigned nibble = hex_value(bitmap[i]);
        for (unsigned bit = 0; bit < 4; ++bit) {
            unsigned de = first_de + static_cast<unsigned>(i) * 4U + bit;
            present[de] = (nibble & (8U >> bit)) != 0U;
        }
    }
}

} // namespace

Iso8583Parser::Iso8583Parser(FieldTable fields)
    : fields_(std::move(fields)) {}

Iso8583Parser::FieldTable Iso8583Parser::nibss_fields() {
    FieldTable table{};
    // NIBSS POS Interface v1.16 section 3 message-layout union.
    // DE70 is deliberately absent; not listed by the specification.
    table[2] = {FieldFormat::llvar, 19};
    table[3] = {FieldFormat::fixed, 6};
    table[4] = {FieldFormat::fixed, 12};
    table[5] = {FieldFormat::fixed, 12};
    table[7] = {FieldFormat::fixed, 10};
    table[9] = {FieldFormat::fixed, 8};
    table[11] = {FieldFormat::fixed, 6};
    table[12] = {FieldFormat::fixed, 6};
    table[13] = {FieldFormat::fixed, 4};
    table[14] = {FieldFormat::fixed, 4};
    table[15] = {FieldFormat::fixed, 4};
    table[16] = {FieldFormat::fixed, 4};
    table[18] = {FieldFormat::fixed, 4};
    table[22] = {FieldFormat::fixed, 3};
    table[23] = {FieldFormat::fixed, 3};
    table[25] = {FieldFormat::fixed, 2};
    table[26] = {FieldFormat::fixed, 2};
    table[28] = {FieldFormat::fixed, 9};
    table[29] = {FieldFormat::fixed, 9};
    table[30] = {FieldFormat::fixed, 9};
    table[31] = {FieldFormat::fixed, 9};
    table[32] = {FieldFormat::llvar, 11};
    table[33] = {FieldFormat::llvar, 11};
    table[35] = {FieldFormat::llvar, 37};
    table[37] = {FieldFormat::fixed, 12};
    table[38] = {FieldFormat::fixed, 6};
    table[39] = {FieldFormat::fixed, 2};
    table[40] = {FieldFormat::fixed, 3};
    table[41] = {FieldFormat::fixed, 8};
    table[42] = {FieldFormat::fixed, 15};
    table[43] = {FieldFormat::fixed, 40};
    table[44] = {FieldFormat::llvar, 25};
    table[45] = {FieldFormat::llvar, 76};
    table[48] = {FieldFormat::lllvar, 999};
    table[49] = {FieldFormat::fixed, 3};
    table[50] = {FieldFormat::fixed, 3};
    table[52] = {FieldFormat::fixed, 16};
    table[53] = {FieldFormat::fixed, 96};
    table[54] = {FieldFormat::lllvar, 120};
    table[55] = {FieldFormat::lllvar, 510};
    table[56] = {FieldFormat::lllvar, 4};
    table[58] = {FieldFormat::lllvar, 11};
    table[59] = {FieldFormat::lllvar, 255};
    table[60] = {FieldFormat::lllvar, 999};
    table[62] = {FieldFormat::lllvar, 999};
    table[63] = {FieldFormat::llllvar, 9999};
    table[64] = {FieldFormat::fixed, 64};
    table[67] = {FieldFormat::fixed, 2};
    table[90] = {FieldFormat::fixed, 42};
    table[95] = {FieldFormat::fixed, 42};
    table[98] = {FieldFormat::fixed, 25};
    table[100] = {FieldFormat::llvar, 11};
    table[102] = {FieldFormat::llvar, 28};
    table[103] = {FieldFormat::llvar, 28};
    table[123] = {FieldFormat::lllvar, 15};
    table[124] = {FieldFormat::llllvar, 9999};
    table[128] = {FieldFormat::fixed, 64};
    return table;
}

std::string Iso8583Parser::parse_fixed(const std::string& wire,
                                       std::size_t& offset,
                                       std::size_t length) {
    if (offset > wire.size() || length > wire.size() - offset) {
        throw ParseError("truncated FIXED field");
    }
    auto result = wire.substr(offset, length);
    offset += length;
    return result;
}

std::string Iso8583Parser::parse_llvar(const std::string& wire,
                                       std::size_t& offset,
                                       std::size_t maximum) {
    return parse_variable(wire, offset, 2, maximum);
}

std::string Iso8583Parser::parse_lllvar(const std::string& wire,
                                        std::size_t& offset,
                                        std::size_t maximum) {
    return parse_variable(wire, offset, 3, maximum);
}

std::string Iso8583Parser::parse_llllvar(const std::string& wire,
                                         std::size_t& offset,
                                         std::size_t maximum) {
    return parse_variable(wire, offset, 4, maximum);
}

Iso8583Parser::PresenceMap Iso8583Parser::parse_bitmaps(
    const std::string& wire, std::size_t& offset) {
    PresenceMap present{};
    std::size_t cursor = offset;
    decode_hex_bitmap(wire, cursor, present, 1);
    if (present[1]) decode_hex_bitmap(wire, cursor, present, 65);
    present[1] = false; // The first bit indicates a second bitmap, not a DE.
    offset = cursor;
    return present;
}

ParsedMessage Iso8583Parser::parse(const std::string& payload) const {
    std::size_t offset = 0;
    ParsedMessage message{};
    message.mti = parse_fixed(payload, offset, 4);
    if (!std::all_of(message.mti.begin(), message.mti.end(),
                     [](char c) { return c >= '0' && c <= '9'; })) {
        throw ParseError("nondecimal MTI");
    }
    message.present = parse_bitmaps(payload, offset);

    for (unsigned de = 2; de <= 128; ++de) {
        if (!message.present[de]) continue;
        const auto spec = fields_[de];
        switch (spec.format) {
        case FieldFormat::fixed:
            message.fields[de] = parse_fixed(payload, offset, spec.maximum);
            break;
        case FieldFormat::llvar:
            message.fields[de] = parse_llvar(payload, offset, spec.maximum);
            break;
        case FieldFormat::lllvar:
            message.fields[de] = parse_lllvar(payload, offset, spec.maximum);
            break;
        case FieldFormat::llllvar:
            message.fields[de] = parse_llllvar(payload, offset, spec.maximum);
            break;
        case FieldFormat::unused:
            throw ParseError("bitmap references unsupported Data Element");
        }
    }
    if (offset != payload.size()) throw ParseError("trailing bytes after last DE");
    return message;
}

} // namespace payment_gateway
