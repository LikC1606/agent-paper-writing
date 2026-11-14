"""Behavioral tests of isolated builds and explicit review records; no production access."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "paper.py"
CHECKS = ("size", "placement", "font", "whitespace", "alignment", "readability", "argument")


class PaperFlowTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get("PAPER_TEST_ARTIFACT_DIR")
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=output))
        else:
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
        command = [sys.executable, str(SCRIPT), *map(str, arguments)]
        process = subprocess.run(command,
                                 capture_output=True, text=True, check=False)
        with (self.root / "cli-calls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"argv": command, "returncode": process.returncode,
                                     "stdout": process.stdout, "stderr": process.stderr}) + "\n")
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

    def test_review_of_previous_pdf_is_rejected_for_new_revision(self):
        # P11/P12: a review of one PDF must never authorize a different revision's PDF.
        source_pdf = (
            "import pathlib,sys; "
            "pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-' + pathlib.Path('main.tex').read_bytes())"
        )
        _, first = self.build(source_pdf)
        old_revision = Path(first["revision"])
        record_path, _ = self.completed_record(old_revision)
        code, old_review = self.invoke("review", "--revision", old_revision, "--record", record_path)
        self.assertEqual(code, 0, old_review)
        original_review = Path(old_review["record"]).read_bytes()
        (self.project / "main.tex").write_text("revised evidence and figure", encoding="utf-8")
        _, second = self.build(source_pdf)
        new_revision = Path(second["revision"])
        self.assertNotEqual(Path(first["pdf"]).read_bytes(), Path(second["pdf"]).read_bytes())

        code, rejected = self.invoke("review", "--revision", new_revision, "--record", record_path)

        self.assertEqual(code, 1)
        self.assertIn("哈希不一致", rejected["error"])
        self.assertFalse((new_revision / "reviews").exists())
        self.assertEqual(Path(old_review["record"]).read_bytes(), original_review)
        code, current = self.invoke("status", "--revision", new_revision)
        self.assertEqual(code, 0, current)
        self.assertEqual(current["status"], "awaiting_visual_review")

    def test_previous_pass_does_not_carry_over_to_new_build(self):
        # P11/P12: even byte-identical rebuilds start with a new, unreviewed record.
        _, first = self.build()
        previous = Path(first["revision"])
        record_path, _ = self.completed_record(previous)
        code, review = self.invoke("review", "--revision", previous, "--record", record_path)
        self.assertEqual(code, 0, review)
        _, second = self.build()
        current = Path(second["revision"])

        code, result = self.invoke("status", "--revision", current)

        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "awaiting_visual_review")
        self.assertFalse((current / "reviews").exists())
        template = json.loads((current / "review-template.json").read_text())
        self.assertTrue(all(item["status"] == "unreviewed" for item in template["pages"]))
        events = [json.loads(line) for line in (current / "events.jsonl").read_text().splitlines()]
        self.assertFalse(any(item["phase"] == "visual_review" for item in events))
        self.assertTrue(Path(review["record"]).is_file())

    def test_identical_pdf_cannot_reuse_a_previous_revisions_review(self):
        # P11/P12: identical bytes do not remove the requirement to review this round.
        _, first = self.build()
        old_revision = Path(first["revision"])
        old_record, _ = self.completed_record(old_revision)
        code, saved = self.invoke("review", "--revision", old_revision, "--record", old_record)
        self.assertEqual(code, 0, saved)
        original_review = Path(saved["record"]).read_bytes()
        _, second = self.build()
        new_revision = Path(second["revision"])
        self.assertNotEqual(old_revision.name, new_revision.name)
        self.assertEqual(Path(first["pdf"]).read_bytes(), Path(second["pdf"]).read_bytes())

        code, rejected = self.invoke("review", "--revision", new_revision, "--record", old_record)

        self.assertEqual(code, 1, rejected)
        self.assertIn("轮次", rejected["error"])
        self.assertFalse((new_revision / "reviews").exists())
        code, current = self.invoke("status", "--revision", new_revision)
        self.assertEqual(code, 0, current)
        self.assertEqual(current["status"], "awaiting_visual_review")
        self.assertEqual(Path(saved["record"]).read_bytes(), original_review)

    def test_legacy_status_is_readable_but_missing_identity_records_are_rejected(self):
        # P11/P12: preserve old archives without accepting identity-free forms again.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, old_record = self.completed_record(revision)
        old_record.pop("revision_id", None)
        record_path.write_text(json.dumps(old_record), encoding="utf-8")
        template_path = revision / "review-template.json"
        old_template = json.loads(template_path.read_text())
        old_template.pop("revision_id", None)
        template_path.write_text(json.dumps(old_template), encoding="utf-8")
        reviews = revision / "reviews"
        reviews.mkdir()
        archived_review = reviews / "legacy-review.json"
        archived_review.write_text(json.dumps({
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "status": "visual_review_passed", "review": old_record,
        }), encoding="utf-8")
        original_files = {path.relative_to(revision): path.read_bytes()
                          for path in revision.rglob("*") if path.is_file()}

        code, archived_status = self.invoke("status", "--revision", revision)

        self.assertEqual(code, 0, archived_status)
        self.assertEqual(archived_status["status"], "visual_review_passed")
        self.assertEqual(archived_status["review"], str(archived_review))
        for legacy_form in (record_path, template_path):
            with self.subTest(form=legacy_form.name):
                code, rejected = self.invoke("review", "--revision", revision, "--record", legacy_form)
                self.assertEqual(code, 1, rejected)
                self.assertIn("revision_id", rejected["error"])
                self.assertIn("新建轮次", rejected["error"])
        self.assertEqual({path.relative_to(revision): path.read_bytes()
                          for path in revision.rglob("*") if path.is_file()}, original_files)

    def test_changed_page_invalidates_saved_review_and_rejects_new_record(self):
        # P09/P12: a checked image's contents are part of the inspected artifact.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, _ = self.completed_record(revision)
        _, saved = self.invoke("review", "--revision", revision, "--record", record_path)
        saved_bytes = Path(saved["record"]).read_bytes()
        Path(result["pages"][1]).write_bytes(b"changed figure alignment")

        for command in ("status", "review"):
            with self.subTest(command=command):
                arguments = [command, "--revision", revision]
                if command == "review":
                    arguments += ["--record", record_path]
                code, rejected = self.invoke(*arguments)
                self.assertEqual(code, 1)
                self.assertIn("页面图片已改变", rejected["error"])
        self.assertEqual(len(list((revision / "reviews").glob("*.json"))), 1)
        self.assertEqual(Path(saved["record"]).read_bytes(), saved_bytes)

    def test_deleted_page_invalidates_saved_review(self):
        # P09/P12: a missing checked page is an error, never a previous visual pass.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, _ = self.completed_record(revision)
        _, saved = self.invoke("review", "--revision", revision, "--record", record_path)
        missing_page = Path(result["pages"][0])
        missing_page.unlink()

        code, rejected = self.invoke("status", "--revision", revision)

        self.assertEqual(code, 1)
        self.assertEqual(rejected["status"], "error")
        self.assertIn(missing_page.name, rejected["error"])
        code, rejected = self.invoke("review", "--revision", revision, "--record", record_path)
        self.assertEqual(code, 1)
        self.assertEqual(len(list((revision / "reviews").glob("*.json"))), 1)
        self.assertTrue(Path(saved["record"]).is_file())

    def test_duplicate_review_page_cannot_hide_an_unreviewed_page(self):
        # P09/P12: an equal-sized list with a duplicate does not cover all pages.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, record = self.completed_record(revision)
        record["pages"][1] = record["pages"][0].copy()
        record_path.write_text(json.dumps(record), encoding="utf-8")

        code, rejected = self.invoke("review", "--revision", revision, "--record", record_path)

        self.assertEqual(code, 1)
        self.assertIn("重复页面", rejected["error"])
        self.assertFalse((revision / "reviews").exists())

    def test_unknown_review_page_cannot_substitute_for_a_rendered_page(self):
        # P09/P12: a record for a page outside this build cannot fill its coverage gap.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, record = self.completed_record(revision)
        record["pages"][1]["page"] = "page-999.png"
        record_path.write_text(json.dumps(record), encoding="utf-8")

        code, rejected = self.invoke("review", "--revision", revision, "--record", record_path)

        self.assertEqual(code, 1)
        self.assertIn("未知页面", rejected["error"])
        self.assertFalse((revision / "reviews").exists())

    def test_failed_check_cannot_be_recorded_as_visual_pass(self):
        # P09/P12: one failed layout check blocks the entire purported passing review.
        _, result = self.build()
        revision = Path(result["revision"])
        record_path, record = self.completed_record(revision)
        record["pages"][1]["checks"]["readability"] = False
        record["pages"][1]["findings"] = "Fixture caption is too small; needs a new build."
        record_path.write_text(json.dumps(record), encoding="utf-8")

        code, rejected = self.invoke("review", "--revision", revision, "--record", record_path)

        self.assertEqual(code, 1)
        self.assertIn("status 必须与实际检查项一致：fail", rejected["error"])
        self.assertFalse((revision / "reviews").exists())
        events = [json.loads(line) for line in (revision / "events.jsonl").read_text().splitlines()]
        self.assertFalse(any(item["phase"] == "visual_review" for item in events))

    def test_compile_failure_never_renders_a_partial_pdf(self):
        # P12: a compiler may leave a PDF before failing; it is not a valid render input.
        code, failed = self.build(
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-partial'); "
            "print('fixture failed after writing a partial PDF'); sys.exit(7)"
        )
        revision = Path(failed["revision"])

        self.assertEqual(code, 1)
        self.assertEqual(failed["phase"], "compile")
        self.assertEqual((revision / "build/main.pdf").read_bytes(), b"%PDF-partial")
        self.assertIn("failed after writing", (revision / "compile-1.log").read_text())
        commands = [json.loads(line) for line in (revision / "commands.jsonl").read_text().splitlines()]
        self.assertEqual([item["label"] for item in commands], ["compile-1"])
        self.assertFalse((revision / "render.log").exists())
        self.assertEqual(list((revision / "pages").iterdir()), [])
        self.assertFalse((revision / "review-template.json").exists())

    def test_second_engine_pass_failure_preserves_both_stage_logs(self):
        # P11/P12: exercise the two-pass engine path; a failed later pass stays failed.
        tools = self.root / "engine tools"
        tools.mkdir()
        engine = tools / "pdflatex"
        engine.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            "import sys\n"
            "if '--version' in sys.argv:\n"
            "    print('fixture engine, not a real LaTeX result')\n"
            "    raise SystemExit(0)\n"
            "output = Path(next(a.split('=', 1)[1] for a in sys.argv if a.startswith('-output-directory=')))\n"
            "counter = output / 'passes.txt'\n"
            "number = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "counter.write_text(str(number))\n"
            "print('fixture compile pass ' + str(number))\n"
            "if number == 1:\n"
            "    (output / 'main.pdf').write_bytes(b'%PDF-first-pass-only')\n"
            "raise SystemExit(9 if number == 2 else 0)\n",
            encoding="utf-8",
        )
        engine.chmod(0o755)

        code, failed = self.invoke("build", "--project", self.project, "--engine", engine,
                                   "--renderer", self.renderer)

        revision = Path(failed["revision"])
        self.assertEqual(code, 1)
        self.assertIn("compile-2.log", failed["error"])
        self.assertIn("pass 1", (revision / "compile-1.log").read_text())
        self.assertIn("pass 2", (revision / "compile-2.log").read_text())
        self.assertEqual((revision / "build/main.pdf").read_bytes(), b"%PDF-first-pass-only")
        commands = [json.loads(line) for line in (revision / "commands.jsonl").read_text().splitlines()]
        self.assertEqual([item["label"] for item in commands], ["compiler-version", "compile-1", "compile-2"])
        self.assertEqual([item["returncode"] for item in commands], [0, 0, 9])
        self.assertFalse((revision / "render.log").exists())
        self.assertFalse((revision / "review-template.json").exists())

    def test_existing_build_script_replays_from_snapshot_with_spaces_in_paths(self):
        # P11/P12: reuse a project's build script and inputs; its archived call is reproducible.
        project = self.root / "paper project with spaces"
        self.project.rename(project)
        self.project = project
        (project / "chapters").mkdir()
        source = project / "chapters/paper draft.tex"
        source.write_text("archived findings", encoding="utf-8")
        (project / "tables").mkdir()
        table = project / "tables/result values.csv"
        table.write_text("method,value\nexample,2\n", encoding="utf-8")
        (project / "build scripts").mkdir()
        script = project / "build scripts/existing paper.py"
        script.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "source, output = map(Path, sys.argv[1:])\n"
            "data = Path('tables/result values.csv').read_bytes()\n"
            "(output / 'paper draft.pdf').write_bytes(b'%PDF-' + source.read_bytes() + data)\n"
            "print('existing build reused in ' + str(Path.cwd()))\n",
            encoding="utf-8",
        )
        renderer = self.root / "render tool with spaces"
        self.renderer.rename(renderer)
        output_root = self.root / "archived revisions with spaces"

        code, result = self.invoke(
            "build", "--project", project, "--source", "chapters/paper draft.tex",
            "--output-root", output_root, "--renderer", renderer,
            "--", sys.executable, "build scripts/existing paper.py", "{source}", "{output}",
        )

        self.assertEqual(code, 0, result)
        revision = Path(result["revision"])
        expected_pdf = b"%PDF-archived findingsmethod,value\nexample,2\n"
        self.assertEqual(Path(result["pdf"]).read_bytes(), expected_pdf)
        self.assertEqual((revision / "source/chapters/paper draft.tex").read_text(), "archived findings")
        self.assertTrue((revision / "source/build scripts/existing paper.py").is_file())
        self.assertFalse((project / "paper draft.pdf").exists())
        source.write_text("new findings", encoding="utf-8")
        table.write_text("new data", encoding="utf-8")
        commands = [json.loads(line) for line in (revision / "commands.jsonl").read_text().splitlines()]
        replay_output = self.root / "replayed build with spaces"
        replay_output.mkdir()
        replay_command = commands[0]["argv"][:-1] + [str(replay_output)]
        with (self.root / "replay.log").open("wb") as log:
            replay = subprocess.run(replay_command, cwd=commands[0]["cwd"],
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(replay.returncode, 0)
        self.assertEqual((replay_output / "paper draft.pdf").read_bytes(), expected_pdf)


if __name__ == "__main__":
    unittest.main()
