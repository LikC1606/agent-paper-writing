"""Protect original agreements and their complete, portable installation.

These are document preservation and packaging tests. They do not grade an
agent's research judgment, writing quality, or actual visual inspection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RequirementContractTests(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get("PROFILE_TEST_ARTIFACT_DIR")
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=output))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.project = self.root / "研究 project with spaces"
        self.project.mkdir()
        self.source = self.root / "experience source"
        self.source.mkdir()
        for name in ("profile.json", "requirements.md"):
            shutil.copyfile(ROOT / name, self.source / name)
        for name in ("tools", "skills"):
            shutil.copytree(ROOT / name, self.source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if (ROOT / "templates").exists():
            shutil.copytree(ROOT / "templates", self.source / "templates")
        self.metadata = json.loads((self.source / "profile.json").read_text(encoding="utf-8"))
        self.profile_id = self.metadata["id"]
        self.skill = self.metadata["skill"]
        self.rules = Path(self.metadata["rules"])

    def invoke(self, action, *, source=None, expected=0):
        command = [sys.executable, str((source or self.source) / "tools/profile.py"), action,
                   "--project", str(self.project)]
        result = subprocess.run(
            command,
            capture_output=True, text=True, check=False,
        )
        with (self.root / "cli-calls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"argv": command, "returncode": result.returncode,
                                     "stdout": result.stdout, "stderr": result.stderr}) + "\n")
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_rule_delivery(self):
        canonical = (self.source / self.rules).read_text(encoding="utf-8").strip()
        for entry in ("AGENTS.md", "CLAUDE.md", f".cursor/rules/{self.profile_id}.mdc"):
            with self.subTest(entry=entry):
                text = (self.project / entry).read_text(encoding="utf-8")
                self.assertEqual(text.count(canonical), 1)
        cursor = (self.project / f".cursor/rules/{self.profile_id}.mdc").read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", cursor)
        gemini = (self.project / "GEMINI.md").read_text(encoding="utf-8")
        imports = re.findall(r"^@\./(.+)$", gemini, flags=re.MULTILINE)
        self.assertEqual(imports, [f".agent-experience/{self.profile_id}/{self.rules.as_posix()}"])
        self.assertEqual((self.project / imports[0]).read_text(encoding="utf-8").strip(), canonical)
        start = f"<!-- agent-experience:{self.profile_id}:start -->"
        for entry in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            self.assertEqual((self.project / entry).read_text(encoding="utf-8").count(start), 1)

    def test_original_requirements_and_observation_cases_remain_complete(self):
        """C01–C14/P01–P13 preservation, especially P11; not adherence."""
        fixture = json.loads((ROOT / "tests/fixtures/requirements.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["profile"], self.profile_id)
        self.assertEqual(fixture["verification"], "agent_observation")
        prefix, count = ("C", 14) if self.profile_id == "agent-engineering" else ("P", 13)
        expected_ids = [f"{prefix}{index:02d}" for index in range(1, count + 1)]
        self.assertEqual([case["id"] for case in fixture["cases"]], expected_ids)
        requirements = (ROOT / "requirements.md").read_text(encoding="utf-8")
        rules = (ROOT / self.rules).read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"\*\*([CP]\d{2})\b", rules), expected_ids)
        for case in fixture["cases"]:
            with self.subTest(requirement=case["id"]):
                lines = [line for line in requirements.splitlines()
                         if re.search(r"\b" + case["id"] + r"\b", line)]
                self.assertEqual(len(lines), 1)
                self.assertIn(case["original"], lines[0])
                for key in ("setup", "prompt"):
                    self.assertIsInstance(case[key], str)
                    self.assertTrue(case[key].strip())
                for key in ("pass_if", "fail_if", "evidence"):
                    self.assertIsInstance(case[key], list)
                    self.assertTrue(case[key])
                    self.assertTrue(all(isinstance(item, str) and item.strip() for item in case[key]))

    def test_real_profile_delivers_every_rule_and_skill_resource_to_five_platforms(self):
        """All clauses arrive intact; file delivery is separate from loading."""
        self.invoke("install")
        self.invoke("check")
        self.assert_rule_delivery()
        installed = self.project / ".agent-experience" / self.profile_id
        self.assertEqual((installed / "requirements.md").read_bytes(),
                         (self.source / "requirements.md").read_bytes())
        skill_source = self.source / "skills" / self.skill
        for resource in skill_source.rglob("*"):
            if not resource.is_file():
                continue
            relative = resource.relative_to(skill_source)
            for directory in (".agents/skills", ".claude/skills", ".cursor/skills"):
                with self.subTest(directory=directory, resource=relative):
                    self.assertEqual((self.project / directory / self.skill / relative).read_bytes(),
                                     resource.read_bytes())

    def test_moved_project_uses_installed_tools_and_relative_guides_without_source_checkout(self):
        """C07/C14 and P12: portability of actual packaged tools and guides."""
        self.invoke("install")
        moved = self.root / "moved research project"
        shutil.move(str(self.project), moved)
        self.project = moved
        shutil.rmtree(self.source)
        installed = moved / ".agent-experience" / self.profile_id
        self.invoke("check", source=installed)
        tool = "run.py" if self.profile_id == "agent-engineering" else "paper.py"
        process = subprocess.run([sys.executable, str(installed / "tools" / tool), "--help"],
                                 cwd=moved, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("usage:", process.stdout)
        skill_root = installed / "skills" / self.skill
        for document in skill_root.rglob("*.md"):
            text = document.read_text(encoding="utf-8")
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                    continue
                with self.subTest(document=document.relative_to(skill_root), link=link):
                    self.assertFalse(Path(link).is_absolute())
                    self.assertTrue((document.parent / link.split("#", 1)[0]).resolve().is_file())

    def test_rule_update_reaches_every_platform_and_preserves_prior_requirements_and_receipts(self):
        """C06/P11: new guidance cannot silently erase installation history."""
        first = self.invoke("install")
        history_root = self.project / ".agent-experience/installations" / self.profile_id
        first_history = self.project / first["history"]
        historical = {path.relative_to(first_history): path.read_bytes()
                      for path in first_history.rglob("*") if path.is_file()}
        old_rules = (self.source / self.rules).read_bytes()
        old_requirements = (self.source / "requirements.md").read_bytes()
        (self.source / self.rules).write_bytes(old_rules + "\n本轮新增说明：保留前一轮证据并明确本轮范围。\n".encode())
        (self.source / "requirements.md").write_bytes(old_requirements + "\n本轮补充约定单独记录。\n".encode())
        updated = self.invoke("install")
        self.invoke("check")
        self.assert_rule_delivery()
        self.assertNotEqual(updated["history"], first["history"])
        for relative, content in historical.items():
            self.assertEqual((first_history / relative).read_bytes(), content)
        backup = self.project / updated["history"] / "before/.agent-experience" / self.profile_id
        self.assertEqual((backup / self.rules).read_bytes(), old_rules)
        self.assertEqual((backup / "requirements.md").read_bytes(), old_requirements)
        self.assertEqual(len([path for path in history_root.iterdir() if path.is_dir()]), 2)


if __name__ == "__main__":
    unittest.main()
