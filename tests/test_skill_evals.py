import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parents[1]
SKILLS = ROOT / "workspace/_base/.agenticdev/skills"


class CuratedSkillEvals(unittest.TestCase):
    """Deterministic safety/trigger evals; model quality evals belong to live acceptance."""

    def setUp(self):
        self.skills = {p.parent.name: p.read_text() for p in SKILLS.glob("*/SKILL.md")}

    def test_trigger_descriptions_are_specific_and_phase_bounded(self):
        expected = {
            "diagnosing-bugs": "defects", "tdd": "behavior changes",
            "codebase-design": "module interfaces", "code-review": "fixed diff",
            "research": "external facts", "writing-for-agents": "AGENTS",
            "domain-modeling": "bounded contexts",
        }
        self.assertEqual(set(expected), set(self.skills))
        for name, trigger in expected.items():
            header = self.skills[name].split("---", 2)[1]
            self.assertIn(trigger, header, name)

    def test_skills_contain_no_network_or_direct_git_mutation_commands(self):
        forbidden = re.compile(r"\b(curl|wget|git\s+(push|merge|rebase)|gh\s+pr)\b")
        for name, body in self.skills.items():
            self.assertIsNone(forbidden.search(body), name)

    def test_security_sensitive_output_requires_evidence_or_approval(self):
        self.assertIn("Cite every finding", self.skills["code-review"])
        self.assertIn("explicitly approved proposal PR", self.skills["domain-modeling"])
        self.assertIn("never authorize a security decision", self.skills["research"])
        self.assertIn("unrelated cleanup out of the diff", self.skills["tdd"])


if __name__ == "__main__":
    unittest.main()
