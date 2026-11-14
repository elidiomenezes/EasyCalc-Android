# Troubleshooting

Start with the boring-but-effective test:

```bash
./run_tests.sh
```

It checks the rule engine, launches a real TCP server, and runs every included
scenario. If it passes, the project is healthy and the remaining problem is
probably your command, port, spec, or new JSON.

To run all scenarios under all nine wire specifications, use:

```bash
./run_all_specs.sh
```

## `No module named iso8583`

Install dependencies with the same Python interpreter that will run the lab.

Windows Git Bash:

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The shell scripts detect either virtual-environment layout automatically.

## `Permission denied` for a shell script

```bash
chmod +x run_tests.sh demo.sh
```

Then run `./run_tests.sh` or `./demo.sh`. On Windows, use Git Bash or another
Bash-compatible shell.

## `Connection refused`

Nothing is listening at the client's host and port. Start the server first and
make both commands use the same values:

```bash
python3 server.py --host 127.0.0.1 --port 8583
python3 client.py --host 127.0.0.1 --port 8583 --rules client-rules/financial.json
```

## `Address already in use`

Another process owns that port. Stop it or select another port on both sides:

```bash
python3 server.py --port 19000
python3 client.py --port 19000 --rules client-rules/financial.json
```

For scripts, use `PORT=19000 ./demo.sh`.

## The client times out

A timeout means the client expected another leg. Check:

- Did the server select `default: null`?
- Is the client action incorrectly using `expect_response: true`?
- Did you start the server with `--drop-response`?
- Are both ends on the same host, port, and spec?

For a terminal message with no reply, use both `expect_response: false` on the
client and a null response on the server.

## Decode or encode errors

The most common causes are:

- Client and server use different specs.
- A fixed-length field has the wrong length.
- A numeric field contains non-numeric data.
- A message manually contains `p` or `1`.
- A variable field exceeds its configured maximum.

Use `--dry-run --log-view both` to inspect the first outbound message without a
connection:

```bash
python3 client.py --rules client-rules/authorization-approved.json --dry-run
```

## Date rules reject a message that looks valid

`$date...` checks whether the value is possible. `$date..._now` also compares
it with the **server's local clock**. Confirm the server clock and timezone,
then adjust `date_now_tolerance` in that MTI's rule file if appropriate.

The tolerance is seconds. For example, `300` means five minutes.

## `register $name is undefined`

The register was used but never created. Verify that:

- Its capture name and use have identical spelling and case.
- The source field exists.
- The capture regex actually matches.
- In a multi-leg client flow, capture happens before the later message uses it.
- You did not expect a server register to survive into the next request.

## My rule never runs

Rules are evaluated from top to bottom and the first complete match wins.
Temporarily make the earlier rules more specific or move your rule upward.
Remember that every condition inside one `match` is required.

## JSON fails to load

JSON requires double quotes, forbids trailing commas, and treats backslash as
an escape character. A regex backslash often needs to be doubled in JSON—for
example, `"^\\d{6}$"` represents the regex `^\d{6}$`.

Run Python's formatter for a quick syntax check:

```bash
python3 -m json.tool path/to/file.json
```

## Raw output contains `\xHH`

That is intentional. Printable ASCII is displayed normally; binary and control
bytes are shown as hexadecimal escapes. With a binary bitmap, the beginning of
the raw message will naturally contain several escapes.

Use `--log-view parsed` if you only want fields, or `--log-view both` to compare
the readable fields with their wire representation.

## Colors look strange in a file or terminal

`--color auto` colors only an interactive terminal. Use `--color never` to
disable it or `--color always` when combining live client and server output.
Files written by `--log-file` never contain color codes.

## A practical five-step diagnosis

1. Run `python3 -m unittest -v`.
2. Encode the first client message with `--dry-run`.
3. Start the server with `--log-view both`.
4. Start the client with the same spec, host, and port.
5. Read the logged rule name before changing any JSON.

Exit code `0` means success, `2` means socket timeout, and `3` means connection
failure. Configuration or encoding errors normally exit with code `1` and a
Python traceback that identifies the bad file or field.
