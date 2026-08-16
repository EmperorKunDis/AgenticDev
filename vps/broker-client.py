#!/usr/bin/env python3
"""Narrow unprivileged broker client; never exposes a runtime identifier."""
import argparse,json,os,select,signal,socket,sys,termios,tty
SOCK='/run/agenticdev/broker.sock'
def call(req,stream=False):
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect(SOCK);s.sendall((json.dumps(req,separators=(',',':'))+'\n').encode())
 line=b''
 while b'\n' not in line:line+=s.recv(65536)
 head,rest=line.split(b'\n',1); result=json.loads(head)
 if not result.get('ok') or not stream:s.close();return result
 if rest:os.write(sys.stdout.fileno(),rest)
 old=termios.tcgetattr(sys.stdin.fileno()) if sys.stdin.isatty() else None
 if old:tty.setraw(sys.stdin.fileno())
 previous=None
 if stream and sys.stdin.isatty():
  def resize(*_):
   rows,cols=os.get_terminal_size(sys.stdin.fileno()).lines,os.get_terminal_size(sys.stdin.fileno()).columns
   call({'action':'resize','work_order_id':req['work_order_id'],'device_token':req['device_token'],'rows':rows,'cols':cols})
  previous=signal.signal(signal.SIGWINCH,resize); resize()
 try:
  while True:
   ready,_,_=select.select([s,sys.stdin],[],[])
   if s in ready:
    data=s.recv(65536)
    if not data:break
    os.write(sys.stdout.fileno(),data)
   if sys.stdin in ready:
    data=os.read(sys.stdin.fileno(),65536)
    if not data:break
    s.sendall(data)
 finally:
  if old:termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,old)
  if previous is not None:signal.signal(signal.SIGWINCH,previous)
  s.close()
 return result
def base(action,wid=None):
 r={'action':action,'device_token':os.environ['AGENTICDEV_DEVICE_TOKEN']}
 if wid:r['work_order_id']=wid
 return r
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=('start','attach','stop','status','resize','probe'));p.add_argument('work_order_id',nargs='?');p.add_argument('--rows',type=int);p.add_argument('--cols',type=int);a=p.parse_args()
 r=base(a.action,a.work_order_id)
 if a.action=='start':r['work_order']=json.load(sys.stdin)
 if a.action=='resize':r.update(rows=a.rows,cols=a.cols)
 out=call(r,a.action=='attach')
 if a.action!='attach':print(json.dumps(out))
 raise SystemExit(0 if out.get('ok') else 1)
if __name__=='__main__':main()
