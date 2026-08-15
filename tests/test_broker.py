from __future__ import annotations
import base64, importlib.util, json, os, sys, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('broker',ROOT/'vps/broker.py'); mod=importlib.util.module_from_spec(spec); sys.modules['broker']=mod; spec.loader.exec_module(mod)
P='11111111-1111-4111-8111-111111111111'; W='22222222-2222-4222-8222-222222222222'; T='33333333-3333-4333-8333-333333333333'; WO='44444444-4444-4444-8444-444444444444'
class Boundary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/'workloads').mkdir(); os.environ['AGENTICDEV_WORK_ROOT']=str(self.root/'workloads'); os.environ['AGENTICDEV_BROKER_STATE']=str(self.root/'state')
  self.private=Ed25519PrivateKey.generate(); public=self.private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw); self.plans=[]
  self.b=mod.Broker(public,'instance','http://invalid','secret',mod.ReplayStore(self.root/'replay.db'),self.root/'audit.jsonl',runner=self.plans.append,clock=lambda:2_000_000_000); self.b._post=self.authorize
 def tearDown(self): self.tmp.cleanup()
 @staticmethod
 def ts(d): return datetime.fromtimestamp(2_000_000_000+d,timezone.utc).isoformat()
 def manifest(self,**changes):
  m={'schema':'agenticdev.work-order/v1','issuer':'instance','key_id':'primary','work_order_id':WO,'nonce':'unique-nonce','issued_at':self.ts(-60),'not_before':self.ts(-5),'expires_at':self.ts(3600),'kill_epoch':7,'subject':{'principal_id':P,'workstation_id':W,'unix_user':'alice'},'task':{'id':T,'project':'alpha','phase':'implementation','kind':'feature','title':'test','risk_class':'standard','spec_ref':None,'dod':[]},'repo':{'url':'ssh://ignored','base_ref':'main','work_branch':'task/x','write_scope':['src']},'runtime':{'template':'agent-pod-v1','limits':{'cpus':'2','memory_mb':4096,'pids':256,'wall_seconds':3600,'disk_mb':1024}},'policy':{'egress_allowlist':['api.example.test']}}
  m.update(changes); m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode(); return m
 def authorize(self,path,body,token):
  if path.endswith('audit'): return {'ok':True}
  m=body['work_order']; return {'authorized':True,'principal_id':m['subject']['principal_id'],'workstation_id':m['subject']['workstation_id'],'unix_user':'alice','project':m['task']['project'],'task_id':m['task']['id'],'phase':m['task']['phase'],'work_order_id':m['work_order_id'],'kill_epoch':m['kill_epoch']}
 def call(self,m,user='alice',extra=None):
  r={'action':'start','work_order':m,'device_token':'jwt'}; r.update(extra or {}); return self.b.handle(r,user)
 def reject(self,m,reason,**kw):
  r=self.call(m,**kw); self.assertFalse(r['ok']); self.assertEqual(r['reason'],reason)
 def test_unsigned(self):
  m=self.manifest(); del m['signature']; self.reject(m,'unsigned_or_incomplete')
 def test_tampered(self):
  m=self.manifest(); m['task']['project']='other'; self.reject(m,'bad_signature')
 def test_expired(self): self.reject(self.manifest(expires_at=self.ts(-1)),'expired')
 def test_future(self): self.reject(self.manifest(not_before=self.ts(60)),'not_yet_valid')
 def test_replay(self): self.assertTrue(self.call(self.manifest())['ok']); self.reject(self.manifest(),'replay')
 def test_other_user(self): self.reject(self.manifest(),'wrong_user',user='mallory')
 def test_other_project(self):
  orig=self.authorize
  def wrong(path,body,token):
   a=orig(path,body,token)
   if 'project' in a:a['project']='other'
   return a
  self.b._post=wrong; self.reject(self.manifest(),'authorization_mismatch')
 def deny_online(self):
  self.b._post=lambda *x: (_ for _ in ()).throw(mod.Reject('control_plane_unavailable_or_denied'))
 def test_revoked_user_rejected(self): self.deny_online(); self.reject(self.manifest(),'control_plane_unavailable_or_denied')
 def test_unassigned_user_rejected(self): self.deny_online(); self.reject(self.manifest(),'control_plane_unavailable_or_denied')
 def test_kill_switch_rejects_new_workload(self): self.deny_online(); self.reject(self.manifest(),'control_plane_unavailable_or_denied')
 def test_control_plane_unavailable_rejected(self): self.deny_online(); self.reject(self.manifest(),'control_plane_unavailable_or_denied')
 def test_forbidden_runtime_inputs(self):
  for k in ('host_path','mounts','image','command','environment','network','docker_flags'): self.reject(self.manifest(**{k:'/etc'}),'forbidden_runtime_input')
 def test_traversal(self):
  m=self.manifest(); m['repo']['write_scope']=['../etc']; m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode(); self.reject(m,'unsafe_scope')
 def test_symlink_escape(self):
  (self.root/'workloads'/P).symlink_to('/tmp'); self.reject(self.manifest(),'symlink_escape')
 def test_runtime_hardening_limits_mount_and_proxy(self):
  self.assertTrue(self.call(self.manifest())['ok']); flat='\n'.join(' '.join(c) for c in self.plans[0])
  for x in ('--user 1000:1000','no-new-privileges','--cap-drop ALL','--pids-limit 256','--cpus 2','--memory 4096m','--storage-opt size=1024M','--internal','HTTP_PROXY=http://egress:8888','dst=/workspace,readonly','dst=/workspace/src'): self.assertIn(x,flat)
  for x in ('/srv/agenticdev/config','/etc','/var/run/docker.sock','--privileged','--pid=host','--network=host'): self.assertNotIn(x,flat)
 def plan_text(self):
  self.assertTrue(self.call(self.manifest())["ok"]); return "\n".join(" ".join(c) for c in self.plans[0])
 def test_pod_cannot_mount_server_secrets_or_runtime_socket(self):
  flat=self.plan_text(); self.assertNotIn("/srv/agenticdev/config",flat); self.assertNotIn("docker.sock",flat); self.assertNotIn("containerd.sock",flat)
 def test_pod_cannot_mount_other_user_or_project_worktree(self):
  flat=self.plan_text(); self.assertIn(P+"/alpha/"+T,flat); self.assertNotIn("22222222-1111-4111-8111-111111111111",flat); self.assertNotIn("/other/",flat)
 def test_workspace_root_read_only_and_only_scope_rw(self):
  flat=self.plan_text(); self.assertIn("dst=/workspace,readonly",flat); self.assertIn("dst=/workspace/src",flat); self.assertNotIn("dst=/workspace/etc",flat)
 def test_pod_network_is_internal_and_proxy_mandatory(self):
  flat=self.plan_text(); self.assertIn("network create --internal",flat); self.assertIn("HTTP_PROXY=http://egress:8888",flat); self.assertNotIn("--network host",flat)
 def test_narrow_protocol(self): self.reject(self.manifest(),'narrow_protocol_violation',extra={'command':'sh'})
 def test_audit_start_stop(self):
  self.call(self.manifest()); self.assertEqual([json.loads(x)['verb'] for x in (self.root/'audit.jsonl').read_text().splitlines()],['start','stop'])
class Installed(unittest.TestCase):
 def test_no_privileged_groups(self):
  text=(ROOT/'vps/agenticdev-ctl').read_text()+(ROOT/'install-vps.sh').read_text(); self.assertNotIn('usermod -aG docker',text); self.assertIn('gpasswd -d "$LOGIN" docker',text); self.assertIn('gpasswd -d "$login" docker',text); self.assertIn('gpasswd -d "$LOGIN" sudo',text)
 def test_client_cannot_invoke_runtime(self):
  launcher=(ROOT/'launcher/agenticdev').read_text(); client=(ROOT/'vps/broker-client.py').read_text(); self.assertNotIn('docker compose',launcher); self.assertNotIn('docker exec',launcher)
  for forbidden in ('image','mounts','host_path','command','environment','network','docker_flags'): self.assertNotIn('"'+forbidden+'"',client)
 def test_socket_is_narrow_not_runtime_socket(self):
  service=(ROOT/'vps/agenticdev-broker.service').read_text(); self.assertIn('User=root',service); self.assertIn('Group=agenticdev-broker',service); self.assertNotIn('docker.sock',service)
  installer=(ROOT/'install-vps.sh').read_text(); self.assertIn('chmod 0660 /var/run/docker.sock',installer); self.assertIn('chmod 0600 /run/containerd/containerd.sock',installer)
if __name__=='__main__': unittest.main()
