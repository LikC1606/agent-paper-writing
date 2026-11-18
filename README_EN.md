<!-- README_SYNC: source=50d87639cf9f0960bb39a3588d7760e98c6792aa; updated=2026-11-18 -->

[简体中文](./README.md) · English

# Agent Paper Writing

Give a manuscript project the same writing rules across five supported clients. Organize claims around evidence, and keep figures, builds, and page checks with the revision they belong to so feedback stays attached to the PDF you inspected.

[Star the repository](https://github.com/LikC1606/agent-paper-writing/stargazers) if you want to revisit the workflow.

[![Stars](https://img.shields.io/github/stars/LikC1606/agent-paper-writing)](https://github.com/LikC1606/agent-paper-writing/stargazers)
[![Checks](https://github.com/LikC1606/agent-paper-writing/actions/workflows/check.yml/badge.svg)](https://github.com/LikC1606/agent-paper-writing/actions/workflows/check.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](./tools/profile.py)
[![Issues](https://img.shields.io/github/issues/LikC1606/agent-paper-writing)](https://github.com/LikC1606/agent-paper-writing/issues)

## Install into a manuscript project

You need Git and Python 3.10 or later. If your `python3` command launches a container, check which interpreter and working directory the installer will see.

```bash
git clone https://github.com/LikC1606/agent-paper-writing.git
cd agent-paper-writing
python3 tools/profile.py install --project /path/to/research-project --dry-run
python3 tools/profile.py install --project /path/to/research-project
python3 tools/profile.py check --project /path/to/research-project
```

The default prepares project entry points for Codex, Claude Code, Cursor, Gemini CLI, and Antigravity. Use `--agents gemini antigravity` to select just those clients. Installation preserves existing project material and history. It leaves accounts, permissions, and global settings to the clients. Open a fresh client session in the manuscript project to confirm it loads the rules. See the [platform guide](./docs/platforms.md) for discovery and upgrades.

## From an argument to a reviewable PDF

1. Read the [13 original agreements](./requirements.md) and [canonical rules](./skills/paper-writing/references/rules.md). Agree on the research question, claims, evidence, and terminology.
2. Use the [writing Skill](./skills/paper-writing/SKILL.md), [workflow](./skills/paper-writing/references/workflow.md), [templates](./skills/paper-writing/assets/templates.md), and [reading notes](./skills/paper-writing/references/reading.md) to plan the manuscript, figures, and checks.
3. Run the build from the manuscript project. It needs an existing LaTeX engine and Poppler's `pdftoppm`. The tool does not install either.

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source main.tex --engine latexmk
```

Each build creates a revision under `.paper-runs/` and compiles a source snapshot. It records Git state, source hashes, commands, and logs. Find the PDF in that revision's `build/` and rendered pages in `pages/`. Use a dedicated manuscript directory, repeat `--exclude` to omit unrelated files, and preserve traceable references to external experiment artifacts. If your own build script can accept an output directory, pass it the current revision's build directory:

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py build --project . --source paper.tex --pdf-name paper.pdf -- ./build-paper.sh '{output}'
```

## Review each rendered page

A successful build is `awaiting_visual_review`. Open the PDF or its rendered pages and fill in that revision's `review-template.json` with the reviewer and per-page findings. Check sizing, placement, fonts, whitespace, alignment, legibility, and whether graphics support the claims. Mark a page `fail` if any check fails.

```bash
python3 .agent-experience/agent-paper-writing/tools/paper.py review --revision .paper-runs/REVISION --record /path/to/completed-review.json
python3 .agent-experience/agent-paper-writing/tools/paper.py status --revision .paper-runs/REVISION
```

The form is bound to its `revision_id`, PDF, and pages. The tool checks coverage and format; the reviewer supplies the visual judgment. Keep unsuccessful builds and open a new revision after fixing them. Archive the revision evidence using your project's storage policy.

## Update and verify

Pull updates in the source checkout, then preview and repeat the install. Uninstall also has a preview:

```bash
git pull --ff-only
python3 tools/profile.py uninstall --project /path/to/research-project --dry-run
python3 -m unittest discover -s tests -v
```

The [verification scope](./verification.md), [test instructions](./docs/testing.md), and [client results](./docs/behavior-results.md) document the environment, reproduction steps, and observed behavior. Use [Agent Engineering](https://github.com/LikC1606/agent-engineering) alongside this profile to track experiments and evaluations.

For an installation, build, or review problem, share a minimal reproduction in [Issues](https://github.com/LikC1606/agent-paper-writing/issues).
