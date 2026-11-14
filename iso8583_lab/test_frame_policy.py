"""Real TCP regression tests for frame failure and shared upstream session."""
import json
import socket
import struct
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from iso8583_common import load_spec, encode_message, decode_message
from server import IsoServer
from tcp_framing import recv_frame, send_frame

ROOT = Path(__file__).resolve().parent

class SilentLogger:
    def status(self, *args, **kwargs): pass
    def message(self, *args, **kwargs): pass

class FramePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec(ROOT / 'specs/nibss-v1.16.json')
        args = SimpleNamespace(response_delay=0, drop_response=False, timeout=1.0,
                               framing='binary-2', once=False,
                               rules=str(ROOT / 'rules/nibss-rules.json'))
        cls.server = IsoServer(('127.0.0.1', 0), args=args, spec=cls.spec, logger=SilentLogger())
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.port = cls.server.server_address[1]
        cls.message = json.loads((ROOT / 'messages/nibss-authorization.json').read_text())
        now = datetime.now()
        cls.message.update({'7': now.strftime('%m%d%H%M%S'), '12': now.strftime('%H%M%S'), '13': now.strftime('%m%d')})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def connect(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=2)
        sock.settimeout(2)
        return sock

    def request(self, sock, stan):
        msg = dict(self.message, **{'11': stan})
        send_frame(sock, encode_message(msg, self.spec), 'binary-2')
        return decode_message(recv_frame(sock, 'binary-2'), self.spec)

    def test_zero_length_frame_closes_only_offending_connection(self):
        with self.connect() as good, self.connect() as bad:
            bad.sendall(b'\x00\x00')
            self.assertEqual(bad.recv(1), b'')
            self.assertEqual(self.request(good, '300001')['39'], '00')

    def test_oversized_declared_frame_closes_connection(self):
        with self.connect() as bad:
            bad.sendall(b'\xff\xff')
            self.assertEqual(bad.recv(1), b'')
        with self.connect() as fresh:
            self.assertEqual(self.request(fresh, '300002')['39'], '00')

    def test_truncated_frame_closes_then_new_connection_works(self):
        with self.connect() as bad:
            bad.sendall(b'\x00\x20' + b'0100')
            bad.shutdown(socket.SHUT_WR)
            self.assertEqual(bad.recv(1), b'')
        with self.connect() as fresh:
            self.assertEqual(self.request(fresh, '300003')['39'], '00')

    def test_malformed_bitmap_returns_30_and_keeps_connection(self):
        with self.connect() as sock:
            send_frame(sock, b'0100NOT_A_VALID_BITMAP', 'binary-2')
            response = decode_message(recv_frame(sock, 'binary-2'), self.spec)
            self.assertEqual(response['t'], '0110')
            self.assertEqual(response['39'], '30')
            self.assertEqual(self.request(sock, '300004')['39'], '00')

    def test_decodable_iso_missing_required_fields_returns_30_and_keeps_socket(self):
        with self.connect() as sock:
            # A syntactically valid ISO wire lacking mandatory NIBSS fields.
            minimal = {'t': '0100', '3': '000000', '4': '000000002500',
                       '7': self.message['7'], '11': '300005'}
            send_frame(sock, encode_message(minimal, self.spec), 'binary-2')
            response = decode_message(recv_frame(sock, 'binary-2'), self.spec)
            self.assertEqual(response.get('39'), '30')
            self.assertEqual(self.request(sock, '300006')['39'], '00')

    def test_shared_gateway_socket_correlates_three_clients_by_stan(self):
        # A simulated gateway multiplexes 3 downstream requests over 1 upstream TCP socket.
        # The host is synchronous: do not claim it supports out-of-order responses.
        with self.connect() as upstream:
            stans = {'client_A': '300011', 'client_B': '300012', 'client_C': '300013'}
            for stan in stans.values():
                msg = dict(self.message, **{'11': stan})
                send_frame(upstream, encode_message(msg, self.spec), 'binary-2')
            received = [decode_message(recv_frame(upstream, 'binary-2'), self.spec) for _ in stans]
            by_stan = {response['11']: response for response in received}
            for client, stan in stans.items():
                self.assertEqual(by_stan[stan]['39'], '00', client)
            self.assertEqual(len(by_stan), 3)

if __name__ == '__main__':
    unittest.main(verbosity=2)
