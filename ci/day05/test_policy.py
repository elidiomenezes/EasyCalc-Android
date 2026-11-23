#!/usr/bin/env python3
import os, socket, sqlite3, subprocess, sys, tempfile, threading, time
from datetime import datetime, timezone
from pathlib import Path

BIN=sys.argv[1]
SCHEMA=sys.argv[2]
FORMATS={2:("LL",19),4:("F",12),11:("F",6),13:("F",4),37:("F",12),39:("F",2),42:("F",15)}
def wire(mti, fields):
    bitmap=0
    for de in fields: bitmap |= 1 << (64-de)
    result=mti+f"{bitmap:016X}"
    for de,val in sorted(fields.items()):
        kind,size=FORMATS[de]
        assert len(val)<=size
        if kind=="F": assert len(val)==size
        else:result+=f"{len(val):02d}"
        result+=val
    return result.encode("ascii")
def frame(payload):return len(payload).to_bytes(2,"big")+payload
def readn(s,n):
    out=b""
    while len(out)<n:
        part=s.recv(n-len(out))
        if not part:raise RuntimeError("connection closed")
        out+=part
    return out
def readframe(s):return readn(s,int.from_bytes(readn(s,2),"big"))
def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));return s.getsockname()[1]
today=datetime.now(timezone.utc).strftime("%m%d")
received=[]
auth_port=port()
def authorizer():
    listener=socket.socket()
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(("127.0.0.1",auth_port));listener.listen(4)
    listener.settimeout(10)
    try:
        conn,_=listener.accept()
        with conn:
            conn.settimeout(5)
            payload=readframe(conn)
            received.append(payload)
            stan=payload[-(6+4+12+15):] # not used for response construction
            answer=wire("0110",{11:"000004",13:today,37:"123456789004",39:"00"})
            conn.sendall(frame(answer))
    finally:listener.close()
with tempfile.TemporaryDirectory() as temp:
    db=Path(temp)/"payments.db"
    sql=Path(SCHEMA).read_text()
    con=sqlite3.connect(db);con.executescript(sql);con.commit();con.close()
    thread=threading.Thread(target=authorizer,daemon=True);thread.start()
    listen=port()
    env=dict(os.environ,ISO8583_DB_PATH=str(db),ISO8583_UPSTREAM_TIMEOUT_MS="1500")
    proc=subprocess.Popen([BIN,f"127.0.0.1:{listen}",f"127.0.0.1:{auth_port}"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        client=None
        for _ in range(100):
            try:
                client=socket.create_connection(("127.0.0.1",listen),timeout=.25);break
            except OSError:time.sleep(.03)
        assert client is not None,"gateway did not start"
        with client:
            client.settimeout(3)
            base={2:"4111111111111111",4:"000000000500",13:today,42:"MERCHANT0000001"}
            cases=[
               ({**base,11:"000001",37:"123456789001",4:"000001000000"},"61"),
               ({**base,11:"000002",37:"123456789002",2:"4111111111111112"},"14"),
               ({**base,11:"000003",37:"123456789003",42:"MERCHANT9999999"},"03"),
               ({**base,11:"000004",37:"123456789004"},"00")
            ]
            for f,expected in cases:
                req=frame(wire("0100",f))
                # Exercise fragmented TCP writes on every request.
                client.sendall(req[:3]);client.sendall(req[3:])
                answer=readframe(client)
                assert answer[:4]==b"0110",(expected,answer)
                assert answer[-2:]==expected.encode(),(expected,answer)
            thread.join(3)
            assert len(received)==1,("unexpected upstream traffic",len(received))
            assert received[0]==wire("0100",cases[-1][0]),"forwarded payload mutated"
        con=sqlite3.connect(db)
        rows=con.execute("SELECT outcome_code,status FROM transactions ORDER BY id").fetchall()
        assert rows==[("61","DECLINED"),("14","DECLINED"),("03","DECLINED"),("00","APPROVED")],rows
        print("PASS: amount, Luhn, merchant, forwarding, split frames, SQLite lifecycle")
    finally:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill()
        if proc.returncode not in (0,-15):
            print(proc.stderr.read(),file=sys.stderr)
