#!/usr/bin/env python3
"""Instructor-only black-box tests H1-H7 for the Day 2 gateway.

Uses the *original* public harness for fixtures and mock authorizer.
Run from the instructor repository:
  python3 test_hidden_gateway.py --gateway-cmd './gateway {listen} {authorizer}'
"""
import argparse
import concurrent.futures
import pathlib
import sys
import threading
import time
import unittest

# The test lives beside tests/public/ in the EasyCalc repository.
public = pathlib.Path(__file__).resolve().parents[1] / 'public'
sys.path.insert(0, str(public))
from test_gateway import GatewayCase, frame, iso_wire, recv_frame, expected_response


class HiddenGatewayCase(GatewayCase):
    def test_h1_one_byte_at_a_time(self):
        body = iso_wire(extra=b'0123456789')
        with self.client() as conn:
            for byte in frame(body):
                conn.sendall(bytes([byte]))
                time.sleep(0.002)
            self.assertEqual(recv_frame(conn), expected_response(body))

    def test_h2_eight_frames_one_write(self):
        bodies = [iso_wire(unique=f'{n:06d}'.encode()) for n in range(8)]
        with self.client() as conn:
            conn.sendall(b''.join(frame(body) for body in bodies))
            for body in bodies:
                self.assertEqual(recv_frame(conn), expected_response(body))

    def test_h3_ten_clients_six_exchanges(self):
        def worker(index):
            with self.client() as conn:
                for n in range(6):
                    body = iso_wire(unique=f'{index:02d}{n:04d}'.encode())
                    conn.sendall(frame(body))
                    if recv_frame(conn) != expected_response(body):
                        raise AssertionError(f'wrong response on client {index}')
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(worker, range(10)))

    def test_h4_reuse_after_idle(self):
        with self.client() as conn:
            self.exchange(conn, iso_wire(unique=b'000001'))
            time.sleep(1.5)
            self.exchange(conn, iso_wire(unique=b'000002'))

    def test_h5_large_frame_many_buffers(self):
        body = iso_wire(extra=bytes(range(256)) * 230)  # ~59 KiB payload
        with self.client() as conn:
            conn.settimeout(8)
            conn.sendall(frame(body))
            self.assertEqual(recv_frame(conn), expected_response(body))

    def test_h6_one_client_closes_other_survives(self):
        with self.client() as first, self.client() as second:
            self.exchange(first, iso_wire(unique=b'000001'))
            self.exchange(second, iso_wire(unique=b'000002'))
            first.shutdown(2)
            first.close()
            for n in range(4):
                self.exchange(second, iso_wire(unique=f'{n:06d}'.encode()))

    def test_h7_thirty_sequential_sessions(self):
        for n in range(30):
            with self.client() as conn:
                self.exchange(conn, iso_wire(unique=f'{n:06d}'.encode()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway-cmd', required=True)
    args = parser.parse_args()
    HiddenGatewayCase.cmd_template = args.gateway_cmd
    # Execute only H1-H7. The public P1-P5 already run in the public workflow.
    test_names = [f'test_h{i}_{suffix}' for i, suffix in [
        (1, 'one_byte_at_a_time'), (2, 'eight_frames_one_write'),
        (3, 'ten_clients_six_exchanges'), (4, 'reuse_after_idle'),
        (5, 'large_frame_many_buffers'), (6, 'one_client_closes_other_survives'),
        (7, 'thirty_sequential_sessions')]]
    suite = unittest.TestSuite(HiddenGatewayCase(name) for name in test_names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
