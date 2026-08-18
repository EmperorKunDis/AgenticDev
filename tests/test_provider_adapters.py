import importlib.util
import pathlib
import sys
import tempfile
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
  self.assertEqual(mod.classify_failure("OAuth access token has been revoked",1),"AUTH_REQUIRED")
  self.assertEqual(mod.classify_failure("usage limit reached",1),"RATE_LIMITED")
  self.assertEqual(mod.classify_failure("unexpected",1),"FAILED")
 def test_analysis_cli_is_read_only_and_ignores_project_rules(self):
  with mock.patch.object(mod.shutil,"which",return_value="/bin/codex"):
   cmd=mod.command("codex","scan",mode="analysis")
  for flag in ("--dangerously-bypass-approvals-and-sandbox","--ephemeral","--ignore-user-config","--ignore-rules"):
   self.assertIn(flag,cmd)
  self.assertEqual(cmd[cmd.index("--cd")+1],"/workspace")
  with mock.patch.object(mod.shutil,"which",return_value="/bin/claude"):
   cmd=mod.command("claude","scan",mode="analysis")
  self.assertEqual(cmd[cmd.index("--add-dir")+1],"/workspace")
 def test_no_cross_provider_fallback(self):
  with mock.patch.object(mod.shutil,"which",return_value=None):
   self.assertEqual(mod.command("claude","x"),[]);self.assertEqual(mod.command("codex","x"),[])
 def test_remote_codex_login_uses_device_flow(self):
  launcher=(ROOT/"launcher/agenticdev").read_text()
  self.assertIn("codex login --device-auth",launcher)
  self.assertIn("claude auth login --claudeai",launcher)
  self.assertNotIn("|| codex login\n",launcher)
  self.assertIn("provider_probe claude",launcher);self.assertIn("provider_probe codex",launcher)
  self.assertLess(launcher.index("provider_probe claude"),launcher.index('/v1/provider-profile'))
 def test_analysis_parses_stdout_without_cli_diagnostics(self):
  result=mock.Mock(returncode=0,stdout='{"result":true}',stderr='Codex diagnostic\n')
  with mock.patch.object(analysis,"command",return_value=["codex"]),mock.patch.object(analysis.subprocess,"run",return_value=result):
   state,output=analysis._run("codex","scan",{},pathlib.Path("/tmp"))
  self.assertEqual(state,"OK");self.assertEqual(output,'{"result":true}')
 def test_analysis_rejects_provider_workspace_questions(self):
  questions=[{"id":"access","question":"Can read-only access to /workspace be restored?"}]
  self.assertTrue(analysis._has_workspace_question(questions))
  self.assertFalse(analysis._has_workspace_question([{"id":"product","question":"Which users need access?"}]))
 def test_analysis_preflight_verifies_requested_commit(self):
  completed=mock.Mock(stdout="a"*40+"\n")
  with tempfile.TemporaryDirectory() as root, \
       mock.patch.object(analysis,"WORKSPACE",pathlib.Path(root)), \
       mock.patch.object(analysis,"REQUEST",pathlib.Path(root)/"request.json"), \
       mock.patch.object(analysis.subprocess,"run",return_value=completed) as run:
   analysis.REQUEST.touch()
   self.assertIsNone(analysis._preflight({"commit_sha":"a"*40}))
   run.assert_called_once_with(["git","-C",root,"rev-parse","HEAD"],capture_output=True,text=True,timeout=10,check=True)
 def test_failed_analysis_is_reported_and_launcher_stops_before_review(self):
  with mock.patch.object(analysis,"_post") as post:
   self.assertEqual(analysis._fail({"project":"p"},"FAILED"," provider failed \n"),"FAILED")
  post.assert_called_once_with({"project":"p"},"failure",{"code":"FAILED","detail":"provider failed"})
  launcher=(ROOT/"launcher/agenticdev").read_text()
  self.assertLess(launcher.index('failed)'),launcher.index('Otevírám výsledek analýzy'))
  self.assertIn("Broker rejected workload: $broker_reason",launcher)
  self.assertIn('return "$outcome_status"',launcher)

if __name__=="__main__":unittest.main()
