#include "iso8583_parser.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <string_view>
#include <utility>

namespace payment_gateway {
namespace {

bool decimal(std::string_view s) {
    return std::all_of(s.begin(), s.end(), [](unsigned char c) {
        return c >= '0' && c <= '9';
    });
}

std::string take(const std::string& wire, std::size_t& offset,
                 std::size_t length) {
    if (offset > wire.size() || length > wire.size() - offset)
        throw ParseError("truncated ISO 8583 field");
    auto result = wire.substr(offset, length);
    offset += length;
    return result;
}

std::string variable(const std::string& wire, std::size_t& offset,
                     std::size_t maximum, std::size_t digits) {
    const auto prefix = take(wire, offset, digits);
    if (!decimal(prefix)) throw ParseError("non-decimal field length");
    std::size_t length = 0;
    for (char c : prefix) length = length * 10 + static_cast<std::size_t>(c - '0');
    if (length > maximum) throw ParseError("field exceeds configured maximum");
    return take(wire, offset, length);
}

unsigned nibble(char ch) {
    if (ch >= '0' && ch <= '9') return static_cast<unsigned>(ch - '0');
    if (ch >= 'A' && ch <= 'F') return static_cast<unsigned>(ch - 'A' + 10);
    if (ch >= 'a' && ch <= 'f') return static_cast<unsigned>(ch - 'a' + 10);
    throw ParseError("invalid ASCII-hex bitmap");
}

void read_bitmap(const std::string& wire, std::size_t& offset,
                 Iso8583Parser::PresenceMap& presence, unsigned first) {
    auto hex = take(wire, offset, 16);
    for (unsigned i = 0; i < 16; ++i) {
        unsigned bits = nibble(hex[i]);
        for (unsigned b = 0; b < 4; ++b)
            presence[first + i * 4 + b] = (bits & (8u >> b)) != 0;
    }
}

std::string write_bitmap(const Iso8583Parser::PresenceMap& presence,
                         unsigned first) {
    constexpr char hex[] = "0123456789ABCDEF";
    std::string result;
    result.reserve(16);
    for (unsigned i = 0; i < 16; ++i) {
        unsigned bits = 0;
        for (unsigned b = 0; b < 4; ++b)
            if (presence[first + i * 4 + b]) bits |= 8u >> b;
        result.push_back(hex[bits]);
    }
    return result;
}

void append_length(std::string& output, std::size_t length, unsigned width) {
    const auto value = std::to_string(length);
    output.append(width - value.size(), '0');
    output += value;
}

} // namespace

Iso8583Parser::Iso8583Parser(FieldTable fields) : fields_(std::move(fields)) {}

Iso8583Parser::FieldTable Iso8583Parser::nibss_fields() {
    // ASCII-hex bitmap and ASCII field representation, NIBSS POS v1.16,
    // section 4. This table covers fields expressible by the Day 3
    // FIXED/LLVAR/LLLVAR model. In particular, DE63 and DE124 require
    // LLLLVAR and are deliberately unsupported by this limited codec.
    FieldTable table{};
    const auto fixed = [&](unsigned de, std::size_t n) {
        table[de] = {FieldFormat::fixed, n};
    };
    const auto llvar = [&](unsigned de, std::size_t n) {
        table[de] = {FieldFormat::llvar, n};
    };
    const auto lllvar = [&](unsigned de, std::size_t n) {
        table[de] = {FieldFormat::lllvar, n};
    };
    llvar(2, 19); fixed(3, 6); fixed(4, 12); fixed(5, 12);
    fixed(7, 10); fixed(9, 8); fixed(11, 6); fixed(12, 6);
    fixed(13, 4); fixed(14, 4); fixed(15, 4); fixed(16, 4);
    fixed(18, 4); fixed(22, 3); fixed(23, 3); fixed(25, 2);
    fixed(26, 2); fixed(28, 9); fixed(29, 9); fixed(30, 9);
    fixed(31, 9); llvar(32, 11); llvar(33, 11); llvar(35, 37);
    fixed(37, 12); fixed(38, 6); fixed(39, 2); fixed(40, 3);
    fixed(41, 8); fixed(42, 15); fixed(43, 40);
    llvar(44, 25); llvar(45, 76);
    fixed(49, 3); fixed(50, 3); fixed(52, 16); fixed(53, 96);
    lllvar(54, 120); lllvar(55, 510); lllvar(56, 4);
    lllvar(58, 11); lllvar(59, 255); lllvar(60, 999);
    lllvar(62, 999); fixed(64, 64); fixed(67, 2);
    fixed(90, 42); fixed(95, 42); fixed(98, 25);
    llvar(100, 11); llvar(102, 28); llvar(103, 28);
    lllvar(123, 15); fixed(128, 64);
    // DE48 has contradictory LLVAR/max-999 text in the source PDF;
    // it is not silently assigned an incompatible length encoding.
    return table;
}

std::string Iso8583Parser::parse_fixed(const std::string& wire,
                                        std::size_t& offset, std::size_t length) {
    return take(wire, offset, length);
}

std::string Iso8583Parser::parse_llvar(const std::string& wire,
                                        std::size_t& offset, std::size_t maximum) {
    return variable(wire, offset, maximum, 2);
}

std::string Iso8583Parser::parse_lllvar(const std::string& wire,
                                         std::size_t& offset, std::size_t maximum) {
    return variable(wire, offset, maximum, 3);
}

Iso8583Parser::PresenceMap Iso8583Parser::parse_bitmaps(
    const std::string& wire, std::size_t& offset) {
    PresenceMap presence{};
    read_bitmap(wire, offset, presence, 1);
    if (presence[1]) read_bitmap(wire, offset, presence, 65);
    presence[1] = false; // indicator only, never a data element
    return presence;
}

ParsedMessage Iso8583Parser::parse(const std::string& payload) const {
    std::size_t offset = 0;
    ParsedMessage message;
    message.mti = take(payload, offset, 4);
    if (!decimal(message.mti)) throw ParseError("invalid MTI");
    message.present = parse_bitmaps(payload, offset);
    for (unsigned de = 2; de <= 128; ++de) {
        if (!message.present[de]) continue;
        const FieldSpec spec = fields_[de];
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
        case FieldFormat::unused:
            throw ParseError("unsupported data element");
        }
    }
    if (offset != payload.size()) throw ParseError("trailing bytes in ISO payload");
    return message;
}

std::string Iso8583Parser::compose(const ParsedMessage& message) const {
    if (message.mti.size() != 4 || !decimal(message.mti))
        throw ComposeError("invalid MTI");
    if (message.present[0] || message.present[1])
        throw ComposeError("DE0/DE1 are reserved");

    auto bitmap = message.present;
    bool secondary = false;
    std::size_t payload_size = 4 + 16;

    // Validate the entire message before constructing any output.
    for (unsigned de = 2; de <= 128; ++de) {
        if (!message.present[de]) continue;
        auto spec = fields_[de];
        if (spec.format == FieldFormat::unused)
            throw ComposeError("unsupported data element");
        auto length = message.fields[de].size();
        if (spec.format == FieldFormat::fixed && length != spec.maximum)
            throw ComposeError("incorrect fixed field length");
        if (spec.format != FieldFormat::fixed && length > spec.maximum)
            throw ComposeError("field exceeds configured maximum");
        if (spec.format == FieldFormat::llvar && length > 99)
            throw ComposeError("LLVAR length not representable");
        if (spec.format == FieldFormat::lllvar && length > 999)
            throw ComposeError("LLLVAR length not representable");
        if (de >= 65) secondary = true;
        payload_size += length + (spec.format == FieldFormat::fixed ? 0 :
                                  spec.format == FieldFormat::llvar ? 2 : 3);
    }
    if (secondary) payload_size += 16;
    bitmap[1] = secondary;
    std::string output;
    output.reserve(payload_size);
    output += message.mti;
    output += write_bitmap(bitmap, 1);
    if (secondary) output += write_bitmap(bitmap, 65);
    for (unsigned de = 2; de <= 128; ++de) {
        if (!message.present[de]) continue;
        auto spec = fields_[de];
        if (spec.format == FieldFormat::llvar)
            append_length(output, message.fields[de].size(), 2);
        else if (spec.format == FieldFormat::lllvar)
            append_length(output, message.fields[de].size(), 3);
        output += message.fields[de];
    }
    return output;
}

} // namespace payment_gateway
