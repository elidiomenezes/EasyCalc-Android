# Configuration Reference

This lab keeps behavior in JSON instead of hiding it in Python. There are four
kinds of configuration:

| Kind | Job | Example |
|---|---|---|
| Specification | Describes how fields are encoded on the wire | `specs/nibss-v1.16.json` |
| Message | Contains one outbound ISO 8583 message | `messages/financial.json` |
| Server rules | Validates a request and builds a response | `rules/0100.json` |
| Client flow | Chooses the first and any later client messages | `client-rules/three-leg-authorization.json` |

The easiest mental model is: **the spec is the grammar, a message is a
sentence, and rules decide which sentence comes next.**

## 1. Specifications

Pass a pyiso8583 JSON specification to both programs with `--spec`:

```bash
python3 server.py --spec specs/nibss-v1.16.json
python3 client.py --spec specs/nibss-v1.16.json --rules client-rules/financial.json
```

Both ends must use compatible specs. “ISO 8583” alone does not define whether
the bitmap is ASCII hex or binary, how variable lengths are encoded, or what a
field means in a particular network.

Included specs:

- `nibss-v1.16.json`: the course reference dialect, using ASCII MTI and ASCII-hex bitmaps with NIBSS field definitions.
- `ascii.json`: the bitmap is 16 printable hexadecimal characters per bitmap.
- `binary-bitmap.json`: the bitmap is 8 binary bytes per bitmap.
- `ascii-bitmap-bcd-length.json`: ASCII bitmap/data and packed-BCD length prefixes.
- `binary-bitmap-bcd-length.json`: binary bitmap, ASCII data, and packed-BCD lengths.
- `ascii-bitmap-binary-length.json`: ASCII bitmap/data and unsigned binary lengths.
- `ebcdic.json`: EBCDIC cp500 text, lengths, and hexadecimal bitmap.
- `ebcdic-binary-bitmap.json`: EBCDIC cp500 text with binary bitmaps.
- `packed-bcd-numeric.json`: packed MTI/common numeric fields with ASCII text fields.

These profiles deliberately isolate different choices: bitmap representation,
length-prefix representation, character set, and packed numeric data. The TCP
length header is not part of the ISO parser specification. It is selected
separately with `--framing`; the NIBSS launch scripts select `binary-2`.

The encoder creates fields `p` and `1` automatically. Never put them in a
message or response template. A field above 64, such as DE90, automatically
causes a secondary bitmap.

Run `python3 generate_specs.py` to regenerate the included specs from the
installed pyiso8583 version.

## 2. Message files

A message is a JSON object. Every key and every value must be a string:

```json
{
  "t": "0200",
  "3": "000000",
  "4": "000000002500",
  "7": "$(date %m%d%H%M%S)",
  "11": "200001",
  "41": "TERM0001"
}
```

- `t` is the MTI and is mandatory.
- Numeric keys are data-element numbers.
- Do not add `p` or `1`.
- Values are not automatically padded. They must satisfy the selected spec.

### Current date and time

When a complete value has the form `$(date FORMAT)`, the client evaluates it
with its local clock immediately before sending:

```json
{
  "7": "$(date %m%d%H%M%S)",
  "12": "$(date %H%M%S)",
  "13": "$(date %m%d)"
}
```

This is interpreted by Python, not by a shell. The usual `strftime` directives
apply: `%m` month, `%d` day, `%H` hour, `%M` minute, `%S` second.

### Registers in later messages

A client response rule can capture a value and a later message can reuse it:

```json
{
  "11": "$stan",
  "37": "$rrn"
}
```

Use `$$` to write one literal dollar sign. Referring to an undefined register
is an error; it does not silently produce an empty value.

## 3. Server rule index

The file passed to the server with `--rules` maps an incoming MTI to one rule
file:

```json
{
  "0100": "0100.json",
  "0120": "0120.json",
  "0200": "0200.json"
}
```

Paths are relative to this index file. An absent MTI, or an MTI mapped to
`null`, receives no response.

## 4. Server rules for one MTI

A per-MTI file has three working parts:

```json
{
  "date_now_tolerance": 300,
  "captures": {},
  "rules": [],
  "default": "responses/system-error.json"
}
```

The engine performs these steps in order:

1. Read the complete incoming message.
2. Create all captures and special registers.
3. Try rules from top to bottom.
4. Select the first matching response template.
5. If no rule matches, use `default`.

All conditions inside one `match` object must match. Rule order therefore
matters. Put specific rejection rules before a broad approval rule.

### Normal captures

```json
"$pan4": { "field": "2", "regex": "([0-9]{4})$" }
```

The first regex group is stored. If there is no group, the complete match is
stored. If the field is missing or the regex fails, the register is undefined.

### The special Luhn register

Only the exact name `$luhn` activates the Luhn check:

```json
"$luhn": { "field": "2", "regex": "^[0-9]{13,19}$" }
```

The regex is applied first. The register then contains `"1"` for a valid
checksum or `"0"` for an invalid checksum. A missing field or failed regex
leaves it undefined.

### Special date registers

Any register whose name begins with `$date` is a date register:

```json
"$date7": { "field": "7", "format": "%m%d%H%M%S" }
```

It creates two values:

| Register | Meaning |
|---|---|
| `$date7` | `1` if the value is a possible date/time, otherwise `0` |
| `$date7_now` | `1` if it is also near the server's local clock, otherwise `0` |

`date_now_tolerance` is the allowed difference in seconds for the whole rule
file. The default is 300 seconds. Date-only fields allow the adjacent date near
midnight. Do not define a capture ending in `_now`; the engine creates it.

### Matching

Match a raw field by its number, or a saved register by a `$` name:

```json
"match": {
  "$luhn": "^1$",
  "$date7_now": "^1$",
  "2": "0000$"
}
```

Every value is a Python regular expression. Missing fields or registers do not
match. The first complete rule wins.

### Default behavior

`default` is either a response-template path or `null`:

```json
"default": null
```

Use `null` for a terminal MTI that intentionally has no response. This is not
the same as a timeout: it is declared behavior.

## 5. Response templates

A response template lists only the fields that will appear in the response.
Values use a tiny sed-like language:

```json
{
  "t": "/^0100$/0110/",
  "11": "//",
  "39": "//00/",
  "44": "//PAN4=$pan4,STAN=$stan/"
}
```

| Expression | Result |
|---|---|
| `//` | Copy the incoming field unchanged |
| `/old/new/` | Replace regex `old` with `new` in an existing field |
| `//new/` | Create a new field with value `new` |
| `/x/$1/` | Use a regex capture group in the replacement |
| `//$name/` | Insert a saved register |

For a field absent from the request, the match part is ignored and the
replacement creates the value. Such a new field must contain exactly one
substitution and cannot use echo.

Separate multiple operations with `;`. Write `\/` for a literal slash, `\;`
for a literal semicolon, and `$$` for a literal dollar sign. If a register or
capture group does not exist, rendering fails loudly.

Template paths are relative to the per-MTI rule file. Again, do not include
`p` or `1`.

## 6. Client flow files

The client receives a flow file through `--rules`:

```json
{
  "start": {
    "message": "../messages/authorization-approved.json",
    "expect_response": true
  },
  "responses": {
    "0110": "responses/stop.json"
  }
}
```

`start` chooses the first message. `responses` maps a received MTI to a
client-side response-rule file. A missing received MTI ends the flow.

An action may be a short string (message path, response expected) or an object:

```json
{ "message": "../messages/example.json", "expect_response": false }
```

Set `expect_response` to `false` on a terminal message. The client sends it and
exits immediately instead of waiting for a timeout.

## 7. Client response rules

These use the same capture and match syntax as server rules, but select `next`
instead of `response`:

```json
{
  "captures": {
    "$stan": { "field": "11", "regex": "^([0-9]{6})$" },
    "$rrn": { "field": "37", "regex": "^(.{12})$" }
  },
  "rules": [
    {
      "name": "approved - send confirmation",
      "match": { "39": "^00$" },
      "next": {
        "message": "../../messages/authorization-confirmation.json",
        "expect_response": false
      }
    }
  ],
  "default": null
}
```

Client registers survive for the entire TCP connection. This is what allows a
value captured from leg 2 to appear in leg 3. Server registers, by contrast,
belong only to the one incoming message currently being processed.

Paths in `next` are relative to the client response-rule file. `next: null` or
`default: null` ends the flow.

## 8. Command-line options

Both programs accept:

| Option | Default | Purpose |
|---|---:|---|
| `--host` | `127.0.0.1` | TCP address |
| `--port` | `8583` | TCP port |
| `--timeout` | `5.0` | Socket timeout in seconds |
| `--spec` | `specs/nibss-v1.16.json` | Wire specification |
| `--log-view` | `both` | `raw`, `parsed`, `both`, or `none` |
| `--log-file` | none | Append a plain-text copy of logs |
| `--color` | `auto` | `auto`, `always`, or `never` |

Client-only: `--rules` is required; `--dry-run` encodes and logs only the first
message without connecting.

Server-only: `--rules`, `--response-delay`, `--drop-response`, and `--once`.
The last three are useful for timeout and single-session demonstrations.

## 9. Path rule worth remembering

Every relative path is resolved from the JSON file that contains it—not from
the shell's current directory. This makes whole scenario folders portable.
