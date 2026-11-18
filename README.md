<!-- README_SYNC: source=50d87639cf9f0960bb39a3588d7760e98c6792aa; updated=2026-11-18 -->

简体中文 · [English](./README_EN.md)

# 论文写作经验 · Agent Paper Writing

给论文项目安装一套 Agent 写作规则：用主张和证据组织文章，把图表、编译与逐页检查留在对应的修订轮次。五种客户端使用同一份项目规则。

觉得这个工作方式有用，可以 [Star 收藏](https://github.com/LikC1606/agent-paper-writing/stargazers)。

[![Stars](https://img.shields.io/github/stars/LikC1606/agent-paper-writing)](https://github.com/LikC1606/agent-paper-writing/stargazers)
[![Checks](https://github.com/LikC1606/agent-paper-writing/actions/workflows/check.yml/badge.svg)](https://github.com/LikC1606/agent-paper-writing/actions/workflows/check.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](./tools/profile.py)
[![Issues](https://img.shields.io/github/issues/LikC1606/agent-paper-writing)](https://github.com/LikC1606/agent-paper-writing/issues)

## 安装到论文项目

需要 Git 和 Python 3.10 或更新版本。若本机的 `python3` 是容器包装命令，先核对实际解释器和工作目录。

```bash
git clone https://github.com/LikC1606/agent-paper-writing.git
cd agent-paper-writing
python3 tools/profile.py install --project /path/to/research-project --dry-run
python3 tools/profile.py install --project /path/to/research-project
python3 tools/profile.py check --project /path/to/research-project
```

默认安装到指定项目的 Codex、Claude Code、Cursor、Gemini CLI 和 Antigravity 入口。用 `--agents gemini antigravity` 等参数选择客户端。安装器保留已有项目内容和历史；账户、权限和全局配置继续由客户端管理。在论文项目新开会话，核对客户端是否实际读到了规则。入口、兼容和更新方式见[平台说明](./docs/platforms.md)。

## 从论证到可查看的 PDF

1. 用[原始 13 条约定](./requirements.md)和[共同规则](./skills/paper-writing/references/rules.md)对齐研究问题、主张、证据与术语。
2. 通过[写作 Skill](./skills/paper-writing/SKILL.md)、[流程](./skills/paper-writing/references/workflow.md)、[模板](./skills/paper-writing/assets/templates.md)和[写作参考](./skills/paper-writing/references/reading.md)准备正文、图表及检查记录。
3. 在论文项目中运行下方命令。需要已有 LaTeX 引擎及 Poppler 的 `pdftoppm`；工具不安装这些依赖。

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source main.tex --engine latexmk
```

每次构建会在 `.paper-runs/` 新建轮次，在源码快照中编译，保存 Git 状态、源码哈希、命令和日志。PDF 在该轮的 `build/`，全部页面渲染到 `pages/`。项目目录应专用于论文；需要排除无关文件可重复传 `--exclude`，外部实验结果保留可追溯索引。已有构建脚本且能指定输出位置时，可改用：

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source paper.tex --pdf-name paper.pdf -- ./build-paper.sh '{output}'
```

## 记录逐页检查

构建成功的轮次显示 `awaiting_visual_review`。打开当轮 PDF 或渲染页，复制当轮的 `review-template.json` 填入检查者和逐页发现。七项检查包括尺寸、位置、字体、留白、对齐、可读性及图文是否支持论证，任何一项未通过都要将对应页标为 `fail`。

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py review --revision .paper-runs/REVISION --record /path/to/completed-review.json
python3 .agent-experience/agent-paper-writing/tools/paper.py status --revision .paper-runs/REVISION
```

检查记录绑定当前轮的 `revision_id`、PDF 和渲染页。它验证记录覆盖与格式；是否实际查看由检查者负责。修复失败后新建轮次，保留历史。长期归档按论文项目的存储约定办理。

## 更新和验证

拉取源仓库更新后重跑安装，先预览规则差异；卸载也支持预览。

```bash
git pull --ff-only
python3 tools/profile.py uninstall --project /path/to/research-project --dry-run
python3 -m unittest discover -s tests -v
```

[验证范围](./verification.md)、[检查方法](./docs/testing.md)和[真实客户端结果](./docs/behavior-results.md)分别说明验证环境、复现步骤和行为证据。需要同时管理训练和评测时，可在同一项目加装 [Agent Engineering](https://github.com/LikC1606/agent-engineering)。

发现安装、编译或视觉检查流程的问题，可以带上最小复现[开 Issue](https://github.com/LikC1606/agent-paper-writing/issues)。
