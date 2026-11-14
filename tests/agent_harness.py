"""Run explicit client acceptance cases and retain evidence, without auto-grading prose."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def inventory(project):
    return {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in project.rglob("*") if path.is_file() and ".git" not in path.relative_to(project).parts}


def prepare(case_id, client, output_root, companion=None):
    cases = json.loads((ROOT / "tests/fixtures/requirements.json").read_text(encoding="utf-8"))["cases"]
    case = next((item for item in cases if item["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    spec = importlib.util.spec_from_file_location("acceptance_projects", ROOT / "tests/agent_projects.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{client}-{case_id}-" + uuid.uuid4().hex[:8]
    run = Path(output_root).expanduser().resolve() / name
    project = run / "project"
    project.mkdir(parents=True)
    preparation_source = run / "preparation-source"
    preparation_source.mkdir()
    for relative in ("tests/agent_harness.py", "tests/agent_projects.py", "tests/fixtures/requirements.json"):
        shutil.copyfile(ROOT / relative, preparation_source / Path(relative).name)
    fixture = module.prepare_case(case_id, project, sys.executable)
    if client == "gemini" and os.environ.get("GEMINI_API_KEY"):
        # Only this disposable project chooses the auth type. No credential
        # value or machine-wide setting is copied into the case.
        settings = project / ".gemini/settings.json"
        settings.parent.mkdir(exist_ok=True)
        write_json(settings, {"security": {"auth": {"selectedType": "gemini-api-key"}}})
    calls = []
    for source in (ROOT, Path(companion).resolve() if companion else None):
        if source is None:
            continue
        command = [sys.executable, str(source / "tools/profile.py"), "install", "--project", str(project), "--agents", client]
        completed = subprocess.run(command, capture_output=True, text=True)
        calls.append({"argv": command, "returncode": completed.returncode,
                      "stdout": completed.stdout, "stderr": completed.stderr})
        write_json(run / f"installation-{len(calls)}.json", calls[-1])
        if completed.returncode:
            raise RuntimeError(f"Installation failed; evidence: {run}")
    prompt = fixture["prompt"] + (
        "\n\n这是隔离的合成研究项目；只在本项目内读写，不访问其他研究目录、修改全局设置或调用付费实验接口。"
        f"本机实际 Python 为 {sys.executable}；同名 python3 可能是包装入口。"
        "执行本任务已获授权；对会改变目标的实质歧义先提出具体问题。"
    )
    (run / "prompt.txt").write_text(prompt, encoding="utf-8")
    write_json(run / "case.json", case)
    write_json(run / "fixture.json", fixture)
    write_json(run / "configuration.json", {
        "case": case_id, "client": client, "project": str(project), "profile_source": str(ROOT),
        "companion": str(companion) if companion else None, "python": sys.executable,
        "host": socket.gethostname(), "platform": platform.platform(), "cwd": str(Path.cwd()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    write_json(run / "initial-files.json", inventory(project))
    shutil.copytree(project, run / "before")
    write_json(run / "review-template.json", {
        "case": case_id, "client": client, "reviewer": "",
        "checks": [{"kind": kind, "criterion": criterion, "status": "unreviewed", "evidence": [], "notes": ""}
                   for kind, key in (("required", "pass_if"), ("forbidden", "fail_if")) for criterion in case[key]],
        "notes": "Pass means the criterion was observed, or the forbidden behavior was checked and absent. Use actual traces and artifacts.",
    })
    return {"run": str(run), "status": "prepared", "case": case_id, "client": client}


def client_command(client, project, run, executable=None, budget=1.0):
    default = {"codex": "codex", "claude": "claude", "gemini": "gemini",
               "antigravity": "agy", "cursor": "cursor-agent"}[client]
    binary = executable or shutil.which(default)
    if not binary:
        raise FileNotFoundError(f"No {client} client found; use --executable with an installed client")
    prompt = (run / "prompt.txt").read_text(encoding="utf-8")
    if client == "codex":
        return [binary, "exec", "--ephemeral", "--sandbox", "workspace-write", "--skip-git-repo-check",
                "--json", "--color", "never", "-C", str(project), "-o", str(run / "answer.md"), "-"], prompt
    if client == "claude":
        return [binary, "-p", "--verbose", "--output-format", "stream-json", "--no-session-persistence",
                "--setting-sources", "project", "--settings", '{"disableAllHooks":true}',
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--tools", "Bash,Read,Write,Edit,Glob,Grep", "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
                "--permission-mode", "acceptEdits", "--max-budget-usd", str(budget)], prompt
    if client == "gemini":
        return [binary, "--skip-trust", "--approval-mode", "auto_edit", "--output-format", "stream-json", "--prompt", prompt], None
    if client == "antigravity":
        return [binary, "--mode", "accept-edits", "--sandbox", "--output-format", "stream-json", "--print", prompt], None
    raise ValueError("Cursor client commands vary; pass the verified command as --command-json")


def execute(run, timeout=240, executable=None, command=None, budget=1.0):
    run = Path(run).expanduser().resolve()
    if (run / "result.json").exists():
        raise ValueError("This execution is already recorded; prepare a new round to retry")
    shutil.copyfile(Path(__file__), run / "execution-source.py")
    configuration = json.loads((run / "configuration.json").read_text())
    project = run / "project"
    started = time.monotonic()
    result = {"case": configuration["case"], "client": configuration["client"], "status": "execution_error"}
    process = None
    try:
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        argv, stdin = ((command, None) if command else
                       client_command(configuration["client"], project, run, executable, budget))
        if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
            raise ValueError("Command must be a nonempty JSON array of strings")
        description = {"argv": argv, "cwd": str(project), "timeout_seconds": timeout,
                       "custom_command": command is not None}
        if command is None:
            try:
                version = subprocess.run([argv[0], "--version"], capture_output=True, text=True, timeout=8)
                description["client_version"] = {"returncode": version.returncode, "stdout": version.stdout, "stderr": version.stderr}
            except (OSError, subprocess.TimeoutExpired) as error:
                description["client_version"] = {"error": str(error)}
        child_environment = os.environ.copy()
        if configuration["client"] == "gemini":
            child_environment["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
            description["session_environment_names"] = ["GEMINI_CLI_TRUST_WORKSPACE"]
        write_json(run / "command.json", description)
        with (run / "stdout.jsonl").open("xb") as out, (run / "stderr.log").open("xb") as err:
            process = subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True, text=True, env=child_environment)
            try:
                process.communicate(input=stdin, timeout=timeout)
                result.update(returncode=process.returncode,
                              status="awaiting_review" if process.returncode == 0 else "execution_error")
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                result.update(returncode=124, status="timed_out", error="Client exceeded the explicit case timeout")
    except (OSError, ValueError) as error:
        result.update(error=str(error), status="blocked" if isinstance(error, FileNotFoundError) else "execution_error")
    final = inventory(project)
    original = json.loads((run / "initial-files.json").read_text())
    fixture = json.loads((run / "fixture.json").read_text())
    result["protected_changes"] = [path for path in fixture.get("protected", []) if original.get(path) != final.get(path)]
    result["changed_files"] = [path for path in sorted(set(original) | set(final)) if original.get(path) != final.get(path)]
    result["elapsed_seconds"] = time.monotonic() - started
    # A client may finish its process with zero while reporting a budget/API
    # failure in its own stream. Transport success is not native completion.
    stream_path = run / "stdout.jsonl"
    if stream_path.exists():
        for line in stream_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                native = json.loads(line)
            except ValueError:
                continue
            if not isinstance(native, dict):
                continue
            if native.get("type") == "result":
                result["native_subtype"] = native.get("subtype")
                result["reported_cost_usd"] = native.get("total_cost_usd")
                if isinstance(native.get("result"), str) and not (run / "answer.md").exists():
                    (run / "answer.md").write_text(native["result"], encoding="utf-8")
                if (native.get("is_error") or str(native.get("subtype", "")).startswith("error")) and result["status"] != "timed_out":
                    result["status"] = "execution_error"
            if native.get("event") == "result" and isinstance(native.get("result"), dict):
                detail = native["result"]
                result["native_status"] = detail.get("status")
                result["native_error"] = detail.get("error")
                if detail.get("status") == "ERROR" and result["status"] != "timed_out":
                    result["status"] = "execution_error"
            if native.get("type") == "turn.completed":
                result["native_turn_completed"] = True
    write_json(run / "final-files.json", final)
    write_json(run / "result.json", result)
    return result


def review(run, record_path):
    run = Path(run).resolve()
    template = json.loads((run / "review-template.json").read_text())
    record = json.loads(Path(record_path).read_text())
    result = json.loads((run / "result.json").read_text())
    if (record.get("case"), record.get("client")) != (template["case"], template["client"]):
        raise ValueError("Review does not belong to this case and client")
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        raise ValueError("Name the reviewer")
    entries = record.get("checks", [])
    if [(item.get("kind"), item.get("criterion")) for item in entries] != [(item["kind"], item["criterion"]) for item in template["checks"]]:
        raise ValueError("Review every required and forbidden criterion")
    for item in entries:
        if item.get("status") not in {"pass", "fail", "unverified"} or not item.get("notes", "").strip():
            raise ValueError("Each criterion needs an observed status and concrete notes")
        if not isinstance(item.get("evidence"), list) or not item["evidence"]:
            raise ValueError("Each criterion needs evidence")
        for evidence in item["evidence"]:
            path = (run / evidence).resolve()
            if not path.is_relative_to(run) or not path.is_file():
                raise ValueError(f"Evidence must be a saved file in this run: {evidence}")
    criteria_status = "passed" if all(item["status"] == "pass" for item in entries) else "failed" if any(item["status"] == "fail" for item in entries) else "unverified"
    status = criteria_status
    if result["protected_changes"]:
        status = "failed"
    elif status == "passed" and result["status"] != "awaiting_review":
        status = "unverified"
    directory = run / "reviews"
    directory.mkdir(exist_ok=True)
    destination = directory / (uuid.uuid4().hex + ".json")
    outcome = {"status": status, "criteria_status": criteria_status,
               "execution_status": result["status"], "protected_changes": result["protected_changes"]}
    write_json(destination, {**outcome, "record": record})
    return {**outcome, "record": str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("prepare")
    create.add_argument("--case", required=True)
    create.add_argument("--client", required=True, choices=("codex", "claude", "gemini", "antigravity", "cursor"))
    create.add_argument("--output-root", required=True)
    create.add_argument("--companion")
    run = commands.add_parser("run")
    run.add_argument("--run", required=True)
    run.add_argument("--timeout", type=float, default=240)
    run.add_argument("--executable")
    run.add_argument("--command-json")
    run.add_argument("--budget", type=float, default=1.0)
    grading = commands.add_parser("review")
    grading.add_argument("--run", required=True)
    grading.add_argument("--record", required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare(args.case, args.client, args.output_root, args.companion)
        elif args.action == "run":
            result = execute(args.run, args.timeout, args.executable,
                             json.loads(args.command_json) if args.command_json else None, args.budget)
        else:
            result = review(args.run, args.record)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] in {"execution_error", "blocked", "timed_out", "failed"} else 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
