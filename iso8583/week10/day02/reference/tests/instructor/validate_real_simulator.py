#!/usr/bin/env python3
"""Run the actual course server.py and client.py through a TCP gateway.

Example:
  python3 instructor/validate_real_simulator.py \
      --simulator-dir /path/to/iso8583_lab \
      --gateway-cmd './gateway {listen} {authorizer}'

This integration check complements, rather than replaces, the public/hidden
black-box transport tests. Requires pyiso8583 in the Python environment.
"""
import argparse
import contextlib
import os
import pathlib
import shlex
import socket
import subprocess
import sys
import time
import threading


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_port(port, proc):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise RuntimeError(f'process exited early with {proc.returncode}')
        with contextlib.suppress(OSError):
            with socket.create_connection(('127.0.0.1', port), timeout=.1):
                return
        time.sleep(.05)
    raise TimeoutError(f'port {port} did not start listening')


def terminate(proc):
    proc.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=2)
    if proc.poll() is None:
        proc.kill()
        proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulator-dir', type=pathlib.Path, required=True)
    ap.add_argument('--gateway-cmd', required=True)
    args = ap.parse_args()
    root = args.simulator_dir.resolve()
    upstream_port, gateway_port = free_port(), free_port()
    while upstream_port == gateway_port:
        gateway_port = free_port()
    env = dict(os.environ)
    spec = str(root / 'specs' / 'nibss-v1.16.json')
    server_args = [sys.executable, str(root / 'server.py'), '--host', '127.0.0.1',
                   '--port', str(upstream_port), '--spec', spec,
                   '--rules', str(root / 'rules' / 'rules.json'), '--log-view', 'none']
    gateway_args = [s.replace('{listen}', f'127.0.0.1:{gateway_port}')
                    .replace('{authorizer}', f'127.0.0.1:{upstream_port}')
                    for s in shlex.split(args.gateway_cmd)]
    server = subprocess.Popen(server_args, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=env)
    try:
        wait_port(upstream_port, server)
        gateway = subprocess.Popen(gateway_args, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, env=env)
        try:
            wait_port(gateway_port, gateway)
            client_args = [sys.executable, str(root / 'client.py'), '--host', '127.0.0.1',
                           '--port', str(gateway_port), '--spec', spec,
                           '--rules', str(root / 'client-rules' / 'authorization-approved.json'),
                           '--log-view', 'parsed', '--color', 'never']
            result = subprocess.run(client_args, env=env, capture_output=True,
                                    text=True, timeout=12)
            output = result.stdout + result.stderr
            ok = (result.returncode == 0 and 'CLIENT RECEIVED LEG 2' in output
                  and 'FLOW COMPLETE' in output and '0110' in output)
            print('REAL client.py/server.py 0100/0110:', 'PASS' if ok else 'FAIL')
            if not ok:
                print(output[-3500:])
                return 1

            # Exercise real simulator encoders and framing over persistent TCP.
            sys.path.insert(0, str(root))
            from iso8583_common import load_spec, load_message, encode_message, decode_message
            from tcp_framing import send_frame, recv_frame
            message_spec = load_spec(spec)
            wires = [
                (encode_message(load_message(root / 'messages' / 'authorization-approved.json'), message_spec), '0110'),
                (encode_message(load_message(root / 'messages' / 'network-sign-on.json'), message_spec), '0810'),
            ]

            def exchange_many():
                with socket.create_connection(('127.0.0.1', gateway_port), timeout=3) as conn:
                    conn.settimeout(3)
                    for request, response_mti in wires * 3:
                        send_frame(conn, request, 'binary-2')
                        reply = decode_message(recv_frame(conn, 'binary-2'), message_spec)
                        if reply.get('t') != response_mti:
                            raise AssertionError(f'expected {response_mti}, got {reply.get("t")}')

            try:
                exchange_many()
                print('REAL persistent 0100/0800 exchanges:', 'PASS')
            except Exception as exc:
                print('REAL persistent 0100/0800 exchanges: FAIL', exc)
                return 1

            failures = []
            def concurrent():
                try:
                    exchange_many()
                except Exception as exc:
                    failures.append(str(exc))
            workers = [threading.Thread(target=concurrent) for _ in range(5)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            print('REAL simulator five concurrent clients:', 'PASS' if not failures else 'FAIL')
            if failures:
                print(failures)
            return 0 if not failures else 1
        finally:
            terminate(gateway)
    finally:
        terminate(server)


if __name__ == '__main__':
    raise SystemExit(main())
