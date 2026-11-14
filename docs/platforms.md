# 项目级平台兼容

两个经验仓库用于论文相关研究项目。`clone` 下载规则与工具；对研究项目执行 `install` 才会生成客户端入口。`--agents` 接受 `codex claude cursor gemini antigravity`，省略时操作全部五平台；`install` 与 `uninstall` 可用 `--dry-run` 预览，`check` 为只读内容检查。

## 入口与共同正文

| 平台 | 项目规则入口 | 项目 Skill 位置 |
| --- | --- | --- |
| Codex | `AGENTS.md` 内联核心规则 | `.agents/skills/<skill>/` |
| Claude Code | `CLAUDE.md` 内联核心规则 | `.claude/skills/<skill>/` |
| Cursor | `.cursor/rules/<profile-id>.mdc`，`alwaysApply: true` | `.cursor/skills/<skill>/`，供读取详细流程 |
| Google Gemini CLI | `GEMINI.md` 原生相对导入核心规则 | `.agents/skills/<skill>/` |
| Google Antigravity | 与 Codex 共用 `AGENTS.md` 内联规则 | 与 Codex/Gemini 共用 `.agents/skills/<skill>/` |

权威正文仍在每个经验仓库的 `skills/<skill>/references/rules.md`。安装器生成平台入口；公共工作流和工具位于研究项目的 `.agent-experience/<profile-id>/`。两个 profile 分别为 `agent-engineering` / `research-engineering` 与 `agent-paper-writing` / `paper-writing`。

Gemini 的受管区域使用原生导入，例如：

```markdown
@./.agent-experience/agent-engineering/skills/research-engineering/references/rules.md
@./.agent-experience/agent-paper-writing/skills/paper-writing/references/rules.md
```

Antigravity 同时发现项目 `AGENTS.md` 与 `GEMINI.md`。其 `@filename` 只解析成文件引用，不内联正文；完整规则已由共享 `AGENTS.md` 提供。因此不用再生成 `.agents/rules` 中的第三份规则，也不依赖跨文件内容去重。Antigravity 的 `@[label](path)` 才是内联语法，与普通 Markdown 链接及 Gemini 的导入语义区分使用。

共享入口或技能仍有消费者时保留：例如卸载 Codex 后，Antigravity 使用的 `AGENTS.md` 区域和 Gemini/Antigravity 使用的 `.agents/skills` 继续存在。最后一个使用该区域或技能的平台卸载后才移除受管内容；其他 profile 的区域、用户原文及研究运行历史保留。

安装只操作指定项目，不修改全局 `context.fileName`、权限、账户、认证或模型。已有全局设置和更具体的项目规则可能改变客户端发现过程，应在客户端核对实际加载结果。

## 两个仓库安装到同一研究项目

从存放经验仓库的目录执行，将示例项目路径替换为实际路径：

```bash
git clone https://github.com/LikC1606/agent-engineering.git
git clone https://github.com/LikC1606/agent-paper-writing.git
python3 agent-engineering/tools/profile.py install --project /path/to/research-project --dry-run
python3 agent-paper-writing/tools/profile.py install --project /path/to/research-project --dry-run
python3 agent-engineering/tools/profile.py install --project /path/to/research-project
python3 agent-paper-writing/tools/profile.py install --project /path/to/research-project
python3 agent-engineering/tools/profile.py check --project /path/to/research-project
python3 agent-paper-writing/tools/profile.py check --project /path/to/research-project
```

一个项目中两套规则分别占用自己的命名区域与 Skill。实验工具稳定在 `.agent-experience/agent-engineering/tools/run.py`，论文工具在 `.agent-experience/agent-paper-writing/tools/paper.py`。

## 从原三平台升级

更新两个经验仓库，再重新安装和检查，默认加入全部五平台：

```bash
git -C agent-engineering pull --ff-only
git -C agent-paper-writing pull --ff-only
python3 agent-engineering/tools/profile.py install --project /path/to/research-project
python3 agent-paper-writing/tools/profile.py install --project /path/to/research-project
python3 agent-engineering/tools/profile.py check --project /path/to/research-project
python3 agent-paper-writing/tools/profile.py check --project /path/to/research-project
```

如只要原三平台，在上述两仓库的 `install` 和 `check` 命令中均显式加 `--agents codex claude cursor`。这指定本次操作的平台，不会卸载已安装的 Google 适配；移除已有平台请显式执行对应 `uninstall`。

也可只添加 Google 平台：

```bash
python3 agent-engineering/tools/profile.py install --project /path/to/research-project --agents gemini antigravity
python3 agent-paper-writing/tools/profile.py install --project /path/to/research-project --agents gemini antigravity
python3 agent-engineering/tools/profile.py check --project /path/to/research-project --agents gemini antigravity
python3 agent-paper-writing/tools/profile.py check --project /path/to/research-project --agents gemini antigravity
```

当仓库内容也发生更新时，局部安装会更新共同源码，但未选中的旧平台 Skill 或入口可能仍是旧内容，完整 `check` 会指出未对齐。建议对已经使用的全部平台执行安装和检查；需要全部五平台时直接省略 `--agents`。

## 客户端核对

从研究项目根目录打开新会话。Gemini CLI 可执行 `/memory show` 查看合并后的规则，`/memory reload` 重新加载，`/skills list` 核对 `research-engineering`、`paper-writing` 是否可见；确认导入的规则条目实际出现，再用小任务观察行为。`.agents/skills` 是官方支持的别名，优先于 `.gemini/skills` 中的同名技能，本适配不再生成重复副本。

Antigravity 从安装项目根目录打开，在 Customizations 中核对 Rules 与 Skills。它读取当前工作区及 Git 仓库根以内的父目录，不会因为访问某个子文件而自动加载更深层目录规则；非 Git 工作区只检查当前目录。新安装内容可通过新会话重新发现。文件安装检查不能代替真实客户端加载或任务行为验证；本次实际验证范围见仓库 `verification.md`。

## Antigravity 大小约束

Antigravity 官方规定单个规则在展开 includes 后最多 24,000 bytes；全部 global 与 `always_on` 规则还有 20,000 tokens 的合计预算。安装器在选择 `antigravity` 时检查项目 `AGENTS.md` 的直接文件字节数，`install` 与 `check` 遇到超限会报错。该检查不计算 include 展开后的内容，也不估算其他规则及全局配置的总 token；这些需在客户端核对。超限时先整理已有规则，再重新预览和安装。

若另外维护 Antigravity 原生规则，直接放在 `.agents/rules/*.md`，使用 `trigger: always_on` 等合法 YAML frontmatter；`alwaysOn` 或缺失 `trigger` 会被静默忽略。当前适配使用无需 frontmatter 的共享 `AGENTS.md`，无需新增此类文件。

## 卸载选择的平台

例如只移除 Google 适配，先预览再执行：

```bash
python3 agent-engineering/tools/profile.py uninstall --project /path/to/research-project --agents gemini antigravity --dry-run
python3 agent-paper-writing/tools/profile.py uninstall --project /path/to/research-project --agents gemini antigravity --dry-run
python3 agent-engineering/tools/profile.py uninstall --project /path/to/research-project --agents gemini antigravity
python3 agent-paper-writing/tools/profile.py uninstall --project /path/to/research-project --agents gemini antigravity
```

Codex 仍在使用时保留共享 `AGENTS.md` 和技能。省略 `--agents` 则卸载该 profile 的全部平台适配。运行记录按研究项目自己的持久存储约定保存。

## 官方依据

- Gemini CLI：[GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md)、[Skills](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md)、[Memory imports](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/memport.md)。分别核对上下文加载、技能目录别名及相对 `@./` 导入。
- Antigravity：[Rules](https://antigravity.google/docs/rules)、[Agent skills](https://antigravity.google/docs/skills)、[Customization discovery](https://antigravity.google/docs/customization-discovery)。分别核对规则入口与引用语义、技能位置，以及扫描范围和累计规则行为。

这些依据说明适配文件约定，不代表所有客户端版本均已实测；客户端结果以 `verification.md` 的实际记录为准。
