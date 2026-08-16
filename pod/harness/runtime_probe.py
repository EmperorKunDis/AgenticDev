#!/usr/bin/env python3
"""Fixed-command live sandbox probe. It never accepts client arguments."""
import json, os, pathlib, socket, urllib.request

results=[]
def result(name,status,detail): results.append({"name":name,"status":status,"detail":detail})
def denied(name,path):
 try:pathlib.Path(path).read_bytes();result(name,"FAIL",f"readable: {path}")
 except (PermissionError,FileNotFoundError,OSError) as e:result(name,"PASS",type(e).__name__)
for n,p in (("server-env","/srv/agenticdev/config/.env"),("docker-socket","/var/run/docker.sock"),("containerd-socket","/run/containerd/containerd.sock"),("foreign-home","/home/root/.ssh/id_ed25519")):
 denied(n,p)
status=pathlib.Path('/proc/self/status').read_text()
result("no-new-privileges","PASS" if "NoNewPrivs:\t1" in status else "FAIL","/proc/self/status")
cap=next((x.split()[1] for x in status.splitlines() if x.startswith('CapEff:')),None)
result("capabilities","PASS" if cap=='0000000000000000' else "FAIL",str(cap))
try:
 pathlib.Path('/workspace/.acceptance-ro').write_text('x'); result("workspace-ro","FAIL","write succeeded")
except OSError as e:result("workspace-ro","PASS",type(e).__name__)
try:
 work_order=json.loads(pathlib.Path('/run/agenticdev/work-order.json').read_text())
 scope_names=[s.split('/',1)[0] for s in work_order.get('repo',{}).get('write_scope',[])]
 scope=next((pathlib.Path('/workspace')/s for s in scope_names
             if (pathlib.Path('/workspace')/s).is_dir()),None)
except (OSError,ValueError):scope=None
if scope:
 try:
  f=scope/'.agenticdev-acceptance-rw';f.write_text('x');f.unlink();result("scope-rw","PASS",scope.name)
 except OSError as e:result("scope-rw","FAIL",repr(e))
else:result("scope-rw","SKIP","Work Order has no writable scope")
try:
 socket.create_connection(('1.1.1.1',443),timeout=3);result("direct-public-ip","FAIL","connected without proxy")
except OSError as e:result("direct-public-ip","PASS",type(e).__name__)
try:
 socket.create_connection(('example.com',443),timeout=3);result("direct-dns-egress","FAIL","connected without proxy")
except OSError as e:result("direct-dns-egress","PASS",type(e).__name__)
try:
 s=socket.socket(socket.AF_INET6);s.settimeout(3);s.connect(('2606:4700:4700::1111',443));result("ipv6-bypass","FAIL","connected")
except OSError as e:result("ipv6-bypass","PASS",type(e).__name__)
print(json.dumps(results))
raise SystemExit(1 if any(x['status']=='FAIL' for x in results) else 0)
