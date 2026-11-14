"""Check task materials and actual toy data, without evaluating an agent."""

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from agent_projects import prepare_case, ROOT


class PaperAgentProjectFixturesTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get("PAPER_TEST_ARTIFACT_DIR")
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=output))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)

    def prepare(self, case_id):
        project = self.root / case_id
        project.mkdir()
        record = prepare_case(case_id, project, sys.executable)
        # Checker metadata remains a sibling of the project, never an agent input.
        (self.root / (case_id + "-checker.json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return project, record

    def test_thirteen_cases_have_real_inputs_without_exposing_judge_rubrics(self):
        cases = json.loads((ROOT / "tests/fixtures/requirements.json").read_text())["cases"]
        self.assertEqual(len(cases), 13)
        for case in cases:
            with self.subTest(case=case["id"]):
                project, record = self.prepare(case["id"])
                self.assertTrue(record["prompt"].startswith(case["prompt"]))
                self.assertIn(r"\documentclass", (project / "main.tex").read_text())
                self.assertIn("synthetic toy", (project / "README.md").read_text())
                self.assertEqual(record["facts"]["expected_agent_result"], "unverified")
                for relative in record["protected"]:
                    path = project / relative
                    self.assertFalse(Path(relative).is_absolute())
                    self.assertTrue(path.resolve().is_relative_to(project))
                    self.assertTrue(path.is_file(), relative)
                text = "\n".join(path.read_text(encoding="utf-8") for path in project.rglob("*")
                                 if path.is_file() and path.suffix in {".md", ".json", ".tex"})
                self.assertNotIn('"pass_if"', text)
                self.assertNotIn('"fail_if"', text)
                self.assertNotIn('"expected_agent_result"', text)

    def test_three_experiments_match_raw_toy_data_and_keep_ablation_unrun(self):
        project, record = self.prepare("P06")
        values = json.loads((project / "results/accuracy.json").read_text())
        indexed = {(row["dataset"], row["method"]): row for row in values}
        self.assertEqual(indexed[("toy-A", "score_filter")]["accuracy"], 0.8)
        self.assertEqual(indexed[("toy-B", "score_filter")]["accuracy"], 0.7)
        self.assertEqual(indexed[("toy-A", "budget_matched")]["accuracy"], 0.7)
        for filename in ["observations.csv", "control.csv"]:
            with (project / "data" / filename).open(newline="") as stream:
                for row in csv.DictReader(stream):
                    actual = indexed[(row["dataset"], row["method"])]
                    self.assertEqual(actual["accuracy"], int(row["correct"]) / int(row["total"]))
        correlation = json.loads((project / "results/correlation.json").read_text())
        self.assertEqual(correlation, {"n": 4, "pearson_r": 0.8, "assignment": "observational"})
        with (project / "results/timing.csv").open(newline="") as stream:
            timing = list(csv.DictReader(stream))
        self.assertEqual(len(timing), 30)
        self.assertTrue(all(int(row["elapsed_ns"]) > 0 for row in timing))
        self.assertFalse(record["facts"]["ablation_executed"])
        self.assertFalse((project / "results/ablation.json").exists())
        call = json.loads((project / "results/analysis-command.json").read_text())
        self.assertEqual(call["argv"][0], sys.executable)
        self.assertEqual(call["returncode"], 0)

    def test_p09_plot_source_regenerates_original_bytes_and_drives_font_output(self):
        project, record = self.prepare("P09")
        original = (project / "figures/quality-plot.pdf").read_bytes()
        command = json.loads((project / "plot-command.json").read_text())
        self.assertEqual(command[0], sys.executable)
        result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        regenerated = project / "figures/quality-plot-working.pdf"
        self.assertEqual(regenerated.read_bytes(), original)
        source = json.loads((project / record["facts"]["plot_source"]).read_text())
        source["labels"][2]["size"] += 1
        changed_source = project / "figures/font-probe-source.json"
        changed_source.write_text(json.dumps(source), encoding="utf-8")
        changed_command = command[:2] + ["--source", str(changed_source), "--output", "figures/font-probe.pdf"]
        changed = subprocess.run(changed_command, cwd=project, capture_output=True, text=True, timeout=10)
        self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
        self.assertNotEqual((project / "figures/font-probe.pdf").read_bytes(), original)
        self.assertEqual((project / "figures/quality-plot.pdf").read_bytes(), original)
        (self.root / "P09-plot-regeneration.json").write_text(json.dumps({
            "argv": command, "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "byte_difference_count": 0,
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "regenerated_sha256": hashlib.sha256(regenerated.read_bytes()).hexdigest(),
            "font_probe_argv": changed_command, "font_probe_returncode": changed.returncode,
        }, indent=2), encoding="utf-8")

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftoppm"), "Real build needs LaTeX and Poppler")
    def test_p12_has_a_real_archived_build_without_a_fabricated_visual_pass(self):
        project, record = self.prepare("P12")
        baseline = record["facts"]["baseline"]
        self.assertEqual(baseline["status"], "awaiting_visual_review")
        self.assertFalse(baseline["visual_review_performed"])
        revision = project / baseline["revision"]
        self.assertTrue((project / "history/round-01/main.pdf").read_bytes().startswith(b"%PDF-"))
        review = json.loads((project / "history/round-01/review-unfilled.json").read_text())
        self.assertEqual(review["reviewer"], "")
        self.assertTrue(all(page["status"] == "unreviewed" for page in review["pages"]))
        self.assertFalse((revision / "reviews").exists())
        self.assertNotEqual((project / "main.tex").read_bytes(), (project / "history/round-01/main.tex").read_bytes())
        self.assertIn((revision / "render-manifest.json").relative_to(project).as_posix(), record["protected"])

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftoppm"), "Real build needs LaTeX and Poppler")
    def test_representative_drafts_compile_and_keep_their_original_inputs(self):
        for case in ["P01", "P03", "P09", "P10"]:
            with self.subTest(case=case):
                project, record = self.prepare(case)
                initial = {relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
                           for relative in record["protected"]}
                command = [sys.executable, str(project / "tools/paper.py"), "build", "--project", str(project),
                           "--engine", shutil.which("pdflatex"), "--renderer", shutil.which("pdftoppm")]
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                (self.root / (case + "-build-call.json")).write_text(json.dumps({
                    "argv": command, "returncode": result.returncode, "stdout": result.stdout,
                    "stderr": result.stderr}, indent=2), encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "awaiting_visual_review")
                self.assertEqual(initial, {relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
                                           for relative in record["protected"]})


if __name__ == "__main__":
    unittest.main()
