#!/usr/bin/env python3
"""Week 11 Day 1 acceptance: framed ISO8583 responses and SQLite outcomes.

Test expectations are independent of the gateway implementation.
Run with: python3 tests/test_day01.py PATH_TO_GATEWAY PATH_TO_SCHEMA --scenario local
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time

DAY = datetime.now(timezone.utc).strftime("%m%d")
SPECS = {2: ("LL", 19), 4: ("F", 12), 11: ("F", 6),
         13: ("F", 4), 37: ("F", 12), 39: ("F", 2), 42: ("F", 15)}

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def wire(mti, fields):
    bitmap = sum(1 << (64-de) for de in fields)
    value = mti + f"{bitmap:016X}"
    for de, field in sorted(fields.items()):
        kind, max_size = SPECS[de]
        assert len(field) <= max_size, (de, field)
        if kind == "LL":
            value += f"{len(field):02d}"
        else:
            assert len(field) == max_size, (de, field)
        value += field
    return value.encode("ascii")

def framed(payload):
    return len(payload).to_bytes(2, "big") + payload

def read_exact(sock, n):
    result = b""
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise EOFError("connection closed while reading frame")
        result += part
    return result

def read_frame(sock):
    n = int.from_bytes(read_exact(sock, 2), "big")
    return read_exact(sock, n)

def request(stan, *, amount="000000000500", pan="4111111111111111",
            merchant="MERCHANT0000001"):
    return wire("0100", {
        2: pan, 4: amount, 11: f"{stan:06d}", 13: DAY,
        37: f"{stan:012d}", 42: merchant
    })

def response(stan, outcome):
    return wire("0110", {
        11: f"{stan:06d}", 13: DAY, 37: f"{stan:012d}", 39: outcome
    })

def query_rows(db):
    with sqlite3.connect(db, timeout=3) as con:
        return con.execute(
            "SELECT stan, status, outcome_code FROM transactions ORDER BY id"
        ).fetchall()

def ready_connect(port):
    for _ in range(150):
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=.2)
        except OSError:
            time.sleep(.02)
    raise AssertionError("gateway did not accept connections")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gateway")
    parser.add_argument("schema")
    parser.add_argument("--scenario", choices=("local", "normal"), required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "gateway.sqlite"
        with sqlite3.connect(db) as con:
            con.executescript(Path(args.schema).read_text())
        listening, upstream = free_port(), free_port()

        observed = []
        ready = threading.Event()
        def authorize():
            with socket.socket() as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("127.0.0.1", upstream))
                server.listen(4)
                server.settimeout(2)
                ready.set()
                if args.scenario == "local":
                    try:
                        conn, _ = server.accept()
                        with conn:
                            conn.settimeout(1)
                            observed.append(read_frame(conn))
                    except socket.timeout:
                        return
                    except EOFError:
                        return
                else:
                    try:
                        conn, _ = server.accept()
                        with conn:
                            conn.settimeout(3)
                            received = read_frame(conn)
                            observed.append(received)
                            conn.sendall(framed(response(4001, "00")))
                    except (socket.timeout, EOFError):
                        pass
        worker = threading.Thread(target=authorize, daemon=True)
        worker.start()
        assert ready.wait(2)
        env = dict(os.environ, ISO8583_DB_PATH=str(db),
                   ISO8583_UPSTREAM_TIMEOUT_MS="1000")
        process = subprocess.Popen(
            [args.gateway, f"127.0.0.1:{listening}",
             f"127.0.0.1:{upstream}"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        try:
            with ready_connect(listening) as client:
                client.settimeout(3)
                if args.scenario == "local":
                    cases = [
                        (5001, request(5001, amount="000001000000"), "61"),
                        (5002, request(5002, pan="4111111111111112"), "14"),
                        (5003, request(5003, merchant="MERCHANT9999999"), "03"),
                    ]
                else:
                    cases = [(4001, request(4001), "00")]
                for stan, payload, code in cases:
                    client.sendall(framed(payload))
                    actual = read_frame(client)
                    expected = response(stan, code)
                    assert actual == expected, (
                        f"STAN {stan}: incorrect ISO8583 response"
                    )
            expected_rows = [
                (f"{stan:06d}", "APPROVED" if code == "00" else "DECLINED", code)
                for stan, _, code in cases
            ]
            actual_rows = query_rows(db)
            assert actual_rows == expected_rows, (
                f"SQLite mismatch:\nexpected={expected_rows}\nactual={actual_rows}"
            )
            if args.scenario == "normal":
                worker.join(timeout=3)
                assert observed == [cases[0][1]], "upstream request changed"
            else:
                assert observed == [], "locally rejected request sent upstream"
            print(f"PASS {args.scenario}: ISO responses, routing and persistence")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()

if __name__ == "__main__":
    main()
