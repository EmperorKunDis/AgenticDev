#!/usr/bin/env python3
"""Root-owned AgenticDev workload broker.

The Unix-socket protocol is deliberately not a generic runtime API.  Start accepts
one signed Work Order; every later action accepts only its opaque Work Order ID
and a device JWT.  Images, commands, paths, mounts and Docker flags are compiled
into the broker.
"""
from __future__ import annotations

import base64, fcntl, hashlib, json, os, pty, pwd, re, select, shutil, signal, socket, sqlite3, struct, subprocess, termios, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ID=re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PROJECT=re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SCOPE_PART=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REF=re.compile(r"^(?:task/[0-9a-f-]{8,64}/[a-z0-9._/-]+|agenticdev/[a-z0-9._/-]+)$")
TEMPLATES={"agent-pod-v1"}
STATES={"CREATED","STARTING","RUNNING","STOPPING","STOPPED","FAILED","EXPIRED"}
TRANSITIONS={
 "CREATED":{"STARTING","FAILED","EXPIRED"},
 "STARTING":{"RUNNING","FAILED","EXPIRED"},
 "RUNNING":{"STOPPING","FAILED","EXPIRED"},
 "STOPPING":{"STOPPED","FAILED"},
 "STOPPED":set(),"FAILED":set(),"EXPIRED":set(),
}
ACTION_KEYS={
 "start":{"action","work_order","device_token"},
 "attach":{"action","work_order_id","device_token"},
 "stop":{"action","work_order_id","device_token"},
 "status":{"action","work_order_id","device_token"},
 "resize":{"action","work_order_id","device_token","rows","cols"},
 "probe":{"action","work_order_id","device_token"},
}

class Reject(Exception): pass

def canonical(m): return json.dumps({k:v for k,v in m.items() if k!="signature"},sort_keys=True,separators=(",",":")).encode()
def parse_time(v):
 try:return datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()
 except (TypeError,ValueError) as e:raise Reject("invalid_time") from e

def scope_path(raw):
 if not isinstance(raw,str) or not raw or raw.startswith('/') or len(raw)>512:raise Reject("unsafe_scope")
 value=raw[:-3] if raw.endswith('/**') else raw
 if not value or any(x in value for x in ('*','?','[',']')):raise Reject("unsafe_scope")
 path=Path(value)
 if any(part in ('..','.git','.agenticdev','.agenticdev-trees') or not SCOPE_PART.fullmatch(part) for part in path.parts):raise Reject("unsafe_scope")
 return path

@dataclass(frozen=True)
class Limits: cpus:str; memory_mb:int; pids:int; wall_seconds:int; disk_mb:int

class StateStore:
 def __init__(self,path:Path):
  path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock()
  self.db=sqlite3.connect(path,check_same_thread=False)
  self.db.execute("CREATE TABLE IF NOT EXISTS nonce(value TEXT PRIMARY KEY,used_at INTEGER NOT NULL)")
  self.db.execute("""CREATE TABLE IF NOT EXISTS workload(
   id TEXT PRIMARY KEY, manifest TEXT NOT NULL, principal TEXT NOT NULL, workstation TEXT NOT NULL,
   project TEXT NOT NULL, task TEXT NOT NULL, unix_user TEXT NOT NULL, container TEXT NOT NULL,
   worktree TEXT NOT NULL, state TEXT NOT NULL, expires REAL NOT NULL, created REAL NOT NULL)"""); self.db.commit()
  self.db.execute("CREATE TABLE IF NOT EXISTS quota(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT UNIQUE NOT NULL)"); self.db.commit()
 def consume(self,n):
  with self.lock:
   try:self.db.execute("INSERT INTO nonce VALUES(?,?)",(n,int(time.time()))); self.db.commit()
   except sqlite3.IntegrityError as e:raise Reject("replay") from e
 def create(self,m,container,worktree,now=None):
  s=m["subject"]; t=m["task"]
  with self.lock:
   now=time.time() if now is None else now
   deadline=min(parse_time(m["expires_at"]),now+int(m["runtime"]["limits"]["wall_seconds"]))
   try:self.db.execute("INSERT INTO workload VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(m["work_order_id"],json.dumps(m,separators=(",",":")),s["principal_id"],s["workstation_id"],t["project"],t["id"],s["unix_user"],container,str(worktree),"CREATED",deadline,now)); self.db.commit()
   except sqlite3.IntegrityError as e:raise Reject("workload_exists") from e
 def get(self,wid):
  with self.lock:
   r=self.db.execute("SELECT * FROM workload WHERE id=?",(wid,)).fetchone()
  if not r:raise Reject("unknown_workload")
  keys=("id","manifest","principal","workstation","project","task","unix_user","container","worktree","state","expires","created")
  d=dict(zip(keys,r)); d["manifest"]=json.loads(d["manifest"]); return d
 def transition(self,wid,allowed,new):
  if new not in STATES:raise Reject("invalid_state")
  with self.lock:
   current=self.db.execute("SELECT state FROM workload WHERE id=?",(wid,)).fetchone()
   if not current or current[0] not in allowed or new not in TRANSITIONS[current[0]]:raise Reject("invalid_transition")
   marks=','.join('?' for _ in allowed); cur=self.db.execute(f"UPDATE workload SET state=? WHERE id=? AND state IN ({marks})",(new,wid,*allowed))
   if cur.rowcount!=1:raise Reject("invalid_transition")
   self.db.commit()
 def due(self,now):
  with self.lock:return [r[0] for r in self.db.execute("SELECT id FROM workload WHERE expires<=? AND state IN ('CREATED','STARTING','RUNNING')",(now,)).fetchall()]
 def active(self):
  with self.lock:return [r[0] for r in self.db.execute("SELECT id FROM workload WHERE state IN ('CREATED','STARTING','RUNNING')").fetchall()]
 def stopping(self):
  with self.lock:return [r[0] for r in self.db.execute("SELECT id FROM workload WHERE state='STOPPING'").fetchall()]
 def quota_id(self,path):
  with self.lock:
   self.db.execute("INSERT OR IGNORE INTO quota(path) VALUES(?)",(str(path),));self.db.commit();return self.db.execute("SELECT id FROM quota WHERE path=?",(str(path),)).fetchone()[0]+10000

class Broker:
 def __init__(self,verify_key:bytes,issuer:str,control_plane:str,broker_secret:str,state:StateStore,audit_file:Path,
              runner:Callable[[list[list[str]]],None]|None=None,clock=time.time,git_runner:Callable[[list[str]],None]|None=None,quota_runner=None,account_lookup=pwd.getpwnam):
  self.key=Ed25519PublicKey.from_public_bytes(verify_key); self.issuer=issuer; self.cp=control_plane.rstrip('/'); self.secret=broker_secret
  self.state=state; self.audit_file=audit_file; self.runner=runner or self._run; self.git_runner=git_runner or self._git_run; self.quota_runner=quota_runner or self._quota_run; self.account_lookup=account_lookup; self.clock=clock; self.ptys={}
 def audit(self,verb,m,reason,user,state=None):
  s=m.get("subject") or {}; t=m.get("task") or {}; row={"ts":datetime.now(timezone.utc).isoformat(),"verb":verb,"reason":reason,"state":state,"peer_user":user,"principal_id":s.get("principal_id"),"project":t.get("project"),"task_id":t.get("id"),"work_order_id":m.get("work_order_id")}
  self.audit_file.parent.mkdir(parents=True,exist_ok=True); fd=os.open(self.audit_file,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
  try:self._post('/v1/broker/audit',row,None)
  except Reject:pass
 def handle(self,r,user):
  m=r.get("work_order") if isinstance(r,dict) and isinstance(r.get("work_order"),dict) else {}
  try:
   action=r.get("action") if isinstance(r,dict) else None
   if action not in ACTION_KEYS or set(r)!=ACTION_KEYS[action]:raise Reject("narrow_protocol_violation")
   if action=="start":return self._start(r,user)
   w=self._owned(r["work_order_id"],r["device_token"],user,allow_expired=action in ("stop","status"))
   m=w["manifest"]
   if action=="status":return {"ok":True,"work_order_id":w["id"],"state":w["state"]}
   if action=="probe":
    if w["state"]!="RUNNING":raise Reject("workload_not_running")
    try:
     acct=self.account_lookup(w["unix_user"]); out=subprocess.run(["docker","exec","--user",f"{acct.pw_uid}:{acct.pw_gid}",w["container"],"python3","/opt/agenticdev/runtime_probe.py"],check=False,capture_output=True,text=True,timeout=120)
     return {"ok":True,"work_order_id":w["id"],"probe":json.loads(out.stdout)}
    except Exception as e:raise Reject("runtime_probe_failed") from e
   if action=="attach":
    if w["state"]!="RUNNING":raise Reject("workload_not_running")
    self.audit("attach",m,"authorized",user,w["state"]); return {"ok":True,"work_order_id":w["id"],"state":w["state"],"stream":True}
   if action=="resize":
    if not(1<=int(r["rows"])<=1000 and 1<=int(r["cols"])<=1000):raise Reject("invalid_terminal_size")
    fd=self.ptys.get(w["id"])
    if fd is None:raise Reject("not_attached")
    fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack("HHHH",int(r["rows"]),int(r["cols"]),0,0)); return {"ok":True}
   return self._stop(w,user,"requested")
  except (Reject,KeyError,TypeError,ValueError) as e:
   reason=str(e) if isinstance(e,Reject) else "invalid_request"; self.audit("reject",m,reason,user); return {"ok":False,"reason":reason}
 def _start(self,r,user):
  m=r["work_order"]
  if not isinstance(r["device_token"],str):raise Reject("invalid_request")
  self._verify(m,user); auth=self._post('/v1/broker/authorize',{"work_order":m},r["device_token"]); self._match(m,auth,user)
  try:
   self.state.consume(m["nonce"])
   work=self.provision(m,auth,r["device_token"]); name="agenticdev-"+m["work_order_id"]; self.state.create(m,name,work,self.clock()); self.audit("created",m,"worktree_ready",user,"CREATED"); self.state.transition(m["work_order_id"],{"CREATED"},"STARTING"); self.audit("start",m,"provisioned",user,"STARTING")
   try:self.runner(self.runtime_plan(m,work,r["device_token"],auth)); self.state.transition(m["work_order_id"],{"STARTING"},"RUNNING")
   except Exception as e:
    self.state.transition(m["work_order_id"],{"STARTING"},"FAILED"); raise Reject("runtime_start_failed") from e
  except Exception as e:
   reason=str(e) if isinstance(e,Reject) else "runtime_start_failed"
   self.audit("start_failed",m,reason,user,"FAILED")
   raise Reject(reason) from e
  self.audit("running",m,"started",user,"RUNNING"); return {"ok":True,"work_order_id":m["work_order_id"],"state":"RUNNING"}
 def _owned(self,wid,token,user,allow_expired=False):
  if not ID.fullmatch(str(wid)):raise Reject("invalid_workload_id")
  w=self.state.get(wid); m=w["manifest"]
  if w["unix_user"]!=user:raise Reject("wrong_user")
  if w["expires"]<=self.clock():
   if not allow_expired:raise Reject("expired_workload")
  auth=self._post('/v1/broker/authorize',{"work_order":m},token); self._match(m,auth,user); return self.state.get(wid)
 def _stop(self,w,user,reason):
  if w["state"] in ("STOPPED","FAILED"):return {"ok":True,"work_order_id":w["id"],"state":w["state"]}
  if w["state"]=="EXPIRED":
   self._run_cleanup(w); self.audit("stop",w["manifest"],"expired_resources_removed",user,"EXPIRED")
   return {"ok":True,"work_order_id":w["id"],"state":"EXPIRED"}
  if w["state"]!="STOPPING":self.state.transition(w["id"],{w["state"]},"STOPPING"); self.audit("stop",w["manifest"],reason,user,"STOPPING")
  published=True
  try:
   if w["manifest"]["runtime"].get("mode")!="analysis":self._publish(w)
  except Reject:published=False
  try:self._run_cleanup(w)
  except Reject:
   self.audit("cleanup_retry",w["manifest"],"runtime_resources_remain",user,"STOPPING");raise
  if not published:
   self.state.transition(w["id"],{"STOPPING"},"FAILED"); self.audit("failed",w["manifest"],"git_publish_failed",user,"FAILED"); raise Reject("git_publish_failed")
  self.state.transition(w["id"],{"STOPPING"},"STOPPED"); self.audit("stopped",w["manifest"],"resources_removed",user,"STOPPED"); return {"ok":True,"work_order_id":w["id"],"state":"STOPPED"}
 def _publish(self,w):
  work=Path(w["worktree"]); branches={(work,w["manifest"]["repo"]["work_branch"])}
  for marker in [work/".agenticdev/finished",*list((work/".agenticdev-trees").glob("*/.agenticdev/finished"))]:
   if not marker.is_file():continue
   candidate=marker.parents[1].resolve();
   if work.resolve() not in candidate.parents and candidate!=work.resolve():raise Reject("worktree_escape")
   branch=json.loads(marker.read_text()).get("branch",""); branches.add((candidate,branch))
  for checkout,branch in branches:
   if not REF.fullmatch(branch):raise Reject("unsafe_git_ref")
   self.git_runner(["git","-C",str(checkout),"rev-parse","--verify",branch])
   self.git_runner(["git","-C",str(checkout),"push","origin",f"{branch}:{branch}"])
  self._post('/v1/broker/pull-request',{"work_order_id":w["id"],"project":w["project"],"branch":w["manifest"]["repo"]["work_branch"]},None)
 def _verify(self,m,user):
  req={"schema","issuer","key_id","work_order_id","nonce","not_before","expires_at","subject","task","runtime","policy","signature","repo"}
  if not req<=set(m):raise Reject("unsigned_or_incomplete")
  if m["schema"]!="agenticdev.work-order/v1" or m["issuer"]!=self.issuer or m["key_id"]!="primary":raise Reject("untrusted_issuer")
  sig=m["signature"]
  try:self.key.verify(base64.b64decode(sig[8:],validate=True),canonical(m))
  except Exception as e:raise Reject("bad_signature") from e
  if parse_time(m["not_before"])>self.clock()+5:raise Reject("not_yet_valid")
  if parse_time(m["expires_at"])<=self.clock():raise Reject("expired")
  s,t,rt=m["subject"],m["task"],m["runtime"]
  if not all(ID.fullmatch(str(s.get(k,''))) for k in ("principal_id","workstation_id")) or s.get("unix_user")!=user:raise Reject("wrong_user")
  if not ID.fullmatch(str(t.get("id",''))) or not PROJECT.fullmatch(str(t.get("project",''))):raise Reject("invalid_task")
  if rt.get("template") not in TEMPLATES or set(rt)!={"template","provider","mode","limits"}:raise Reject("runtime_template_denied")
  if rt.get("provider") not in {"claude","codex"}:raise Reject("provider_denied")
  if rt.get("mode") not in {"analysis","work"}:raise Reject("runtime_mode_denied")
  if rt.get("mode")=="analysis" and m["repo"].get("write_scope"):raise Reject("analysis_write_scope_denied")
  self._limits(rt.get("limits"))
  if any(k in m for k in ("host_path","mounts","image","command","environment","network","docker_flags")):raise Reject("forbidden_runtime_input")
 @staticmethod
 def _limits(raw):
  try:l=Limits(str(raw["cpus"]),int(raw["memory_mb"]),int(raw["pids"]),int(raw["wall_seconds"]),int(raw["disk_mb"])); cpu=float(l.cpus)
  except Exception as e:raise Reject("invalid_limits") from e
  if not(.1<=cpu<=8 and 128<=l.memory_mb<=32768 and 16<=l.pids<=4096 and 60<=l.wall_seconds<=14400 and 128<=l.disk_mb<=102400):raise Reject("invalid_limits")
  return l
 def _get(self,path,token):
  try:
   req=urllib.request.Request(self.cp+path,headers={"Authorization":"Bearer "+token,"X-AgenticDev-Broker":self.secret})
   with urllib.request.urlopen(req,timeout=5) as x:return json.load(x)
  except Exception as e:raise Reject("control_plane_unavailable_or_denied") from e
 def _post(self,path,body,token):
  h={"Content-Type":"application/json","X-AgenticDev-Broker":self.secret}; h.update({"Authorization":"Bearer "+token} if token else {})
  try:
   with urllib.request.urlopen(urllib.request.Request(self.cp+path,json.dumps(body).encode(),h,method="POST"),timeout=3) as x:return json.load(x)
  except Exception as e:raise Reject("control_plane_unavailable_or_denied") from e
 @staticmethod
 def _match(m,a,user):
  exp={"principal_id":m["subject"]["principal_id"],"workstation_id":m["subject"]["workstation_id"],"unix_user":user,"project":m["task"]["project"],"task_id":m["task"]["id"],"phase":m["task"]["phase"],"work_order_id":m["work_order_id"],"kill_epoch":m["kill_epoch"]}
  if not a.get("authorized") or any(a.get(k)!=v for k,v in exp.items()):raise Reject("authorization_mismatch")
  if not isinstance(a.get("repo_url"),str) or not a["repo_url"]:raise Reject("missing_server_repo")
 @staticmethod
 def safe_dir(root,*ids):
  if any(not(ID.fullmatch(x) or PROJECT.fullmatch(x)) for x in ids):raise Reject("unsafe_path_id")
  root=root.resolve(strict=True); cur=root
  for x in ids:
   cur=cur/x; cur.mkdir(mode=0o700,exist_ok=True)
   if cur.is_symlink() or root not in cur.resolve().parents:raise Reject("symlink_escape")
  return cur
 def provision(self,m,a,token):
  account=self.account_lookup(m["subject"]["unix_user"]); uid,gid=account.pw_uid,account.pw_gid
  root=Path(os.environ.get("AGENTICDEV_WORK_ROOT","/srv/agenticdev/workloads")); repos=Path(os.environ.get("AGENTICDEV_REPO_ROOT","/srv/agenticdev/repos")); repos.mkdir(parents=True,exist_ok=True,mode=0o700)
  project=m["task"]["project"]; task=m["task"]["id"]; principal=m["subject"]["principal_id"]; branch=m["repo"].get("work_branch","")
  if not REF.fullmatch(branch):raise Reject("unsafe_git_ref")
  mirror=self.safe_dir(repos,project).with_suffix('.git')
  # Serialize fetch/worktree creation per project without invoking a shell.
  lock=Path(str(mirror)+'.lock'); lock.parent.mkdir(parents=True,exist_ok=True)
  with lock.open('w') as lf:
   fcntl.flock(lf,fcntl.LOCK_EX)
   if not mirror.exists():self.git_runner(["git","clone","--mirror","--",a["repo_url"],str(mirror)])
   elif mirror.is_symlink() or not (mirror/"HEAD").is_file():raise Reject("invalid_mirror")
   source_marker=mirror/"agenticdev-source.sha256"; source_hash=hashlib.sha256(a["repo_url"].encode()).hexdigest()
   if source_marker.exists() and source_marker.read_text()!=source_hash:raise Reject("repository_identity_mismatch")
   if not source_marker.exists():source_marker.write_text(source_hash);os.chmod(source_marker,0o400)
   if (mirror/"HEAD").is_file() and any(mirror.iterdir()):self.git_runner(["git","-C",str(mirror),"fetch","--prune","origin"])
   work=self.safe_dir(root,principal,project,task)
   marker=work/".agenticdev-worktree.json"
   identity={"principal":principal,"project":project,"task":task,"branch":branch,"mirror":str(mirror)}
   if marker.exists():
    if json.loads(marker.read_text())!=identity or not (work/".git").exists():raise Reject("worktree_identity_mismatch")
   else:
    if any(work.iterdir()):raise Reject("worktree_not_empty")
    # Checkout se mountuje do podu bez hostitelského mirroru. `--shared` by
    # vytvořilo absolute alternates path do /srv, takže Git uvnitř podu
    # nedokáže načíst ani HEAD.
    self.git_runner(["git","clone","--no-hardlinks","--no-checkout","--",str(mirror),str(work)])
    self.git_runner(["git","-C",str(work),"checkout","-B",branch,m["repo"].get("base_ref","main")])
    marker.write_text(json.dumps(identity,sort_keys=True)); os.chmod(marker,0o400)
   # Provisioning čte z root-owned mirroru, ale hotovou větev musí pushnout
   # do Forgeja. URL pochází výhradně z online autorizace serveru.
   self.git_runner(["git","-C",str(work),"remote","set-url","origin",a["repo_url"]])
  bundle=self._get(f"/v1/workspace/{project}/bundle",token)
  if bundle.get("project",{}).get("code")!=project or bundle.get("project",{}).get("phase")!=m["task"]["phase"]:raise Reject("workspace_bundle_mismatch")
  author=bundle.get("author") or {}
  if author.get("name"):self.git_runner(["git","-C",str(work),"config","user.name",str(author["name"])])
  if author.get("email"):self.git_runner(["git","-C",str(work),"config","user.email",str(author["email"])])
  self._chown_tree(work/".git",uid,gid)
  metadata=work/".agenticdev"; metadata.mkdir(mode=0o700,exist_ok=True); self._chown_tree(metadata,uid,gid)
  trees=work/".agenticdev-trees"; trees.mkdir(mode=0o700,exist_ok=True); self._chown_tree(trees,uid,gid)
  for rel,content in (bundle.get("files") or {}).items():
   path=Path(rel)
   if path.is_absolute() or '..' in path.parts or path.parts[0]=='.git':raise Reject("unsafe_workspace_file")
   parent=work
   for part in path.parts[:-1]:
    candidate=parent/part
    if candidate.is_symlink():raise Reject("symlink_escape")
    candidate.mkdir(exist_ok=True)
    if work.resolve() not in candidate.resolve().parents:raise Reject("symlink_escape")
    parent=candidate
   target=work/path
   if target.exists() and target.is_symlink():raise Reject("symlink_escape")
   rendered=str(content)
   if not target.exists() or target.read_text()!=rendered:target.write_text(rendered)
  for executable in (work/'bin').glob('*') if (work/'bin').is_dir() else ():
   executable.chmod(0o555)
  for scope in m["repo"].get("write_scope",[]):
   rel=scope_path(scope); target=work/rel
   if not target.exists():
    if scope.endswith('/**') or (len(rel.parts)==1 and '.' not in rel.name):
     target=self.safe_dir(work,*rel.parts)
    else:
     parent=work
     for part in rel.parts[:-1]:
      candidate=parent/part
      if candidate.is_symlink():raise Reject("symlink_escape")
      candidate.mkdir(mode=0o550,exist_ok=True)
      if work.resolve() not in candidate.resolve().parents:raise Reject("symlink_escape")
      parent=candidate
     try:
      fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
     except OSError as e:raise Reject("scope_target_create_failed") from e
   resolved=target.resolve()
   if work.resolve() not in resolved.parents:raise Reject("symlink_escape")
   self._chown_tree(target,uid,gid)
  os.chown(work,uid,gid);os.chmod(work,0o550)
  self.quota_runner(work,self.state.quota_id(work),self._limits(m["runtime"]["limits"]).disk_mb)
  return work
 @staticmethod
 def _chown_tree(root,uid,gid):
  if root.is_symlink():raise Reject("symlink_escape")
  os.chown(root,uid,gid)
  for base,dirs,files in os.walk(root,followlinks=False):
   for name in dirs+files:
    p=Path(base)/name
    if not p.is_symlink():os.chown(p,uid,gid)
 def runtime_plan(self,m,work,token,authorization=None):
  l=self._limits(m["runtime"]["limits"]); state=Path(os.environ.get("AGENTICDEV_BROKER_STATE","/var/lib/agenticdev-broker/runs")); state.mkdir(parents=True,exist_ok=True,mode=0o700); run=self.safe_dir(state,m["work_order_id"])
  wo,tok=run/"work-order.json",run/"token"; wo.write_text(json.dumps(m,sort_keys=True,separators=(",",":"))); tok.write_text(token); os.chmod(wo,0o400);os.chmod(tok,0o400)
  account=self.account_lookup(m["subject"]["unix_user"]); uid,gid=account.pw_uid,account.pw_gid
  os.chown(wo,uid,gid);os.chown(tok,uid,gid)
  provider=m["runtime"]["provider"]
  credentials=Path(account.pw_dir)/(".claude" if provider=="claude" else ".codex")
  if credentials.is_symlink() or not credentials.is_dir() or Path(account.pw_dir).resolve() not in credentials.resolve().parents:raise Reject("credential_identity_mismatch")
  credential_stat=credentials.stat()
  if credential_stat.st_uid!=uid or credential_stat.st_gid!=gid or credential_stat.st_mode & 0o077:raise Reject("credential_permissions_invalid")
  wid=m["work_order_id"]; net="ad-"+wid; name="agenticdev-"+wid; egress="egress-"+wid
  live=(authorization or {}).get("egress_allowlist")
  if not isinstance(live,list) or not live:raise Reject("live_egress_policy_missing")
  allow=','.join(live)
  cred_dst="/home/node/.claude" if provider=="claude" else "/home/node/.codex"
  pod=["docker","run","-d","--name",name,"--user",f"{uid}:{gid}","--read-only","--security-opt","no-new-privileges","--cap-drop","ALL","--pids-limit",str(l.pids),"--cpus",l.cpus,"--memory",f"{l.memory_mb}m","--memory-swap",f"{l.memory_mb}m","--storage-opt",f"size={l.disk_mb}M","--network",net,"--env","HOME=/home/node","--env","HTTP_PROXY=http://egress:8888","--env","HTTPS_PROXY=http://egress:8888","--env","NO_PROXY=localhost,127.0.0.1","--mount",f"type=bind,src={credentials},dst={cred_dst}","--tmpfs","/tmp:rw,noexec,nosuid,size=64m","--tmpfs",f"/run/agenticdev:rw,noexec,nosuid,size=8m,mode=0700,uid={uid},gid={gid}","--mount",f"type=bind,src={work},dst=/workspace,readonly","--entrypoint","sleep","agenticdev/pod:installed","infinity"]
  for scope in m["repo"].get("write_scope",[]):
   rel=scope_path(scope); pod[-4:-4]=["--mount",f"type=bind,src={work/rel},dst=/workspace/{rel}"]
  pod[-4:-4]=["--mount",f"type=bind,src={work/'.git'},dst=/workspace/.git","--mount",f"type=bind,src={work/'.agenticdev'},dst=/workspace/.agenticdev","--mount",f"type=bind,src={work/'.agenticdev-trees'},dst=/trees"]
  pod[-4:-4]=["--mount",f"type=bind,src={wo},dst=/run/agenticdev/work-order.json,readonly","--mount",f"type=bind,src={tok},dst=/run/agenticdev/token,readonly"]
  if m["runtime"]["mode"]=="analysis":
   output=run/"analysis-output";output.mkdir(mode=0o700);os.chown(output,uid,gid)
   pod[-4:-4]=["--mount",f"type=bind,src={output},dst=/analysis-output"]
  return [["docker","network","create","--internal",net],["docker","network","create",net+"-outside"],["docker","run","-d","--name",egress,"--user","100:101","--network",net,"--network-alias","egress","--read-only","--security-opt","no-new-privileges","--cap-drop","ALL","--tmpfs","/tmp","--env","AGENTICDEV_EGRESS_ALLOW="+allow,"agenticdev/egress:installed"],["docker","network","connect",net+"-outside",egress],pod]
 def attach_stream(self,wid,token,user,conn):
  w=self._owned(wid,token,user); m=w["manifest"]
  if w["state"]!="RUNNING":raise Reject("workload_not_running")
  master,slave=pty.openpty(); self.ptys[wid]=master
  acct=self.account_lookup(w["unix_user"]); cmd=["docker","exec","--user",f"{acct.pw_uid}:{acct.pw_gid}","-it",w["container"],"python3","/opt/agenticdev/harness.py"]
  p=subprocess.Popen(cmd,stdin=slave,stdout=slave,stderr=slave,close_fds=True); os.close(slave); self.audit("attach",m,"connected",user,"RUNNING")
  try:
   while True:
    ready,_,_=select.select([conn,master],[],[])
    if conn in ready:
     data=conn.recv(65536)
     if not data:break
     os.write(master,data)
    if master in ready:
     try:data=os.read(master,65536)
     except OSError:break
     if not data:break
     conn.sendall(data)
  finally:
   self.ptys.pop(wid,None); os.close(master); p.send_signal(signal.SIGHUP); self.audit("detach",m,"disconnected",user,"RUNNING")
 def _run_cleanup(self,w):
  wid=w["id"]
  containers=(w["container"],"egress-"+wid);networks=("ad-"+wid,"ad-"+wid+"-outside")
  for name in containers:subprocess.run(["docker","rm","-f",name],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for name in networks:subprocess.run(["docker","network","rm",name],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  checks=(["docker","inspect",name] for name in containers)
  checks=(*checks,*(["docker","network","inspect",name] for name in networks))
  if any(subprocess.run(c,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0 for c in checks):raise Reject("cleanup_incomplete")
 def reap(self):
  for wid in self.state.stopping():
   try:
    w=self.state.get(wid);self._run_cleanup(w);self.state.transition(wid,{"STOPPING"},"STOPPED");self.audit("stopped",w["manifest"],"cleanup_retry_succeeded",w["unix_user"],"STOPPED")
   except Reject:pass
  reasons={wid:"deadline_reached" for wid in self.state.due(self.clock())}
  try:
   platform=self._post('/v1/broker/epoch',{},None)
   for wid in self.state.active():
    w=self.state.get(wid)
    if not platform.get("issuing_enabled") or platform.get("epoch")!=w["manifest"].get("kill_epoch"):reasons[wid]="kill_epoch_changed"
  except Reject:pass  # outage blocks every new action; it does not destroy recoverable work
  for wid,reason in reasons.items():
   try:
    w=self.state.get(wid); self._run_cleanup(w); self.state.transition(wid,{w["state"]},"EXPIRED"); self.audit("expired",w["manifest"],reason,w["unix_user"],"EXPIRED")
   except Reject:pass
 @staticmethod
 def _run(plan):
  for c in plan:subprocess.run(c,check=True,stdin=subprocess.DEVNULL)
 @staticmethod
 def _git_run(cmd):
  original=cmd;config=["-c","core.hooksPath=/dev/null"]
  if len(original)>3 and original[:2]==["git","-C"]:config += ["-c",f"safe.directory={original[2]}"]
  cmd=["git",*config,*original[1:]]
  env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"GIT_TERMINAL_PROMPT":"0",
       "GIT_SSH_COMMAND":"ssh -F /dev/null -i /srv/agenticdev/config/broker_git_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/srv/agenticdev/config/broker_known_hosts"}
  try:subprocess.run(cmd,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=300,env=env)
  except Exception as e:raise Reject("git_provision_failed") from e
 @staticmethod
 def _quota_run(path,project_id,disk_mb):
  try:
   mount=subprocess.check_output(["findmnt","-n","-o","TARGET","-T",str(path)],text=True,timeout=10).strip()
   subprocess.run(["xfs_quota","-x","-c",f"project -s -p {path} {project_id}",mount],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   subprocess.run(["xfs_quota","-x","-c",f"limit -p bhard={disk_mb}m {project_id}",mount],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  except Exception as e:raise Reject("worktree_quota_unavailable") from e

def recv_request(c,timeout=5):
 c.settimeout(timeout)
 data=b''
 while b'\n' not in data:
  try:chunk=c.recv(65536)
  except socket.timeout as e:raise Reject("request_timeout") from e
  if not chunk or len(data)+len(chunk)>1024*1024:raise Reject("invalid_request")
  data+=chunk
 return json.loads(data.split(b'\n',1)[0])
def serve(b,sock):
 sock.unlink(missing_ok=True)
 def reaper():
  while True:b.reap();time.sleep(5)
 threading.Thread(target=reaper,daemon=True).start()
 capacity=threading.BoundedSemaphore(32)
 with ThreadPoolExecutor(max_workers=16,thread_name_prefix="broker") as pool,socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.bind(str(sock));os.chmod(sock,0o660);s.listen(32)
  while True:
   c,_=s.accept()
   if not capacity.acquire(blocking=False):c.close();continue
   def worker(conn):
    try:
     with conn:
      try:
       uid=struct.unpack('3i',conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]; user=pwd.getpwuid(uid).pw_name; r=recv_request(conn)
       if r.get("action")=="attach":
        result=b.handle(r,user); conn.sendall((json.dumps(result)+'\n').encode())
        if result.get("ok"):b.attach_stream(r["work_order_id"],r["device_token"],user,conn)
       else:conn.sendall((json.dumps(b.handle(r,user))+'\n').encode())
      except Exception:conn.sendall(b'{"ok":false,"reason":"invalid_request"}\n')
    finally:capacity.release()
   pool.submit(worker,c)
def main():
 key=base64.b64decode(os.environ["WO_VERIFY_KEY_B64"]); b=Broker(key,os.environ["AGENTICDEV_INSTANCE_ID"],os.environ["CONTROL_PLANE_URL"],os.environ["BROKER_SECRET"],StateStore(Path('/var/lib/agenticdev-broker/state.sqlite3')),Path('/var/log/agenticdev-broker.jsonl'));serve(b,Path('/run/agenticdev/broker.sock'))
if __name__=='__main__':main()
