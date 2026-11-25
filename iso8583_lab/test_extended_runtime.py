import json, socket, struct, threading, time, unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from iso8583_common import load_spec, load_message, encode_message, decode_message
from tcp_framing import recv_frame, send_frame
from server import IsoServer

ROOT=Path(__file__).resolve().parent
class Logger:
 def status(self,*args,**kwargs): pass
 def message(self,*args,**kwargs): pass

class RuntimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.spec=load_spec(ROOT/'specs/nibss-v1.16.json')
  cls.server=IsoServer(('127.0.0.1',0),args=SimpleNamespace(response_delay=0,drop_response=False,timeout=1.2,framing='binary-2',once=False,rules=str(ROOT/'rules/nibss-rules.json')),spec=cls.spec,logger=Logger())
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.port=cls.server.server_address[1]
  cls.msg=json.loads((ROOT/'messages/nibss-authorization.json').read_text())
  now=datetime.now();cls.msg['7']=now.strftime('%m%d%H%M%S');cls.msg['12']=now.strftime('%H%M%S');cls.msg['13']=now.strftime('%m%d')
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
 def connect(self):
  s=socket.create_connection(('127.0.0.1',self.port),timeout=2);s.settimeout(2);return s
 def request(self,s,fields):
  send_frame(s,encode_message(fields,self.spec),'binary-2');return decode_message(recv_frame(s,'binary-2'),self.spec)
 def test_01_authorization_roundtrip(self):
  with self.connect() as s:
   r=self.request(s,self.msg);self.assertEqual((r['t'],r['39']),('0110','00'))
 def test_02_persistent_socket_three_authorizations(self):
  with self.connect() as s:
   for i in range(3):
    m=dict(self.msg);m['11']=f'{100001+i:06d}';r=self.request(s,m)
    self.assertEqual(r['t'],'0110');self.assertEqual(r['11'],m['11'])
 def test_03_heartbeat_invalid_transaction_then_authorization(self):
  with self.connect() as s:
   m=load_message(ROOT/'messages/network-heartbeat.json')
   r=self.request(s,m)
   self.assertEqual((r['t'],r.get('39')),('0810','12'))
   r2=self.request(s,self.msg);self.assertEqual(r2['t'],'0110')
 def test_04_fragmented_tcp_frame(self):
  raw=encode_message(self.msg,self.spec);framed=struct.pack('!H',len(raw))+raw
  with self.connect() as s:
   for chunk in (framed[:1],framed[1:2],framed[2:11],framed[11:]):
    s.sendall(chunk)
   r=decode_message(recv_frame(s,'binary-2'),self.spec);self.assertEqual(r['t'],'0110')
 def test_05_two_frames_in_one_send(self):
  raw=encode_message(self.msg,self.spec);frame=struct.pack('!H',len(raw))+raw
  with self.connect() as s:
   s.sendall(frame+frame)
   self.assertEqual(decode_message(recv_frame(s,'binary-2'),self.spec)['t'],'0110')
   self.assertEqual(decode_message(recv_frame(s,'binary-2'),self.spec)['t'],'0110')
 def test_06_zero_length_rejected(self):
  with self.connect() as s:
   s.sendall(b'\x00\x00');self.assertEqual(s.recv(1),b'')
 def test_07_truncated_frame_connection_closed(self):
  with self.connect() as s:
   s.sendall(b'\x00\x20' + b'0100');s.shutdown(socket.SHUT_WR)
   self.assertEqual(s.recv(1),b'')
 def test_08_idle_timeout(self):
  with self.connect() as s:
   start=time.monotonic();self.assertEqual(s.recv(1),b'');elapsed=time.monotonic()-start
   self.assertGreaterEqual(elapsed,1.0);self.assertLess(elapsed,2.8)
 def test_09_parallel_clients(self):
  errors=[];lock=threading.Lock()
  def worker(i):
   try:
    with self.connect() as s:
     m=dict(self.msg);m['11']=f'{200000+i:06d}'
     r=self.request(s,m)
     if r.get('11')!=m['11'] or r.get('39')!='00':raise AssertionError(r)
   except Exception as e:
    with lock:errors.append(str(e))
  threads=[threading.Thread(target=worker,args=(i,)) for i in range(8)]
  for t in threads:t.start()
  for t in threads:t.join(timeout=4)
  self.assertFalse(errors,errors)
 def test_10_client_disconnect_does_not_kill_server(self):
  s=self.connect();s.close()
  with self.connect() as s2:self.assertEqual(self.request(s2,self.msg)['t'],'0110')
if __name__=='__main__':unittest.main(verbosity=2)
