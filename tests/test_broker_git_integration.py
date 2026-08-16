import importlib.util,os,pathlib,subprocess,sys,tempfile,unittest
from unittest import mock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT=pathlib.Path(__file__).parents[1];spec=importlib.util.spec_from_file_location('broker_git',ROOT/'vps/broker.py');mod=importlib.util.module_from_spec(spec);sys.modules['broker_git']=mod;spec.loader.exec_module(mod)
P='11111111-1111-4111-8111-111111111111';T='33333333-3333-4333-8333-333333333333'
class GitProvisioning(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=pathlib.Path(self.tmp.name);self.root=root
  self.source=root/'source';self.source.mkdir();subprocess.run(['git','init','-q','-b','main',self.source],check=True);subprocess.run(['git','-C',self.source,'config','user.email','t@example.test'],check=True);subprocess.run(['git','-C',self.source,'config','user.name','T'],check=True);(self.source/'README.md').write_text('source\n');subprocess.run(['git','-C',self.source,'add','.'],check=True);subprocess.run(['git','-C',self.source,'commit','-qm','initial'],check=True)
  (root/'workloads').mkdir();(root/'repos').mkdir()
  self.env=mock.patch.dict(os.environ,{'AGENTICDEV_WORK_ROOT':str(root/'workloads'),'AGENTICDEV_REPO_ROOT':str(root/'repos')});self.env.start()
  self.chown_patcher=mock.patch.object(mod.os,'chown');self.chown=self.chown_patcher.start()
  key=Ed25519PrivateKey.generate().public_key().public_bytes_raw();self.b=mod.Broker(key,'i','http://x','s',mod.StateStore(root/'state.db'),root/'audit',quota_runner=lambda *x:None,account_lookup=lambda u:type('A',(),{'pw_uid':1000,'pw_gid':1000,'pw_dir':str(root/'home')})());self.b._get=lambda p,t:{'project':{'code':'alpha','phase':'implementation'},'files':{'bin/server-tool':'#!/bin/sh\n','AGENTS.md':'server\n'}}
 def tearDown(self):self.b.state.db.close();self.chown_patcher.stop();self.env.stop();self.tmp.cleanup()
 def manifest(self,task=T):return {'subject':{'principal_id':P,'unix_user':'alice'},'task':{'project':'alpha','id':task,'phase':'implementation'},'repo':{'work_branch':f'task/{task[:8]}/wip','base_ref':'main','write_scope':['src/**']},'runtime':{'limits':{'cpus':'1','memory_mb':512,'pids':64,'wall_seconds':600,'disk_mb':256}}}
 def auth(self,task=T):return {'repo_url':str(self.source),'project':'alpha','task_id':task}
 def test_real_git_checkout_is_idempotent_and_server_composed(self):
  m=self.manifest();first=self.b.provision(m,self.auth(),'jwt');second=self.b.provision(m,self.auth(),'jwt');self.assertTrue(first.is_relative_to(self.root/'workloads'));self.assertTrue(any((self.root/'repos').iterdir()));self.assertTrue(self.chown.called);self.assertEqual(first,second);self.assertEqual((first/'README.md').read_text(),'source\n');self.assertEqual((first/'AGENTS.md').read_text(),'server\n');self.assertTrue((first/'.git').exists());self.assertEqual(subprocess.check_output(['git','-c',f'safe.directory={first}','-C',first,'branch','--show-current'],text=True).strip(),'task/33333333/wip')
 def test_tasks_never_share_writable_checkout(self):
  other='55555555-5555-4555-8555-555555555555';a=self.b.provision(self.manifest(),self.auth(),'jwt');b=self.b.provision(self.manifest(other),self.auth(other),'jwt');self.assertNotEqual(a,b);self.assertFalse(a.samefile(b))
if __name__=='__main__':unittest.main()
