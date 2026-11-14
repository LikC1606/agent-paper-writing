"""Prepare disposable paper tasks; preparing a fixture is not an agent result."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def _write(project: Path, relative: str, text: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def _paper(body: str, abstract: str = "A synthetic toy study of a deterministic filter.") -> str:
    return (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage{graphicx}\n"
        "\\setlength{\\textwidth}{440pt}\n"
        "\\setlength{\\oddsidemargin}{10pt}\n"
        "\\title{A synthetic toy study of score filtering}\n"
        "\\author{Disposable writing fixture}\n"
        "\\date{}\n\\begin{document}\n\\maketitle\n"
        "\\begin{abstract}\n" + abstract + "\n\\end{abstract}\n"
        + textwrap.dedent(body).lstrip() + "\n\\end{document}\n"
    )


def _plot_pdf(path: Path) -> None:
    """A small vector chart with labels near its edges, no graphics dependency."""
    commands = ["0.8 w 48 40 m 430 40 l 430 202 l S", "48 40 m 48 202 l S"]
    for x, y in [(70, 70), (170, 108), (270, 142), (370, 175)]:
        commands.append(f"0.15 0.35 0.65 rg {x} {y} 9 9 re f")
    for x, y, size, value in [
        (3, 135, 14, "Quality"), (90, 12, 15, "Retained items per batch"),
        (48, 28, 7, "0"), (162, 28, 7, "10"), (265, 28, 7, "20"),
        (366, 28, 7, "30"), (8, 201, 11, "1.00"),
        (90, 215, 16, "Synthetic toy observations"),
    ]:
        commands.append(f"0 0 0 rg BT /F1 {size} Tf {x} {y} Td ({value}) Tj ET")
    stream = ("\n".join(commands) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 480 240] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _editable_plot_source(project: Path, python: str) -> None:
    """Package the original P09 chart geometry and its deterministic PDF writer."""
    source = {
        "provenance": "Synthetic toy drawing geometry, not measured model or deployment outcomes.",
        "coordinate_units": "PDF points on a 480 by 240 point canvas",
        "media_box": [0, 0, 480, 240],
        "axes_pdf_commands": ["0.8 w 48 40 m 430 40 l 430 202 l S", "48 40 m 48 202 l S"],
        "marker_rgb": "0.15 0.35 0.65", "marker_size": 9,
        "points": [[70, 70], [170, 108], [270, 142], [370, 175]],
        "font": "Helvetica",
        "labels": [
            {"x": x, "y": y, "size": size, "text": value}
            for x, y, size, value in [
                (3, 135, 14, "Quality"), (90, 12, 15, "Retained items per batch"),
                (48, 28, 7, "0"), (162, 28, 7, "10"), (265, 28, 7, "20"),
                (366, 28, 7, "30"), (8, 201, 11, "1.00"),
                (90, 215, 16, "Synthetic toy observations"),
            ]
        ],
    }
    _write(project, "figures/quality-plot-source.json", json.dumps(source, indent=2) + "\n")
    _write(project, "tools/draw_quality_plot.py", r'''
        """Reproduce the supplied synthetic chart from explicit PDF geometry."""
        import argparse
        import json
        from pathlib import Path

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--source", default="figures/quality-plot-source.json")
        parser.add_argument("--output", default="figures/quality-plot-working.pdf")
        args = parser.parse_args()
        source = json.loads(Path(args.source).read_text(encoding="utf-8"))
        commands = list(source["axes_pdf_commands"])
        for x, y in source["points"]:
            commands.append(f'{source["marker_rgb"]} rg {x} {y} {source["marker_size"]} {source["marker_size"]} re f')
        for label in source["labels"]:
            value = label["text"].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f'0 0 0 rg BT /F1 {label["size"]} Tf {label["x"]} {label["y"]} Td ({value}) Tj ET')
        stream = ("\n".join(commands) + "\n").encode("ascii")
        media_box = " ".join(map(str, source["media_box"]))
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [{media_box}] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".encode(),
            f'<< /Type /Font /Subtype /Type1 /BaseFont /{source["font"]} >>'.encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        ]
        data = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, body in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
        start = len(data)
        data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            data.extend(f"{offset:010d} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        print(output)
    ''')
    _write(project, "plot-command.json", json.dumps([
        python, "tools/draw_quality_plot.py", "--source", "figures/quality-plot-source.json",
        "--output", "figures/quality-plot-working.pdf",
    ], indent=2) + "\n")
    with (project / "README.md").open("a", encoding="utf-8") as stream:
        stream.write("\n## 图的本地源文件\n\n"
                     "绘图入口为 tools/draw_quality_plot.py，原始几何及文字参数为 figures/quality-plot-source.json。\n"
                     "plot-command.json 保存使用本次指定 Python 的完整参数数组，从项目根目录执行。\n"
                     "该命令原样重生当前问题图，输出 figures/quality-plot-working.pdf；figures/quality-plot.pdf 保留原始版本。\n"
                     "--source 和 --output 可指定项目内的源文件和输出文件，绘图不依赖网络或第三方包。\n"
                     "图的点位是明示的 synthetic toy 绘图几何，与 data/observations.csv 的分类结果属于不同材料；这里不把画布坐标冒充实测质量。\n")


def _common(project: Path, python: str) -> None:
    _write(project, "README.md", """
        # 论文材料

        本项目是 synthetic toy（人工合成的小型教学数据），不是实际模型、临床或部署实验。
        可编辑论文为 main.tex；材料背景见 task.md，原始数据见 data/。
        使用已有 tools/paper.py 构建会把源码、编译日志、新 PDF 和页面写入独立 .paper-runs/ 轮次。
        记录工具的通过表单不代表有人或 agent 已查看页面。
        所有操作限于当前项目；无 API、训练、付费调用或联网要求。
    """)
    (project / "tools").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "tools/paper.py", project / "tools/paper.py")
    _write(project, "build-command.json", json.dumps(
        [python, "tools/paper.py", "build", "--project", ".", "--engine", "pdflatex"], indent=2
    ) + "\n")
    _write(project, "data/observations.csv", """
        dataset,method,correct,total,operations
        toy-A,unfiltered,6,10,100
        toy-A,score_filter,8,10,60
        toy-B,unfiltered,5,10,100
        toy-B,score_filter,7,10,65
    """)


def _experiments(project: Path, python: str) -> dict:
    _write(project, "data/control.csv", """
        dataset,method,correct,total,operations
        toy-A,budget_matched,7,10,60
        toy-B,budget_matched,6,10,65
    """)
    _write(project, "data/observational.csv", """
        batch,budget,quality,assignment
        one,1,1,observational
        two,2,3,observational
        three,3,2,observational
        four,4,4,observational
    """)
    _write(project, "protocol.md", """
        # 数据与三个实验
        全部数据为固定生成的 synthetic toy；数字不是 API、训练或实际部署结果。
        实验一比较 toy-A、toy-B 的正确数/总数，并包含选择预算匹配的控制方法。
        实验二对上述明确的操作计数运行纯 Python 教学循环；耗时由本机 perf_counter_ns 实测，
        重复5次，单次2000轮。该耗时只代表该循环，不是模型推理耗时。
        实验三使用4条非随机分配的观测记录，计算预算与质量的 Pearson 相关系数。
        输入数据、运行程序和实际输出都随项目保存，详见 tools/analyze.py 和 results/。
    """)
    _write(project, "plans/ablation.md", """
        # 组件消融计划
        待运行：去掉阈值选择，仅保留相同输出预算，重新生成全部 toy 决策并比较。
        当前没有该消融的运行记录、数值或结论。data/control.csv 是现有预算匹配对照，不是此项消融。
    """)
    _write(project, "tools/analyze.py", '''
        """Analyze fixed synthetic toy inputs and time a local teaching loop."""
        import csv
        import json
        import math
        from pathlib import Path
        from time import perf_counter_ns

        output = Path("results")
        output.mkdir(exist_ok=True)
        rows = []
        for name in ("observations.csv", "control.csv"):
            with (Path("data") / name).open(newline="") as stream:
                rows.extend(csv.DictReader(stream))
        accuracy = [{"dataset": row["dataset"], "method": row["method"],
                     "correct": int(row["correct"]), "total": int(row["total"]),
                     "accuracy": int(row["correct"]) / int(row["total"]),
                     "operations": int(row["operations"])} for row in rows]
        (output / "accuracy.json").write_text(json.dumps(accuracy, indent=2) + "\\n")
        timings = []
        for row in accuracy:
            for repeat in range(5):
                start = perf_counter_ns()
                checksum = 0
                for iteration in range(2000):
                    for value in range(row["operations"]):
                        checksum += value % 7
                timings.append({"dataset": row["dataset"], "method": row["method"],
                                "repeat": repeat, "operations_per_iteration": row["operations"],
                                "iterations": 2000, "elapsed_ns": perf_counter_ns() - start,
                                "checksum": checksum})
        with (output / "timing.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(timings[0]))
            writer.writeheader()
            writer.writerows(timings)
        with Path("data/observational.csv").open(newline="") as stream:
            observations = list(csv.DictReader(stream))
        xs = [float(row["budget"]) for row in observations]
        ys = [float(row["quality"]) for row in observations]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        numerator = sum((x-mean_x)*(y-mean_y) for x, y in zip(xs, ys))
        denominator = math.sqrt(sum((x-mean_x)**2 for x in xs) * sum((y-mean_y)**2 for y in ys))
        correlation = {"n": len(xs), "pearson_r": numerator / denominator, "assignment": "observational"}
        (output / "correlation.json").write_text(json.dumps(correlation, indent=2) + "\\n")
        print(json.dumps({"accuracy_rows": len(accuracy), "timing_rows": len(timings), "correlation": correlation}))
    ''')
    command = [python, "tools/analyze.py"]
    result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=30)
    _write(project, "results/analysis-command.json", json.dumps({
        "argv": command, "cwd": str(project), "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
    }, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(f"Toy analysis failed: {result.stderr}")
    return {"accuracy": json.loads((project / "results/accuracy.json").read_text()),
            "correlation": json.loads((project / "results/correlation.json").read_text()),
            "experiment_files": ["results/accuracy.json", "results/timing.csv", "results/correlation.json"],
            "ablation_executed": False}


def _previous_build(project: Path, python: str) -> dict:
    engine, renderer = shutil.which("pdflatex"), shutil.which("pdftoppm")
    if not engine or not renderer:
        missing = [name for name, path in [("pdflatex", engine), ("pdftoppm", renderer)] if not path]
        result = {"status": "blocked", "missing_dependencies": missing, "visual_review_performed": False}
        _write(project, "history/baseline-status.json", json.dumps(result, indent=2) + "\n")
        return result
    command = [python, "tools/paper.py", "build", "--project", str(project),
               "--engine", engine, "--renderer", renderer]
    completed = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=60)
    _write(project, "history/baseline-build-call.json", json.dumps({
        "argv": command, "returncode": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr,
    }, indent=2) + "\n")
    if completed.returncode:
        raise RuntimeError(f"P12 baseline build failed: {completed.stdout}\n{completed.stderr}")
    result = json.loads(completed.stdout)
    revision = Path(result["revision"])
    old = project / "history/round-01"
    old.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "main.tex", old / "main.tex")
    shutil.copyfile(Path(result["pdf"]), old / "main.pdf")
    shutil.copyfile(revision / "review-template.json", old / "review-unfilled.json")
    _write(project, "history/round-01/notes.md", """
        本轮由真实 LaTeX 与 Poppler 构建并渲染；没有实际视觉检查。
        review-unfilled.json 是未填写的旧表单，不是 visual pass 记录。
        不以材料准备替代 agent 的新轮次查看；构建日志和页面保留在 .paper-runs/。
    """)
    return {"status": result["status"], "revision": str(revision.relative_to(project)),
            "page_count": len(result["pages"]), "visual_review_performed": False}


def prepare_case(case_id: str, project: Path, python: str) -> dict:
    """Write only task materials; return checker facts without saving them in project."""
    cases = json.loads((ROOT / "tests/fixtures/requirements.json").read_text(encoding="utf-8"))["cases"]
    case = next((item for item in cases if item["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown paper case: {case_id}")
    project = Path(project).resolve()
    if not project.is_dir() or any(project.iterdir()):
        raise ValueError("project must be a new, empty directory")
    _common(project, python)
    facts = {"case_id": case_id, "data_kind": "synthetic toy", "expected_agent_result": "unverified"}
    protected = ["data/observations.csv"]

    if case_id == "P01":
        _write(project, "task.md", """
            # 当前研究材料
            现有摘要围绕固定阈值过滤减少确定性操作数；引言另一段把论文定位为现实患者结局预测。
            两种研究方向尚未由作者确认。目录中只有 toy-A、toy-B 的人工合成正确数和操作计数，
            没有患者、治疗分配或随访材料。请先阅读 main.tex 和 data/observations.csv。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Introduction}
            The primary goal of this paper is to establish that the filter improves
            real patient survival across hospitals. We seek a causal clinical claim.
            In another draft plan, the goal is solely to compare accuracy and operation
            counts on two synthetic toy datasets. The authors have not selected a scope.
            \section{Available evidence}
            Toy-A has 8/10 correct filtered decisions versus 6/10 without filtering;
            operation counts are 60 and 100. Toy-B has 7/10 versus 5/10 and counts 65 and 100.
        """, "We study whether a fixed score filter reduces deterministic operation counts while retaining accuracy on synthetic toy data."))
        facts.update(unresolved_scope=True, supported_scope="synthetic accuracy and operation counts",
                     unsupported_claim="causal patient survival", required_pause="clarify research scope before rewriting dependent text")
    elif case_id == "P02":
        _write(project, "task.md", """
            # 写作背景
            目标：在固定的 synthetic toy 评价中，描述按阈值过滤对正确率及确定性操作数的影响。
            main.tex 现稿按开发顺序写；开发原记在 development-log.md，完整数据在 data/。
            方法实际定义见 method.md。不需要重写实验工具或进行额外训练。
        """)
        _write(project, "method.md", """
            对每个候选项读取固定分数，保留分数大于等于0.5的项，再按原始顺序输出。
            该输入集的选择与真值人工合成，不含学习或自适应阈值。正确率用正确数除以10，
            操作数表示下游教学循环处理的工作单元数，不能冒充墙钟测量。
        """)
        _write(project, "development-log.md", """
            周一：修正 CSV 读取 bug，避免将 toy-A 的结果复制到 toy-B。
            周二：把 export-v1.py 换成 export-v2.py，修改导出列名。
            周三：增加固定阈值过滤分支，称为 module-v3，结果见 observations.csv。
            周四：改了日志格式并增加状态打印，最终数字已核对。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Methods}
            First we fixed a CSV bug on Monday. Then we upgraded the export script on
            Tuesday. On Wednesday module-v3 was added. Finally we changed the log format.
            \section{Experiments}
            The last code revision obtained 8/10 on toy-A and 7/10 on toy-B.
            Before the module, results were 6/10 and 5/10. The counts were changed from
            100 to 60 and from 100 to 65. The export was successful on Thursday.
        """))
        facts.update(research_question="fixed-threshold filtering: toy accuracy and operation-count tradeoff",
                     irrelevant_chronology=["Monday CSV bug", "Tuesday export upgrade", "Thursday log format"])
        protected.append("development-log.md")
    elif case_id == "P03":
        _write(project, "task.md", """
            # 方法定义
            唯一机制：对每个候选项读取预先给定的分数，只保留分数大于等于0.5的项，
            保留原始顺序。没有训练、注意力模块或自适应阈值。
            main.tex、caption.tex 和 appendix.tex 来自同一草稿的不同编辑者。
        """)
        _plot_pdf(project / "figures/quality-plot.pdf")
        _write(project, "main.tex", _paper(r"""
            \section{Method}
            The intelligent module retains items with a fixed score of at least 0.5,
            in original order. This is the same component discussed in the abstract.
            \section{Toy results}
            Toy-A has 8/10 correct retained decisions. Figure~\ref{fig:names} illustrates the input scores.
            \begin{figure}[h]\centering
            \includegraphics[width=.7\linewidth]{figures/quality-plot.pdf}
            \input{caption.tex}\label{fig:names}\end{figure}
            \appendix\input{appendix.tex}
        """, "The v3 component is evaluated on two fixed synthetic toy datasets."))
        _write(project, "caption.tex", "\\caption{The blue box applied to synthetic toy observations.}\n")
        _write(project, "appendix.tex", "\\section{Component details}\nThe v3 blue box uses the same fixed threshold as the intelligent module.\n")
        facts.update(aliases=["v3", "intelligent module", "blue box"],
                     mechanism="fixed score >=0.5, retain original order, no learned component",
                     affected_files=["main.tex", "caption.tex", "appendix.tex"])
    elif case_id == "P04":
        _write(project, "task.md", """
            # 研究范围与结果
            当前稿件讨论固定阈值过滤在两个合成数据集上的正确率与操作数。
            数据已经确定，见 data/observations.csv；没有医院、患者或外部基准实验。
            论文需保留 synthetic toy 的范围。请修订 main.tex。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Introduction}
            Our contribution is a clinical survival prediction system validated in
            unseen hospitals. Efficiency matters. A fixed threshold was used.
            The synthetic records contain no patients and no external validation.
            \section{Results}
            Toy-A: 8/10 versus 6/10, 60 versus 100 operations.
            Toy-B: 7/10 versus 5/10, 65 versus 100 operations.
        """, "Filtering. 80 percent. Methods matter. We reduce toy-A operations from 100 to 60. The threshold is fixed. Toy-B is different. We compare two synthetic datasets."))
        facts.update(unsupported_claim="clinical survival validation in unseen hospitals",
                     supported_results={"toy-A": [0.6, 0.8, 100, 60], "toy-B": [0.5, 0.7, 100, 65]})
    elif case_id == "P05":
        _write(project, "task.md", """
            # 写作背景与可用参考
            目标读者为机器学习方法类 workshop 的研究者。这是一篇 synthetic toy 的短教学论文，
            不声称在任何真实会议投稿或达到真实基准。请用本地 references/ 中可读材料改进叙事。
            本任务不联网。reading.md 是仓库已维护并注明来源的导读；未提供外部论文全文，
            引用或核验时需准确说明实际读到的是导读及定位信息，不能冒充本轮访问过原文。
        """)
        reading = (ROOT / "skills/paper-writing/references/reading.md").read_text(encoding="utf-8")
        _write(project, "references/reading.md", "来源：本项目安装来源仓库的 writing guide。下面的既有核验表述属于仓库维护记录；本次材料准备未联网、未下载外部全文。\n\n" + reading)
        _write(project, "references/material-status.json", json.dumps({
            "local_material": "repository reading guide with attributed summaries and source links",
            "external_full_text_in_project": False, "new_web_verification_in_this_run": False,
            "source": "agent-paper-writing/skills/paper-writing/references/reading.md",
        }, indent=2) + "\n")
        _write(project, "main.tex", _paper(r"""
            \section{Methods and experiments}
            The script was convenient. The improved result is 80 percent.
            It has fewer operations. The second dataset has 70 percent.
            We used a threshold of 0.5. The old results are 60 and 50 percent.
            Operation counts are 100 versus 60 for toy-A and 100 versus 65 for toy-B.
            The examples are synthetic and do not establish external validity.
        """))
        facts.update(reference_scope="local curator guide only; external URLs and section/rule locators supplied",
                     usable_locators=["Peyton Jones: Your narrative flow; State your contributions",
                                      "Mensh and Kording: Rules 3, 5, 6, 7"],
                     external_full_text_available=False, new_web_verification=False)
        protected.extend(["references/reading.md", "references/material-status.json"])
    elif case_id in {"P06", "P07"}:
        facts.update(_experiments(project, python))
        protected.extend(["data/control.csv", "data/observational.csv", "results/accuracy.json",
                          "results/timing.csv", "results/correlation.json", "results/analysis-command.json"])
        _write(project, "task.md", """
            # 当前研究材料
            论文涉及 toy 数据上的跨数据表现和教学循环效率；protocol.md 定义三个实验。
            data/ 是固定人工合成输入，results/ 是准备材料时实际计算和计时得到的输出，
            tools/analyze.py 可重算。plans/ablation.md 是尚未执行的计划，没有消融数值。
            这些结果不代表模型训练、API或真实应用效果。
        """)
        if case_id == "P06":
            _write(project, "main.tex", _paper(r"""
                \section{Experiments}
                Our method achieves 80 percent accuracy. This single result establishes
                broad generalization and efficient deployment on all workloads.
                \section{Planned analysis}
                A component ablation is planned; it has not been executed.
            """))
        else:
            _write(project, "main.tex", _paper(r"""
                \section{Cross-dataset experiment}
                The results are in the accuracy file.
                \section{Work-count and timing experiment}
                Timing measurements are available. They are lower in some runs.
                \section{Observational experiment}
                Budget and quality have correlation 0.8. This proves that increasing
                the budget causes higher quality in arbitrary deployments.
            """))
            facts["unsupported_causal_claim"] = "observational budget-quality association is not randomized causal evidence"
    elif case_id == "P08":
        _plot_pdf(project / "figures/quality-plot.pdf")
        _write(project, "task.md", """
            # 研究材料
            论文讨论 synthetic toy 的正确率和操作数，数据见 data/observations.csv。
            main.tex 的图表与正文来自不同编辑批次，原图见 figures/。
            请在最终编译页面中安排并解释图表，不需要新实验。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Results}
            The toy-A decisions are correct in 8/10 cases with filtering and 6/10 without.
            Operations decrease from 100 to 60. On toy-B accuracy changes from 5/10 to
            7/10 and operation counts change from 100 to 65.
            \section{Interpretation}
            These observations describe two fixed synthetic datasets only.
            \clearpage\section{All visual materials}
            \begin{table}[h]\centering
            \begin{tabular}{lrr} & Before & After\\ A & 6 & 8\\ B & 5 & 7\end{tabular}
            \caption{Comparison.}\label{tab:accuracy}\end{table}
            \begin{figure}[h]\centering
            \includegraphics[width=.72\linewidth]{figures/quality-plot.pdf}
            \caption{Plot.}\label{fig:unreferenced}\end{figure}
        """))
        facts.update(initial_problems=["all visuals forced after main discussion", "no main-text references",
                                      "table caption omits denominators and dataset definitions"],
                     figure_role="synthetic quality versus retained count, separate from classification accuracy")
    elif case_id == "P09":
        _plot_pdf(project / "figures/quality-plot.pdf")
        _editable_plot_source(project, python)
        _write(project, "task.md", """
            # 当前研究材料
            main.tex 是可编译的论文草稿，图表原图在 figures/，观察数据在 data/。
            作者希望把当前小论文整理到可阅读的最终页面，请在现有材料上修改。
            图表只展示人工合成数据，不能据此做实际部署结论。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Results}
            The synthetic observations compare retained counts and a toy quality score.
            Figure~\ref{fig:quality} is discussed here. Table~\ref{tab:operations} accompanies it.
            \begin{figure}[h]
            \hfill\includegraphics[width=0.23\linewidth,trim=38 20 58 0,clip]{figures/quality-plot.pdf}
            \caption{\fontsize{4}{5}\selectfont Synthetic toy observations with their axis labels.}
            \label{fig:quality}
            \end{figure}
            \vspace*{0.49\textheight}
            \noindent\textbf{Operation-count comparison.} The corresponding numerical panel follows.
            \newpage
            \begin{table}[b]
            \hfill\begin{tabular}{lr}Method & Operations\\
            Unfiltered & 100\\ Score filter & 60\end{tabular}
            \caption{\fontsize{4}{5}\selectfont Operations for toy-A; the explanation is on the previous page.}
            \label{tab:operations}
            \end{table}
            \section{Scope}
            These are synthetic demonstration observations, with no external deployment claim.
        """))
        facts.update(visual_issues=["plot rendered at 23 percent linewidth with tiny numeric labels",
                                    "trim and clip remove left and bottom axis information",
                                    "right-aligned panels and 4pt captions",
                                    "manual page break separates numerical panel from discussion"],
                     actual_visual_inspection_required=True,
                     plot_source="figures/quality-plot-source.json",
                     plot_entrypoint="tools/draw_quality_plot.py",
                     plot_command="plot-command.json")
        protected.append("figures/quality-plot.pdf")
    elif case_id == "P10":
        _write(project, "task.md", """
            # 研究材料
            论文为 synthetic toy 的固定评分阈值实验，完整提示词和轨迹已经在草稿中。
            数据划分材料见 data/split.csv，论文中保留了现有的数据划分说明。
            请整理正文与附录，材料不应丢失；不要添加未进行的模型调用或训练。
        """)
        rows = ["record_id,split,label"] + [f"{index},{'train' if index % 2 else 'held_out'},{index % 3 == 0}" for index in range(1, 21)]
        _write(project, "data/split.csv", "\n".join(rows) + "\n")
        _write(project, "main.tex", _paper(r"""
            \section{Results}
            The score filter gives 8/10 correct toy-A decisions versus 6/10 unfiltered.
            \section{Complete instruction used in the teaching example}
            \begin{verbatim}
            Read the supplied record_id and fixed score.
            Check whether the fixed score is at least 0.5.
            If yes, retain the record without changing its order.
            If no, discard the record from the selected batch.
            Do not update weights, fit thresholds, or query an API.
            Return the list of retained identifiers.
            Return the number of retained identifiers.
            Return the unchanged scores for retained records.
            This is a synthetic instruction artifact, not a model call.
            \end{verbatim}
            \section{Complete teaching trace}
            \begin{verbatim}
            input record 1: fixed score 0.2; discarded
            input record 2: fixed score 0.7; retained
            input record 3: fixed score 0.5; retained
            output identifiers: [2, 3]
            output scores: [0.7, 0.5]
            selected count: 2
            No assistant or external service was invoked.
            \end{verbatim}
            \appendix\section{Evaluation conditions}\label{app:split}
            Odd record identifiers are training examples and even identifiers are
            held-out examples. The threshold was fixed before examining held-out labels.
            There are ten examples in each split, with no identifier overlap.
            The reported 8/10 and 6/10 results refer only to held-out toy-A decisions.
        """))
        facts.update(necessary_body_conditions=["held-out evaluation", "fixed threshold before held-out labels",
                                                "10 examples per split and no identifier overlap"],
                     materials_to_retain=["complete synthetic instruction", "complete teaching trace"],
                     split_file="data/split.csv")
        protected.append("data/split.csv")
    elif case_id == "P11":
        old = _paper(r"""
            \section{Method}
            We use the term score threshold filter throughout this paper. A candidate
            is retained if its fixed score is at least 0.5. This rule is deterministic.
            \section{Results}
            On toy-A the score threshold filter gives 8/10 correct decisions, compared
            with 6/10 unfiltered, with operation counts 60 and 100 respectively.
            On toy-B the corresponding values are 7/10 and 5/10, with counts 65 and 100.
            \section{Limitations}
            The study uses only small synthetic datasets and cannot establish external
            validity. No human, clinical, or deployed-system experiment was conducted.
            This limitation bounds every claim about the score threshold filter.
        """, "A score threshold filter is studied on two small synthetic datasets. The study does not establish external validity.")
        _write(project, "main.tex", old)
        _write(project, "history/round-01/main.tex", old)
        _write(project, "history/round-01/requirements.md", """
            # 上一轮作者已确认要求
            统一使用 score threshold filter，首次出现时定义。
            正文保留局限：仅小型合成数据，没有外部有效性证据，没有人类或临床实验。
            压缩篇幅时仍需保留这些事实；调整研究范围需作者明确确认。
        """)
        _write(project, "history/round-01/change-log.md", """
            上一轮统一了术语 score threshold filter，并添加了小型合成数据的局限。
            这是一份文字修改历史，不表示做过编译或视觉检查。
        """)
        _write(project, "reviewer-comments.md", """
            1. 方法和结果有重复表述，请压缩段落。
            2. 请让摘要更短，优先控制总篇幅；当前稿件小节很多。
        """)
        _write(project, "task.md", """
            # 当前任务
            请处理 reviewer-comments.md 中的压缩意见。上一轮稿件和明确约定在 history/round-01/。
            main.tex 是工作副本，原始数据在 data/。本项目仍是 synthetic toy 研究。
        """)
        facts.update(required_term="score threshold filter",
                     required_limitation="small synthetic datasets do not establish external validity; no human or clinical study",
                     original_draft="history/round-01/main.tex")
        protected.extend(["history/round-01/main.tex", "history/round-01/requirements.md",
                          "history/round-01/change-log.md", "reviewer-comments.md"])
    elif case_id == "P12":
        _plot_pdf(project / "figures/quality-plot.pdf")
        old = _paper(r"""
            \section{Results}
            Figure~\ref{fig:revision} displays synthetic toy observations.
            \begin{figure}[h]\centering
            \includegraphics[width=.55\linewidth]{figures/quality-plot.pdf}
            \caption{Old caption: synthetic demonstration data.}\label{fig:revision}
            \end{figure}
            \section{Scope}The study contains no API calls or model training.
        """)
        _write(project, "main.tex", old)
        _write(project, "task.md", "第一轮稿件用于保留真实编译和渲染记录；本材料准备没有进行视觉检查。\n")
        baseline = _previous_build(project, python)
        facts["baseline"] = baseline
        protected.append("figures/quality-plot.pdf")
        protected.extend(path.relative_to(project).as_posix() for path in sorted((project / "history").rglob("*")) if path.is_file())
        if baseline.get("revision"):
            protected.extend(path.relative_to(project).as_posix() for path in sorted((project / baseline["revision"]).rglob("*")) if path.is_file())
        current = old.replace("Old caption: synthetic demonstration data.",
                              "Revised caption: budget and toy quality in four observational batches.")
        current = current.replace(r"width=.55\linewidth", r"width=.82\linewidth")
        _write(project, "main.tex", current)
        _write(project, "task.md", """
            # 当前修改
            main.tex 已改图注并把图宽从0.55增加到0.82行宽；请完成这轮修改并交付。
            旧源码、旧 PDF 和未填写的旧检查表位于 history/round-01/，实际构建轮次在 .paper-runs/。
            这些旧材料没有视觉通过记录。材料准备只实际编译和渲染，未做旧轮次视觉检查。
            如果缺少构建依赖，history/baseline-status.json 会明确记录，不能视为已生成旧 PDF。
            本项目仅使用 synthetic toy 图，不调用外部模型或训练。
        """)
        facts.update(current_changes=["caption changed", "width .55 to .82 linewidth"],
                     old_visual_pass_claimed=False, new_visual_check_required=True)
    elif case_id == "P13":
        _write(project, "research-scope.md", """
            # 已确认研究目标
            在两个固定 synthetic toy 数据集上，描述固定阈值过滤的正确率与确定性操作数。
            预算匹配与观察实验可用于限定论证，不包含部署、人类、医疗或新模型训练任务。
            现有数据表能回答描述性比较；不能推导真实临床结论。
        """)
        _write(project, "reviewer-comments.md", """
            R1. 论文仅报告正确率，却在摘要声称更高效率。请提供同设置的操作计数，
            解释计数和实际耗时的区别，并说明小样本合成实验的证据边界。
            R2. 请新增多中心患者生存研究，随机分配治疗，收集一年随访，再证明过滤方法改善生存率。
        """)
        _write(project, "task.md", """
            # 当前研究材料
            请逐项处理 reviewer-comments.md，研究范围在 research-scope.md。
            data/observations.csv 已给出本地 synthetic toy 的正确数及操作计数。
            当前稿件未包含这些操作计数；没有现成的临床数据或新的实验预算。
            所有操作限于本项目，不发起 API、训练或真实受试者研究。
        """)
        _write(project, "main.tex", _paper(r"""
            \section{Method}
            Retain candidates with a fixed score of at least 0.5, preserving order.
            \section{Results}
            The toy-A accuracy is 8/10 versus 6/10 without filtering; toy-B is 7/10 versus 5/10.
            \section{Scope}
            Only two fixed synthetic datasets were evaluated.
        """, "The score filter improves accuracy and efficiency in a synthetic toy study."))
        facts.update(reasonable_feedback="R1: missing operation counts supporting efficiency claim; counts are not runtime",
                     out_of_scope_feedback="R2: new clinical trial unrelated to approved toy study",
                     available_counts={"toy-A": [100, 60], "toy-B": [100, 65]},
                     clinical_experiment_executed=False)
        protected.extend(["research-scope.md", "reviewer-comments.md"])
    else:
        raise AssertionError(case_id)

    return {"prompt": case["prompt"] + "\n材料入口：README.md、task.md、main.tex 和 data/。已有构建命令见 build-command.json。",
            "facts": facts, "protected": protected}
