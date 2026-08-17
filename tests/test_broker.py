from __future__ import annotations
import base64, importlib.util, json, os, sys, tempfile, unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('broker',ROOT/'vps/broker.py'); mod=importlib.util.module_from_spec(spec); sys.modules['broker']=mod; spec.loader.exec_module(mod)
P='11111111-1111-4111-8111-111111111111'; W='22222222-2222-4222-8222-222222222222'; T='33333333-3333-4333-8333-333333333333'; WO='44444444-4444-4444-8444-444444444444'
class Boundary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/'workloads').mkdir(); (self.root/'repos').mkdir(); (self.root/'home').mkdir()
  (self.root/'home'/'.claude').mkdir(mode=0o700); (self.root/'home'/'.codex').mkdir(mode=0o700)
  self.env=mock.patch.dict(os.environ,{'AGENTICDEV_WORK_ROOT':str(self.root/'workloads'),'AGENTICDEV_REPO_ROOT':str(self.root/'repos'),'AGENTICDEV_BROKER_STATE':str(self.root/'state'),'AGENTICDEV_IDENTITY_ROOT':str(self.root/'identities')}); self.env.start()
  self.chown_patcher=mock.patch.object(mod.os,'chown'); self.chown=self.chown_patcher.start()
  self.private=Ed25519PrivateKey.generate(); public=self.private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw); self.plans=[]
  self.uid,self.gid=os.getuid(),os.getgid()
  self.b=mod.Broker(public,'instance','http://invalid','secret',mod.StateStore(self.root/'replay.db'),self.root/'audit.jsonl',runner=self.plans.append,clock=lambda:2_000_000_000,git_runner=self.fake_git,quota_runner=lambda *x:None,account_lookup=lambda u:type('A',(),{'pw_uid':self.uid,'pw_gid':self.gid,'pw_dir':str(self.root/'home')})()); self.b._post=self.authorize; self.b._get=lambda path,token:{'project':{'code':'alpha','phase':'implementation'},'files':{}}
 def fake_git(self,cmd):
  if 'clone' not in cmd:return
  target=Path(cmd[-1]); target.mkdir(parents=True,exist_ok=True)
  if '--mirror' in cmd:(target/'HEAD').write_text('ref: refs/heads/main')
  else:(target/'.git').mkdir(exist_ok=True)
 def tearDown(self):
  self.b.state.db.close(); self.chown_patcher.stop(); self.env.stop(); self.tmp.cleanup()
 @staticmethod
 def ts(d): return datetime.fromtimestamp(2_000_000_000+d,timezone.utc).isoformat()
 def manifest(self,**changes):
  m={'schema':'agenticdev.work-order/v1','issuer':'instance','key_id':'primary','work_order_id':WO,'nonce':'unique-nonce','issued_at':self.ts(-60),'not_before':self.ts(-5),'expires_at':self.ts(3600),'kill_epoch':7,'subject':{'principal_id':P,'workstation_id':W,'unix_user':'alice'},'task':{'id':T,'project':'alpha','phase':'implementation','kind':'feature','title':'test','risk_class':'standard','spec_ref':None,'dod':[]},'repo':{'url':'ssh://ignored','base_ref':'main','work_branch':'task/33333333/wip','write_scope':['src']},'runtime':{'template':'agent-pod-v1','provider':'codex','mode':'work','limits':{'cpus':'2','memory_mb':4096,'pids':256,'wall_seconds':3600,'disk_mb':1024}},'policy':{'egress_allowlist':['api.example.test']}}
  m.update(changes); m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode(); return m
 def authorize(self,path,body,token):
  if path.endswith('audit'): return {'ok':True}
  if path.endswith('epoch'): return {'issuing_enabled':True,'epoch':7}
  if path.endswith('pull-request'): return {'ok':True}
  m=body['work_order']; return {'authorized':True,'principal_id':m['subject']['principal_id'],'workstation_id':m['subject']['workstation_id'],'unix_user':'alice','project':m['task']['project'],'task_id':m['task']['id'],'phase':m['task']['phase'],'work_order_id':m['work_order_id'],'kill_epoch':m['kill_epoch'],'repo_url':'ssh://server/alpha.git','egress_allowlist':['api.example.test','control-plane']}
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
 def test_quota_failure_is_fail_closed(self):
  self.b.quota_runner=lambda *x: (_ for _ in ()).throw(mod.Reject('worktree_quota_unavailable'))
  self.reject(self.manifest(),'worktree_quota_unavailable')
 def test_workspace_bundle_identity_mismatch_rejected(self):
  self.b._get=lambda p,t:{'project':{'code':'other','phase':'implementation'},'files':{}}
  self.reject(self.manifest(),'workspace_bundle_mismatch')
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
 def test_analysis_mode_is_read_only_and_mounts_only_selected_credentials(self):
  m=self.manifest();m['runtime']['mode']='analysis';m['repo']['write_scope']=[];m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode()
  self.assertTrue(self.call(m)['ok']);flat='\n'.join(' '.join(c) for c in self.plans[0]);self.assertIn('/.codex,dst=/home/node/.codex',flat);self.assertNotIn('/home/node/.claude',flat)
 def test_analysis_mode_rejects_write_scope(self):
  m=self.manifest();m['runtime']['mode']='analysis';m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode();self.reject(m,'analysis_write_scope_denied')
 def test_traversal(self):
  m=self.manifest(); m['repo']['write_scope']=['../etc']; m['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m))).decode(); self.reject(m,'unsafe_scope')
 def test_symlink_escape(self):
  (self.root/'workloads'/P).symlink_to('/tmp'); self.reject(self.manifest(),'symlink_escape')
 def test_workspace_bundle_parent_symlink_escape(self):
  outside=self.root/'outside';outside.mkdir();self.b._get=lambda p,t:{'project':{'code':'alpha','phase':'implementation'},'files':{'bin/tool':'owned'}}
  original=self.fake_git
  def malicious(cmd):
   original(cmd)
   if 'clone' in cmd and '--mirror' not in cmd:
    work=Path(cmd[-1]);(work/'bin').symlink_to(outside)
  self.b.git_runner=malicious;self.reject(self.manifest(),'symlink_escape');self.assertFalse((outside/'tool').exists())
 def test_runtime_hardening_limits_mount_and_proxy(self):
  self.assertTrue(self.call(self.manifest())['ok']); plan=self.plans[0];flat='\n'.join(' '.join(c) for c in plan)
  pod=plan[-1];entry=pod.index('--entrypoint');self.assertEqual(pod[entry:entry+3],['--entrypoint','sleep','agenticdev/pod:installed'])
  for x in (f'--user {self.uid}:{self.gid}','no-new-privileges','--cap-drop ALL','--pids-limit 256','--cpus 2','--memory 4096m','--storage-opt size=1024M','--internal','HOME=/home/node','HTTP_PROXY=http://egress:8888','dst=/workspace,readonly','dst=/workspace/src'): self.assertIn(x,flat)
  self.assertIn('--network-alias egress',flat)
  for x in ('/srv/agenticdev/config','/etc','/var/run/docker.sock','--privileged','--pid=host','--network=host'): self.assertNotIn(x,flat)
  self.assertNotIn('docker cp',flat);self.assertNotIn('docker exec --user 0',flat)
 def plan_text(self):
  self.assertTrue(self.call(self.manifest())["ok"]); return "\n".join(" ".join(c) for c in self.plans[0])
 def test_pod_cannot_mount_server_secrets_or_runtime_socket(self):
  flat=self.plan_text(); self.assertNotIn("/srv/agenticdev/config",flat); self.assertNotIn("docker.sock",flat); self.assertNotIn("containerd.sock",flat)
 def test_pod_cannot_mount_other_user_or_project_worktree(self):
  flat=self.plan_text(); self.assertIn(P+"/alpha/"+T,flat); self.assertNotIn("22222222-1111-4111-8111-111111111111",flat); self.assertNotIn("/other/",flat)
 def test_workspace_root_read_only_and_only_scope_rw(self):
  flat=self.plan_text(); self.assertIn("dst=/workspace,readonly",flat); self.assertIn("dst=/workspace/src",flat); self.assertNotIn("dst=/workspace/etc",flat)
 def test_worktree_permissions_are_read_only_except_explicit_scope(self):
  m=self.manifest();a=self.authorize('/v1/broker/authorize',{'work_order':m},'jwt');work=self.b.provision(m,a,'jwt')
  self.assertEqual(work.stat().st_mode & 0o777,0o550);self.assertEqual((work/'src').stat().st_mode & 0o777,0o700);self.assertEqual((work/'.agenticdev').stat().st_mode & 0o777,0o700)
 def test_runtime_files_are_preowned_and_read_only(self):
  self.call(self.manifest());flat='\n'.join(' '.join(c) for c in self.plans[0]);run=self.root/'state'/WO
  self.assertEqual((run/'work-order.json').stat().st_mode & 0o777,0o400);self.assertEqual((run/'token').stat().st_mode & 0o777,0o400)
  self.assertIn('dst=/run/agenticdev/work-order.json,readonly',flat);self.assertIn('dst=/run/agenticdev/token,readonly',flat);self.assertIn('--cap-drop ALL',flat)
 def test_cleanup_failure_stays_retryable_and_reaper_retries(self):
  wid=self.call(self.manifest())['work_order_id'];self.b._publish=lambda w:None
  self.b._run_cleanup=mock.Mock(side_effect=[mod.Reject('cleanup_incomplete'),None])
  rejected=self.b.handle({'action':'stop','work_order_id':wid,'device_token':'jwt'},'alice')
  self.assertEqual(rejected['reason'],'cleanup_incomplete');self.assertEqual(self.b.state.get(wid)['state'],'STOPPING')
  self.b.reap();self.assertEqual(self.b.state.get(wid)['state'],'STOPPED');self.assertEqual(self.b._run_cleanup.call_count,2)
 def test_cleanup_verifies_resources_are_absent(self):
  result=type('R',(),{'returncode':0})()
  with mock.patch.object(mod.subprocess,'run',return_value=result):
   with self.assertRaisesRegex(mod.Reject,'cleanup_incomplete'):self.b._run_cleanup({'id':WO,'container':'agenticdev-'+WO})
 def test_silent_socket_client_hits_read_deadline(self):
  left,right=mod.socket.socketpair()
  try:
   with self.assertRaisesRegex(mod.Reject,'request_timeout'):mod.recv_request(left,0.01)
  finally:left.close();right.close()
 def test_pod_network_is_internal_and_proxy_mandatory(self):
  flat=self.plan_text(); self.assertIn("network create --internal",flat); self.assertIn("HTTP_PROXY=http://egress:8888",flat); self.assertIn("--user 100:101",flat); self.assertNotIn("--network host",flat)
 def test_narrow_protocol(self): self.reject(self.manifest(),'narrow_protocol_violation',extra={'command':'sh'})
 def test_audit_start_stop(self):
  self.call(self.manifest()); self.assertEqual([json.loads(x)['verb'] for x in (self.root/'audit.jsonl').read_text().splitlines()],['created','start','running'])
 def test_provision_is_reentrant_and_bound_to_identity(self):
  m=self.manifest(); a=self.authorize('/v1/broker/authorize',{'work_order':m},'jwt')
  first=self.b.provision(m,a,'jwt'); marker=first/'.agenticdev-worktree.json'; before=(marker.read_bytes(),marker.stat().st_mode & 0o777,marker.stat().st_mtime_ns)
  second=self.b.provision(m,a,'jwt'); self.assertEqual(first,second);self.assertEqual((marker.read_bytes(),marker.stat().st_mode & 0o777,marker.stat().st_mtime_ns),before)
  identity=json.loads((first/'.agenticdev-worktree.json').read_text()); self.assertEqual(identity['task'],T); self.assertEqual(identity['principal'],P)
 def test_cross_task_gets_distinct_worktree(self):
  m=self.manifest(); a=self.authorize('/v1/broker/authorize',{'work_order':m},'jwt'); first=self.b.provision(m,a,'jwt')
  t2='55555555-5555-4555-8555-555555555555'; m2=self.manifest(nonce='n2',work_order_id='66666666-6666-4666-8666-666666666666'); m2['task']['id']=t2; m2['repo']['work_branch']='task/55555555/wip'; m2['signature']='ed25519:'+base64.b64encode(self.private.sign(mod.canonical(m2))).decode(); a2=self.authorize('/v1/broker/authorize',{'work_order':m2},'jwt')
  self.assertNotEqual(first,self.b.provision(m2,a2,'jwt'))
 def test_publish_rejects_main_branch_in_agent_marker(self):
  m=self.manifest(); a=self.authorize('/v1/broker/authorize',{'work_order':m},'jwt'); work=self.b.provision(m,a,'jwt'); marker=work/'.agenticdev/finished'; marker.write_text(json.dumps({'branch':'main'}))
  with self.assertRaisesRegex(mod.Reject,'unsafe_git_ref'):self.b._publish({'worktree':str(work),'manifest':m})
 def test_kill_epoch_reaper_expires_running_workload(self):
  m=self.manifest(); wid=self.call(m)['work_order_id']; cleaned=[]; self.b._run_cleanup=lambda w:cleaned.append(w['id'])
  original=self.authorize
  def killed(path,body,token):
   if path.endswith('epoch'):return {'issuing_enabled':False,'epoch':8}
   return original(path,body,token)
  self.b._post=killed;self.b.reap();self.assertEqual(self.b.state.get(wid)['state'],'EXPIRED');self.assertEqual(cleaned,[wid])
 def test_deadline_reaper_transitions_to_expired_and_cleans(self):
  m=self.manifest(); started=self.call(m); wid=started['work_order_id']; cleaned=[]; self.b._run_cleanup=lambda w:cleaned.append(w['id'])
  self.b.state.db.execute('UPDATE workload SET expires=? WHERE id=?',(1,wid));self.b.state.db.commit();self.b.reap()
  self.assertEqual(self.b.state.get(wid)['state'],'EXPIRED');self.assertEqual(cleaned,[wid])
 def test_terminal_lifecycle_states_cannot_be_resurrected(self):
  wid=self.call(self.manifest())['work_order_id']
  self.b.state.transition(wid,{'RUNNING'},'EXPIRED')
  for target in ('STARTING','RUNNING','STOPPING','STOPPED','FAILED'):
   with self.assertRaisesRegex(mod.Reject,'invalid_transition'):
    self.b.state.transition(wid,{'EXPIRED'},target)
 def test_stop_of_expired_workload_cleans_without_resurrection(self):
  wid=self.call(self.manifest())['work_order_id']; cleaned=[]
  self.b.state.transition(wid,{'RUNNING'},'EXPIRED'); self.b._run_cleanup=lambda w:cleaned.append(w['id'])
  stopped=self.b.handle({'action':'stop','work_order_id':wid,'device_token':'jwt'},'alice')
  self.assertTrue(stopped['ok']);self.assertEqual(stopped['state'],'EXPIRED');self.assertEqual(cleaned,[wid])
  self.assertEqual(self.b.state.get(wid)['state'],'EXPIRED')
 def test_attach_lifecycle_and_stop_authorization(self):
  m=self.manifest(); started=self.call(m); wid=started['work_order_id']
  attach=self.b.handle({'action':'attach','work_order_id':wid,'device_token':'jwt'},'alice'); self.assertTrue(attach['ok']); self.assertTrue(attach['stream'])
  foreign=self.b.handle({'action':'attach','work_order_id':wid,'device_token':'jwt'},'mallory'); self.assertEqual(foreign['reason'],'wrong_user')
  arbitrary=self.b.handle({'action':'attach','work_order_id':wid,'device_token':'jwt','command':'sh'},'alice'); self.assertEqual(arbitrary['reason'],'narrow_protocol_violation')
  foreign_stop=self.b.handle({'action':'stop','work_order_id':wid,'device_token':'jwt'},'mallory'); self.assertEqual(foreign_stop['reason'],'wrong_user')
  self.b._run_cleanup=lambda w:None
  stopped=self.b.handle({'action':'stop','work_order_id':wid,'device_token':'jwt'},'alice'); self.assertEqual(stopped['state'],'STOPPED')
  denied=self.b.handle({'action':'attach','work_order_id':wid,'device_token':'jwt'},'alice'); self.assertEqual(denied['reason'],'workload_not_running')
class Installed(unittest.TestCase):
 def test_no_privileged_groups(self):
  text=(ROOT/'vps/agenticdev-ctl').read_text()+(ROOT/'install-vps.sh').read_text(); self.assertNotIn('usermod -aG docker',text); self.assertIn('gpasswd -d "$LOGIN" docker',text); self.assertIn('gpasswd -d "$login" docker',text); self.assertIn('gpasswd -d "$LOGIN" sudo',text)
 def test_client_cannot_invoke_runtime(self):
  launcher=(ROOT/'launcher/agenticdev').read_text(); client=(ROOT/'vps/broker-client.py').read_text(); self.assertNotIn('docker compose',launcher); self.assertNotIn('docker exec',launcher)
  for forbidden in ('image','mounts','host_path','command','environment','network','docker_flags'): self.assertNotIn('"'+forbidden+'"',client)
 def test_socket_is_narrow_not_runtime_socket(self):
  service=(ROOT/'vps/agenticdev-broker.service').read_text(); self.assertIn('User=root',service); self.assertIn('Group=agenticdev-broker',service); self.assertNotIn('docker.sock',service)
  self.assertIn('ProtectHome=read-only',service)
  self.assertNotIn('ProtectHome=true',service)
  installer=(ROOT/'install-vps.sh').read_text(); self.assertIn('chmod 0660 /var/run/docker.sock',installer); self.assertIn('chmod 0600 /run/containerd/containerd.sock',installer)
if __name__=='__main__': unittest.main()
