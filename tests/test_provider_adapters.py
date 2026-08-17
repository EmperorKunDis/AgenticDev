import importlib.util
import pathlib
import sys
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location("providers",ROOT/"pod/harness/providers.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
sys.modules["providers"]=mod
analysis_spec=importlib.util.spec_from_file_location("analysis_runner",ROOT/"pod/harness/analysis_runner.py")
analysis=importlib.util.module_from_spec(analysis_spec);analysis_spec.loader.exec_module(analysis)

class ProviderAdapters(unittest.TestCase):
 def test_auth_and_quota_failures_are_recoverable_states(self):
  self.assertEqual(mod.classify_failure("Please login to continue",1),"AUTH_REQUIRED")
  self.assertEqual(mod.classify_failure("usage limit reached",1),"RATE_LIMITED")
  self.assertEqual(mod.classify_failure("unexpected",1),"FAILED")
 def test_analysis_cli_is_read_only_and_ignores_project_rules(self):
  with mock.patch.object(mod.shutil,"which",return_value="/bin/codex"):
   cmd=mod.command("codex","scan",mode="analysis")
  for flag in ("read-only","--ephemeral","--ignore-user-config","--ignore-rules"):
   self.assertIn(flag,cmd)
 def test_no_cross_provider_fallback(self):
  with mock.patch.object(mod.shutil,"which",return_value=None):
   self.assertEqual(mod.command("claude","x"),[]);self.assertEqual(mod.command("codex","x"),[])
 def test_remote_codex_login_uses_device_flow(self):
  launcher=(ROOT/"launcher/agenticdev").read_text()
  self.assertIn("codex login --device-auth",launcher)
  self.assertNotIn("|| codex login\n",launcher)
 def test_analysis_parses_stdout_without_cli_diagnostics(self):
  result=mock.Mock(returncode=0,stdout='{"result":true}',stderr='Codex diagnostic\n')
  with mock.patch.object(analysis,"command",return_value=["codex"]),mock.patch.object(analysis.subprocess,"run",return_value=result):
   state,output=analysis._run("codex","scan",{},pathlib.Path("/tmp"))
  self.assertEqual(state,"OK");self.assertEqual(output,'{"result":true}')

if __name__=="__main__":unittest.main()
