import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class DeveloperSettings(unittest.TestCase):
    def test_github_device_flow_keeps_tokens_server_side_and_encrypted(self):
        backend = (ROOT / "control-plane/app/developer_settings.py").read_text()
        dashboard = (ROOT / "control-plane/app/dashboard.html").read_text()
        self.assertIn("https://github.com/login/device/code", backend)
        self.assertIn("AESGCM(_KEY).encrypt", backend)
        self.assertNotIn("token_encrypted", dashboard)
        self.assertNotIn("access_token", dashboard)

    def test_multiple_github_identities_and_environment_inventory_are_exposed(self):
        backend = (ROOT / "control-plane/app/developer_settings.py").read_text()
        self.assertIn('github_identity ORDER BY is_default DESC', backend)
        for name in ('"harness"', '"agents"', '"skills"', '"hooks"', '"scripts"', '"instructions"'):
            self.assertIn(name, backend)

    def test_environment_files_include_bounded_safe_text_metadata(self):
        backend = (ROOT / "control-plane/app/developer_settings.py").read_text()
        for field in ('"path"', '"language"', '"size_bytes"', '"lines"',
                      '"sha256"', '"content"', '"truncated"'):
            self.assertIn(field, backend)
        self.assertIn("TEXT_PREVIEW_LIMIT", backend)
        self.assertIn('if b"\\0" in raw[:8192]', backend)
        self.assertNotIn('str(path.resolve())', backend)

    def test_dashboard_gives_work_and_environment_information_proportional_space(self):
        dashboard = (ROOT / "control-plane/app/dashboard.html").read_text()
        self.assertNotIn('data-t="rozhodnuti"', dashboard)
        self.assertIn('data-t="prace"', dashboard)
        self.assertIn('data-t="prostredi"', dashboard)
        self.assertIn('class="dashboard-layout"', dashboard)
        for surface in ("harness", "agents", "skills", "hooks", "scripts", "instructions"):
            self.assertIn(f"{surface}:", dashboard)
        self.assertIn('class="file-view"', dashboard)
        self.assertIn("esc(selected.content)", dashboard)

    def test_subscription_mode_has_no_cash_fields_in_active_contracts(self):
        active = "\n".join((ROOT / path).read_text() for path in (
            "control-plane/app/main.py", "control-plane/app/admin.py",
            "control-plane/app/dashboard.html", "vps/sql/001_schema.sql"))
        for field in ("budget_czk", "cost_czk", "eval_cost_czk", "spend_measured"):
            self.assertNotIn(field, active)


if __name__ == "__main__":
    unittest.main()
