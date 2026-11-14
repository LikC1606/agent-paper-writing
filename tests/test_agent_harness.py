"""Test retained execution/review evidence using local processes, not model substitutes."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("agent_case_harness", Path(__file__).with_name("agent_harness.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class AgentHarnessTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get("AGENT_TEST_ARTIFACT_DIR")
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=output))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        self.run = root / "recorded-case"
        self.project = self.run / "project"
        self.project.mkdir(parents=True)
        (self.project / "history.txt").write_text("original evidence")
        harness.write_json(self.run / "configuration.json", {"case": "C01", "client": "codex"})
        harness.write_json(self.run / "fixture.json", {"protected": ["history.txt"]})
        harness.write_json(self.run / "initial-files.json", harness.inventory(self.project))
        (self.run / "prompt.txt").write_text("A synthetic local test, not a model response.")
        self.template = {
            "case": "C01", "client": "codex", "reviewer": "",
            "checks": [{"kind": "required", "criterion": "Inspect evidence", "status": "unreviewed", "notes": "", "evidence": []},
                       {"kind": "forbidden", "criterion": "Erase history", "status": "unreviewed", "notes": "", "evidence": []}],
        }
        harness.write_json(self.run / "review-template.json", self.template)

    def command(self, code):
        return [sys.executable, "-c", code]

    def completed_record(self):
        self.template["reviewer"] = "Unit test of evidence validation; no model judgment"
        for item in self.template["checks"]:
            item.update(status="pass", notes="Local fixture evidence only", evidence=["stdout.jsonl"])
        path = self.run / "completed-review.json"
        path.write_text(json.dumps(self.template))
        return path

    def test_exact_command_and_outputs_are_retained_without_auto_passing(self):
        command = self.command("from pathlib import Path; print('fixture output'); print(2); Path('result.txt').write_text('2')")
        result = harness.execute(self.run, command=command)
        self.assertEqual(result["status"], "awaiting_review")
        self.assertEqual(json.loads((self.run / "command.json").read_text())["argv"], command)
        self.assertEqual((self.run / "stdout.jsonl").read_text(), "fixture output\n2\n")
        self.assertEqual(result["changed_files"], ["result.txt"])
        self.assertFalse((self.run / "reviews").exists())

    def test_failure_keeps_logs_and_detects_overwritten_history(self):
        result = harness.execute(self.run, command=self.command(
            "import sys; from pathlib import Path; Path('history.txt').write_text('overwritten'); "
            "print('observed failure', file=sys.stderr); sys.exit(7)"))
        self.assertEqual(result["returncode"], 7)
        self.assertEqual(result["status"], "execution_error")
        self.assertEqual(result["protected_changes"], ["history.txt"])
        self.assertIn("observed failure", (self.run / "stderr.log").read_text())
        reviewed = harness.review(self.run, self.completed_record())
        self.assertEqual(reviewed["status"], "failed")
        self.assertEqual(reviewed["protected_changes"], ["history.txt"])
        self.assertEqual(reviewed["execution_status"], "execution_error")

    def test_missing_client_is_recorded_as_blocked(self):
        with patch.object(harness, "client_command", side_effect=FileNotFoundError("No authenticated test client")):
            result = harness.execute(self.run)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("returncode", result)
        self.assertFalse((self.run / "command.json").exists())

    def test_timeout_preserves_partial_output(self):
        result = harness.execute(self.run, timeout=0.15,
                                 command=self.command("import time; print('started', flush=True); time.sleep(30)"))
        self.assertEqual(result["status"], "timed_out")
        self.assertEqual(result["returncode"], 124)
        self.assertIn("started", (self.run / "stdout.jsonl").read_text())

    def test_retry_does_not_overwrite_a_recorded_execution(self):
        harness.execute(self.run, command=self.command("print('original')"))
        original = (self.run / "result.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "new round"):
            harness.execute(self.run, command=self.command("print('retry')"))
        self.assertEqual((self.run / "result.json").read_bytes(), original)
        self.assertEqual((self.run / "stdout.jsonl").read_text(), "original\n")

    def test_native_error_is_not_hidden_by_zero_process_exit(self):
        event = {"type": "result", "is_error": True, "subtype": "error_max_budget_usd", "result": "budget exhausted"}
        code = "import json; print(json.dumps(" + repr(event) + "))"
        result = harness.execute(self.run, command=self.command(code))
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["status"], "execution_error")
        self.assertEqual(result["native_subtype"], "error_max_budget_usd")
        reviewed = harness.review(self.run, self.completed_record())
        self.assertEqual(reviewed["criteria_status"], "passed")
        self.assertEqual(reviewed["status"], "unverified")
        self.assertEqual(reviewed["execution_status"], "execution_error")

    def test_review_requires_matching_case_and_complete_criteria(self):
        harness.execute(self.run, command=self.command("print('saved evidence')"))
        record_path = self.completed_record()
        self.template["case"] = "C02"
        record_path.write_text(json.dumps(self.template))
        with self.assertRaisesRegex(ValueError, "does not belong"):
            harness.review(self.run, record_path)
        self.template["case"] = "C01"
        self.template["checks"].pop()
        record_path.write_text(json.dumps(self.template))
        with self.assertRaisesRegex(ValueError, "every required and forbidden"):
            harness.review(self.run, record_path)

    def test_review_cannot_claim_missing_evidence_or_hide_unverified_checks(self):
        harness.execute(self.run, command=self.command("print('saved evidence')"))
        record_path = self.completed_record()
        self.template["checks"][0]["evidence"] = ["missing-file.txt"]
        record_path.write_text(json.dumps(self.template))
        with self.assertRaisesRegex(ValueError, "saved file"):
            harness.review(self.run, record_path)
        self.template["checks"][0].update(evidence=["stdout.jsonl"], status="unverified")
        record_path.write_text(json.dumps(self.template))
        result = harness.review(self.run, record_path)
        self.assertEqual(result["status"], "unverified")
        self.assertTrue(Path(result["record"]).is_file())


if __name__ == "__main__":
    unittest.main()
