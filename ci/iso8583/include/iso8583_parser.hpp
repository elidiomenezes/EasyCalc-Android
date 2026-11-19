#pragma once

#include <array>
#include <cstddef>
#include <stdexcept>
#include <string>

namespace payment_gateway {

enum class FieldFormat { unused, fixed, llvar, lllvar };

struct FieldSpec {
    FieldFormat format = FieldFormat::unused;
    std::size_t maximum = 0;
};

struct ParsedMessage {
    std::string mti;
    std::array<bool, 129> present{};
    std::array<std::string, 129> fields{};
};

class ParseError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ComposeError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Iso8583Parser {
public:
    using FieldTable = std::array<FieldSpec, 129>;
    using PresenceMap = std::array<bool, 129>;

    static FieldTable nibss_fields();
    explicit Iso8583Parser(FieldTable fields = nibss_fields());

    static std::string parse_fixed(const std::string& wire,
                                   std::size_t& offset,
                                   std::size_t length);
    static std::string parse_llvar(const std::string& wire,
                                   std::size_t& offset,
                                   std::size_t maximum);
    static std::string parse_lllvar(const std::string& wire,
                                    std::size_t& offset,
                                    std::size_t maximum);
    static PresenceMap parse_bitmaps(const std::string& wire,
                                     std::size_t& offset);
    ParsedMessage parse(const std::string& payload) const;

    // Day 5 addition: exactly one ISO payload, without the TCP length prefix.
    std::string compose(const ParsedMessage& message) const;

private:
    FieldTable fields_;
};

} // namespace payment_gateway
