# 从这里开始

PM Toolkit 的本地工作台已经公开，发布基线为 `d54e658`（2026-10-28）。本目录提供完整操作演示和首批试用任务。工具用一份任务材料生成同版原型、PRD、Word，并把修改和检查记录带进交接。

## 先选一个目的

1. **先看一遍**：打开完整副本的 [walkthrough.html](walkthrough.html)，跟随同一个全新合成任务看创建、修订、实际观察、交接与恢复。[文字版](docs/walkthrough.md)可直接在 GitHub 阅读。
2. **自己动手**：打开 [start.html](start.html)，按说明启动真实 Python 工作台，再在 Chrome 使用终端显示的本机地址。[详细启动说明](docs/local-workbench.md)

GitHub 的 HTML 链接显示源码；下载并解压完整副本后，从 `index.html` 进入。静态首页不能代替 Python 服务。只有预制案例浏览不需要 Python。

## 首次试用

按 [首批 PM 试用包](trial/README.md)完成一个合成的个人灵感收集任务：导入 → 保存生成 → 修改筛选位置 → 逐条处理反馈 → 实际操作与记录 → 下载交接 → 重启恢复。辅助预期结果不等于已经实测通过。

当前实际验证 macOS + Chrome；服务器需要 Python 3.10+ 和 `fcntl`。Windows 不支持本服务器，Linux 首次安装及其他浏览器未验收。工作目录在源码外，单进程写入；启动后保持终端运行。

## 进阶与历史路径

| 需要 | 入口 |
|---|---|
| 直接使用 CLI 完成一轮任务 | [生命周期说明](docs/lifecycle.md)，`pm_task.py init/build/check/review/deliver` |
| 只生成有限集合 | [集合说明](docs/prototype-loop.md)，`pm_flow.py build/check` |
| 只生成有限表单 | [表单说明](docs/form-cli.md)，`pm_form.py build/check` |
| 向自己的助手提供文字审阅材料 | [六项 Skill 使用说明](docs/skills-v1.md) |
| 只看预制结果 | [阅读任务](examples/lifecycle/README.md)、[表单](examples/request-flow/output/prototype.html)、[个人任务板](examples/personal-tasks/output/prototype.html) |

工具不调用模型、不替人作决定；内容保留调用者输入，本身不脱敏。代理技术验证与真人采用分开记录，当前未采集真人使用效果。

## 保留的旧版入口

- [v0.1 手动交接与 Word CLI](docs/cli.md)，以及[旧走读案例](examples/reading-list/output/journey.html)。
- [v0.2 评审变更工作包](docs/review-workpack.md)，以及[页面](review.html)。
- [v0.3 集合原型与给定评审核对](docs/prototype-loop.md)，以及[页面](flow.html)。

旧版输入合同继续保留。整轮任务使用新的同任务适配器，不应将旧版独立 Word 和另一份规格的原型拼成同版证据。
