# 维护这个仓库

本仓库维护论文写作经验及其项目级安装材料。`requirements.md` 保存用户原文；`skills/paper-writing/references/rules.md` 是 Codex、Claude Code、Cursor、Google Gemini CLI 和 Google Antigravity 共同使用的权威规则。平台入口由 `tools/profile.py` 生成，`--agents` 默认全部五平台，修改规则时不要另维护各平台正文副本。

Codex/Antigravity 共用内联 `AGENTS.md` 区域；Gemini 在 `GEMINI.md` 使用原生相对导入，三者共用 `.agents/skills`。共享文件直到最后一个使用平台卸载后才移除。保持项目范围，不修改全局上下文文件名、权限或账户；发现约定和更新示例见 `docs/platforms.md`。

只改请求涉及的内容。改脚本后运行 `python3 -m unittest discover -s tests -v`；改构建流程时，用小型论文实际编译、渲染并查看页面。编译成功或图片生成均不能代替视觉检查记录。需要编译器时先确认实际可执行文件及版本，依赖保留在当前任务环境中。

运行记录保存在独立输出目录；修复后新建轮次，不覆盖失败证据。发布材料使用通用路径和示例，不加入凭据、个人机器配置或任务原始日志。
