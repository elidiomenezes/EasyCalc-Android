#!/usr/bin/env python3
"""Parallel persistent load + fuzzed malformed frames, no external simulator."""
import concurrent.futures, os, random, socket, sqlite3, subprocess, sys
import tempfile, threading, time
from datetime import datetime, timezone
from pathlib import Path

BIN, SCHEMA=sys.argv[1:3]
day=datetime.now(timezone.utc).strftime("%m%d")
def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));return s.getsockname()[1]
def framed(payload):return len(payload).to_bytes(2,"big")+payload
def message(stan,amount):
    fields={2:"4111111111111111",4:f"{amount:012d}",11:f"{stan:06d}",
            13:day,37:f"{stan:012d}",42:"MERCHANT0000001"}
    bitmap=sum(1<<(64-d) for d in fields)
    b=f"0100{bitmap:016X}"
    for de,v in sorted(fields.items()):
        if de==2:b+=f"{len(v):02d}"
        b+=v
    return framed(b.encode())
def response(stan):
    fields={11:f"{stan:06d}",13:day,37:f"{stan:012d}",39:"00"}
    bits=sum(1<<(64-d) for d in fields)
    b=f"0110{bits:016X}"+''.join(v for d,v in sorted(fields.items()))
    return framed(b.encode())
def recv_exact(sock,n):
    b=b""
    while len(b)<n:
        piece=sock.recv(n-len(b))
        if not piece:raise EOFError
        b+=piece
    return b
def readframe(sock):
    n=int.from_bytes(recv_exact(sock,2),"big")
    return recv_exact(sock,n)
authport,listen=port(),port()
stop=threading.Event();count=[];errors=[]
def serve():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        server.bind(("127.0.0.1",authport));server.listen(64);server.settimeout(.1)
        children=[]
        while not stop.is_set():
            try:c,_=server.accept()
            except socket.timeout:continue
            def handle(c):
                with c:
                    c.settimeout(8)
                    while not stop.is_set():
                        try:
                            data=readframe(c)
                            # Extract DE11 (fields ordered: LLVAR PAN, DE4, DE11, ...).
                            field_offset=4+16+2+16+12
                            stan=int(data[field_offset:field_offset+6])
                            count.append(stan)
                            c.sendall(response(stan))
                        except (EOFError,socket.timeout,OSError):break
                        except Exception as e:errors.append(str(e));break
            t=threading.Thread(target=handle,args=(c,),daemon=True)
            t.start();children.append(t)
        for t in children:t.join(timeout=1)
thread=threading.Thread(target=serve,daemon=True);thread.start()
with tempfile.TemporaryDirectory() as temp:
    db=Path(temp)/"payments.db"
    with sqlite3.connect(db) as con:con.executescript(Path(SCHEMA).read_text())
    env=dict(os.environ,ISO8583_DB_PATH=str(db),ISO8583_UPSTREAM_TIMEOUT_MS="6000",
             ISO8583_IDLE_TIMEOUT_MS="6000")
    p=subprocess.Popen([BIN,f"127.0.0.1:{listen}",f"127.0.0.1:{authport}"],
                       env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",listen),timeout=.1):break
            except OSError:time.sleep(.02)
        workers=24;iterations=6
        def client(worker):
            with socket.create_connection(("127.0.0.1",listen),timeout=3) as s:
                s.settimeout(8)
                for i in range(iterations):
                    stan=400000+worker*iterations+i
                    payload=message(stan,500)
                    s.sendall(payload)
                    assert readframe(s)==response(stan)[2:],stan
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(client,range(workers)))
        assert not errors,errors
        assert len(count)==workers*iterations,(len(count),workers*iterations)
        with sqlite3.connect(db) as con:
            rows=con.execute("SELECT status,outcome_code FROM transactions WHERE stan >= '400000'").fetchall()
        assert len(rows)==workers*iterations,(len(rows),workers*iterations)
        assert all(row==("APPROVED","00") for row in rows)
        print(f"PASS: {workers} parallel persistent clients, {workers*iterations} transactions, no cross-talk",flush=True)

        # Reproducible malformed messages, each isolated to its own TCP session.
        rng=random.Random(8583)
        malformed=[]
        for i in range(100):
            size=rng.randrange(1,100)
            payload=bytes(rng.getrandbits(8) for _ in range(size))
            malformed.append(framed(payload))
        for frame in malformed:
            with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
                s.settimeout(3)
                s.sendall(frame)
                try: result=s.recv(16)
                except ConnectionResetError:result=b""
                assert result==b"",("garbage frame received answer",result)
        # Final valid transaction after malformed client storm.
        with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
            s.settimeout(3)
            s.sendall(message(499999,500))
            assert readframe(s)==response(499999)[2:]
        assert p.poll() is None,"fuzzing crashed the gateway"
        print("PASS: 100 deterministic malformed frame cases, process survives, subsequent transaction works",flush=True)
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill()
        stop.set();thread.join(timeout=2)
