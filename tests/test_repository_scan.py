import importlib.util
import hashlib
import pathlib
import unittest

ROOT=pathlib.Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location("repo_scan",ROOT/"control-plane/app/repo_scan.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class RepositoryScan(unittest.TestCase):
 def test_detects_stacks_tests_ci_and_hostile_instructions_without_content_execution(self):
  names=("pyproject.toml","package.json","go.mod","main.py","LICENSE","tests/test_app.py",
         ".forgejo/workflows/test.yml","README.md","AGENTS.md",".mcp.json",
         ".git/hooks/post-checkout","vendor/huge.js")
  entries=[{"type":"blob","path":p,"sha":f"{i:040x}"} for i,p in enumerate(names,1)]
  scan=mod.scan_tree(entries,"a"*40)
  self.assertEqual(scan["commit_sha"],"a"*40);self.assertEqual(scan["ignored"],2)
  self.assertEqual(scan["manifests"],["go.mod","package.json","pyproject.toml"])
  self.assertIn("tests/test_app.py",scan["tests"]);self.assertIn(".forgejo/workflows/test.yml",scan["ci"])
  self.assertEqual(scan["entrypoints"],["main.py"]);self.assertEqual(scan["licenses"],["LICENSE"])
  self.assertEqual(scan["untrusted_executable_instructions"],[".mcp.json","AGENTS.md"])
 def test_scan_is_deterministic_across_input_order(self):
  a=[{"type":"blob","path":"b.py","sha":"b"*40},{"type":"blob","path":"a.py","sha":"a"*40}]
  self.assertEqual(mod.scan_tree(a,"c"*40),mod.scan_tree(list(reversed(a)),"c"*40))
 def test_all_repository_fixtures_scan_as_data(self):
  root=ROOT/"tests/fixtures/repositories"
  self.assertEqual({p.name for p in root.iterdir()},
      {"python","node","go","monorepo","no-tests","large-vendor","malicious"})
  for fixture in root.iterdir():
   entries=[]
   for path in fixture.rglob("*"):
    if path.is_file():
     rel=path.relative_to(fixture).as_posix()
     entries.append({"type":"blob","path":rel,"sha":hashlib.sha1(path.read_bytes()).hexdigest()})
   scan=mod.scan_tree(entries,"d"*40)
   self.assertEqual(scan["commit_sha"],"d"*40)
  # Directly scan the malicious fixture so its instructions remain inert metadata.
  entries=[{"type":"blob","path":p.relative_to(root/"malicious").as_posix(),
            "sha":hashlib.sha1(p.read_bytes()).hexdigest()}
           for p in (root/"malicious").rglob("*") if p.is_file()]
  hostile=mod.scan_tree(entries,"d"*40)
  self.assertEqual(hostile["untrusted_executable_instructions"],[".mcp.json","AGENTS.md"])

if __name__=="__main__":unittest.main()
