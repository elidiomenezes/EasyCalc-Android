#!/usr/bin/env python3
"""Integration test for copied gateway using a local byte-preserving mock authorizer."""
import argparse
import socket
import subprocess
import threading
import time
import concurrent.futures


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def recv_n(sock, size):
    result = bytearray()
    while len(result) < size:
        part = sock.recv(size - len(result))
        if not part:
            raise AssertionError('early EOF')
        result.extend(part)
    return bytes(result)


def frame(payload):
    return len(payload).to_bytes(2, 'big') + payload


def authorizer(stop, port):
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', port))
        server.listen(16)
        server.settimeout(.2)
        workers = []
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            def serve(s):
                with s:
                    s.settimeout(3)
                    while True:
                        try:
                            header = s.recv(2)
                            if not header: return
                            if len(header) < 2: header += recv_n(s,2-len(header))
                            data=recv_n(s,int.from_bytes(header,'big'))
                            s.sendall(frame(data))
                        except (OSError, AssertionError): return
            worker=threading.Thread(target=serve,args=(conn,),daemon=True)
            worker.start()
            workers.append(worker)
        for worker in workers: worker.join(timeout=1)


def request(port, messages, fragmented=False):
    with socket.create_connection(('127.0.0.1',port), timeout=3) as conn:
        conn.settimeout(5)
        for message in messages:
            raw=frame(message)
            if fragmented:
                for part in (raw[:1],raw[1:4],raw[4:]):
                    conn.sendall(part)
                    time.sleep(.004)
            else: conn.sendall(raw)
            response=recv_n(conn,2)
            data=recv_n(conn,int.from_bytes(response,'big'))
            assert data == message, 'gateway changed bytes'


def main():
    arg=argparse.ArgumentParser()
    arg.add_argument('--gateway',required=True)
    opts=arg.parse_args()
    target=available_port()
    listen=available_port()
    stopped=threading.Event()
    worker=threading.Thread(target=authorizer,args=(stopped,target),daemon=True)
    worker.start()
    gateway=subprocess.Popen([opts.gateway,f'127.0.0.1:{listen}',f'127.0.0.1:{target}'],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',listen),timeout=.05): break
            except OSError: time.sleep(.02)
        else: raise AssertionError('gateway did not listen')
        # NIBSS DE3 FIXED(6): bit 3 set. No additional fields.
        valid = b'02002000000000000000000000'
        # Intentionally malformed sign-on, just like the heartbeat: forwarded unchanged.
        heartbeat = b'0800000000000000000'
        request(listen,[valid,valid,heartbeat],fragmented=True)
        print('PASS persistent framed messages + fragmented TCP + malformed sign-on forwarded')
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            future=[pool.submit(request,listen,[valid,heartbeat,valid],i%2==0) for i in range(5)]
            for item in future: item.result(timeout=15)
        print('PASS five simultaneous sessions, 15 complete request/response exchanges')
    finally:
        gateway.terminate()
        try: _, stderr=gateway.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            gateway.kill(); _, stderr=gateway.communicate()
        stopped.set()
        worker.join(timeout=2)
    logs=stderr.decode(errors='replace')
    assert 'ISO8583 MTI=0200' in logs, 'parser not integrated with gateway logging'
    assert 'unparsed ISO8583 frame' in logs, 'malformed heartbeat was not observed'
    print('PASS real gateway parsed valid traffic and diagnosed malformed heartbeat')

if __name__=='__main__': main()
