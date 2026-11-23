#!/usr/bin/env python3
"""Negative and boundary black-box coverage for the reference gateway."""
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

BIN, SCHEMA=sys.argv[1:3]
DAY=datetime.now(timezone.utc).strftime("%m%d")
FORMATS={2:("ll",19),4:("fixed",12),11:("fixed",6),13:("fixed",4),
         37:("fixed",12),39:("fixed",2),42:("fixed",15)}
def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));return s.getsockname()[1]
def pack(mti,values):
    bitmap=sum(1<<(64-de) for de in values)
    s=mti+f"{bitmap:016X}"
    for de,value in sorted(values.items()):
        form,n=FORMATS[de];assert len(value)<=n
        if form=="fixed":assert len(value)==n
        else:s+=f"{len(value):02d}"
        s+=value
    b=s.encode();return len(b).to_bytes(2,"big")+b
def recv_exact(s,n):
    out=b""
    while len(out)<n:
        b=s.recv(n-len(out))
        if not b:raise EOFError
        out+=b
    return out
def get_response(s):
    n=int.from_bytes(recv_exact(s,2),"big")
    return recv_exact(s,n)
def make_req(stan,amount="000000000500",pan="4111111111111111",merchant="MERCHANT0000001",mti="0100",missing=()):
    fields={2:pan,4:amount,11:f"{stan:06d}",13:DAY,
            37:f"{stan:012d}",42:merchant}
    for de in missing:fields.pop(de)
    return pack(mti,fields)
def luhn_pan(prefix,total):
    assert len(prefix)<total
    digits=prefix + "0"*(total-1-len(prefix))
    for digit in "0123456789":
        pan=digits+digit;total_sum=0;double=False
        for c in pan[::-1]:
            n=int(c)
            if double:
                n=n*2
                if n>9:n-=9
            total_sum+=n;double=not double
        if total_sum%10==0:return pan
    raise AssertionError
class Mock:
    def __init__(self,reply_code="00",response_stan=None,delay=0):
        self.port=port();self.received=[];self.reply_code=reply_code
        self.response_stan=response_stan;self.delay=delay;self.quit=threading.Event()
        self.listener=socket.socket();self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.listener.bind(("127.0.0.1",self.port));self.listener.listen(32);self.listener.settimeout(.1)
        self.thread=threading.Thread(target=self.serve,daemon=True);self.thread.start()
    def serve(self):
        children=[]
        while not self.quit.is_set():
            try:c,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:break
            t=threading.Thread(target=self.handle,args=(c,),daemon=True);t.start();children.append(t)
        for t in children:t.join(timeout=1)
    def handle(self,c):
        with c:
            c.settimeout(3)
            while not self.quit.is_set():
                try:
                    n=int.from_bytes(recv_exact(c,2),"big");v=recv_exact(c,n)
                except (EOFError,OSError,socket.timeout):break
                self.received.append(v)
                # No ISO decode needed: test requests have fixed ordered fields
                # ending in STAN, DE13, DE37, merchant. Find STAN by marker:
                stan=self.response_stan or v[-(6+4+12+15):][:6].decode()
                rrn=v[-(12+15):-15].decode()
                if self.delay:time.sleep(self.delay)
                response=pack("0110",{11:stan,13:DAY,37:rrn,39:self.reply_code})
                try:c.sendall(response)
                except OSError:break
    def close(self):
        self.quit.set();self.listener.close();self.thread.join(timeout=2)
def launch(db,auth):
    listen=port()
    env=dict(os.environ,ISO8583_DB_PATH=str(db),ISO8583_UPSTREAM_TIMEOUT_MS="450",
             ISO8583_IDLE_TIMEOUT_MS="700")
    p=subprocess.Popen([BIN,f"127.0.0.1:{listen}",f"127.0.0.1:{auth}"],
                       env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1",listen),timeout=.1):break
        except OSError:time.sleep(.02)
    return p,listen
def exchange(listen,req,expected):
    with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
        s.settimeout(3);s.sendall(req)
        answer=get_response(s)
        assert answer[:4] in (b"0110",b"0210"),answer
        assert answer[-2:]==expected.encode(),(expected,answer)
def run():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"good.sqlite"
        with sqlite3.connect(db) as con:con.executescript(Path(SCHEMA).read_text())
        auth=Mock()
        proc,listen=launch(db,auth.port)
        try:
            # Boundaries: 0 and 999999 should go upstream, 1000000 and above should not.
            for i,amount,expected in [(3001,"000000000000","00"),
                                       (3002,"000000999999","00"),
                                       (3003,"000001000000","61"),
                                       (3004,"000001000001","61")]:
                exchange(listen,make_req(i,amount=amount),expected)
            assert len(auth.received)==2,len(auth.received)
            print("PASS: exact amount boundary 0, 999999, 1000000, 1000001",flush=True)

            # PAN 12/16/19 passing Luhn; 11, non-digit and invalid checksum rejected.
            for i,n in enumerate((12,16,19),start=3010):
                exchange(listen,make_req(i,pan=luhn_pan("411111",n)),"00")
            for i,pan in [(3020,"12345678901"),(3021,"4111111111111112"),
                          (3022,"41111111111111A1"),(3023,"")]:
                exchange(listen,make_req(i,pan=pan),"14")
            assert len(auth.received)==5,len(auth.received)
            print("PASS: PAN 12/16/19, too short, checksum, non-digit and empty",flush=True)

            # Seeded IDs at both ends and exact-match whitespace policy.
            exchange(listen,make_req(3031,merchant="MERCHANT0000010"),"00")
            exchange(listen,make_req(3032,merchant="MERCHANT0000001"),"00")
            exchange(listen,make_req(3033,merchant="MERCHANT000000 "), "03")
            assert len(auth.received)==7,len(auth.received)
            print("PASS: first and last merchant ID, whitespace not silently normalized",flush=True)

            # Invalid framing and bitmap cannot reach upstream and must isolate sessions.
            before=len(auth.received)
            bad_frames=[b"\x00\x00",b"\x00\x04ABCD",
                        b"\x00\x14"+b"0100"+b"Z"*16,
                        b"\x00\x20"+b"0100"]
            for bad in bad_frames:
                with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
                    s.settimeout(2);s.sendall(bad)
                    if bad==bad_frames[-1]:s.shutdown(socket.SHUT_WR)
                    assert s.recv(1)==b"","bad frame must close"
            assert len(auth.received)==before,len(auth.received)
            exchange(listen,make_req(3034,amount="000001000000"),"61")
            print("PASS: invalid length, malformed MTI, bad bitmap, truncated frame, client isolation",flush=True)

            # Missing any essential decision field should be safe format error.
            for i,de in enumerate((2,4,11,13,37,42),start=3040):
                req=make_req(i,missing=(de,))
                with socket.create_connection(("127.0.0.1",listen),timeout=2) as s:
                    s.settimeout(2);s.sendall(req)
                    try:
                        reply=get_response(s)
                        assert reply[-2:]==b"30", (de,reply)
                    except EOFError:
                        # Missing correlation context can prohibit safe response.
                        assert de in (11,13,37),de
            print("PASS: six required fields absent (format rejection or safe close)",flush=True)
        finally:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill()
            logs=proc.stderr.read()
            # PANs must not occur in diagnostics.
            assert "4111111111111111" not in logs, "PAN leaked in logs"
            assert "4111111111111112" not in logs, "PAN leaked in logs"
            auth.close()
        with sqlite3.connect(db) as con:
            statuses=con.execute("SELECT status,outcome_code FROM transactions").fetchall()
        assert not any(code is None for _,code in statuses),"missing outcome after completed local/upstream decision"
        print("PASS: completed transaction statuses and PAN-free diagnostic logs",flush=True)

        # Explicit SQL query errors are not equivalent to 'unknown merchant'.
        broken=Path(td)/"missing_merchants.sqlite"
        with sqlite3.connect(broken) as con:
            con.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY, stan TEXT)")
        p,l=launch(broken,port())
        try:exchange(l,make_req(3060),"96")
        finally:
            p.terminate();p.wait(timeout=3)
        print("PASS: missing merchant table causes system error 96, not decline 03",flush=True)

        # SQLite unavailable: directory path must fail to open, never authorize.
        p,l=launch(td,port())
        try:exchange(l,make_req(3061),"96")
        finally:
            p.terminate();p.wait(timeout=3)
        print("PASS: unavailable database fail-closed",flush=True)

        # SQLite lock: explicit bounded wait and technical failure, not 03.
        with sqlite3.connect(db,timeout=1) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            lock.execute("UPDATE authorized_merchants SET merchant_id=merchant_id")
            p,l=launch(db,port())
            try:
                start=time.monotonic()
                exchange(l,make_req(3062),"96")
                assert time.monotonic()-start<2.5
            finally:
                p.terminate();p.wait(timeout=3)
        print("PASS: locked SQLite fails closed within bounded wait",flush=True)

        # Unmatched upstream STAN must not complete a different pending row.
        mismatch=Mock(response_stan="999999")
        p,l=launch(db,mismatch.port)
        try:
            with socket.create_connection(("127.0.0.1",l),timeout=2) as sock:
                sock.settimeout(2)
                sock.sendall(make_req(3070))
                assert sock.recv(2)==b"","mismatched response leaked to client"
            with sqlite3.connect(db) as con:
                row=con.execute("SELECT status,outcome_code FROM transactions WHERE stan='003070'").fetchone()
            assert row==("PENDING",None),row
        finally:
            p.terminate();p.wait(timeout=3);mismatch.close()
        print("PASS: mismatched response STAN not forwarded or recorded as completed",flush=True)
if __name__=="__main__":run()
