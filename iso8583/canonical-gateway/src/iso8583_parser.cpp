#include "iso8583_parser.hpp"

#include <algorithm>
#include <utility>

namespace payment_gateway {
namespace {

unsigned hex_value(char character) {
    if (character >= '0' && character <= '9') return static_cast<unsigned>(character - '0');
    if (character >= 'A' && character <= 'F') return static_cast<unsigned>(character - 'A') + 10U;
    if (character >= 'a' && character <= 'f') return static_cast<unsigned>(character - 'a') + 10U;
    throw ParseError("invalid bitmap hexadecimal character");
}

std::string parse_variable(const std::string& wire, std::size_t& offset,
                           std::size_t prefix_width, std::size_t maximum) {
    // Do not update the caller cursor unless the entire field was read.
    std::size_t cursor = offset;
    const auto prefix = Iso8583Parser::parse_fixed(wire, cursor, prefix_width);
    std::size_t length = 0;
    for (char digit : prefix) {
        if (digit < '0' || digit > '9') throw ParseError("invalid decimal length prefix");
        length = length * 10U + static_cast<std::size_t>(digit - '0');
    }
    if (length > maximum) throw ParseError("field exceeds maximum length");
    auto result = Iso8583Parser::parse_fixed(wire, cursor, length);
    offset = cursor;
    return result;
}

void decode_bitmap(const std::string& wire, std::size_t& cursor,
                   Iso8583Parser::PresenceMap& present, unsigned start_de) {
    auto encoded = Iso8583Parser::parse_fixed(wire, cursor, 16);
    for (std::size_t nibble = 0; nibble < encoded.size(); ++nibble) {
        const unsigned bits = hex_value(encoded[nibble]);
        for (unsigned bit = 0; bit < 4; ++bit) {
            present[start_de + static_cast<unsigned>(nibble) * 4U + bit] =
                (bits & (8U >> bit)) != 0U;
        }
    }
}

} // namespace

Iso8583Parser::Iso8583Parser(FieldTable fields)
    : fields_(std::move(fields)) {}

Iso8583Parser::FieldTable Iso8583Parser::nibss_fields() {
    FieldTable table{};
    // NIBSS POS Interface v1.16, union of message layouts in section 3.
    // The course simulator also uses DE70 for network management.
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
    table[70] = {FieldFormat::fixed, 3};
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
    decode_bitmap(wire, cursor, present, 1);
    if (present[1]) decode_bitmap(wire, cursor, present, 65);
    present[1] = false; // DE1 is the secondary-bitmap indicator.
    offset = cursor;
    return present;
}

ParsedMessage Iso8583Parser::parse(const std::string& payload) const {
    std::size_t offset = 0;
    ParsedMessage message{};
    message.mti = parse_fixed(payload, offset, 4);
    if (!std::all_of(message.mti.begin(), message.mti.end(),
                     [](char ch) { return ch >= '0' && ch <= '9'; })) {
        throw ParseError("nondecimal MTI");
    }
    message.present = parse_bitmaps(payload, offset);

    for (unsigned de = 2; de <= 128; ++de) {
        if (!message.present[de]) continue;
        const auto& spec = fields_[de];
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


namespace {
bool day05_digits(const std::string& s) {
    return std::all_of(s.begin(),s.end(),[](unsigned char c){return c>='0' && c<='9';});
}
std::string day05_bitmap(const Iso8583Parser::PresenceMap& present,unsigned first) {
    static const char hex[]="0123456789ABCDEF";
    std::string s;
    for(unsigned n=0;n<16;++n) {
        unsigned bits=0;
        for(unsigned b=0;b<4;++b)if(present[first+n*4+b])bits|=(8U>>b);
        s+=hex[bits];
    }
    return s;
}
void day05_length(std::string& output,std::size_t length,unsigned width) {
    const std::string decimal=std::to_string(length);
    output.append(width-decimal.size(),'0');
    output+=decimal;
}
}
std::string Iso8583Parser::compose(const ParsedMessage& msg) const {
    if(msg.mti.size()!=4 || !day05_digits(msg.mti))throw ComposeError("invalid MTI");
    if(msg.present[0] || msg.present[1])throw ComposeError("reserved data element");
    auto bitmap=msg.present;
    bool secondary=false;
    for(unsigned de=2;de<=128;++de) {
        if(!msg.present[de])continue;
        const auto spec=fields_[de];
        const std::size_t n=msg.fields[de].size();
        if(spec.format==FieldFormat::unused)throw ComposeError("unsupported data element");
        if(spec.format==FieldFormat::fixed && n!=spec.maximum)throw ComposeError("fixed length mismatch");
        if(spec.format!=FieldFormat::fixed && n>spec.maximum)throw ComposeError("variable length too long");
        if(spec.format==FieldFormat::llvar && n>99)throw ComposeError("LLVAR prefix overflow");
        if(spec.format==FieldFormat::lllvar && n>999)throw ComposeError("LLLVAR prefix overflow");
        if(spec.format==FieldFormat::llllvar && n>9999)throw ComposeError("LLLLVAR prefix overflow");
        if(de>64)secondary=true;
    }
    bitmap[1]=secondary;
    std::string output=msg.mti+day05_bitmap(bitmap,1);
    if(secondary)output+=day05_bitmap(bitmap,65);
    for(unsigned de=2;de<=128;++de) {
        if(!msg.present[de])continue;
        auto format=fields_[de].format;
        if(format==FieldFormat::llvar)day05_length(output,msg.fields[de].size(),2);
        else if(format==FieldFormat::lllvar)day05_length(output,msg.fields[de].size(),3);
        else if(format==FieldFormat::llllvar)day05_length(output,msg.fields[de].size(),4);
        output+=msg.fields[de];
    }
    return output;
}
} // namespace payment_gateway
