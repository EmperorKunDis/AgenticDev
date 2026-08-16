import pathlib, unittest

ROOT=pathlib.Path(__file__).parents[1]
class RuntimeCompletion(unittest.TestCase):
 def test_preflight_is_fail_closed_for_storage(self):
  s=(ROOT/'tools/runtime-host-check.sh').read_text()
  for invariant in ('cgroup2fs','overlay2','xfs','pquota','prjquota','Supports d_type','seccomp'):
   self.assertIn(invariant,s)
  self.assertNotIn('exit 0',s)
  self.assertIn('exit "$bad"',s)
 def test_installer_runs_hard_gate_and_verifies_upgrade(self):
  s=(ROOT/'install-vps.sh').read_text()
  self.assertIn('runtime-host-check.sh',s);self.assertIn('zůstal v docker group',s);self.assertIn('zůstal v sudo group',s)
  self.assertIn('systemctl is-active --quiet agenticdev-broker.service',s);self.assertIn('broker socket má nebezpečná práva',s)
  self.assertNotIn('rm -rf /srv/agenticdev/workloads',s);self.assertNotIn('rm -rf /srv/agenticdev/repos',s)
 def test_acceptance_never_converts_skip_to_pass(self):
  s=(ROOT/'tools/acceptance-runtime.sh').read_text()
  self.assertIn('PASS=',s);self.assertIn('FAIL=',s);self.assertIn('SKIP=',s);self.assertIn('(( F == 0 ))',s)
  self.assertIn('supply dedicated signed acceptance fixture',s)
 def test_protocol_actions_have_exact_schemas(self):
  s=(ROOT/'vps/broker.py').read_text()
  for action in ('start','attach','stop','status','resize','probe'):self.assertIn(f'"{action}":',s)
  self.assertIn('set(r)!=ACTION_KEYS[action]',s)
 def test_git_source_is_only_online_authorization(self):
  s=(ROOT/'vps/broker.py').read_text()
  self.assertIn('a["repo_url"]',s);self.assertNotIn('m["repo"]["url"]',s)

if __name__=='__main__':unittest.main()
