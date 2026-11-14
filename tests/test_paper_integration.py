"""P09/P12: optional real build/render checks; they do not assess visual quality."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "paper.py"
PDFLATEX = shutil.which("pdflatex")
PDFTOPPM = shutil.which("pdftoppm")


@unittest.skipUnless(PDFLATEX and PDFTOPPM, "Real paper integration requires pdflatex and Poppler pdftoppm")
class RealPaperBuildTests(unittest.TestCase):
    def test_real_latex_and_poppler_leave_each_revision_awaiting_visual_review(self):
        # P09/P12: real PDF/pages establish a build, never an automatic visual pass.
        artifacts = os.environ.get("PAPER_TEST_ARTIFACT_DIR")
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix="real-paper-", dir=output))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        project = root / "paper source"
        project.mkdir()
        source = project / "main.tex"
        source.write_text(
            r"\documentclass{article}" "\n"
            r"\begin{document}" "\n"
            r"\section{Research question}" "\n"
            r"Does a compiled revision preserve evidence for a separate page review?" "\n"
            r"Table~\ref{tab:example} contains demonstration data only." "\n"
            r"\begin{table}[h]\centering" "\n"
            r"\begin{tabular}{lr}Example & Value\\ A & 2\\ B & 4\end{tabular}" "\n"
            r"\caption{Example values for a build check.}\label{tab:example}\end{table}" "\n"
            r"\newpage\section{Interpretation}" "\n"
            r"Compilation and rendering do not demonstrate that a person or agent inspected this page." "\n"
            r"\appendix\section{Details}This is a disposable integration example." "\n"
            r"\end{document}" "\n",
            encoding="utf-8",
        )
        command = [sys.executable, str(SCRIPT), "build", "--project", str(project),
                   "--engine", PDFLATEX, "--renderer", PDFTOPPM]
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        (root / "build-call.json").write_text(json.dumps({
            "argv": command, "returncode": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr,
        }, indent=2), encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "awaiting_visual_review")
        revision = Path(result["revision"])
        self.assertTrue(Path(result["pdf"]).read_bytes().startswith(b"%PDF-"))
        self.assertEqual(len(result["pages"]), 2)
        for image in result["pages"]:
            self.assertTrue(Path(image).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        commands = [json.loads(line) for line in (revision / "commands.jsonl").read_text().splitlines()]
        self.assertEqual([item["label"] for item in commands],
                         ["compiler-version", "compile-1", "compile-2", "render"])
        self.assertTrue(all(item["returncode"] == 0 for item in commands))
        self.assertNotIn("undefined references", (revision / "compile-2.log").read_text())
        self.assertFalse((project / "main.pdf").exists())
        self.assertFalse((revision / "reviews").exists())
        template = json.loads((revision / "review-template.json").read_text())
        self.assertEqual(template["revision_id"], revision.name)
        self.assertTrue(all(item["status"] == "unreviewed" for item in template["pages"]))
        self.assertEqual(template["reviewer"], "")


if __name__ == "__main__":
    unittest.main()
