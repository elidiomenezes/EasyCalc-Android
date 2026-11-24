import os,sys,socket,subprocess,tempfile,sqlite3,time,contextlib
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
from iso8583_common import load_spec,load_message,encode_message,decode_message
from tcp_framing import send_frame,recv_frame
spec_path=root/'specs/nibss-v1.16.json'
spec=load_spec(str(spec_path))
message=load_message(root/'messages/network-sign-on.json')
payload=encode_message(message,spec)
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]
def ready(p,n):
    for _ in range(100):
        assert p.poll() is None,'process exited'
        try:
            with socket.create_connection(('127.0.0.1',n),timeout=.1):return
        except OSError:time.sleep(.05)
    raise RuntimeError('not listening')
def stop(p):
    p.terminate()
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:p.kill();p.wait()
def exchange(n,broken=False):
    with socket.create_connection(('127.0.0.1',n),timeout=3) as s:
        s.settimeout(5)
        send_frame(s,payload,'binary-2')
        if broken:
            started=time.monotonic()
            assert s.recv(1)==b'', 'unexpected response'
            assert time.monotonic()-started>=1, 'premature disconnect'
        else:
            response=decode_message(recv_frame(s,'binary-2'),spec)
            assert response.get('t')=='0810',response
a=port()
server=subprocess.Popen([sys.executable,str(root/'server.py'),'--host','127.0.0.1','--port',str(a),'--spec',str(spec_path),'--rules',str(root/'rules/rules.json'),'--log-view','none'],cwd=root)
try:
    ready(server,a)
    exchange(a)
    print('PASS direct course simulator 0800/0810',flush=True)
    for binary,broken in [(sys.argv[2],True),(sys.argv[3],False)]:
        n=port()
        with tempfile.TemporaryFile(mode='w+') as log:
            p=subprocess.Popen([binary,f'127.0.0.1:{n}',f'127.0.0.1:{a}'],env=dict(os.environ,ISO8583_UPSTREAM_TIMEOUT_MS='1500'),stderr=log)
            try:
                ready(p,n)
                exchange(n,broken)
                assert p.poll() is None
            finally:
                stop(p);log.seek(0);logs=log.read();print(logs)
            if broken:assert 'Upstream response timed out or disconnected' in logs
            print('PASS real simulator through '+('defective gateway (timeout)' if broken else 'corrected gateway (0810)'),flush=True)
finally:stop(server)
