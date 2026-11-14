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
ALL_AGENTS = ("codex", "claude", "cursor", "gemini", "antigravity")


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

    def project_snapshot(self, project=None):
        project = project or self.project
        return {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in project.rglob("*") if path.is_file()}

    def history_directories(self, profile_id="agent-engineering"):
        parent = self.project / ".agent-experience/installations" / profile_id
        return sorted(path.name for path in parent.iterdir() if path.is_dir())

    def test_profiles_coexist_and_repeated_install_is_unchanged(self):
        (self.project / "AGENTS.md").write_text("User rules.\n")
        (self.project / "CLAUDE.md").write_text("User Claude rules.\n")
        (self.project / "GEMINI.md").write_text("User Gemini rules.\n")
        installed = self.run_cli(self.engineering, "install")
        self.assertEqual(set(installed["installed_agents"]), set(ALL_AGENTS))
        self.run_cli(self.writing, "install")
        self.run_cli(self.engineering, "check")
        self.run_cli(self.writing, "check")
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            text = (self.project / name).read_text()
            self.assertEqual(text.count("agent-experience:agent-engineering:start"), 1)
            self.assertEqual(text.count("agent-experience:agent-paper-writing:start"), 1)
        gemini = (self.project / "GEMINI.md").read_text()
        self.assertIn("@./.agent-experience/agent-engineering/skills/research-engineering/references/rules.md", gemini)
        self.assertIn("@./.agent-experience/agent-paper-writing/skills/paper-writing/references/rules.md", gemini)
        self.assertNotIn("Understand the task before running it.", gemini)
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
        cases = (("codex", "AGENTS.md"),
                 ("claude", ".claude/skills/research-engineering/assets/example.md"),
                 ("gemini", "GEMINI.md"), ("antigravity", "AGENTS.md"))
        for agent, target in cases:
            with self.subTest(agent=agent, target=target), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                self.run_cli(self.engineering, "install", "--agents", agent, project=project)
                path = project / target
                original = path.read_text()
                if target == "AGENTS.md":
                    modified = original.replace("Understand the task", "User changed the task")
                elif target == "GEMINI.md":
                    modified = original.replace("@./.agent-experience/", "@./user-experience/")
                else:
                    modified = "User asset replacement.\n"
                self.assertNotEqual(original, modified)
                path.write_text(modified)
                before = self.project_snapshot(project)
                result = self.run_cli(self.engineering, "install", "--agents", agent, expected=1, project=project)
                self.assertIn("preserving", result["error"].lower())
                self.run_cli(self.engineering, "uninstall", "--agents", agent, expected=1, project=project)
                self.assertEqual(before, self.project_snapshot(project))

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
        self.run_cli(self.engineering, "check", "--agents", "claude", "cursor", "gemini", "antigravity")
        self.assertTrue((self.project / ".agent-experience/agent-engineering/tools/profile.py").is_file())
        self.assertTrue((self.project / ".agents/skills/research-engineering/SKILL.md").is_file())
        self.assertIn("agent-experience:agent-engineering:start", (self.project / "AGENTS.md").read_text())
        self.run_cli(self.engineering, "uninstall", "--agents", "gemini", "antigravity")
        self.run_cli(self.engineering, "check", "--agents", "claude", "cursor")
        self.assertFalse((self.project / ".agents/skills/research-engineering/SKILL.md").exists())
        self.assertTrue((self.project / ".agent-experience/agent-engineering/tools/profile.py").is_file())
        self.run_cli(self.engineering, "uninstall", "--agents", "claude", "cursor")
        self.assertFalse((self.project / ".agent-experience/agent-engineering").exists())
        before = self.project_snapshot()
        result = self.run_cli(self.engineering, "uninstall")
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.project_snapshot())

    def test_google_agents_install_upgrade_and_restore_original_entries(self):
        for agent, entry in (("gemini", "GEMINI.md"), ("antigravity", "AGENTS.md")):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                originals = {"AGENTS.md": "User AGENTS with no final newline".encode(),
                             "GEMINI.md": "用户的 Gemini 规则。\n".encode()}
                for name, content in originals.items():
                    (project / name).write_bytes(content)
                self.run_cli(self.engineering, "install", "--agents", agent, project=project)
                self.run_cli(self.engineering, "check", "--agents", agent, project=project)
                other_entry = "AGENTS.md" if entry == "GEMINI.md" else "GEMINI.md"
                self.assertEqual((project / other_entry).read_bytes(), originals[other_entry])
                self.assertIn("agent-experience:agent-engineering:start", (project / entry).read_text())
                rules = self.engineering / "skills/research-engineering/references/rules.md"
                updated_rules = f"Updated workflow for {agent}.\n"
                rules.write_text(updated_rules)
                upgraded = self.run_cli(self.engineering, "install", "--agents", agent, project=project)
                self.assertTrue(upgraded["changed"])
                self.run_cli(self.engineering, "check", "--agents", agent, project=project)
                installed_rules = project / ".agents/skills/research-engineering/references/rules.md"
                self.assertEqual(installed_rules.read_text(), updated_rules)
                if agent == "gemini":
                    gemini = (project / entry).read_text()
                    self.assertIn("@./.agent-experience/agent-engineering/skills/research-engineering/references/rules.md", gemini)
                    self.assertNotIn(updated_rules.strip(), gemini)
                else:
                    self.assertIn(updated_rules.strip(), (project / entry).read_text())
                self.run_cli(self.engineering, "uninstall", "--agents", agent, project=project)
                for name, content in originals.items():
                    self.assertEqual((project / name).read_bytes(), content)
                self.assertFalse((project / ".agents/skills/research-engineering").exists())
                self.assertFalse((project / ".agent-experience/agent-engineering").exists())

    def test_shared_google_resources_survive_distinct_uninstall_orders(self):
        orders = (("codex", "gemini", "antigravity"),
                  ("antigravity", "codex", "gemini"),
                  ("gemini", "antigravity", "codex"))
        for order in orders:
            with self.subTest(order=order), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                originals = {"AGENTS.md": b"User AGENTS without final newline",
                             "GEMINI.md": b"User Gemini settings.\n"}
                for name, content in originals.items():
                    (project / name).write_bytes(content)
                self.run_cli(self.writing, "install", project=project)
                self.run_cli(self.engineering, "install", "--agents", *order, project=project)
                remaining = set(order)
                for agent in order:
                    self.run_cli(self.engineering, "uninstall", "--agents", agent, project=project)
                    remaining.remove(agent)
                    self.run_cli(self.writing, "check", project=project)
                    shared_skill = project / ".agents/skills/research-engineering/SKILL.md"
                    self.assertEqual(shared_skill.exists(), bool(remaining))
                    snapshot = project / ".agent-experience/agent-engineering/tools/profile.py"
                    self.assertEqual(snapshot.exists(), bool(remaining))
                    for entry, users in (("AGENTS.md", {"codex", "antigravity"}), ("GEMINI.md", {"gemini"})):
                        text = (project / entry).read_text()
                        self.assertEqual("agent-experience:agent-engineering:start" in text, bool(remaining & users))
                        self.assertEqual(text.count("agent-experience:agent-paper-writing:start"), 1)
                    if remaining:
                        self.run_cli(self.engineering, "check", "--agents", *sorted(remaining), project=project)
                self.run_cli(self.writing, "uninstall", project=project)
                for name, content in originals.items():
                    self.assertEqual((project / name).read_bytes(), content)

    def test_three_platform_version_one_state_expands_incrementally_to_five(self):
        self.run_cli(self.engineering, "install", "--agents", "codex", "claude", "cursor")
        state_path = self.project / ".agent-experience/installations/agent-engineering/state.json"
        old_state = json.loads(state_path.read_text())
        self.assertEqual(old_state["version"], 1)
        self.assertEqual(set(old_state["agents"]), {"codex", "claude", "cursor"})
        original_entries = {name: (self.project / name).read_bytes() for name in ("AGENTS.md", "CLAUDE.md")}
        previous_history = self.history_directories()
        self.run_cli(self.engineering, "install", "--agents", "gemini", "antigravity")
        self.run_cli(self.engineering, "check")
        new_state = json.loads(state_path.read_text())
        self.assertEqual(set(new_state["agents"]), set(ALL_AGENTS))
        for name, content in original_entries.items():
            self.assertEqual((self.project / name).read_bytes(), content)
        for name, checksum in old_state["files"].items():
            self.assertEqual(new_state["files"][name], checksum)
        for name, block in old_state["blocks"].items():
            self.assertEqual(new_state["blocks"][name], block)
        self.assertEqual(len(self.history_directories()), len(previous_history) + 1)
        before = self.project_snapshot()
        self.assertFalse(self.run_cli(self.engineering, "install")["changed"])
        self.assertEqual(before, self.project_snapshot())

    def test_antigravity_agents_byte_limit_preserves_rejected_install_and_check(self):
        self.run_cli(self.engineering, "install", "--agents", "antigravity")
        path = self.project / "AGENTS.md"
        installed = path.read_bytes()
        padding_bytes = 24000 - len(installed)
        self.assertGreater(padding_bytes, 0)
        padding = ("界" * (padding_bytes // 3)).encode() + b"x" * (padding_bytes % 3)
        path.write_bytes(installed + padding)
        self.assertEqual(path.stat().st_size, 24000)
        self.run_cli(self.engineering, "check", "--agents", "antigravity")
        before = self.project_snapshot()
        self.assertFalse(self.run_cli(self.engineering, "install", "--agents", "antigravity")["changed"])
        self.assertEqual(before, self.project_snapshot())
        rules = self.engineering / "skills/research-engineering/references/rules.md"
        rules.write_text(rules.read_text().rstrip("\n") + "!\n")
        before = self.project_snapshot()
        self.run_cli(self.engineering, "install", "--agents", "antigravity", expected=1)
        self.assertEqual(before, self.project_snapshot())
        path.write_bytes(path.read_bytes() + b"!")
        self.assertEqual(path.stat().st_size, 24001)
        before = self.project_snapshot()
        checked = self.run_cli(self.engineering, "check", "--agents", "antigravity", expected=1)
        self.assertTrue(any("AGENTS.md" in message and "24000" in message for message in checked["errors"]))
        self.run_cli(self.engineering, "install", "--agents", "antigravity", expected=1)
        self.assertEqual(before, self.project_snapshot())


if __name__ == "__main__":
    unittest.main()
