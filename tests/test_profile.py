"""Exercise installation behavior in disposable, self-contained project fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


INSTALLER = Path(__file__).resolve().parents[1] / "tools" / "profile.py"


class ProfileInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.engineering = self.make_source("agent-engineering", "research-engineering")
        self.writing = self.make_source("agent-paper-writing", "paper-writing")

    def make_source(self, profile_id, skill):
        source = self.root / profile_id
        for directory in ("tools", "templates", f"skills/{skill}/references", f"skills/{skill}/assets"):
            (source / directory).mkdir(parents=True)
        shutil.copyfile(INSTALLER, source / "tools/profile.py")
        (source / "profile.json").write_text(json.dumps({"id": profile_id, "skill": skill, "title": profile_id,
                                                       "rules": f"skills/{skill}/references/rules.md"}))
        (source / "requirements.md").write_text("Original requirements remain available.\n")
        (source / "templates/task.md").write_text("Research question:\n")
        (source / f"skills/{skill}/SKILL.md").write_text(f"---\nname: {skill}\ndescription: Test skill.\n---\nRead references/rules.md and assets/example.md.\n")
        (source / f"skills/{skill}/references/rules.md").write_text("Understand the task before running it.\n")
        (source / f"skills/{skill}/assets/example.md").write_text("A portable example.\n")
        return source

    def run_cli(self, source, command, *extra, expected=0, project=None):
        completed = subprocess.run([sys.executable, str(source / "tools/profile.py"), command,
                                    "--project", str(project or self.project), *extra], capture_output=True, text=True)
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def project_snapshot(self):
        return {path.relative_to(self.project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.project.rglob("*") if path.is_file()}

    def history_directories(self, profile_id="agent-engineering"):
        parent = self.project / ".agent-experience/installations" / profile_id
        return sorted(path.name for path in parent.iterdir() if path.is_dir())

    def test_profiles_coexist_and_repeated_install_is_unchanged(self):
        (self.project / "AGENTS.md").write_text("User rules.\n")
        (self.project / "CLAUDE.md").write_text("User Claude rules.\n")
        self.run_cli(self.engineering, "install")
        self.run_cli(self.writing, "install")
        self.run_cli(self.engineering, "check")
        self.run_cli(self.writing, "check")
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (self.project / name).read_text()
            self.assertEqual(text.count("agent-experience:agent-engineering:start"), 1)
            self.assertEqual(text.count("agent-experience:agent-paper-writing:start"), 1)
        for directory in (".agents", ".claude", ".cursor"):
            for skill in ("research-engineering", "paper-writing"):
                self.assertTrue((self.project / directory / "skills" / skill / "assets/example.md").is_file())
        before = self.project_snapshot()
        result = self.run_cli(self.engineering, "install")
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.project_snapshot())

    def test_upgrade_and_uninstall_preserve_user_and_other_profile(self):
        user_text = "User rules with no final newline"
        (self.project / "AGENTS.md").write_text(user_text)
        self.run_cli(self.engineering, "install")
        self.run_cli(self.writing, "install")
        original_entry = (self.project / "AGENTS.md").read_bytes()
        original_history = self.history_directories()
        rules = self.engineering / "skills/research-engineering/references/rules.md"
        rules.write_text("Updated implementation must be explained.\n")
        self.run_cli(self.engineering, "install")
        self.run_cli(self.engineering, "check")
        self.run_cli(self.writing, "check")
        history = self.history_directories()
        self.assertEqual(len(history), len(original_history) + 1)
        upgrade = self.project / ".agent-experience/installations/agent-engineering" / history[-1]
        self.assertEqual((upgrade / "before/AGENTS.md").read_bytes(), original_entry)
        self.run_cli(self.engineering, "uninstall")
        self.run_cli(self.writing, "check")
        self.assertFalse((self.project / ".agents/skills/research-engineering/SKILL.md").exists())
        self.assertFalse((self.project / ".agent-experience/agent-engineering").exists())
        self.assertTrue((self.project / ".agent-experience/installations/agent-engineering" / original_history[0]).is_dir())
        self.assertIn(user_text, (self.project / "AGENTS.md").read_text())
        self.run_cli(self.writing, "uninstall")
        self.assertEqual((self.project / "AGENTS.md").read_text(), user_text)

    def test_manual_edits_block_upgrade_and_uninstall_without_writes(self):
        for target in ("AGENTS.md", ".claude/skills/research-engineering/assets/example.md"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                self.run_cli(self.engineering, "install", project=project)
                path = project / target
                path.write_text(path.read_text().replace("Understand the task", "User changed the task")
                                if target == "AGENTS.md" else "User asset replacement.\n")
                before = {item.relative_to(project).as_posix(): item.read_bytes() for item in project.rglob("*") if item.is_file()}
                result = self.run_cli(self.engineering, "install", expected=1, project=project)
                self.assertIn("preserving", result["error"].lower())
                self.run_cli(self.engineering, "uninstall", expected=1, project=project)
                after = {item.relative_to(project).as_posix(): item.read_bytes() for item in project.rglob("*") if item.is_file()}
                self.assertEqual(before, after)

    def test_unowned_files_and_conflicting_markers_are_preserved(self):
        destinations = (".agents/skills/research-engineering/SKILL.md", "AGENTS.md")
        for destination in destinations:
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                target = project / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                text = "Existing user skill.\n" if destination != "AGENTS.md" else "<!-- agent-experience:agent-engineering:start -->\nunfinished\n"
                target.write_text(text)
                self.run_cli(self.engineering, "install", expected=1, project=project)
                self.assertEqual(target.read_text(), text)
                self.assertFalse((project / ".agent-experience").exists())

    def test_dry_run_does_not_create_project_or_change_existing_files(self):
        missing = self.root / "not-created"
        result = self.run_cli(self.engineering, "install", "--dry-run", project=missing)
        self.assertTrue(result["changed"])
        self.assertFalse(missing.exists())
        (self.project / "AGENTS.md").write_text("Keep this.\n")
        before = self.project_snapshot()
        self.run_cli(self.engineering, "install", "--dry-run")
        self.assertEqual(before, self.project_snapshot())

    def test_install_without_root_templates_keeps_skill_assets(self):
        shutil.rmtree(self.engineering / "templates")
        self.run_cli(self.engineering, "install")
        self.run_cli(self.engineering, "check")
        self.assertFalse((self.project / ".agent-experience/agent-engineering/templates").exists())
        for directory in (".agents", ".claude", ".cursor"):
            asset = self.project / directory / "skills/research-engineering/assets/example.md"
            self.assertEqual(asset.read_text(), "A portable example.\n")
        shared_asset = self.project / ".agent-experience/agent-engineering/skills/research-engineering/assets/example.md"
        self.assertEqual(shared_asset.read_text(), "A portable example.\n")

    def test_uninstall_dry_run_preserves_user_data_rules_and_history(self):
        (self.project / "AGENTS.md").write_text("Keep these user rules.\n")
        data = self.project / "results/experiment.json"
        data.parent.mkdir()
        data.write_text('{"measured_accuracy": 0.91}\n')
        self.run_cli(self.engineering, "install")
        self.run_cli(self.writing, "install")
        before = self.project_snapshot()
        history_before = self.history_directories()
        result = self.run_cli(self.engineering, "uninstall", "--dry-run")
        self.assertTrue(result["changed"])
        self.assertTrue(result["dry_run"])
        self.assertIsNone(result["history"])
        self.assertEqual(result["installed_agents"], [])
        self.assertEqual(before, self.project_snapshot())
        self.assertEqual(history_before, self.history_directories())
        self.run_cli(self.engineering, "check")
        self.run_cli(self.writing, "check")

    def test_check_reports_corruption_and_stale_unselected_platform(self):
        self.run_cli(self.engineering, "install")
        rules = self.engineering / "skills/research-engineering/references/rules.md"
        rules.write_text("New rules for the selected platform.\n")
        self.run_cli(self.engineering, "install", "--agents", "codex")
        self.run_cli(self.engineering, "check", "--agents", "codex")
        result = self.run_cli(self.engineering, "check", expected=1)
        self.assertTrue(any("CLAUDE.md" in message for message in result["errors"]))
        self.run_cli(self.engineering, "install")
        target = self.project / ".agents/skills/research-engineering/SKILL.md"
        target.write_text("Corrupted installation.\n")
        before = self.project_snapshot()
        result = self.run_cli(self.engineering, "check", expected=1)
        self.assertTrue(any("SKILL.md" in message for message in result["errors"]))
        self.assertEqual(before, self.project_snapshot())

    def test_partial_uninstall_retains_shared_tools_until_last_platform(self):
        self.run_cli(self.engineering, "install")
        self.run_cli(self.engineering, "uninstall", "--agents", "codex")
        self.run_cli(self.engineering, "check", "--agents", "claude", "cursor")
        self.assertTrue((self.project / ".agent-experience/agent-engineering/tools/profile.py").is_file())
        self.run_cli(self.engineering, "uninstall", "--agents", "claude", "cursor")
        self.assertFalse((self.project / ".agent-experience/agent-engineering").exists())
        before = self.project_snapshot()
        result = self.run_cli(self.engineering, "uninstall")
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.project_snapshot())


if __name__ == "__main__":
    unittest.main()
