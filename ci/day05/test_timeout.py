#!/usr/bin/env python3
"""Upstream silence must not become success; the client wait is bounded."""
import os, socket, sqlite3, subprocess, sys, tempfile, threading, time
from datetime import datetime, timezone
from pathlib import Path
gateway,schema=sys.argv[1:3]
def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        return s.getsockname()[1]
def framed(mti,fields):
    bits=0
    for de in fields:bits|=1<<(64-de)
    data=mti+f"{bits:016X}"
    for de,v in sorted(fields.items()):
        if de==2:data+=f"{len(v):02d}"
        data+=v
    payload=data.encode()
    return len(payload).to_bytes(2,"big")+payload
auth_port=port(); listen=port()
ready=threading.Event(); seen=threading.Event()
def upstream():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        server.bind(("127.0.0.1",auth_port));server.listen(2)
        ready.set()
        server.settimeout(5)
        with server.accept()[0] as sock:
            sock.settimeout(3)
            n=int.from_bytes(sock.recv(2),"big")
            received=b""
            while len(received)<n:
                part=sock.recv(n-len(received))
                if not part:break
                received+=part
            if len(received)==n:seen.set()
            time.sleep(1.2) # longer than gateway upstream timeout
t=threading.Thread(target=upstream,daemon=True);t.start();assert ready.wait(2)
with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/"gateway.sqlite"
    with sqlite3.connect(db) as conn:conn.executescript(Path(schema).read_text())
    env=dict(os.environ,ISO8583_DB_PATH=str(db),ISO8583_UPSTREAM_TIMEOUT_MS="250")
    p=subprocess.Popen([gateway,f"127.0.0.1:{listen}",f"127.0.0.1:{auth_port}"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        client=None
        for i in range(100):
            try:client=socket.create_connection(("127.0.0.1",listen),timeout=.2);break
            except OSError:time.sleep(.02)
        assert client is not None
        with client:
            client.settimeout(2)
            req=framed("0100",{2:"4111111111111111",4:"000000000100",11:"000091",13:datetime.now(timezone.utc).strftime("%m%d"),37:"123456789091",42:"MERCHANT0000001"})
            started=time.monotonic()
            client.sendall(req)
            answer=client.recv(2)
            elapsed=time.monotonic()-started
            assert answer==b"",f"unexpected response {answer!r}"
            assert elapsed<1.1,f"upstream wait not bounded: {elapsed:.2f}s"
        assert seen.wait(1),"upstream did not receive request"
        with sqlite3.connect(db) as con:
            rows=con.execute("SELECT status,outcome_code FROM transactions").fetchall()
        assert rows==[("PENDING",None)],rows
        print("PASS: upstream silence bounded, no false response, transaction remains PENDING")
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill()
