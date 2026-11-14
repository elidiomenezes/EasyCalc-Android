# ISO 8583 Client Server Lab

Small command-line laboratory with separate ISO 8583 client and server scripts.

Use only synthetic card data. The program prints complete messages for teaching
purposes and is not designed to handle production cardholder data.

Think of it as a tiny payment-network playground: JSON files define what a
message looks like, rules decide what happens next, and two Python programs
exchange the result over a real TCP connection.

## Documentation map

- Start here and run your first transaction: this README.
- Understand every JSON file and option: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).
- Model one-, two-, and three-leg conversations: [`docs/FLOWS.md`](docs/FLOWS.md).
- Understand the fields used by the examples: [`docs/FIELD_GUIDE.md`](docs/FIELD_GUIDE.md).
- Fix common setup and runtime problems: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).
- Run the client, server, demos, and tests in containers: [`docs/CONTAINERS.md`](docs/CONTAINERS.md).
- Build the native Windows GUI and installer: [`docs/WINDOWS.md`](docs/WINDOWS.md).

If you only have five minutes, follow **Setup**, run `./demo.sh`, and read the
screen. The script explains each scenario before launching it.

To demonstrate only the five classroom MTI pairs, run:

```bash
./demo_mti_pairs.sh
```

## Setup

You need Python 3.10 or newer. From the project directory, create a virtual
environment and install the single runtime dependency.

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

On Linux or macOS, use `python3 -m venv .venv` and
`.venv/bin/python -m pip install -r requirements.txt`.

Confirm that everything is healthy:

```bash
./run_tests.sh
```

Prefer Docker? Build and verify the single interactive laboratory container with:

```bash
./container_smoke_test.sh
```

Build the image and export a transportable `iso8583-lab-image.tar` with:

```bash
./build_container_image.sh
```

## Run client and server separately

Terminal 1:

```bash
python3 server.py --host 127.0.0.1 --port 8583 --rules rules/rules.json
```

Terminal 2:

```bash
python3 client.py --host 127.0.0.1 --port 8583 --rules client-rules/authorization-approved.json
```

Both processes must use compatible specification files:

```bash
python3 server.py --spec specs/nibss-v1.16.json
python3 client.py --spec specs/nibss-v1.16.json --rules client-rules/authorization-approved.json
```

The command above uses the NIBSS wire format with the permissive teaching
rules. To validate NIBSS mandatory data elements before applying the business
rules, start the server with the strict NIBSS rule profile and use the complete
sample message:

```bash
python3 server.py --spec specs/nibss-v1.16.json --rules rules/nibss-rules.json
python3 client.py --spec specs/nibss-v1.16.json --rules client-rules/nibss-authorization.json
```

Or let the launch scripts select the NIBSS spec, strict NIBSS rules, and its
two-byte binary TCP envelope:

```bash
./run_nibss_server.sh
./run_nibss_client.sh
```

The two rule profiles are intentionally separate:

- `rules/rules.json` is the broad teaching profile. It retains generic examples
  such as `0400/0410`, `0600/0610`, and the terminal `0120` three-leg demo.
- `rules/nibss-rules.json` is the NIBSS profile. It checks mandatory DE presence
  before date, Luhn, and business rules; returns response code `30` for a
  structurally incomplete message; maps `0120` to `0130`; and does not claim
  that the generic `0400` or `0600` examples are NIBSS messages.

The included DE128 value is deliberately a dummy teaching value. The lab
checks its presence and encoding, but does not implement NIBSS key management
or cryptographic hash generation.

The included `specs/binary-bitmap.json` uses a binary primary/secondary bitmap
while keeping the MTI and data elements in ASCII:

```bash
python3 server.py --spec specs/binary-bitmap.json
python3 client.py --spec specs/binary-bitmap.json --rules client-rules/authorization-approved.json
```

Try the included authorization scenarios:

```bash
python3 client.py --rules client-rules/authorization-approved.json
python3 client.py --rules client-rules/authorization-invalid-luhn.json
python3 client.py --rules client-rules/authorization-declined.json
```

Inspect a message without opening a connection:

```bash
python3 client.py --rules client-rules/authorization-approved.json --dry-run
```

## Client flows and request messages

The client receives a flow definition through `--rules`. Its `start` action
selects the first message and declares whether a response is expected. The
`responses` map selects client-side rules using the MTI received from the
server:

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

Message files still contain the complete parsed ISO 8583 message. Every field
number and value must be a JSON string. Do not include `p` or `1`; the encoder
creates the bitmaps according to the selected spec.

Included examples:

- `messages/authorization-approved.json`
- `messages/authorization-invalid-luhn.json`
- `messages/authorization-invalid-date.json`
- `messages/authorization-declined.json`
- `messages/financial.json`
- `messages/financial-advice.json`
- `messages/reversal-request.json`
- `messages/reversal.json`
- `messages/administrative-request.json`
- `messages/network-sign-on.json`
- `messages/network-no-response.json`

The message contains field values; the spec independently defines how those
values are encoded on the wire.

Client rules may capture fields from a received response and select another
message through `next`. Registers live for the complete connection and can be
expanded in later message files. `next: null` ends a two-leg flow. An action
with `"expect_response": false` sends a terminal leg and ends the flow.

The included three-leg example runs `0100 → 0110 → 0120`:

```bash
python3 client.py --rules client-rules/three-leg-authorization.json
```

The client captures STAN and RRN from `0110`, inserts them into `0120`, and
sends that final confirmation without waiting for a fourth leg.

Message values may request the client's current local date and time. Python
interprets these expressions directly; they are never passed to a shell:

```json
{
  "7": "$(date %m%d%H%M%S)",
  "12": "$(date %H%M%S)",
  "13": "$(date %m%d)"
}
```

## Logging

Client and server support the same logging controls:

```bash
# Raw messages only, with non-printable bytes escaped as \xHH
python3 server.py --log-view raw

# Parsed fields only
python3 server.py --log-view parsed

# Raw payload followed by parsed JSON
python3 client.py --rules client-rules/authorization-approved.json --log-view both

# Parsed JSON appended to a file
python3 client.py --rules client-rules/authorization-approved.json --log-view parsed --log-file logs/client.log

# Disable message logs
python3 server.py --log-view none
```

Terminal logs identify each process by color: server output is cyan, client
output is green, and errors are red. `--color auto` is the default; use
`--color always` for redirected or combined terminal output and `--color never`
to disable colors. Text written through `--log-file` never contains ANSI color
codes.

Raw messages use a mixed escaped representation: printable ASCII bytes appear
as normal characters, backslash appears as `\\`, and non-printable bytes appear
as uppercase `\xHH` escapes. This keeps fields readable without losing binary
bitmap or control bytes. Parsed messages are logged as indented JSON. The
specification file controls the actual encoding on the wire.

## Specifications

The `--spec` option accepts a pyiso8583 specification stored as JSON. Entries
define data encoding, length encoding, fixed/variable length behavior, maximum
length, and description for each field.

Nine editable specifications are included:

- `specs/nibss-v1.16.json`: course reference profile: binary TCP length prefix, ASCII MTI, ASCII-hex bitmaps, and NIBSS field lengths.
- `specs/ascii.json`: MTI, bitmap, lengths, and fields represented as ASCII.
- `specs/binary-bitmap.json`: binary bitmap with ASCII MTI, lengths, and fields.
- `specs/ascii-bitmap-bcd-length.json`: ASCII bitmap and data with BCD variable-length prefixes.
- `specs/binary-bitmap-bcd-length.json`: binary bitmap, ASCII data, and BCD length prefixes.
- `specs/ascii-bitmap-binary-length.json`: ASCII bitmap and data with unsigned binary length prefixes.
- `specs/ebcdic.json`: EBCDIC cp500 MTI, bitmap, lengths, and textual fields.
- `specs/ebcdic-binary-bitmap.json`: EBCDIC text with binary primary and secondary bitmaps.
- `specs/packed-bcd-numeric.json`: packed MTI and common numeric fields, binary bitmaps, and ASCII text.

Regenerate all files from the base specifications bundled with the installed
pyiso8583 version and the transformations defined by this lab:

```bash
python3 generate_specs.py
```

Run every unit and TCP scenario against every included spec:

```bash
chmod +x run_all_specs.sh
./run_all_specs.sh
```

This design intentionally makes the dialect external to the program. Using
incompatible specs on client and server demonstrates why saying only "ISO
8583" is not sufficient for interoperability.

## Response rules

`rules/rules.json` maps each request MTI to its own rule file:

```json
{
  "0100": "0100.json",
  "0200": "0200.json",
  "0220": "0220.json",
  "0420": "0420.json",
  "0600": "0600.json",
  "0800": "0800.json"
}
```

The MTI file first captures transaction-local registers and then evaluates its
ordered rules. Match keys beginning with `$` read a register; other keys read
ISO 8583 fields. All conditions in one rule are AND conditions.

```json
{
  "date_now_tolerance": 300,
  "captures": {
    "$pan4": { "field": "2", "regex": "([0-9]{4})$" },
    "$stan": { "field": "11", "regex": "^([0-9]{6})$" },
    "$luhn": { "field": "2", "regex": "^[0-9]{13,19}$" },
    "$date7": { "field": "7", "format": "%m%d%H%M%S" },
    "$date12": { "field": "12", "format": "%H%M%S" },
    "$date13": { "field": "13", "format": "%m%d" }
  },
  "rules": [
    {
      "name": "decline invalid PAN checksum",
      "match": { "$luhn": "^0$" },
      "response": "responses/invalid-pan.json"
    }
  ],
  "default": "responses/system-error.json"
}
```

Normal captures store the first regex group, or the complete match when there
is no group. The special `$luhn` capture applies the Luhn algorithm to its
captured value and stores `"1"` for valid or `"0"` for invalid. A missing field
or failed capture leaves the register undefined, so a rule using it does not
match.

Registers whose names begin with `$date` are special date registers. Their
`format` uses Python/Unix `date` directives. The base register returns `"1"`
for a valid value or `"0"` for an impossible date or time. The engine also
creates a derived `_now` register automatically: `$date7_now`, `$date12_now`,
and `$date13_now` compare the captured values with the server's local clock.
They use the rule file's global `date_now_tolerance` in seconds. Date-only
fields accept the adjacent day only inside that window around midnight.

The first matching rule selects a response template. If none matches, `default`
is used. Set `"default": null` when that MTI must receive no response.

Response templates contain only fields that may be emitted. Their values use a
small sed-like language:

```json
{
  "t": "/^0100$/0110/",
  "44": "//PAN4=$pan4,STAN=$stan/",
  "11": "//",
  "12": "//",
  "13": "//",
  "39": "//00/"
}
```

- `//` echoes an incoming field.
- `/match/replace/` transforms an existing field.
- For a new field, `/match/replace/` ignores match and writes replacement.
- `$name` in a replacement expands a register; `$1`, `$2`, and so on expand
  substitution capture groups; `$$` writes a literal dollar sign.
- Semicolon separates operations. Use `\;` inside an expression for a literal
  semicolon and `\/` for a literal slash.
- Fields `p` and `1` are forbidden because the encoder generates bitmaps.

The rule file performs validation and capture first. The selected response file
then renders fields using the sed-like expressions and the saved registers.

Simulate a lost response:

```bash
python3 server.py --drop-response
python3 client.py --rules client-rules/authorization-approved.json --timeout 2
```

Run the automated tests:

```bash
python3 -m unittest -v
```

Run the complete test environment from Git Bash, Linux, or macOS:

```bash
chmod +x run_tests.sh
./run_tests.sh
```

The script detects `.venv/Scripts/python.exe` on Windows and `.venv/bin/python`
on Linux/macOS, then falls back to `python3`. Before every case it explains the objective, input message, and
expected result. It then runs the unit tests, starts the real TCP server, sends
all nine example flows, displays color-coded client and server logs, accepts
the intentional no-response scenario, and stops the server on exit. Override
settings when needed:

```bash
PORT=19000 SPEC=specs/binary-bitmap.json ./run_tests.sh
```

Run the interactive classroom demonstration:

```bash
chmod +x demo.sh
./demo.sh
```

`demo.sh` starts one server, explains each scenario, runs it, and waits for
Enter before launching the next one. It stops the server automatically on exit
or `Ctrl+C`. For a non-interactive smoke test, disable pauses with:

```bash
DEMO_AUTO=1 ./demo.sh
```

## Remove Windows Zone.Identifier metadata

After extracting or copying the project, purge `Zone.Identifier` recursively
from the project directory and every subdirectory:

```bash
chmod +x purge_zone_identifiers.sh
./purge_zone_identifiers.sh
```

Pass another directory when needed:

```bash
./purge_zone_identifiers.sh /path/to/directory
```

The script removes literal `*:Zone.Identifier` sidecar files. Under Windows
Git Bash, it also uses PowerShell `Unblock-File` recursively to remove real
NTFS alternate data streams. It refuses to operate on `/`.

## Laboratory profile

- TCP framing is a transport adapter, not parser behavior. `binary-2` uses a
  two-byte unsigned big-endian length and `ascii-4` uses four ASCII digits.
- Message encoding: selected by the JSON file passed through `--spec`.
- Supported requests include `0100`, `0120`, `0200`, `0220`, `0400`, `0420`,
  `0600`, and `0800`.
- Working classroom pairs are `0100 → 0110`, `0220 → 0230`, `0420 → 0430`,
  `0600 → 0610`, and `0800 → 0810`.
- `rules/rules.json` selects a per-MTI rule file; that file captures registers,
  selects a response template, and may choose no response.
- The included example declines an invalid Luhn checksum with `14`, declines
  authorization PANs ending in `0000` with `05`, and approves other supported
  transaction flows with `00`.
- The reversal request (`0400 → 0410`) and reversal advice (`0420 → 0430`) use
  separate response templates so their roles remain obvious in class.
- Both reversal scenarios carry DE90, forcing primary (`p`) and secondary (`1`)
  bitmaps in the request and response.
- Network sign-on carries DE70, so `0800 → 0810` also demonstrates primary and
  secondary bitmaps.

These rules belong to this educational profile. They are not universal ISO
8583 rules and do not represent FIS, Visa, Mastercard, or another processor.
