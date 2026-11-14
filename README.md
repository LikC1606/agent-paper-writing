# 论文写作经验

把个人的论文写作要求安装到具体研究项目，使 Codex、Claude Code、Cursor、Google Gemini CLI 和 Google Antigravity 使用同一份规则。内容包括原始 13 条约定、写作 Skill、工作流程、参考资料、记录模板，以及保存编译和视觉检查证据的工具。

`clone` 下载经验仓库；对论文项目执行 `install` 后，才会生成该项目的 agent 入口。每个需要这些规则的研究项目分别安装，范围限于项目。

## 下载与安装

需要 Python 3.10 或更新版本。先确认 `python3` 的真实解释器和工作目录；已有环境可能把同名命令包装成容器入口。以下将研究项目记为 `/path/to/research-project`。

```bash
git clone https://github.com/LikC1606/agent-paper-writing.git
cd agent-paper-writing
python3 tools/profile.py install --project /path/to/research-project --dry-run
python3 tools/profile.py install --project /path/to/research-project
python3 tools/profile.py check --project /path/to/research-project
```

`--agents` 接受 `codex claude cursor gemini antigravity`，默认操作全部五平台；例如 `--agents gemini antigravity` 只选择两个 Google 平台。安装器从 `profile.json` 指定的共同规则生成项目入口：Codex/Antigravity 共用内联 `AGENTS.md`，Gemini 用 `GEMINI.md` 原生相对导入；这三个平台共用 `.agents/skills`。已有内容和安装历史由安装器处理。配置不修改全局 `context.fileName`、权限、账户认证或模型设置。

安装后的工具位置稳定为 `.agent-experience/agent-paper-writing/tools/paper.py`。进入研究项目并开始新会话，再让 agent 按论文写作规则处理实际任务。完整入口、升级、客户端核对及两个仓库同时安装的步骤见 [平台兼容说明](docs/platforms.md)。

## 使用写作规则

先读 [原始要求](requirements.md) 和 [权威规则](skills/paper-writing/references/rules.md)。按 [流程](skills/paper-writing/references/workflow.md) 明确研究问题、主张和证据，使用 [模板](skills/paper-writing/assets/templates.md) 保留术语、实验论证、图表检查及轮次记录。[参考资料](skills/paper-writing/references/reading.md) 给出可核验的写作方法与论文示例。

五个平台共享同一份权威规则；规则更新后重新安装。规则约束写作选择，编译工具保存真实操作证据。结果质量仍需要研究判断和实际查看。

## 保存编译与页面

构建需要已有 LaTeX 引擎，以及 Poppler 的 `pdftoppm`。例如 Ubuntu 可安装 `latexmk`、论文所需的 TeX Live 包和 `poppler-utils`；其他环境沿用项目已有引擎。工具本身只用 Python 标准库，不自动安装这些依赖。

在论文项目中执行：

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source main.tex --engine latexmk
```

每次调用新建 `.paper-runs/<独立轮次>/`：先快照论文项目，保存源码哈希和 Git 状态，再在快照中编译到该轮 `build/`，将 PDF 全部页面渲染到 `pages/`，保存命令、日志及检查表。项目范围应是专用论文目录；`.git`、`.agent-experience`、`.paper-runs`、实验工具的 `runs`、虚拟环境等生成目录不进入源码快照。复现所需图、表和数据应放在论文源目录中，或由已有构建流程显式生成；外部实验结果保留可追溯索引。用重复的 `--exclude 相对路径` 排除无关文件或目录；符号链接应先整理为项目内的实际文件，以便快照可复现。

`--engine auto` 优先使用现有 `latexmk`、`tectonic`，随后尝试 `pdflatex`、`xelatex`、`lualatex`。后三种引擎运行两遍，不额外编排 BibTeX/Biber；有文献或特殊构建步骤时使用项目已有 `latexmk` 配置或构建命令。

例如项目已有接受输出目录的脚本：

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source paper.tex --pdf-name paper.pdf -- ./build-paper.sh '{output}'
```

`--` 后是直接执行的参数列表，支持 `{source}`（主文件相对路径）、`{workspace}`（本轮源码快照）和 `{output}`（本轮构建目录）。命令在源码快照中执行，需要把新 PDF 写到 `{output}`；shell 管道等逻辑保留在已有脚本中。可用 `--output-root /path/to/paper-revisions` 指定统一存储位置，用 `--renderer /path/to/pdftoppm` 指定实际渲染器。

## 实际查看并记录

`build` 成功返回 `awaiting_visual_review`。先打开输出的 PDF 或 `pages/page-*.png`，逐页查看；再复制本轮 `review-template.json` 为自己的检查记录，填入检查者和逐页发现。七项检查为尺寸、位置、字体、留白、对齐、可读性及论证对应关系，填写 JSON 布尔值 `true` / `false`；有任何未通过项，该页 `status` 写 `fail`，全部通过才写 `pass`。

保留表单中本轮的 `revision_id`。即使两轮 PDF 字节相同，也不能提交上一轮的检查记录。没有该字段的旧表单须新建轮次并重新查看；已经归档的旧状态仍可读取，历史文件不改写。

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py review --revision .paper-runs/本轮目录 --record /path/to/completed-review.json
python3 .agent-experience/agent-paper-writing/tools/paper.py status --revision .paper-runs/本轮目录
```

检查记录验证必须覆盖所有页面并写明实际发现，且绑定当前 PDF 与渲染页。它保存填写者声明的视觉检查，不自动判断记录者是否真的看过页面。每次登记都保存新文件，旧记录保留。

编译、渲染或视觉检查失败均返回非零状态。保留失败轮次，定位并修复原项目后再次 `build`，新轮次不会覆盖旧 PDF、源码或日志。长期运行记录应纳入当前项目约定的私有持久存储；经验仓库的 Git 历史用于迁移规则与工具。

## 更新、卸载与检查

```bash
git pull --ff-only
python3 tools/profile.py install --project /path/to/research-project
python3 tools/profile.py check --project /path/to/research-project
python3 tools/profile.py uninstall --project /path/to/research-project --dry-run
python3 tools/profile.py uninstall --project /path/to/research-project
```

旧三平台用户在 `git pull` 后执行默认 `install`、`check` 即加入五平台；只保留原三平台则在命令中显式加 `--agents codex claude cursor`。卸载前可先查看预览。共享入口和技能等到最后一个使用它的平台卸载后才移除。论文源码与 `.paper-runs/` 是项目工作产物，按项目自己的保存要求维护。

开发验证：

```bash
python3 -m unittest discover -s tests -v
```

验证范围和实际结果见 [verification.md](verification.md)。

[逐条测试说明](docs/testing.md) 包含 51 项自动检查、P01–P13 的真实客户端验收命令，以及 CI 的编译依赖和测试现场保存方式；实际页面查看与辅助续跑分别记录。
