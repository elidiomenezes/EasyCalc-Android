import os,socket,subprocess,sys,threading,time
def readn(s,n):
    b=b''
    while len(b)<n:
        p=s.recv(n-len(b))
        if not p: raise EOFError()
        b+=p
    return b
def frame(b): return len(b).to_bytes(2,'big')+b
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]
payload=b'08000000000000000000'
answer=b'08100000000000000000'
with socket.socket() as server:
    server.bind(('127.0.0.1',0));server.listen();server.settimeout(5)
    target=server.getsockname()[1];listen=port()
    p=subprocess.Popen([sys.argv[1],f'127.0.0.1:{listen}',f'127.0.0.1:{target}'],env=dict(os.environ,ISO8583_UPSTREAM_TIMEOUT_MS='1500'),stderr=subprocess.PIPE,text=True)
    try:
        for i in range(100):
            try: client=socket.create_connection(('127.0.0.1',listen),timeout=.1);break
            except OSError:time.sleep(.03)
        else: raise AssertionError('gateway not listening')
        with client:
            client.settimeout(4);client.sendall(frame(payload))
            with server.accept()[0] as upstream:
                upstream.settimeout(.4)
                declared=int.from_bytes(readn(upstream,2),'big')
                assert declared==len(payload)+2,declared
                assert readn(upstream,len(payload))==payload
                try: extra=upstream.recv(2)
                except socket.timeout: pass
                else: raise AssertionError(('unexpected bytes or EOF',extra))
                assert client.recv(1)==b'', 'expected session closure'
                assert p.poll() is None
                print('PASS: header overstates payload by two bytes; upstream waits; gateway closes session on timeout')
    finally:
        p.terminate()
        _,logs=p.communicate(timeout=5)
        print(logs)
    assert 'Upstream response timed out or disconnected' in logs
