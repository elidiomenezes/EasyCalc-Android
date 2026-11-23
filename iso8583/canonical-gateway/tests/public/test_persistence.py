#!/usr/bin/env python3
"""Day 4 PUBLIC end-to-end acceptance tests. Uses real TCP and SQLite file.

Tested binary must accept: gateway LISTEN_IPV4:PORT AUTHORIZER_IPV4:PORT
The gateway must read ISO8583_DB_PATH and use that SQLite file.
Run: python3 tests/public/test_persistence.py --gateway ./build/gateway
No third-party Python packages required.
"""
import argparse
import contextlib
from datetime import datetime, timezone
from pathlib import Path
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from init_database import initialize

SPECS = {2: ('v', 2), 3: ('f', 6), 4: ('f', 12), 7: ('f', 10),
         11: ('f', 6), 12: ('f', 6), 13: ('f', 4), 37: ('f', 12),
         39: ('f', 2), 41: ('f', 8), 42: ('f', 15), 49: ('f', 3)}
FINANCIAL = {'0100': '0110', '0200': '0210', '0220': '0230', '0420': '0430'}


def wire(mti, fields):
    """Independent synthetic encoder for NIBSS ASCII-hex bitmap, not the student's parser."""
    assert len(mti) == 4 and all(c in '0123456789' for c in mti)
    bits = 0
    output = []
    for de in sorted(fields):
        assert 2 <= de <= 64 and de in SPECS, de
        value = fields[de]
        assert isinstance(value, str) and value.isascii()
        fmt, maximum = SPECS[de]
        assert (len(value) == maximum if fmt == 'f' else len(value) <= 19), (de, value)
        bits |= 1 << (64-de)
        if fmt == 'v':
            output.append(f'{len(value):02d}{value}')
        else:
            output.append(value)
    return (mti + f'{bits:016X}' + ''.join(output)).encode('ascii')


def request(stan='100001', rrn='123456789001', mti='0100', *, merchant='MERCHANT0000001',
            amount=2500, pan='4111111111111111', date=None):
    now = datetime.now(timezone.utc)
    day = date or now.strftime('%m%d')
    fields = {2: pan, 3: '000000', 4: f'{amount:012d}',
              7: day + now.strftime('%H%M%S'), 11: stan,
              12: now.strftime('%H%M%S'), 13: day,
              37: rrn, 41: 'TERM0001', 42: merchant.ljust(15), 49: '986'}
    return wire(mti, fields), fields


def reply(mti, fields, outcome='00'):
    fields = {de: fields[de] for de in (3, 4, 7, 11, 12, 13, 37, 41, 42, 49)}
    fields[39] = outcome
    return wire(FINANCIAL[mti], fields)


def framed(data):
    return len(data).to_bytes(2, 'big') + data


def exact(sock, size):
    result = bytearray()
    while len(result) < size:
        part = sock.recv(size-len(result))
        if not part:
            raise EOFError('premature EOF')
        result.extend(part)
    return bytes(result)


def receive(sock):
    hdr = exact(sock, 2)
    return exact(sock, int.from_bytes(hdr, 'big'))


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Authorizer:
    """Returns configured synthetic ISO response wires. Records EXACT requests received."""
    def __init__(self, port_number, pairs, *, hold=False, reorder=False, cross_route=False):
        self.port = port_number
        self.pairs = pairs  # request-wire -> response-wire or None
        self.received = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.hold = hold
        self.reorder = reorder
        self.cross_route = cross_route
        self.connections = []
        self.workers = []
        self.thread = threading.Thread(target=self._accept, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=3)
        for t in self.workers: t.join(timeout=1)

    def _accept(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', self.port))
            listener.listen(32)
            listener.settimeout(.1)
            while not self.stop.is_set():
                try: conn, _ = listener.accept()
                except socket.timeout: continue
                with self.lock: self.connections.append(conn)
                t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
                self.workers.append(t)
                t.start()

    def _serve(self, conn):
        with conn:
            conn.settimeout(.15)
            buffered = []
            while not self.stop.is_set():
                try: data = receive(conn)
                except socket.timeout: continue
                except (OSError, EOFError): break
                with self.lock: self.received.append(data)
                if self.cross_route:
                    response = self.pairs.get(data)
                    if response is not None:
                        with self.lock:
                            recipients = [c for c in self.connections if c is not conn]
                        for destination in reversed(recipients):
                            try:
                                destination.sendall(framed(response))
                                break
                            except OSError:
                                continue
                elif self.reorder:
                    buffered.append(data)
                    if len(buffered) < 2: continue
                    for item in reversed(buffered):
                        response = self.pairs.get(item)
                        if response is not None: conn.sendall(framed(response))
                    buffered.clear()
                else:
                    response = self.pairs.get(data)
                    if not self.hold and response is not None:
                        try: conn.sendall(framed(response))
                        except OSError: break
        with self.lock:
            if conn in self.connections: self.connections.remove(conn)


@contextlib.contextmanager
def gateway_env(binary, pairs, *, hold=False, reorder=False, cross_route=False):
    with tempfile.TemporaryDirectory(prefix='day04-pub-') as temp:
        database = Path(temp)/'transactions.sqlite'
        initialize(database, reset=True)
        upstream, listening = port(), port()
        while upstream == listening: listening = port()
        with Authorizer(upstream, pairs, hold=hold, reorder=reorder, cross_route=cross_route) as authorizer:
            env = dict(os.environ, ISO8583_DB_PATH=str(database))
            gateway = subprocess.Popen([str(Path(binary).resolve()),
                 f'127.0.0.1:{listening}',f'127.0.0.1:{upstream}'],
                 env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic()+4
                while time.monotonic() < deadline:
                    if gateway.poll() is not None:
                        raise AssertionError(f'gateway exited with {gateway.returncode}')
                    try:
                        with socket.create_connection(('127.0.0.1', listening), timeout=.05):
                            break
                    except OSError: time.sleep(.02)
                else: raise AssertionError('gateway not listening')
                yield listening, database, authorizer
            finally:
                gateway.terminate()
                try: gateway.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    gateway.kill(); gateway.communicate()


def rows(database):
    with sqlite3.connect(database, timeout=3) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute('SELECT * FROM transactions ORDER BY id')]


def await_rows(database, condition, timeout=3):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        result = rows(database)
        if condition(result): return result
        time.sleep(.03)
    raise AssertionError('database outcome not observed: ' + repr(rows(database)))


def send(port_number, msgs, *, expect=0, fragmented=False):
    with socket.create_connection(('127.0.0.1', port_number), timeout=2) as sock:
        sock.settimeout(3)
        for msg in msgs:
            payload = framed(msg)
            if fragmented:
                sock.sendall(payload[:1]); time.sleep(.003)
                sock.sendall(payload[1:5]); time.sleep(.003)
                sock.sendall(payload[5:])
            else:
                sock.sendall(payload)
        return [receive(sock) for _ in range(expect)]


def public_authorized(binary):
    req, f = request()
    ans = reply('0100', f)
    with gateway_env(binary, {req: ans}) as (p, db, auth):
        got = send(p, [req], expect=1, fragmented=True)
        assert got == [ans], 'proxy mutated real bytes'
        assert auth.received.count(req) == 1, 'authorizer did not receive request'
        rr = await_rows(db, lambda x: len(x) == 1 and x[0]['status'] != 'PENDING')
        r = rr[0]
        assert r['stan'] == f[11] and r['rrn'] == f[37]
        assert r['transaction_date'] and r['outcome_code'] == '00'
        assert r['status'] == 'APPROVED'
        assert r['amount_minor'] == 2500 and r['currency'] == '986'
        assert r['merchant_ref'] == f[42].rstrip()
        assert r['created_at'] and r['completed_at']


def public_declined(binary):
    req, f = request('100002','123456789002', mti='0200')
    ans = reply('0200', f, outcome='05')
    with gateway_env(binary, {req: ans}) as (p, db, _):
        assert send(p, [req], expect=1) == [ans]
        r = await_rows(db, lambda x: len(x)==1 and x[0]['status'] != 'PENDING')[0]
        assert r['outcome_code'] == '05' and r['status'] == 'DECLINED'


def public_pending(binary):
    req, f = request('100003','123456789003')
    with gateway_env(binary, {req: None}, hold=True) as (p, db, auth):
        send(p, [req], expect=0)
        r = await_rows(db, lambda x: len(x)==1)[0]
        assert r['status'] == 'PENDING' and r['completed_at'] is None
        assert auth.received.count(req) == 1


def public_network(binary):
    # Course heartbeat: deliberately malformed 0800, not DE70.
    heartbeat = b'0800000000000000000'
    with gateway_env(binary, {heartbeat: heartbeat}) as (p, db, auth):
        assert send(p,[heartbeat],expect=1) == [heartbeat]
        time.sleep(.15)
        assert rows(db) == [] and heartbeat in auth.received


def public_reversal(binary):
    req, f = request('100004','123456789004',mti='0420')
    ans = reply('0420', f)
    with gateway_env(binary, {req: ans}) as (p, db, _):
        assert send(p, [req], expect=1) == [ans]
        r = await_rows(db, lambda x: len(x)==1 and x[0]['status'] != 'PENDING')[0]
        assert r['operation'] == 'REVERSAL' and r['outcome_code'] == '00'


def public_parallel(binary):
    from concurrent.futures import ThreadPoolExecutor
    fixtures=[]
    for i in range(6):
        req, fields = request(f'{200001+i:06d}', f'{900000000001+i:012d}')
        fixtures.append((req, reply('0100', fields)))
    with gateway_env(binary, dict(fixtures)) as (p, db, auth):
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(send,p,[q],expect=1) for q,_ in fixtures]
            for future, (_, answer) in zip(futures, fixtures):
                assert future.result(timeout=8) == [answer]
        rr=await_rows(db, lambda x: len(x)==6 and all(r['status']=='APPROVED' for r in x))
        assert len({(r['stan'],r['rrn']) for r in rr}) == 6
        assert len(auth.received) >= 6


CASES = {
    'authorized': public_authorized,
    'declined': public_declined,
    'pending': public_pending,
    'network': public_network,
    'reversal': public_reversal,
    'parallel': public_parallel,
}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--gateway', required=True)
    cli.add_argument('--case', choices=list(CASES))
    args = cli.parse_args()
    chosen = {args.case: CASES[args.case]} if args.case else CASES
    failures = 0
    for name, callback in chosen.items():
        try:
            callback(args.gateway)
            print('PASS', name, flush=True)
        except Exception as error:
            failures += 1
            print('FAIL', name, repr(error), flush=True)
    print(f'PUBLIC: {len(chosen)-failures}/{len(chosen)} scenarios passed')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
