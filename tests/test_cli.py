import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from llm_shield.claude_hook import pre_tool_use, session_end
from llm_shield.cli import main
from llm_shield.config import install_claude_hook


class CliTests(unittest.TestCase):
    def setUp(self):
        self.previous_directory = Path.cwd()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.temporary_directory.cleanup()

    def _init_with_terms(self, terms):
        self.assertEqual(main(["init"], stdout=io.StringIO(), stderr=io.StringIO()), 0)
        self.assertIn(".llm-shield/", (self.root / ".gitignore").read_text(encoding="utf-8"))
        (self.root / ".llm-shield.yml").write_text(
            f'version: "1.0"\nterms: {json.dumps(terms)}\npatterns: []\n'
            'options:\n  placeholder_prefix: "REDACTED_"\n  cache_dir: ".llm-shield"\n',
            encoding="utf-8",
        )

    def test_init_scrub_restore_round_trip(self):
        self._init_with_terms(["Secret Name"])
        original = "Hello Secret Name!"
        scrubbed = io.StringIO()
        scrub_stderr = io.StringIO()
        self.assertEqual(
            main(["scrub"], stdin=io.StringIO(original), stdout=scrubbed, stderr=scrub_stderr),
            0,
        )
        session_id = scrub_stderr.getvalue().strip().split()[-1]
        self.assertEqual(scrubbed.getvalue(), "Hello REDACTED_0!")

        returned = io.StringIO()
        self.assertEqual(
            main(
                ["restore", "--session", session_id],
                stdin=io.StringIO(f"Answer: {scrubbed.getvalue()}"),
                stdout=returned,
                stderr=io.StringIO(),
            ),
            0,
        )
        self.assertEqual(returned.getvalue(), f"Answer: {original}")
        self.assertFalse(list((self.root / ".llm-shield").glob("session_*.json")))

    def test_scrub_can_read_literal_input_and_write_file(self):
        self._init_with_terms(["private"])
        destination = self.root / "scrubbed.txt"
        self.assertEqual(
            main(
                ["scrub", "--input", "private data", "--output", str(destination)],
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
            0,
        )
        self.assertEqual(destination.read_text(encoding="utf-8"), "REDACTED_0 data")
        session_files = list((self.root / ".llm-shield").glob("session_*.json"))
        self.assertEqual(len(session_files), 1)
        payload = json.loads(session_files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["mapping"], {"REDACTED_0": "private"})

    def test_wrap_scrubs_child_input_and_restores_child_output(self):
        self._init_with_terms(["private"])
        output = io.StringIO()
        error = io.StringIO()
        self.assertEqual(
            main(
                [
                    "wrap",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; data = sys.stdin.read(); "
                    "assert data == 'REDACTED_0 input'; "
                    "sys.stdout.write('Returned REDACTED_0 output')",
                ],
                stdin=io.StringIO("private input"),
                stdout=output,
                stderr=error,
            ),
            0,
        )
        self.assertEqual(output.getvalue(), "Returned private output")
        self.assertEqual(error.getvalue(), "")
        self.assertFalse(list((self.root / ".llm-shield").glob("session_*.json")))

    def test_claude_read_hook_redirects_to_anonymized_snapshot(self):
        self._init_with_terms(["private"])
        source = self.root / "source.py"
        source.write_text("token = 'private'\n", encoding="utf-8")
        payload = {
            "session_id": "claude-session-123",
            "cwd": str(self.root),
            "tool_name": "Read",
            "tool_input": {"file_path": str(source), "offset": 1},
        }

        first = pre_tool_use(payload)
        snapshot = Path(first["hookSpecificOutput"]["updatedInput"]["file_path"])
        self.assertEqual(snapshot.read_text(encoding="utf-8"), "token = 'REDACTED_0'\n")
        self.assertEqual(source.read_text(encoding="utf-8"), "token = 'private'\n")
        self.assertEqual(first["hookSpecificOutput"]["updatedInput"]["offset"], 1)

        second_source = self.root / "other.py"
        second_source.write_text("private again\n", encoding="utf-8")
        payload["tool_input"] = {"file_path": str(second_source)}
        second = pre_tool_use(payload)
        second_snapshot = Path(second["hookSpecificOutput"]["updatedInput"]["file_path"])
        self.assertEqual(second_snapshot.read_text(encoding="utf-8"), "REDACTED_0 again\n")

        session_end(payload)
        self.assertFalse(snapshot.parent.exists())
        self.assertFalse(list((self.root / ".llm-shield").glob("session_*.json")))

    def test_claude_read_hook_fails_closed_for_missing_files(self):
        self._init_with_terms(["private"])
        result = pre_tool_use(
            {
                "session_id": "claude-session-123",
                "cwd": str(self.root),
                "tool_name": "Read",
                "tool_input": {"file_path": str(self.root / "missing.py")},
            }
        )
        decision = result["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("could not anonymize", decision["permissionDecisionReason"])

    def test_claude_install_merges_project_settings_idempotently(self):
        settings_path = self.root / ".claude" / "settings.json"
        settings_path.parent.mkdir()
        settings_path.write_text('{"permissions": {"defaultMode": "acceptEdits"}}', encoding="utf-8")
        expected_path = settings_path.resolve()

        self.assertEqual(install_claude_hook(self.root), expected_path)
        self.assertEqual(install_claude_hook(self.root), expected_path)
        import json

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(settings["permissions"]["defaultMode"], "acceptEdits")
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["matcher"], "Read")
        self.assertIn("SessionEnd", settings["hooks"])
