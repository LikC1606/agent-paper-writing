#!/usr/bin/env python3
"""Compile immutable paper revisions and record an explicit visual review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid


CHECKS = ("size", "placement", "font", "whitespace", "alignment", "readability", "argument")
EXCLUDED = {".git", ".agent-experience", ".paper-runs", "runs", ".venv", "node_modules", "__pycache__"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def event(revision: Path, **value: object) -> None:
    with (revision / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": timestamp(), **value}, ensure_ascii=False) + "\n")


def run_command(argv: list[str], cwd: Path, revision: Path, label: str) -> int:
    executable = str(cwd / argv[0]) if os.sep in argv[0] and not Path(argv[0]).is_absolute() else shutil.which(argv[0])
    if executable is None and (cwd / argv[0]).is_file():
        executable = str(cwd / argv[0])
    entry = {
        "label": label, "argv": argv, "cwd": str(cwd), "started_at": timestamp(),
        "executable": str(Path(executable).resolve()) if executable else None,
        "log": f"{label}.log",
    }
    event(revision, phase=label, status="running")
    with (revision / entry["log"]).open("xb") as log:
        try:
            completed = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
            code = completed.returncode
        except OSError as error:
            log.write((str(error) + "\n").encode())
            code = 127
        except KeyboardInterrupt:
            log.write(b"Interrupted by user\n")
            code = 130
    entry.update(returncode=code, ended_at=timestamp())
    with (revision / "commands.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    event(revision, phase=label, status="completed" if code == 0 else "failed", returncode=code)
    return code


def git_state(project: Path) -> dict:
    result = {}
    for name, command in (
        ("commit", ["git", "rev-parse", "HEAD"]),
        ("status", ["git", "status", "--porcelain=v1"]),
        ("diff", ["git", "diff", "HEAD", "--", "."]),
    ):
        try:
            process = subprocess.run(command, cwd=project, capture_output=True, text=True, check=False)
            result[name] = {"argv": command, "returncode": process.returncode,
                            "stdout": process.stdout, "stderr": process.stderr}
        except OSError as error:
            result[name] = {"argv": command, "error": str(error)}
    return result


def snapshot(project: Path, destination: Path, output_root: Path, extra_excludes: list[str]) -> dict:
    """Copy the declared paper project, excluding generated state and explicit paths."""
    hashes = {}
    excluded = []
    destination.mkdir()
    for directory, dirs, files in os.walk(project, followlinks=False):
        base = Path(directory)
        retained = []
        for name in sorted(dirs):
            path = base / name
            relative = path.relative_to(project).as_posix()
            if name in EXCLUDED or path.resolve() == output_root or relative in extra_excludes:
                excluded.append(relative + "/")
            elif path.is_symlink():
                raise ValueError(f"源码目录包含符号链接：{relative}；把所需材料放入论文项目，或用 --exclude 排除无关目录")
            else:
                retained.append(name)
                (destination / relative).mkdir(parents=True, exist_ok=True)
        dirs[:] = retained
        for name in sorted(files):
            path = base / name
            relative = path.relative_to(project).as_posix()
            if relative in extra_excludes or name.endswith((".pyc", ".pyo")):
                excluded.append(relative)
                continue
            if path.is_symlink():
                raise ValueError(f"源码包含符号链接：{relative}；把所需材料放入论文项目，或用 --exclude 排除无关文件")
            target = destination / relative
            shutil.copy2(path, target)
            hashes[relative] = digest(target)
    return {"files": hashes, "excluded": excluded}


def engine_commands(engine: str, source: str, output: Path) -> list[list[str]]:
    if engine == "auto":
        engine = next((item for item in ("latexmk", "tectonic", "pdflatex", "xelatex", "lualatex")
                       if shutil.which(item)), "latexmk")
    executable = shutil.which(engine) or engine
    name = Path(engine).name.removesuffix(".exe")
    if name == "latexmk":
        return [[executable, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-recorder",
                 f"-outdir={output}", source]]
    if name == "tectonic":
        return [[executable, "--outdir", str(output), source]]
    if name in {"pdflatex", "xelatex", "lualatex"}:
        command = [executable, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                   "-recorder", f"-output-directory={output}", source]
        return [command, command.copy()]
    raise ValueError("--engine 支持 latexmk、tectonic、pdflatex、xelatex、lualatex 或其完整路径；其他流程使用 -- 后的既有命令")


def build(args: argparse.Namespace) -> dict:
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"论文项目目录不存在：{project}")
    output_root = (Path(args.output_root).expanduser().resolve() if args.output_root
                   else project / ".paper-runs")
    if output_root == project:
        raise ValueError("输出根目录必须与论文项目目录分开")
    output_root.mkdir(parents=True, exist_ok=True)
    revision = output_root / identifier()
    revision.mkdir()
    workspace, output, pages = (revision / part for part in ("source", "build", "pages"))
    output.mkdir()
    pages.mkdir()
    phase = "prepare"
    configuration = {
        "created_at": timestamp(), "project": str(project), "revision": str(revision),
        "source": args.source, "engine": args.engine, "custom_command": args.command,
        "renderer": args.renderer, "dpi": args.dpi, "pdf_name": args.pdf_name,
        "exclude": args.exclude, "python": sys.executable, "python_version": sys.version,
        "platform": platform.platform(), "host": platform.node(), "cwd": str(Path.cwd()),
        "tool_sha256": digest(Path(__file__)),
    }
    write_json(revision / "config.json", configuration)
    event(revision, phase=phase, status="running")
    try:
        if args.dpi <= 0:
            raise ValueError("--dpi 必须大于 0")
        source = (project / args.source).resolve()
        if not source.is_relative_to(project) or not source.is_file():
            raise ValueError("--source 必须是论文项目中的现有文件")
        source_relative = source.relative_to(project).as_posix()
        source_state = {"git": git_state(project),
                        **snapshot(project, workspace, output_root, args.exclude)}
        write_json(revision / "source-state.json", source_state)
        if not (workspace / source_relative).is_file():
            raise ValueError("源文件被排除；请调整 --source 或 --exclude")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if command:
            values = {"source": source_relative, "workspace": str(workspace), "output": str(output)}
            commands = [[argument.replace("{source}", values["source"])
                         .replace("{workspace}", values["workspace"])
                         .replace("{output}", values["output"]) for argument in command]]
        else:
            commands = engine_commands(args.engine, source_relative, output)
            run_command([commands[0][0], "--version"], workspace, revision, "compiler-version")
        phase = "compile"
        for number, command in enumerate(commands, 1):
            if run_command(command, workspace, revision, f"compile-{number}") != 0:
                raise RuntimeError(f"编译失败；查看 compile-{number}.log，修复原项目后新建轮次补跑")
        pdf_name = args.pdf_name or source.stem + ".pdf"
        pdf = (output / pdf_name).resolve()
        if not pdf.is_relative_to(output) or not pdf.is_file():
            raise RuntimeError(f"编译命令未生成 build/{pdf_name}；既有命令应把新 PDF 输出到 {{output}}")
        phase = "render"
        if run_command([args.renderer, "-png", "-r", str(args.dpi), str(pdf), str(pages / "page")],
                       workspace, revision, "render") != 0:
            raise RuntimeError("PDF 渲染失败；查看 render.log，修复依赖后新建轮次补跑")
        images = sorted(pages.glob("page-*.png"), key=lambda item: int(item.stem.rsplit("-", 1)[1]))
        if not images:
            raise RuntimeError("渲染命令未生成页面图片")
        manifest = {"pdf": str(pdf.relative_to(revision)), "pdf_sha256": digest(pdf),
                    "pages": {image.name: digest(image) for image in images}}
        write_json(revision / "render-manifest.json", manifest)
        template = {
            "revision_id": revision.name, "reviewer": "", "pdf_sha256": manifest["pdf_sha256"],
            "pages": [{"page": image.name, "status": "unreviewed",
                       "checks": {check: None for check in CHECKS}, "findings": ""} for image in images],
            "notes": "逐页实际查看后填写。检查项填 true/false；发现写明实际观察及剩余问题。",
        }
        write_json(revision / "review-template.json", template)
        result = {"status": "awaiting_visual_review", "revision": str(revision),
                  "pdf": str(pdf), "pages": [str(image) for image in images], "ended_at": timestamp()}
    except (Exception, KeyboardInterrupt) as error:
        (revision / "error.txt").write_text(str(error) + "\n", encoding="utf-8")
        result = {"status": "failed", "phase": phase, "revision": str(revision),
                  "error": str(error), "ended_at": timestamp()}
    write_json(revision / "result.json", result)
    event(revision, phase="build", status=result["status"])
    return result


def validate_artifacts(revision: Path) -> dict:
    result = read_json(revision / "result.json")
    if result["status"] != "awaiting_visual_review":
        raise ValueError("该轮尚未完成编译和渲染；修复问题后新建轮次")
    manifest = read_json(revision / "render-manifest.json")
    if digest(revision / manifest["pdf"]) != manifest["pdf_sha256"]:
        raise ValueError("该轮 PDF 已改变；旧视觉记录不适用于修改后的 PDF，请新建轮次")
    for name, expected in manifest["pages"].items():
        if digest(revision / "pages" / name) != expected:
            raise ValueError(f"页面图片已改变：{name}；请新建轮次")
    return manifest


def review(args: argparse.Namespace) -> dict:
    revision = Path(args.revision).expanduser().resolve()
    manifest = validate_artifacts(revision)
    record = read_json(Path(args.record).expanduser())
    if record.get("pdf_sha256") != manifest["pdf_sha256"]:
        raise ValueError("检查记录与该轮 PDF 的哈希不一致")
    if not record.get("revision_id"):
        raise ValueError("检查记录缺少 revision_id；旧表单请新建轮次并重新逐页检查")
    if record["revision_id"] != revision.name:
        raise ValueError("检查记录属于其他轮次；请使用当前轮次的表单重新逐页检查")
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
        raise ValueError("检查记录必须写明 reviewer")
    entries = record.get("pages")
    if not isinstance(entries, list) or len(entries) != len(manifest["pages"]):
        raise ValueError("必须逐页填写全部渲染页面")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("每页记录必须是对象")
        name = entry.get("page")
        if name not in manifest["pages"] or name in seen:
            raise ValueError("页面记录存在未知页面或重复页面")
        seen.add(name)
        checks = entry.get("checks", {})
        if not isinstance(checks, dict) or any(type(checks.get(key)) is not bool for key in CHECKS):
            raise ValueError(f"{name} 的全部检查项需要填写 true/false")
        expected = "pass" if all(checks[key] for key in CHECKS) else "fail"
        if entry.get("status") != expected:
            raise ValueError(f"{name} 的 status 必须与实际检查项一致：{expected}")
        if not isinstance(entry.get("findings"), str) or not entry["findings"].strip():
            raise ValueError(f"{name} 需要填写实际查看后的发现")
    reviews = revision / "reviews"
    reviews.mkdir(exist_ok=True)
    path = reviews / (identifier() + ".json")
    outcome = "visual_review_passed" if all(item["status"] == "pass" for item in entries) else "visual_review_failed"
    write_json(path, {"recorded_at": timestamp(), "status": outcome, "review": record})
    event(revision, phase="visual_review", status=outcome, record=str(path.relative_to(revision)))
    return {"status": outcome, "revision": str(revision), "record": str(path)}


def status(args: argparse.Namespace) -> dict:
    revision = Path(args.revision).expanduser().resolve()
    result = read_json(revision / "result.json")
    reviews = sorted((revision / "reviews").glob("*.json"))
    if result["status"] == "awaiting_visual_review":
        validate_artifacts(revision)
        if reviews:
            result = {**result, "status": read_json(reviews[-1])["status"], "review": str(reviews[-1])}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    compile_parser = commands.add_parser("build", help="快照源码、编译并渲染到新的独立轮次")
    compile_parser.add_argument("--project", required=True, help="论文项目根目录")
    compile_parser.add_argument("--source", default="main.tex", help="相对项目根目录的主文件")
    compile_parser.add_argument("--engine", default="auto", help="auto 或既有 LaTeX 引擎/完整路径")
    compile_parser.add_argument("--output-root", help="独立轮次根目录，默认项目/.paper-runs")
    compile_parser.add_argument("--pdf-name", help="相对本轮 build 目录的 PDF 名称")
    compile_parser.add_argument("--renderer", default="pdftoppm", help="Poppler pdftoppm 路径")
    compile_parser.add_argument("--dpi", type=int, default=100)
    compile_parser.add_argument("--exclude", action="append", default=[], help="排除的项目相对路径，可重复")
    compile_parser.add_argument("command", nargs=argparse.REMAINDER,
                                help="-- 后接既有命令；支持 {source}、{workspace}、{output}，不使用 shell")
    review_parser = commands.add_parser("review", help="保存实际查看后填写的逐页视觉检查记录")
    review_parser.add_argument("--revision", required=True)
    review_parser.add_argument("--record", required=True, help="已填写的 JSON 检查记录")
    status_parser = commands.add_parser("status", help="检查本轮构建和最近一次视觉记录")
    status_parser.add_argument("--revision", required=True)
    try:
        args = parser.parse_args(argv)
        result = {"build": build, "review": review, "status": status}[args.action](args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "error", "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] in {"failed", "error", "visual_review_failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
