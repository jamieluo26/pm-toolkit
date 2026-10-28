# 文档中心

本地工作台已于2026-10-28公开并远端验收。已验收运行功能基线为 [`d54e6586f4a173dea73155f8564aafbcfb5d9d25`](https://github.com/jamieluo26/pm-toolkit/commit/d54e6586f4a173dea73155f8564aafbcfb5d9d25)：356 文件、147 项回归通过。走读与试用材料的内容、操作证据见[独立验收记录](verification-promotion.md)；运行、判断和发布的证据分别记录。

## 第一次使用

1. 推荐按[本地工作台启动说明](local-workbench.md)安装固定依赖、启动一次，再从 Chrome 创建、修订与交接。macOS 已实测；Linux 首用未验，Windows 不支持此服务器。
2. [走读演示](../walkthrough.html)及[文字版](walkthrough.md)说明用途和操作过程；[开始体验](../start.html)进入启动指引，[试用包](../trial/README.md)引导记录一次合成任务的实际体验。
3. 想先读预制材料，可打开完整副本的 `index.html` 或[进阶与历史案例](../START-HERE.md#进阶与历史路径)。GitHub 的 HTML 链接显示源码。
4. CLI 使用者看[生命周期说明](lifecycle.md)，依赖不齐看[环境诊断](support-tools.md)，失败/升级看[维护说明](maintenance.md)和[FAQ](faq.md)。

## 本地运行工作台

[启动与操作说明](local-workbench.md)提供可视化创建、真实 Python 生成、准确差异修订、逐项观察和交接下载；以上运行能力已随 `d54e6586` 公开。原核心、固定组件和 Skill 内容沿用，工作台不调用模型。[工作台验证记录](verification-local-workbench.md)区分发布前候选验证与远端验收。

## 保留的工作台交互原型

打开[工作台交互原型](../prototypes/workbench/index.html)，结合[原型说明](workbench-prototype.md)审阅。这是用于设计验证的工作台交互原型；浏览器草案不调用 Python、不生成 DOCX，这个旧入口与新的本地运行入口分开保留。产品目标与适用对象见[产品定位](product-positioning.md)，运行条件与支持边界见[支持范围](support-scope.md)。

## 按任务找说明

| 任务 | 文档 | 对应材料 |
|---|---|---|
| 本地运行与首次操作 | [本地工作台](local-workbench.md) · [支持范围](support-scope.md) | 创建、修订、观察与交接 |
| 一轮产品迭代 | [完整步骤](lifecycle.md) · [统一输入合同](task-spec.md) | [阅读任务](../examples/lifecycle/README.md) |
| 从问题到需求 | [需求澄清](../playbooks/workpacks/01-discover.md) · [范围规格](../playbooks/workpacks/02-specify.md) | [空白任务](../templates/task.json) · [已填任务](../examples/lifecycle/before.json) |
| 集合原型 | [运行说明](prototype-loop.md) · [规格合同](prototype-spec.md) | [个人任务板](../examples/personal-tasks/spec.json) |
| 表单有限状态流 | [运行说明](form-cli.md) · [规格合同](form-spec.md) | [请求规格](../examples/request-flow/spec.json) |
| 评审与修订 | [工作包](../playbooks/workpacks/04-review.md) · [完整命令](lifecycle.md) | [反馈](../examples/lifecycle/feedback.json) · [决定](../examples/lifecycle/decisions.json) |
| 检查、问题与交接 | [验证交付](../playbooks/workpacks/05-deliver.md) | [观察摘要](../examples/lifecycle/browser-observations.md) · [交接包](../examples/lifecycle/delivery-output/delivery.md) |
| 版本说明与产品资产 | [复盘资产](../playbooks/workpacks/06-retrospect.md) | [版本说明](../examples/lifecycle/delivery-output/release-notes.md) · [手册](../examples/lifecycle/delivery-output/product-handbook.md) |
| 文字 Skill | [当前使用说明](skills-v1.md) | 六项入口、供料与人工核对位置 |
| 运行准备与静态 HTML 检查 | [支撑工具](support-tools.md) | 明确选择的本地文件 |
| 升级或恢复 | [维护说明](maintenance.md) · [FAQ](faq.md) | [版本记录](../CHANGELOG.md) |

## CLI 备选：跑通同一版

在工具包根目录运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python pm_doctor.py
.venv/bin/python pm_task.py build --source examples/lifecycle/before.json --output ../reading-before
.venv/bin/python pm_task.py check --source examples/lifecycle/before.json --output ../reading-before
```

打开输出的 `journey.html`。Word 与 PRD 的内容来自同一任务版本；实际界面、Word 排版和业务适用性仍需核对。Windows 的 CLI 首用尚未验收；本地工作台服务器不支持 Windows。

输出目录需尚不存在，父目录需已存在。未决材料可能合法生成 `HOLD`；查看原因而不是删除问题。完整 review/deliver 命令见[生命周期说明](lifecycle.md)。

## 只使用独立模块

集合和表单模块只需 Python 3.10+ 标准库；完整任务的 Word 使用 requirements.txt 中的固定依赖。独立模块输出各自规格合同，不自动把另一个任务的 Word 接过来。

```sh
python3 pm_flow.py build --source examples/personal-tasks/spec.json --output ../my-task-board
python3 pm_flow.py check --source examples/personal-tasks/spec.json --output ../my-task-board
python3 pm_form.py build --source examples/request-flow/spec.json --output ../my-request
python3 pm_form.py check --source examples/request-flow/spec.json --output ../my-request
```

## 保留的历史路径

| 版本 | 文档 | 命令 |
|---|---|---|
| v0.1 手动交接 | [原 CLI](cli.md) · [原走读](../examples/reading-list/output/journey.html) | `pm_toolkit.py init/demo/build/check` |
| v0.2 评审工作包 | [说明](review-workpack.md) · [历史 Skill 边界](skills-v02.md) | `pm_review.py demo/check` |
| v0.3 集合与评审增量 | [说明](prototype-loop.md) · [验证摘要](verification-v03.md) | `pm_flow.py build/check/review/review-check` |

历史命令保留，完整任务走新适配器。生成、内容一致性、浏览器、视觉与人工验收各自支持不同结论；[证据质量说明](../playbooks/evidence-quality.md)解释这些层次。当前工作台证据见[工作台验证记录](verification-local-workbench.md)；v1.0 技术链、Skill 显式调用和代理使用评测见[历史验证记录](verification-v1.md)，后续独立范围见[路线图](../ROADMAP.md)。

[当前验证与适用边界](verification-local-workbench.md)
