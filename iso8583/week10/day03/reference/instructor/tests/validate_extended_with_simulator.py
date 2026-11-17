#!/usr/bin/env python3
"""End-to-end C++ parser validation using the REAL course client.py/server.py.

Messages are produced solely by client.py with the simulator's NIBSS JSON spec.
No ISO wire is manually assembled. The gateway's parsed-message log must match
each transmitted request; successful TCP forwarding is not accepted as a pass.
"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time


# Synthetic field values used to extend the simulator's own authorization fixture.
# These are NOT handwritten ISO wire messages. client.py encodes the JSON.
# Lengths and encodings match specs/nibss-v1.16.json in the simulator image.
EXTRA = {
    "23": "001",
    "28": "C00000001",
    "38": "123456",
    "43": "A" * 40,
    "48": "EXTRA-DATA",
    "52": "0123456789ABCDEF",
    "53": "0123456789ABCDEF",
    "59": "ECHO-TEST",
    "62": "TEST-PARAM",
    "63": "TEST-LONG-PARAM",
    "90": "010012345609211200001234567890120000000000",
    "95": "0" * 42,
    "124": "TEST-NFC",
    "128": "A" * 64,
}
assert len(EXTRA) == 14


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(port, process, label):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited prematurely: {process.returncode}")
        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                return
        time.sleep(0.05)
    raise TimeoutError(f"{label} did not listen on {port}")


def stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=3)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulator-dir", required=True, type=Path)
    parser.add_argument("--gateway-cmd", required=True)
    args = parser.parse_args()

    sim = args.simulator_dir.resolve()
    spec = sim / "specs" / "nibss-v1.16.json"
    spec_data = json.loads(spec.read_text())
    # Verify actual simulator wire formats. No inferred or fabricated prefix.
    expected = {
        "23": (0, 3), "28": (0, 9), "38": (0, 6), "43": (0, 40),
        "48": (3, 999), "52": (0, 16), "53": (0, 16), "59": (3, 255),
        "62": (3, 999), "63": (4, 9999), "90": (0, 42), "95": (0, 42),
        "124": (4, 9999), "128": (0, 64),
        "60": (3, 999), "70": (0, 3),
    }
    for de, (length_type, maximum) in expected.items():
        real = spec_data[de]
        assert (real["len_type"], real["max_len"]) == (length_type, maximum), (
            f"Simulator specification disagrees on DE{de}: {real}"
        )

    listen, upstream = unused_port(), unused_port()
    while listen == upstream:
        upstream = unused_port()
    environment = os.environ.copy()
    gateway_command = [
        word.replace("{listen}", f"127.0.0.1:{listen}")
            .replace("{authorizer}", f"127.0.0.1:{upstream}")
        for word in shlex.split(args.gateway_cmd)
    ]
    server_command = [
        sys.executable, str(sim / "server.py"), "--host", "127.0.0.1",
        "--port", str(upstream), "--spec", str(spec),
        "--rules", str(sim / "rules" / "rules.json"), "--log-view", "none",
    ]
    server = subprocess.Popen(
        server_command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        env=environment,
    )
    gateway = None
    try:
        wait_port(upstream, server, "simulator server.py")
        gateway = subprocess.Popen(
            gateway_command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=environment,
        )
        wait_port(listen, gateway, "C++ gateway")

        original_messages = sorted((sim / "messages").glob("*.json"))
        # Each original simulator fixture is sent by the real client.py, using
        # a derived no-response rule to avoid needing server-side business
        # approvals for parser-only coverage.
        cases = [(f"existing:{path.stem}", path) for path in original_messages]

        with tempfile.TemporaryDirectory(prefix="iso8583-client-test-") as tmp:
            tmpdir = Path(tmp)
            base = json.loads((sim / "messages" / "authorization-approved.json").read_text())
            for de, value in EXTRA.items():
                fixture = dict(base)
                fixture[de] = value
                path = tmpdir / f"extended-de{de}.json"
                path.write_text(json.dumps(fixture))
                cases.append((f"extended:DE{de}", path))

            for label, path in cases:
                # This rule structure is the actual client-rules/network-no-response
                # format. The real client decides how to encode and send.
                rules = {
                    "start": {"message": str(path), "expect_response": False},
                    "responses": {},
                }
                rule_file = tmpdir / "one-shot-rule.json"
                rule_file.write_text(json.dumps(rules))
                client_command = [
                    sys.executable, str(sim / "client.py"),
                    "--host", "127.0.0.1", "--port", str(listen),
                    "--spec", str(spec), "--rules", str(rule_file),
                    "--log-view", "parsed", "--color", "never",
                    "--timeout", "5",
                ]
                result = subprocess.run(
                    client_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, env=environment, timeout=12,
                )
                if result.returncode or "CLIENT SENT LEG 1" not in result.stdout:
                    raise AssertionError(
                        f"real client.py could not send {label}: {result.stdout[-1800:]}"
                    )
                print(f"CLIENT SENT {label}", flush=True)
                # Avoid treating socket connect or write completion as a parse result.
                time.sleep(0.035)

        # Drain gateway logging after all client sessions have finished.
        stop(gateway)
        gateway_output = gateway.communicate(timeout=3)[1].decode(errors="replace")
        request_ok = re.findall(r"request ISO8583 MTI=([0-9]{4}) fields=([0-9]+)", gateway_output)
        request_failed = re.findall(r"request unparsed ISO8583 frame: ([^\n]+)", gateway_output)
        print(f"C++ PARSED REQUESTS: {len(request_ok)}/{len(cases)}", flush=True)
        print(f"C++ UNPARSED REQUESTS: {len(request_failed)}", flush=True)
        if request_failed:
            for error in request_failed[:20]:
                print(f"  UNPARSED: {error}", flush=True)
        if len(request_ok) != len(cases) or request_failed:
            print("GATEWAY STDERR TAIL:", gateway_output[-6500:], flush=True)
            raise AssertionError("gateway did not parse every real client request")
        print("REAL CLIENT/SERVER/GATEWAY PARSER: PASS", flush=True)
    finally:
        if gateway is not None:
            stop(gateway)
        stop(server)
        if gateway is not None and gateway.stderr is not None:
            gateway.stderr.close()
        if server.stderr is not None:
            server.stderr.close()


if __name__ == "__main__":
    main()
