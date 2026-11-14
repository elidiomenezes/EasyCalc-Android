#!/usr/bin/env python3
"""Protocol-level smoke for all 15 listed NIBSS MTIs.

Checks each MTI's ISO encoding and binary-2 framing, then sends each over a
persistent TCP connection to the configured simulator. The 6 configured
request MTIs must yield the corresponding response. The other 9 MTIs have no
response rule in this simulator and must leave the connection operational.
This is a smoke test, not a claim of complete NIBSS conformance.
"""
import json
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from iso8583_common import load_spec, encode_message, decode_message
from tcp_framing import recv_frame, send_frame

ROOT = Path(__file__).resolve().parent
MTIS = ('0100', '0110', '0120', '0121', '0130', '0200', '0210', '0220',
        '0221', '0230', '0420', '0421', '0430', '0800', '0810')
PAIRS = {'0100': '0110', '0120': '0130', '0200': '0210',
         '0220': '0230', '0420': '0430', '0800': '0810'}


def fixture(mti):
    now = datetime.now()
    if mti in ('0800', '0810'):
        msg = {'t': mti, '7': now.strftime('%m%d%H%M%S'),
               '11': '800001', '70': '001'}
    else:
        msg = json.loads((ROOT / 'messages/nibss-authorization.json').read_text())
        msg['t'] = mti
        msg.update({'7': now.strftime('%m%d%H%M%S'),
                    '12': now.strftime('%H%M%S'), '13': now.strftime('%m%d')})
        if mti in ('0420', '0421', '0430'):
            msg.update({'56': '4000', '90': '010010000111142135260000000000011111111111',
                        '95': '0' * 42})
        if mti in ('0110', '0130', '0210', '0230', '0430'):
            msg['39'] = '00'
    return msg


def main():
    spec = load_spec(ROOT / 'specs/nibss-v1.16.json')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    cmd = [sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1',
           '--port', str(port), '--spec', str(ROOT / 'specs/nibss-v1.16.json'),
           '--rules', str(ROOT / 'rules/nibss-rules.json'), '--color', 'never',
           '--log-view', 'none', '--timeout', '300']
    server = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.STDOUT)
    results = []
    try:
        upstream = None
        for _ in range(50):
            try:
                upstream = socket.create_connection(('127.0.0.1', port), timeout=.2)
                break
            except OSError:
                time.sleep(.1)
        if upstream is None:
            raise RuntimeError('server did not start')
        with upstream:
            upstream.settimeout(.4)
            for mti in MTIS:
                msg = fixture(mti)
                raw = encode_message(msg, spec)
                decoded = decode_message(raw, spec)
                assert decoded == msg, f'{mti}: wire roundtrip mismatch'
                assert 0 < len(raw) < 65536
                send_frame(upstream, raw, 'binary-2')
                observed = None
                try:
                    response_raw = recv_frame(upstream, 'binary-2')
                    observed = decode_message(response_raw, spec)
                except socket.timeout:
                    pass
                expected = PAIRS.get(mti)
                if expected:
                    assert observed is not None, f'{mti}: response timeout'
                    assert observed['t'] == expected, f'{mti}: response MTI {observed["t"]}'
                    assert observed.get('39') == '00', f'{mti}: DE39={observed.get("39")}'
                    outcome = 'request-response-pass'
                else:
                    assert observed is None, f'{mti}: unexpected response {observed}'
                    outcome = 'no-rule-no-response-pass'
                results.append({'mti': mti, 'wire_roundtrip': 'PASS',
                                'binary2_tcp': 'PASS', 'behavior': outcome})
                print(f'{mti}: wire=PASS TCP=PASS behavior={outcome}', flush=True)
            # Ensure the session survives the MTI sequence.
            send_frame(upstream, encode_message(fixture('0100'), spec), 'binary-2')
            final = decode_message(recv_frame(upstream, 'binary-2'), spec)
            assert (final['t'], final.get('39')) == ('0110', '00')
            hb = fixture('0800')
            hb['70'] = '000'
            send_frame(upstream, encode_message(hb, spec), 'binary-2')
            reply = decode_message(recv_frame(upstream, 'binary-2'), spec)
            assert (reply['t'], reply.get('39')) == ('0810', '12')
            print('persistent connection: PASS; heartbeat DE70=000, DE39=12: PASS')
        assert len(results) == 15
        print('SMOKE PASS: 15 wire MTIs, 6 configured request flows, 9 no-rule cases')
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == '__main__':
    sys.exit(main())
