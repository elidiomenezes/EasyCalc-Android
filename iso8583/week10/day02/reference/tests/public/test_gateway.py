#!/usr/bin/env python3
"""Black-box TCP gateway tests. Standard library only, Python 3.9+.

Example:
  python3 test_gateway.py --gateway-cmd './gateway {listen} {authorizer}'

The gateway must accept two positional endpoints, each IP:port.
The mock authorizer exchanges length-prefixed synthetic ISO 8583 wires.
"""
import argparse
import contextlib
import socket
import struct
import subprocess
import threading
import time
import unittest


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def recv_exact(sock, count):
    result = bytearray()
    while len(result) < count:
        part = sock.recv(count - len(result))
        if not part:
            raise EOFError('peer closed while reading a frame')
        result.extend(part)
    return bytes(result)


def frame(body):
    assert len(body) <= 65535
    return struct.pack('!H', len(body)) + body


def recv_frame(sock):
    size = struct.unpack('!H', recv_exact(sock, 2))[0]
    return recv_exact(sock, size)


def iso_wire(mti=b'0100', unique=b'000001', extra=b''):
    # Synthetic ISO 8583-style body. The mock host deliberately does NOT parse
    # data elements: day 2 checks transport preservation, not ISO validity.
    return mti + b'\x20\x00\x00\x00\x00\x00\x00\x00' + unique + extra


def expected_response(body):
    mti = {b'0100': b'0110', b'0800': b'0810'}.get(body[:4], body[:4])
    return mti + body[4:]


class MockAuthorizer:
    def __init__(self, delay=0):
        self.port = free_port()
        self.delay = delay
        self.stop = threading.Event()
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(('127.0.0.1', self.port))
        self.listener.listen(32)
        self.listener.settimeout(.2)
        self.connections = []
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while not self.stop.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections.append(client)
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, conn):
        conn.settimeout(3)
        with conn:
            while not self.stop.is_set():
                try:
                    request = recv_frame(conn)
                    if self.delay:
                        time.sleep(self.delay)
                    conn.sendall(frame(expected_response(request)))
                except (OSError, EOFError):
                    break

    def close(self):
        self.stop.set()
        with contextlib.suppress(OSError):
            self.listener.close()
        for conn in list(self.connections):
            with contextlib.suppress(OSError):
                conn.close()
        self.thread.join(timeout=1)


class GatewayCase(unittest.TestCase):
    cmd_template = ''

    def setUp(self):
        self.host = MockAuthorizer()
        self.proxy_port = free_port()
        # Split a literal executable command without shell expansion.
        import shlex
        parts = shlex.split(self.cmd_template)
        argv = [p.replace('{listen}', f'127.0.0.1:{self.proxy_port}')
                  .replace('{authorizer}', f'127.0.0.1:{self.host.port}')
                for p in parts]
        self.proxy = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if self.proxy.poll() is not None:
                self.fail(f'gateway exited early with code {self.proxy.returncode}')
            with contextlib.suppress(OSError):
                with socket.create_connection(('127.0.0.1', self.proxy_port), .1):
                    return
            time.sleep(.05)
        self.fail('gateway did not start listening')

    def tearDown(self):
        if hasattr(self, 'proxy'):
            self.proxy.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proxy.wait(timeout=1)
            if self.proxy.poll() is None:
                self.proxy.kill()
                self.proxy.wait()
        if hasattr(self, 'host'):
            self.host.close()

    def client(self):
        conn = socket.create_connection(('127.0.0.1', self.proxy_port), 2)
        conn.settimeout(3)
        return conn

    def exchange(self, conn, body):
        conn.sendall(frame(body))
        self.assertEqual(recv_frame(conn), expected_response(body))

    def test_p1_authorization(self):
        with self.client() as conn:
            self.exchange(conn, iso_wire())

    def test_p2_reuse_connection(self):
        with self.client() as conn:
            for n in range(5):
                self.exchange(conn, iso_wire(b'0800' if n % 2 else b'0100',
                                             f'{n:06d}'.encode()))

    def test_p3_two_clients(self):
        failures = []
        def run(index):
            try:
                with self.client() as conn:
                    for n in range(4):
                        self.exchange(conn, iso_wire(unique=f'{index}{n:05d}'.encode()))
            except Exception as exc:
                failures.append(str(exc))
        workers = [threading.Thread(target=run, args=(i,)) for i in (1, 2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertFalse(failures, failures)

    def test_p4_reconnect(self):
        for n in range(3):
            with self.client() as conn:
                self.exchange(conn, iso_wire(unique=f'{n:06d}'.encode()))

    def test_p5_binary_bytes(self):
        with self.client() as conn:
            self.exchange(conn, iso_wire(extra=b'\x00\x01\x7f\x80\xfe\xff'))


def run_suite(case_class, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway-cmd', required=True,
                        help='example: "./gateway {listen} {authorizer}"')
    args = parser.parse_args(argv)
    case_class.cmd_template = args.gateway_cmd
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(case_class)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(run_suite(GatewayCase))
