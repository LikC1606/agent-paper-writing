# 如何验证 13 条写作要求

研究问题、术语、叙事、实验解释和审稿取舍需要结合真实论文判断。自动测试覆盖原文与安装完整性，以及编译、页面和检查记录的真实状态；通过表单校验不等于通过写作或视觉质量检查。

## 运行自动测试

先确认实际解释器及工作目录，再在本仓库运行：

```bash
python3 -c 'import os, sys; print(sys.executable); print(os.getcwd()); print(sys.version)'
python3 -m unittest discover -s tests -v
```

本轮新增 17 项：`test_paper.py` 的 12 项工具行为测试、`test_paper_integration.py` 的 1 项真实编译集成，以及 `test_requirement_contract.py` 的 4 项原文、打包与迁移测试。本机共 38 项通过。

真实集成用已有 `pdflatex` 和 Poppler `pdftoppm` 编译两页小论文，核对新 PDF、PNG、两遍编译记录和待视觉检查状态。本地依赖缺失时该项明确 `skip`，其他测试继续运行。单独运行：

```bash
python3 -m unittest discover -s tests -p test_paper_integration.py -v
```

CI 在 Ubuntu 安装 `texlive-latex-base` 和 `poppler-utils`，使用 `--no-install-recommends`；两页 fixture 只使用 `article`、基本表格和交叉引用，不依赖额外 LaTeX 宏包。Python 3.10、3.12 两个任务均设置 `PAPER_TEST_REQUIRE_REAL_BUILD=1`，缺少 `pdflatex` 或 `pdftoppm` 会失败，不能以跳过集成取得通过。要在本地要求相同条件：

```bash
PAPER_TEST_REQUIRE_REAL_BUILD=1 python3 -m unittest discover -s tests -p test_paper_integration.py -v
```

CI 无论成功或失败都上传 `writing-checks-python-<版本>` artifact，保留 14 天。其中包括依赖安装与版本日志、测试命令和输出，以及临时案例的源码、命令记录、失败日志、PDF、页面和检查表；隐藏的 `.paper-runs` 也包含在内。artifact 仅来自独立测试现场，不收集账户配置、凭据或原始模型会话。真实构建通过仍只证明编译和渲染完成，不代表视觉质量通过。

需要保留所有测试现场时，选择全新轮次：

```bash
mkdir -p /absolute/evidence/new-round
PROFILE_TEST_ARTIFACT_DIR=/absolute/evidence/new-round/profile \
PAPER_TEST_ARTIFACT_DIR=/absolute/evidence/new-round/paper \
python3 -m unittest discover -s tests -v \
  > /absolute/evidence/new-round/unittest.log 2>&1
```

案例使用唯一子目录，保留 CLI 调用、源码、失败日志、PDF、页面和检查记录。多数单元测试使用可控的编译/渲染替身，目的在于验证状态与记录；替身的 `pass` 记录明确写明它不代表实际视觉检查。

## 逐条覆盖

每条均有 [真实 agent 场景](../tests/fixtures/requirements.json)。

| 条目 | 自动测试实际验证什么 | 仍需观察 agent 的行为 |
| --- | --- | --- |
| P01 问题和故事 | 原文和规则完整传递 | 在冲突草稿中先明确问题、证据和故事再润色 |
| P02 研究逻辑 | 原文和规则完整传递 | 将开发日志改为问题、方法、验证和结论的论证 |
| P03 专业稳定用词 | 原文和规则完整传递 | 名称准确、首次定义，全文及图注统一 |
| P04 连贯推进 | 原文和规则完整传递 | 摘要和引言完整推进，主张一致、句段承接 |
| P05 学习参考 | 参考资源随真实技能完整安装，链接迁移后仍有效 | 核验来源，说明学习位置及对当前论文的具体用途 |
| P06 实验信息量 | 原文和规则完整传递 | 证据充分，比较和控制有用，缺实验时不编造 |
| P07 实验解释 | 原文和规则完整传递 | 每项实验交代问题、实际结果、含义和推断边界 |
| P08 图表服务论证 | 检查记录要求含论证对应项 | 实际确认图表支持主张、正文解释充分且最终位置合适 |
| P09 反复视觉检查 | 页面改动/删除使旧检查失效；重复页、未知页或失败项冒充通过均拒绝 | 真正查看尺寸、位置、字体、留白、对齐、可读性并修复 |
| P10 正文与附录 | 原文和规则完整传递 | 保留理解主张必需条件，将完整材料放入可引用附录 |
| P11 保留旧要求 | 原始要求逐条保护；更新留存历史；新轮次不继承旧视觉通过 | 逐项核对具体论文旧要求，冲突取舍明确讨论与记录 |
| P12 每轮编译查看 | 不同 PDF 或同字节 PDF 的旧轮检查均不能用于新轮；缺轮次身份的旧表单拒绝登记，历史状态仍可读；编译失败不渲染；第二遍失败留日志；既有脚本可从带空格路径复现；真实两页编译后仍待视觉检查 | 实际查看新页面并记录发现，不能用编译或渲染替代 |
| P13 审稿服务目标 | 原文和规则完整传递 | 处理真实证据缺口，对偏离研究目标的请求解释取舍 |

工具行为方法见 `tests/test_paper.py` 和 `tests/test_paper_integration.py`，每项新增测试注释列出 P 编号。`test_requirement_contract.py` 验证原文、五平台完整规则、全部技能资源、相对链接、更新备份以及不依赖原经验源码的项目迁移。

同字节 PDF 的跨轮回归先复现了旧记录被错误接受，再修复为表单携带 `revision_id`，登记时必须与该轮目录名一致。这个身份不依赖绝对路径，项目整体迁移不改变轮次。已归档的旧检查状态继续读取，不改写历史；缺少身份的旧表单须新建轮次并实际重新检查。

## 真实 agent 场景怎么使用

`tests/fixtures/requirements.json` 按 P01–P13 保存 `setup`、`prompt`、`pass_if`、`fail_if` 和 `evidence`。它们定义实际写作验收；准备好的场景不代表已经在模型上跑过。

1. 为选定案例准备独立论文项目，保存旧稿、旧要求、真实结果及初始哈希。需要视觉测试时先提供实际可编译的小论文。
2. 安装目标平台规则并执行 `check`，在项目中新开客户端会话，只发送案例 `prompt`。不要把评分条件当作 agent 已完成操作的证据。
3. 保存全部回复、工具轨迹、diff、结果来源、编译日志、PDF 和页面。按通过/失败条件检查实际修订；视觉项必须查看真实页面。
4. 每个条目分别登记通过、失败或未验证、证据位置及未完成项。缺依赖、未查看或判断无法确认时保留未验证；修复后新轮次补测，旧记录不覆盖。

可以在 Codex、Claude Code、Cursor、Gemini CLI 和 Antigravity 复用同一套场景。自动 unittest 不发起模型请求，也不把文字存在、编译成功或模拟表单当成 agent 遵循规则的证明。
