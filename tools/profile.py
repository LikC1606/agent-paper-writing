#!/usr/bin/env python3
"""Install one experience profile into a project without replacing user rules."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid


AGENTS = ("codex", "claude", "cursor", "gemini", "antigravity")
SKILL_DIRS = {
    "codex": ".agents/skills",
    "claude": ".claude/skills",
    "cursor": ".cursor/skills",
    "gemini": ".agents/skills",
    "antigravity": ".agents/skills",
}
ENTRY_FILES = {
    "codex": "AGENTS.md", "claude": "CLAUDE.md",
    "gemini": "GEMINI.md", "antigravity": "AGENTS.md",
}
ANTIGRAVITY_RULE_BYTES = 24_000
NOTE = "Checks cover installed files and configuration; real agent behavior needs a separate check."


class Conflict(Exception):
    pass


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def safe_path(project: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise Conflict(f"Unsafe managed path: {relative}")
    current = project
    if current.is_symlink() or (current.exists() and not current.is_dir()):
        raise Conflict(f"Project is not a regular directory: {current}")
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise Conflict(f"Preserving symbolic link at managed path: {current}")
        if current.exists() and index < len(parts) - 1 and not current.is_dir():
            raise Conflict(f"Expected a directory at managed path: {current}")
    return current


def read_file(project: Path, relative: str) -> bytes | None:
    path = safe_path(project, relative)
    if not path.exists():
        return None
    if not path.is_file():
        raise Conflict(f"Expected a regular file: {path}")
    return path.read_bytes()


def tree_files(directory: Path) -> dict[str, bytes]:
    if directory.is_symlink():
        raise Conflict(f"Source directory must be self-contained: {directory}")
    if not directory.is_dir():
        raise Conflict(f"Missing source directory: {directory}")
    result = {}
    for current, directories, files in os.walk(directory, followlinks=False):
        directories[:] = sorted(name for name in directories if name != "__pycache__")
        for name in directories + sorted(files):
            path = Path(current) / name
            if path.is_symlink():
                raise Conflict(f"Source must be self-contained; symbolic link found: {path}")
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(current) / name
            if not path.is_file():
                raise Conflict(f"Source is not a regular file: {path}")
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def load_source(root: Path, include_files: bool = True) -> dict:
    try:
        metadata = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Conflict(f"Cannot read profile.json: {error}") from error
    for key in ("id", "skill"):
        if not isinstance(metadata.get(key), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", metadata[key]):
            raise Conflict(f"profile.json has an invalid {key}")
    expected_rules = f"skills/{metadata['skill']}/references/rules.md"
    if metadata.get("rules") != expected_rules:
        raise Conflict(f"profile.json rules must be {expected_rules}")
    if not isinstance(metadata.get("title"), str) or not metadata["title"].strip():
        raise Conflict("profile.json needs a non-empty title")
    source = {"metadata": metadata}
    if not include_files:
        return source
    files = {}
    for name in ("profile.json", "requirements.md"):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise Conflict(f"Missing regular source file: {path}")
        files[name] = path.read_bytes()
    directories = ["tools", f"skills/{metadata['skill']}"]
    if (root / "templates").exists() or (root / "templates").is_symlink():
        directories.append("templates")
    for directory in directories:
        for relative, content in tree_files(root / directory).items():
            files[f"{directory}/{relative}"] = content
    for required in (expected_rules, f"skills/{metadata['skill']}/SKILL.md", "tools/profile.py"):
        if required not in files:
            raise Conflict(f"Missing source file: {required}")
    try:
        source["rules"] = files[expected_rules].decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise Conflict("Rules must use UTF-8") from error
    if not source["rules"]:
        raise Conflict("Rules must not be empty")
    source["files"] = files
    return source


def markers(profile_id: str) -> tuple[str, str]:
    return (f"<!-- agent-experience:{profile_id}:start -->", f"<!-- agent-experience:{profile_id}:end -->")


def block_span(text: str, profile_id: str) -> tuple[int, int] | None:
    start, end = markers(profile_id)
    reserved = f"<!-- agent-experience:{profile_id}:"
    if reserved not in text:
        return None
    if text.count(start) != 1 or text.count(end) != 1 or text.count(reserved) != 2:
        raise Conflict(f"Conflicting or incomplete managed markers for {profile_id}")
    left = text.index(start)
    right = text.index(end)
    if right < left:
        raise Conflict(f"Managed markers are out of order for {profile_id}")
    return left, right + len(end)


def render_block(source: dict) -> str:
    metadata = source["metadata"]
    start, end = markers(metadata["id"])
    skill_path = f".agent-experience/{metadata['id']}/skills/{metadata['skill']}/SKILL.md"
    return (
        f"{start}\n## {metadata['title']}\n\n{source['rules']}\n\n"
        f"详细流程（相对于项目根目录）：[SKILL.md]({skill_path})。\n{end}"
    )


def entry_names(agents: list[str]) -> list[str]:
    return list(dict.fromkeys(ENTRY_FILES[agent] for agent in agents if agent in ENTRY_FILES))


def render_entry(source: dict, name: str) -> str:
    if name != "GEMINI.md":
        return render_block(source)
    metadata = source["metadata"]
    start, end = markers(metadata["id"])
    base = f".agent-experience/{metadata['id']}/skills/{metadata['skill']}"
    return (
        f"{start}\n## {metadata['title']}\n\n"
        f"@./{base}/references/rules.md\n\n"
        f"详细流程（相对于项目根目录）：[SKILL.md]({base}/SKILL.md)。\n{end}"
    )


def check_antigravity_size(project: Path, agents: list[str], changes: dict | None = None) -> None:
    if "antigravity" not in agents:
        return
    content = changes["AGENTS.md"] if changes and "AGENTS.md" in changes else read_file(project, "AGENTS.md")
    if content is not None and len(content) > ANTIGRAVITY_RULE_BYTES:
        raise Conflict(
            f"AGENTS.md is {len(content)} bytes; Antigravity limits each expanded rule file to "
            f"{ANTIGRAVITY_RULE_BYTES} bytes. Preserving project files; shorten or reorganize existing "
            "instructions before installing this platform. This check covers the direct file only."
        )


def cursor_rule(source: dict) -> bytes:
    title = json.dumps(source["metadata"]["title"], ensure_ascii=False)
    return (f"---\ndescription: {title}\nalwaysApply: true\n---\n\n{render_block(source)}\n").encode()


def scope_roots(metadata: dict, agents: list[str], shared: bool) -> list[str]:
    roots = [f"{SKILL_DIRS[agent]}/{metadata['skill']}" for agent in agents]
    if "cursor" in agents:
        roots.append(f".cursor/rules/{metadata['id']}.mdc")
    if shared:
        roots.append(f".agent-experience/{metadata['id']}")
    return list(dict.fromkeys(roots))


def in_scope(relative: str, roots: list[str]) -> bool:
    return any(relative == root or relative.startswith(root + "/") for root in roots)


def desired_files(source: dict, agents: list[str], shared: bool = True) -> dict[str, bytes]:
    metadata = source["metadata"]
    desired = {}
    if shared:
        desired.update({f".agent-experience/{metadata['id']}/{name}": content for name, content in source["files"].items()})
    skill_prefix = f"skills/{metadata['skill']}/"
    for agent in agents:
        for name, content in source["files"].items():
            if name.startswith(skill_prefix):
                desired[f"{SKILL_DIRS[agent]}/{metadata['skill']}/{name[len(skill_prefix):]}"] = content
    if "cursor" in agents:
        desired[f".cursor/rules/{metadata['id']}.mdc"] = cursor_rule(source)
    return desired


def empty_state(metadata: dict) -> dict:
    return {"version": 1, "id": metadata["id"], "skill": metadata["skill"], "agents": [], "files": {}, "blocks": {}}


def load_state(project: Path, metadata: dict) -> tuple[str, dict]:
    relative = f".agent-experience/installations/{metadata['id']}/state.json"
    content = read_file(project, relative)
    if content is None:
        return relative, empty_state(metadata)
    try:
        state = json.loads(content)
        if state["version"] != 1 or state["id"] != metadata["id"] or state["skill"] != metadata["skill"]:
            raise ValueError("profile identity or version does not match")
        if not isinstance(state["agents"], list) or any(agent not in AGENTS for agent in state["agents"]):
            raise ValueError("invalid installed agents")
        if not isinstance(state["files"], dict) or not isinstance(state["blocks"], dict):
            raise ValueError("invalid file manifest")
        allowed_roots = scope_roots(metadata, state["agents"], True)
        for name, checksum in state["files"].items():
            safe_path(project, name)
            if not in_scope(name, allowed_roots) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError(f"invalid owned file: {name}")
        for name, record in state["blocks"].items():
            if name not in {ENTRY_FILES[agent] for agent in state["agents"] if agent in ENTRY_FILES}:
                raise ValueError(f"invalid owned block: {name}")
            if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
                raise ValueError(f"invalid block record: {name}")
    except (ValueError, KeyError, TypeError) as error:
        raise Conflict(f"Preserving invalid installation state at {relative}: {error}") from error
    return relative, state


def verify_owned_files(project: Path, state: dict, roots: list[str]) -> list[str]:
    errors = []
    for relative, expected in state["files"].items():
        if not in_scope(relative, roots):
            continue
        try:
            content = read_file(project, relative)
            if content is None or digest(content) != expected:
                errors.append(f"Managed file was changed or removed; preserving it: {relative}")
        except Conflict as error:
            errors.append(str(error))
    for root in roots:
        try:
            path = safe_path(project, root)
            if not path.exists():
                continue
            if path.is_file():
                names = [root]
            else:
                names = []
                for current, directories, files in os.walk(path, followlinks=False):
                    for name in directories + files:
                        child = Path(current) / name
                        if child.is_symlink():
                            errors.append(f"Preserving symbolic link in managed directory: {child.relative_to(project)}")
                    names.extend((Path(current) / name).relative_to(project).as_posix() for name in files)
            for name in names:
                if name not in state["files"]:
                    errors.append(f"Unowned file at installation destination; preserving it: {name}")
        except Conflict as error:
            errors.append(str(error))
    return errors


def decode_entry(content: bytes | None, name: str) -> str:
    try:
        return (content or b"").decode("utf-8")
    except UnicodeDecodeError as error:
        raise Conflict(f"Preserving non-UTF-8 entry file: {name}") from error


def owned_block(text: str, profile_id: str, record: dict | None, name: str) -> tuple[int, int] | None:
    span = block_span(text, profile_id)
    if record is None:
        if span is not None:
            raise Conflict(f"Managed markers exist without ownership state; preserving {name}")
        return None
    if span is None or digest(text[span[0]:span[1]].encode()) != record["sha256"]:
        raise Conflict(f"Managed block was changed or removed; preserving {name}")
    return span


def plan_install(project: Path, source: dict, agents: list[str], state: dict) -> tuple[dict, dict]:
    metadata = source["metadata"]
    roots = scope_roots(metadata, agents, True)
    errors = verify_owned_files(project, state, roots)
    desired = desired_files(source, agents)
    changes = {}
    next_state = json.loads(json.dumps(state))
    next_state["files"] = {name: checksum for name, checksum in state["files"].items() if not in_scope(name, roots)}
    for relative in sorted(set(desired) | {name for name in state["files"] if in_scope(name, roots)}):
        try:
            old = read_file(project, relative)
            new = desired.get(relative)
            if old is not None and relative not in state["files"]:
                errors.append(f"Unowned file at installation destination; preserving it: {relative}")
            if old != new:
                changes[relative] = new
            if new is not None:
                next_state["files"][relative] = digest(new)
        except Conflict as error:
            errors.append(str(error))
    for name in entry_names(agents):
        new_block = render_entry(source, name)
        try:
            old = read_file(project, name)
            text = decode_entry(old, name)
            record = state["blocks"].get(name)
            span = owned_block(text, metadata["id"], record, name)
            if span is None:
                padding = "" if not text or text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n"
                new_text = text + padding + new_block + "\n"
                record = {"prefix": padding, "suffix": "\n", "created": old is None}
            else:
                new_text = text[:span[0]] + new_block + text[span[1]:]
                record = dict(record)
            record["sha256"] = digest(new_block.encode())
            next_state["blocks"][name] = record
            if new_text.encode() != old:
                changes[name] = new_text.encode()
        except Conflict as error:
            errors.append(str(error))
    if errors:
        raise Conflict("\n".join(dict.fromkeys(errors)))
    next_state["agents"] = [agent for agent in AGENTS if agent in set(state["agents"]) | set(agents)]
    check_antigravity_size(project, next_state["agents"], changes)
    return changes, next_state


def plan_uninstall(project: Path, source: dict, agents: list[str], state: dict) -> tuple[dict, dict]:
    metadata = source["metadata"]
    selected = [agent for agent in agents if agent in state["agents"]]
    remaining = [agent for agent in state["agents"] if agent not in selected]
    remaining_roots = scope_roots(metadata, remaining, False)
    roots = [root for root in scope_roots(metadata, selected, not remaining) if root not in remaining_roots]
    errors = verify_owned_files(project, state, roots)
    changes = {name: None for name in state["files"] if in_scope(name, roots)}
    next_state = json.loads(json.dumps(state))
    next_state["files"] = {name: checksum for name, checksum in state["files"].items() if not in_scope(name, roots)}
    for name in entry_names(selected):
        if name in entry_names(remaining):
            continue
        try:
            old = read_file(project, name)
            text = decode_entry(old, name)
            record = state["blocks"].get(name)
            if record is None:
                raise Conflict(f"Missing ownership record for installed entry: {name}")
            span = owned_block(text, metadata["id"], record, name)
            left, right = span
            prefix = record.get("prefix", "")
            suffix = record.get("suffix", "")
            if prefix and text[:left].endswith(prefix):
                left -= len(prefix)
            if suffix and text[right:].startswith(suffix):
                right += len(suffix)
            new = (text[:left] + text[right:]).encode()
            changes[name] = None if not new and record.get("created") else new
            del next_state["blocks"][name]
        except Conflict as error:
            errors.append(str(error))
    if errors:
        raise Conflict("\n".join(dict.fromkeys(errors)))
    next_state["agents"] = remaining
    return changes, next_state


def atomic_write(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_changes(project: Path, metadata: dict, operation: str, changes: dict) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    history_relative = f".agent-experience/installations/{metadata['id']}/{run_id}"
    history = safe_path(project, history_relative)
    before = {name: read_file(project, name) for name in changes}
    manifest = {
        "id": metadata["id"], "operation": operation, "run_id": run_id,
        "changes": [{"path": name, "before_sha256": digest(before[name]) if before[name] is not None else None,
                     "after_sha256": digest(content) if content is not None else None}
                    for name, content in sorted(changes.items())],
    }
    history.mkdir(parents=True, exist_ok=False)
    for name, content in before.items():
        if content is not None:
            snapshot = history / "before" / name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(content)
    (history / "manifest.json").write_bytes(json_bytes(manifest))
    atomic_write(history / "status.json", json_bytes({"status": "prepared"}))
    written = []
    try:
        for name, content in sorted(changes.items()):
            atomic_write(safe_path(project, name), content)
            written.append(name)
        atomic_write(history / "status.json", json_bytes({"status": "applied"}))
    except OSError as error:
        rollback_errors = []
        for name in reversed(written):
            try:
                atomic_write(safe_path(project, name), before[name])
            except OSError as rollback_error:
                rollback_errors.append(f"{name}: {rollback_error}")
        atomic_write(history / "status.json", json_bytes({"status": "failed", "error": str(error), "rollback_errors": rollback_errors}))
        raise Conflict(f"Installation failed; snapshots preserved at {history_relative}: {error}; rollback errors: {rollback_errors}") from error
    for name, content in changes.items():
        if content is not None:
            continue
        directory = (project / name).parent
        while directory != project and directory != project.parent:
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
    return history_relative


def check_installation(project: Path, source: dict, agents: list[str], state: dict) -> dict:
    metadata = source["metadata"]
    errors = verify_owned_files(project, state, scope_roots(metadata, agents, True))
    for agent in agents:
        if agent not in state["agents"]:
            errors.append(f"Platform is not installed: {agent}")
    for name, content in desired_files(source, agents).items():
        try:
            actual = read_file(project, name)
            if actual is None or digest(actual) != digest(content):
                errors.append(f"Installed file differs from the current source: {name}")
            if state["files"].get(name) != digest(content):
                errors.append(f"Installation manifest differs from the current source: {name}")
        except Conflict as error:
            errors.append(str(error))
    for name in entry_names(agents):
        expected_block = render_entry(source, name)
        try:
            text = decode_entry(read_file(project, name), name)
            record = state["blocks"].get(name)
            span = owned_block(text, metadata["id"], record, name)
            if span is None or text[span[0]:span[1]] != expected_block:
                errors.append(f"Managed block differs from the current source: {name}")
        except Conflict as error:
            errors.append(str(error))
    try:
        check_antigravity_size(project, agents)
    except Conflict as error:
        errors.append(str(error))
    return {"status": "error" if errors else "ok", "id": metadata["id"], "agents": agents,
            "errors": list(dict.fromkeys(errors)), "note": NOTE}


def main(argv: list[str] | None = None, source_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "check", "uninstall"):
        subparser = subcommands.add_parser(command)
        subparser.add_argument("--project", type=Path, required=True)
        subparser.add_argument("--agents", nargs="+", choices=AGENTS, default=list(AGENTS))
        if command in ("install", "uninstall"):
            subparser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        root = (source_root or Path(__file__).resolve().parents[1]).resolve()
        project = arguments.project.expanduser().resolve()
        source = load_source(root, include_files=arguments.command != "uninstall")
        metadata = source["metadata"]
        state_relative, state = load_state(project, metadata)
        agents = [agent for agent in AGENTS if agent in arguments.agents]
        if arguments.command == "check":
            result = check_installation(project, source, agents, state)
        else:
            if arguments.command == "install":
                changes, next_state = plan_install(project, source, agents, state)
            else:
                changes, next_state = plan_uninstall(project, source, agents, state)
            if next_state != state:
                changes[state_relative] = json_bytes(next_state)
            dry_run = getattr(arguments, "dry_run", False)
            history = None
            if changes and not dry_run:
                history = apply_changes(project, metadata, arguments.command, changes)
            result = {"status": "ok", "id": metadata["id"], "operation": arguments.command,
                      "agents": agents, "installed_agents": next_state["agents"], "dry_run": dry_run,
                      "changed": bool(changes), "changed_files": sorted(changes), "history": history,
                      "note": NOTE}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ok" else 1
    except (Conflict, OSError) as error:
        print(json.dumps({"status": "error", "error": str(error), "note": NOTE}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
