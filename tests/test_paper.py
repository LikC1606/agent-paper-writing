"""Behavioral tests of isolated builds and explicit review records; no production access."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "paper.py"
CHECKS = ("size", "placement", "font", "whitespace", "alignment", "readability", "argument")


class PaperFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "paper"
        self.project.mkdir()
        (self.project / "main.tex").write_text("first revision", encoding="utf-8")
        (self.project / "figure.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        self.renderer = self.root / "render"
        self.renderer.write_text(
            f"#!{sys.executable}\n"
            "import pathlib, sys\n"
            "prefix = sys.argv[-1]\n"
            "for number in [1, 2]:\n"
            "    pathlib.Path(prefix + '-' + str(number) + '.png').write_bytes(b'unit-test-image')\n",
            encoding="utf-8",
        )
        self.renderer.chmod(0o755)

    def invoke(self, *arguments):
        process = subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                                 capture_output=True, text=True, check=False)
        self.assertTrue(process.stdout, process.stderr)
        return process.returncode, json.loads(process.stdout)

    def build(self, code=None):
        code = code or "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-unit-test')"
        return self.invoke("build", "--project", self.project, "--renderer", self.renderer,
                           "--", sys.executable, "-c", code, "{output}/main.pdf")

    def completed_record(self, revision):
        record = json.loads((revision / "review-template.json").read_text())
        record["reviewer"] = "Unit test record validator"
        for item in record["pages"]:
            item.update(status="pass", checks={name: True for name in CHECKS},
                        findings="Fixture observation for record validation; no real visual review claimed.")
        path = self.root / "review.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path, record

    def test_build_snapshots_inputs_and_leaves_visual_review_pending(self):
        code, result = self.build()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "awaiting_visual_review")
        revision = Path(result["revision"])
        self.assertEqual((revision / "source/main.tex").read_text(), "first revision")
        self.assertTrue((revision / "source/figure.csv").is_file())
        self.assertFalse((self.project / "main.pdf").exists())
        self.assertEqual(len(result["pages"]), 2)
        self.assertFalse((revision / "source/.paper-runs").exists())
        commands = [json.loads(line) for line in (revision / "commands.jsonl").read_text().splitlines()]
        self.assertEqual([item["label"] for item in commands], ["compile-1", "render"])
        self.assertEqual(commands[0]["cwd"], str(revision / "source"))
        self.assertFalse((revision / "reviews").exists())

    def test_failure_retains_evidence_and_retry_uses_new_revision(self):
        code, failure = self.build("import sys; print('intentional compile failure'); sys.exit(7)")
        self.assertEqual(code, 1)
        old = Path(failure["revision"])
        self.assertEqual(failure["phase"], "compile")
        self.assertIn("intentional compile failure", (old / "compile-1.log").read_text())
        original_result = (old / "result.json").read_bytes()
        (self.project / "main.tex").write_text("fixed revision", encoding="utf-8")
        code, success = self.build()
        self.assertEqual(code, 0, success)
        self.assertNotEqual(success["revision"], failure["revision"])
        self.assertEqual((old / "result.json").read_bytes(), original_result)
        self.assertEqual((old / "source/main.tex").read_text(), "first revision")
        self.assertEqual((Path(success["revision"]) / "source/main.tex").read_text(), "fixed revision")

    def test_snapshot_keeps_paper_inputs_without_experiment_history(self):
        history = self.project / "runs" / "old-experiment"
        history.mkdir(parents=True)
        (history / "checkpoint.bin").write_bytes(b"historical experiment output")
        figures = self.project / "figures"
        figures.mkdir()
        (figures / "result-table.csv").write_text("method,score\nexample,1\n")
        _, result = self.build()
        revision = Path(result["revision"])
        self.assertFalse((revision / "source/runs").exists())
        self.assertEqual((revision / "source/figures/result-table.csv").read_text(),
                         "method,score\nexample,1\n")
        self.assertTrue((history / "checkpoint.bin").is_file())
        self.assertIn("runs/", json.loads((revision / "source-state.json").read_text())["excluded"])

    def test_zero_exit_without_new_pdf_is_not_a_successful_build(self):
        (self.project / "main.pdf").write_bytes(b"old pdf")
        code, result = self.build("print('no output')")
        self.assertEqual(code, 1)
        self.assertEqual(result["phase"], "compile")
        self.assertIn("未生成", result["error"])

    def test_renderer_failure_preserves_compiled_pdf(self):
        self.renderer.write_text(f"#!{sys.executable}\nimport sys\nsys.exit(8)\n")
        code, result = self.build()
        self.assertEqual(code, 1)
        self.assertEqual(result["phase"], "render")
        self.assertTrue((Path(result["revision"]) / "build/main.pdf").is_file())
        self.assertFalse((Path(result["revision"]) / "review-template.json").exists())

    def test_unfilled_or_incomplete_reviews_are_rejected(self):
        _, result = self.build()
        revision = Path(result["revision"])
        code, error = self.invoke("review", "--revision", revision, "--record", revision / "review-template.json")
        self.assertEqual(code, 1)
        self.assertIn("reviewer", error["error"])
        path, record = self.completed_record(revision)
        record["pages"].pop()
        path.write_text(json.dumps(record))
        code, error = self.invoke("review", "--revision", revision, "--record", path)
        self.assertEqual(code, 1)
        self.assertIn("全部", error["error"])
        self.assertFalse((revision / "reviews").exists())

    def test_reviews_preserve_history_and_match_checked_artifacts(self):
        _, result = self.build()
        revision = Path(result["revision"])
        path, record = self.completed_record(revision)
        code, passed = self.invoke("review", "--revision", revision, "--record", path)
        self.assertEqual(code, 0, passed)
        first_record = Path(passed["record"]).read_bytes()
        record["pages"][0]["checks"]["alignment"] = False
        record["pages"][0]["status"] = "fail"
        record["pages"][0]["findings"] = "Fixture label overlaps the margin; repair in a new revision."
        path.write_text(json.dumps(record))
        code, failed = self.invoke("review", "--revision", revision, "--record", path)
        self.assertEqual(code, 1)
        self.assertEqual(failed["status"], "visual_review_failed")
        self.assertEqual(Path(passed["record"]).read_bytes(), first_record)
        self.assertEqual(len(list((revision / "reviews").glob("*.json"))), 2)
        code, current = self.invoke("status", "--revision", revision)
        self.assertEqual(current["status"], "visual_review_failed")
        (revision / "build/main.pdf").write_bytes(b"modified pdf")
        code, error = self.invoke("status", "--revision", revision)
        self.assertEqual(code, 1)
        self.assertIn("PDF 已改变", error["error"])

    def test_pass_needs_boolean_checks_and_concrete_findings(self):
        _, result = self.build()
        revision = Path(result["revision"])
        path, record = self.completed_record(revision)
        record["pages"][0]["checks"]["font"] = "true"
        path.write_text(json.dumps(record))
        code, error = self.invoke("review", "--revision", revision, "--record", path)
        self.assertEqual(code, 1)
        self.assertIn("true/false", error["error"])
        record["pages"][0]["checks"]["font"] = True
        record["pages"][0]["findings"] = ""
        path.write_text(json.dumps(record))
        code, error = self.invoke("review", "--revision", revision, "--record", path)
        self.assertEqual(code, 1)
        self.assertIn("实际查看", error["error"])


if __name__ == "__main__":
    unittest.main()
