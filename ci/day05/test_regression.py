#!/usr/bin/env python3
"""Gateway full regression: prior-day functionality under Day 5's frame-aware contract.

Use only synthetic card data. Does not require access to an external simulator.
"""
import concurrent.futures
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BIN, SCHEMA = sys.argv[1:3]
DAY = datetime.now(timezone.utc).strftime("%m%d")
FORMATS = {2: ("ll", 19), 3: ("fixed", 6), 4: ("fixed", 12),
           7: ("fixed", 10), 11: ("fixed", 6), 13: ("fixed", 4),
           37: ("fixed", 12), 39: ("fixed", 2), 41: ("fixed", 8),
           42: ("fixed", 15), 49: ("fixed", 3), 55: ("lll", 510)}

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def encode(mti, fields):
    bits = 0
    for de in fields:
        assert de in FORMATS and 1 < de <= 64
        bits |= 1 << (64 - de)
    value = mti + f"{bits:016X}"
    for de, field in sorted(fields.items()):
        form, size = FORMATS[de]
        assert len(field) <= size, (de, field)
        if form == "fixed":
            assert len(field) == size, (de, field)
        else:
            value += f"{len(field):0{2 if form == 'll' else 3}d}"
        value += field
    payload = value.encode("ascii")
    return len(payload).to_bytes(2, "big") + payload

def readn(sock, n):
    b = b""
    while len(b) < n:
        part = sock.recv(n - len(b))
        if not part:
            raise EOFError("socket closed mid-frame")
        b += part
    return b

def readframe(sock):
    size = int.from_bytes(readn(sock, 2), "big")
    assert 0 < size <= 65535
    return readn(sock, size)

def full_request(stan, mti="0100", **changes):
    data = {2: "4111111111111111", 3: "000000", 4: "000000000100",
            11: f"{stan:06d}", 13: DAY, 37: f"{stan:012d}",
            42: "MERCHANT0000001", 49: "566"}
    data.update(changes)
    return encode(mti, data)

def response(request):
    req_mti = request[2:6].decode()
    replies = {"0100":"0110", "0200":"0210", "0220":"0230",
               "0420":"0430", "0800":"0810"}
    mti = replies[req_mti]
    # In this test profile DE11/DE13/DE37 are at the end only if built by
    # full_request. Rather than parse the wire, bind correlation by unique
    # values known to the controller.
    return mti

def run_gateway(db, listen, upstream, timeout=1000):
    env = dict(os.environ, ISO8583_DB_PATH=str(db),
               ISO8583_UPSTREAM_TIMEOUT_MS=str(timeout),
               ISO8583_IDLE_TIMEOUT_MS="1200")
    process = subprocess.Popen([BIN, f"127.0.0.1:{listen}", f"127.0.0.1:{upstream}"],
                               env=env, stderr=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, text=True)
    for _ in range(150):
        if process.poll() is not None:
            raise AssertionError(f"gateway exited: {process.stderr.read()}")
        try:
            with socket.create_connection(("127.0.0.1", listen), timeout=.1):
                break
        except OSError:
            time.sleep(.02)
    else:
        raise AssertionError("gateway did not listen")
    return process

class Authorizer:
    def __init__(self, response_factory, fragment=False):
        self.port = free_port()
        self.received = []
        self.errors = []
        self.stop = threading.Event()
        self.response_factory = response_factory
        self.fragment = fragment
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", self.port))
        self.listener.listen(32)
        self.listener.settimeout(.1)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        children = []
        while not self.stop.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self.handle, args=(sock,), daemon=True)
            t.start()
            children.append(t)
        for t in children:
            t.join(timeout=2)

    def handle(self, sock):
        with sock:
            sock.settimeout(2)
            while not self.stop.is_set():
                try:
                    payload = readframe(sock)
                except (EOFError, socket.timeout, OSError):
                    break
                self.received.append(payload)
                try:
                    out = self.response_factory(payload)
                    if out is None:
                        continue
                    if self.fragment:
                        # Split the header and payload across distinct sends.
                        for chunk in (out[:1], out[1:4], out[4:]):
                            sock.sendall(chunk)
                            time.sleep(.005)
                    else:
                        sock.sendall(out)
                except (OSError, AssertionError, KeyError) as e:
                    self.errors.append(str(e))
                    break

    def close(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(timeout=2)

def payload_mti(frame_payload):
    return frame_payload[:4].decode("ascii")

def report(name):
    print("PASS:", name, flush=True)

def main():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "payments.sqlite"
        with sqlite3.connect(db) as con:
            con.executescript(Path(SCHEMA).read_text())

        # Store request->response mapping by exact synthetic payload.
        expected = {}
        lock = threading.Lock()
        def authorizer_response(payload):
            with lock:
                return expected[payload]
        auth = Authorizer(authorizer_response, fragment=True)
        gateway_port = free_port()
        process = run_gateway(db, gateway_port, auth.port)
        try:
            # Persistent connection: four different MTI flows, responses split.
            # Two frames deliberately sent in one TCP sendall (coalescing).
            jobs = []
            for stan, req_mti, ans_mti in [
                (1001, "0100", "0110"), (1002, "0200", "0210"),
                (1003, "0220", "0230"), (1004, "0420", "0430"),
                (1005, "0800", "0810")]:
                if req_mti == "0800":
                    req = encode("0800", {11:f"{stan:06d}",13:DAY,37:f"{stan:012d}"})
                else:
                    req = full_request(stan,req_mti)
                reply = encode(ans_mti,{11:f"{stan:06d}",13:DAY,
                                        37:f"{stan:012d}",39:"00"})
                expected[req[2:]] = reply
                jobs.append((req,reply))
            with socket.create_connection(("127.0.0.1", gateway_port),timeout=2) as client:
                client.settimeout(3)
                client.sendall(jobs[0][0]+jobs[1][0])
                assert readframe(client) == jobs[0][1][2:]
                assert readframe(client) == jobs[1][1][2:]
                for req,ans in jobs[2:]:
                    client.sendall(req[:1]);time.sleep(.003)
                    client.sendall(req[1:])
                    assert readframe(client) == ans[2:], req[2:6]
            assert not auth.errors, auth.errors
            assert auth.received == [req[2:] for req,_ in jobs], auth.received
            report("MTI 0100/0200/0220/0420/0800, persistent session, combined and fragmented TCP")

            # Reuse the same server with 16 concurrent financial transactions.
            jobs2=[]
            for stan in range(2001,2017):
                req=full_request(stan)
                reply=encode("0110",{11:f"{stan:06d}",13:DAY,
                                       37:f"{stan:012d}",39:"00"})
                expected[req[2:]]=reply
                jobs2.append((req,reply))
            def roundtrip(pair):
                req,reply=pair
                with socket.create_connection(("127.0.0.1",gateway_port),timeout=2) as s:
                    s.settimeout(4)
                    s.sendall(req)
                    assert readframe(s)==reply[2:]
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                list(pool.map(roundtrip,jobs2))
            assert not auth.errors,auth.errors
            assert len(auth.received)==21,len(auth.received)
            report("16 concurrent clients with real upstream responses")

            with sqlite3.connect(db) as con:
                rows=con.execute("SELECT operation,status,outcome_code FROM transactions").fetchall()
            assert len(rows)==20, (len(rows),rows) # network 0800 not a transaction
            assert all(status=="APPROVED" and code=="00" for _,status,code in rows)
            assert sorted(operation for operation,_,_ in rows).count("AUTHORIZATION")==17
            assert sorted(operation for operation,_,_ in rows).count("FINANCIAL")==1
            assert sorted(operation for operation,_,_ in rows).count("ADVICE")==1
            assert sorted(operation for operation,_,_ in rows).count("REVERSAL")==1
            report("SQLite request/response lifecycle for authorization, financial, advice, reversal")
        finally:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill()
            auth.close()

if __name__=="__main__":
    main()
