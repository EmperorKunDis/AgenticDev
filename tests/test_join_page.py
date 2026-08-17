import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class JoinPage(unittest.TestCase):
    def test_commands_have_accessible_copy_controls_and_fallback(self):
        page = (ROOT / "control-plane/app/join.html").read_text()
        self.assertEqual(page.count('class="copy" type="button"'), 2)
        self.assertEqual(page.count('aria-label="Kopírovat příkaz"'), 2)
        self.assertIn("navigator.clipboard && window.isSecureContext", page)
        self.assertIn("document.execCommand('copy')", page)
        self.assertIn("label.textContent = 'Zkopírováno'", page)
