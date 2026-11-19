#include "iso8583_parser.hpp"

#include <cassert>
#include <functional>
#include <iostream>
#include <string>
#include <random>

using payment_gateway::ComposeError;
using payment_gateway::Iso8583Parser;
using payment_gateway::ParseError;
using payment_gateway::ParsedMessage;

template <typename Error, typename F>
void must_throw(F operation) {
    bool did_throw = false;
    try { operation(); }
    catch (const Error&) { did_throw = true; }
    assert(did_throw);
}

void same(const ParsedMessage& a, const ParsedMessage& b) {
    assert(a.mti == b.mti);
    for (unsigned de = 2; de <= 128; ++de) {
        assert(a.present[de] == b.present[de]);
        if (a.present[de]) assert(a.fields[de] == b.fields[de]);
    }
}

int main() {
    const Iso8583Parser codec;

    // Independent oracle: exact ASCII bitmap 3020000000000000 encodes DE3,
    // DE4 and DE11. This test does not use the composer to obtain its input.
    const std::string purchase =
        "0100" "3020000000000000" "000000" "000000001000" "123456";
    const auto parsed = codec.parse(purchase);
    assert(parsed.mti == "0100" && parsed.present[3] && parsed.present[11]);
    assert(codec.compose(parsed) == purchase);

    // Exact expected bitmap after locally inserting DE39.
    auto reply = parsed;
    reply.mti = "0110";
    reply.present[39] = true;
    reply.fields[39] = "14";
    const std::string rejection =
        "0110" "3020000002000000" "000000" "000000001000" "123456" "14";
    assert(codec.compose(reply) == rejection);
    same(codec.parse(rejection), reply);

    // DE2 length prefix and secondary bitmap containing DE123.
    const std::string secondary =
        "0100" "C000000000000000" "0000000000000020"
        "16" "4111111111111111" "015" "511344101000000";
    auto decoded = codec.parse(secondary);
    assert(decoded.present[2] && decoded.present[123]);
    assert(decoded.fields[123] == "511344101000000");
    assert(codec.compose(decoded) == secondary);

    // A present empty LLVAR differs from an absent one.
    ParsedMessage empty;
    empty.mti = "0100";
    empty.present[2] = true;
    empty.fields[2] = "";
    assert(codec.compose(empty) == "0100400000000000000000");
    assert(codec.parse(codec.compose(empty)).present[2]);
    empty.present[2] = false;
    assert(codec.compose(empty) == "01000000000000000000");

    // Unused field values have no effect when present[] is false.
    empty.fields[41] = "BAD";
    assert(codec.compose(empty) == "01000000000000000000");

    // NIBSS source PDF defines no DE70; this profile rejects it.
    assert(codec.parse(secondary).present[123]);
    assert(Iso8583Parser::nibss_fields()[70].format == payment_gateway::FieldFormat::unused);
    empty.present[70] = true;
    empty.fields[70] = "001";
    must_throw<ComposeError>([&] { codec.compose(empty); });
    empty.present[70] = false;

    auto bad = reply;
    bad.mti = "01A0";
    must_throw<ComposeError>([&] { codec.compose(bad); });
    bad = reply; bad.present[1] = true;
    must_throw<ComposeError>([&] { codec.compose(bad); });
    bad = reply; bad.fields[39] = "1";
    must_throw<ComposeError>([&] { codec.compose(bad); });
    bad = reply; bad.present[2] = true; bad.fields[2] = std::string(20, '4');
    must_throw<ComposeError>([&] { codec.compose(bad); });

    must_throw<ParseError>([&] { codec.parse(purchase + "X"); });
    must_throw<ParseError>([&] { codec.parse(purchase.substr(0, purchase.size()-1)); });
    must_throw<ParseError>([&] { codec.parse("0100G000000000000000"); });
    must_throw<ParseError>([&] { codec.parse("0100C000000000000000"); });
    must_throw<ParseError>([&] { codec.parse("01004000000000000000AA"); });
    must_throw<ParseError>([&] { codec.parse("0100400000000000000020" + std::string(20, '1')); });

    // Field table injection remains usable for alternate profiles; no
    // NIBSS-specific special case is buried in compose().
    auto custom_table = Iso8583Parser::nibss_fields();
    custom_table[70] = {payment_gateway::FieldFormat::fixed, 3};
    Iso8583Parser alternate(custom_table);
    ParsedMessage custom;
    custom.mti = "0800";
    custom.present[70] = true;
    custom.fields[70] = "001";
    const auto wire = alternate.compose(custom);
    same(alternate.parse(wire), custom);

    // Independently constructed bitmap oracle for every configured DE.
    // Compare to manually calculated bit position, not to the codec parser.
    const auto specs = Iso8583Parser::nibss_fields();
    unsigned field_cases = 0;
    for (unsigned de = 2; de <= 128; ++de) {
        const auto spec = specs[de];
        if (spec.format == payment_gateway::FieldFormat::unused) continue;
        ++field_cases;
        for (std::size_t len : {std::size_t{0}, std::size_t{1}, spec.maximum}) {
            if (spec.format == payment_gateway::FieldFormat::fixed && len != spec.maximum)
                continue;
            if (spec.format != payment_gateway::FieldFormat::fixed && len > spec.maximum)
                continue;
            ParsedMessage candidate;
            candidate.mti = "0100";
            candidate.present[de] = true;
            candidate.fields[de] = std::string(len, 'X');
            const auto encoded = codec.compose(candidate);
            const auto roundtrip = codec.parse(encoded);
            same(candidate, roundtrip);
            const bool secondary_bit = de > 64;
            assert(encoded.size() >= 20 + (secondary_bit ? 16 : 0));
            // The presence bitmap is hexadecimal. Independently check the
            // hexadecimal digit containing the DE's single active bit.
            const std::size_t hex_offset = 4 + (de - 1) / 4;
            const unsigned mask = 8u >> ((de - 1) % 4);
            const char hex = "0123456789ABCDEF"[mask];
            assert(encoded[hex_offset] == hex);
            assert(encoded[4] == (secondary_bit ? '8' :
                                  (de >= 2 && de <= 4 ? hex : '0')));
        }
    }

    // Deterministic property tests over combinations of fields, including
    // binary NUL in opaque data values.
    std::mt19937 rng(0x8583);
    for (unsigned trial = 0; trial < 1000; ++trial) {
        ParsedMessage candidate;
        candidate.mti = "0100";
        for (unsigned de = 2; de <= 128; ++de) {
            const auto spec = specs[de];
            if (spec.format == payment_gateway::FieldFormat::unused || rng() % 9 != 0)
                continue;
            auto len = spec.format == payment_gateway::FieldFormat::fixed
                ? spec.maximum : rng() % (spec.maximum + 1);
            candidate.present[de] = true;
            candidate.fields[de] = std::string(len, static_cast<char>(rng() % 256));
        }
        const auto encoded = codec.compose(candidate);
        same(codec.parse(encoded), candidate);
    }

    std::cout << "Codec tests passed: " << field_cases
              << " supported DEs + 1000 randomized messages\n";
}
