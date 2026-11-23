#!/usr/bin/env python3
"""Additional black-box safety and concurrency checks, distinct from happy path."""
import os, socket, sqlite3, subprocess, sys, tempfile, threading, time
from datetime import datetime, timezone
from pathlib import Path

gateway, schema=sys.argv[1:3]
today=datetime.now(timezone.utc).strftime("%m%d")
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));return s.getsockname()[1]
def encode(mti, values):
    specs={2:("ll",19),4:("fixed",12),11:("fixed",6),13:("fixed",4),37:("fixed",12),39:("fixed",2),42:("fixed",15)}
    bitmap=sum(1<<(64-de) for de in values)
    text=mti+f"{bitmap:016X}"
    for de,value in sorted(values.items()):
        mode,size=specs[de]
        assert len(value)<=size
        if mode=="ll":text+=f"{len(value):02d}"
        else:assert len(value)==size
        text+=value
    result=text.encode("ascii")
    return len(result).to_bytes(2,"big")+result
def recv_all(s,n):
    out=b""
    while len(out)<n:
        data=s.recv(n-len(out))
        if not data: raise AssertionError("early EOF")
        out+=data
    return out
def request(port,raw):
    with socket.create_connection(("127.0.0.1",port),timeout=2) as client:
        client.settimeout(2)
        client.sendall(raw)
        header=recv_all(client,2)
        return recv_all(client,int.from_bytes(header,"big"))
with tempfile.TemporaryDirectory() as d:
    db=Path(d)/"gateway.sqlite"
    with sqlite3.connect(db) as con:con.executescript(Path(schema).read_text())
    listen,unused=free_port(),free_port()
    env=dict(os.environ,ISO8583_DB_PATH=str(db),ISO8583_UPSTREAM_TIMEOUT_MS="400")
    p=subprocess.Popen([gateway,f"127.0.0.1:{listen}",f"127.0.0.1:{unused}"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        for i in range(100):
            try:
                with socket.create_connection(("127.0.0.1",listen),timeout=.1):break
            except OSError:time.sleep(.02)
        base={2:"4111111111111111",4:"000000000100",13:today,42:"MERCHANT0000001"}
        jobs=[
            ({**base,11:"000011",37:"123456789011",4:"000001000000",2:"4111111111111112",42:"MERCHANT9999999"},"61"),
            ({**base,11:"000012",37:"123456789012",2:"4111111111111112",42:"MERCHANT9999999"},"14"),
            ({**base,11:"000013",37:"123456789013",42:"MERCHANT9999999"},"03"),
            ({2:"4111111111111111",4:"000000000100",11:"000014",13:today,37:"123456789014"},"30"),
        ]
        errors=[]
        def worker(f,expected):
            try:
                answer=request(listen,encode("0200",f))
                assert answer[:4]==b"0210",(expected,answer)
                assert answer[-2:]==expected.encode(),(expected,answer)
            except Exception as e:errors.append(e)
        ts=[threading.Thread(target=worker,args=job) for job in jobs]
        for t in ts:t.start()
        for t in ts:t.join(5)
        assert all(not t.is_alive() for t in ts),"worker hung"
        assert not errors,errors
        # Malformed payload must not be relayed to unreachable upstream.
        with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
            s.settimeout(2)
            s.sendall(b"\x00\x04ABCD")
            assert s.recv(1)==b"","malformed ISO not rejected"
        # A malformed client must not break a new valid client.
        again=request(listen,encode("0100",{**base,11:"000015",37:"123456789015",4:"000001000000"}))
        assert again[:4]==b"0110" and again[-2:]==b"61"
        with sqlite3.connect(db) as con:
            rows=con.execute("SELECT outcome_code,status FROM transactions ORDER BY id").fetchall()
        assert len(rows)==5,rows
        assert all(status=="DECLINED" for code,status in rows),rows
        assert sorted(code for code,status in rows)==["03","14","30","61","61"],rows
        print("PASS: first-failure precedence, required fields, concurrent clients, malformed ISO isolation")
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill()
