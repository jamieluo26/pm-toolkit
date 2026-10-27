# 文档中心

这份说明对应 **PM Toolkit v1.0 本地工作包**。首次使用先选一条路径，运行、判断和发布的证据分别记录。

## 第一次使用

1. 使用完整副本，双击根目录 `index.html`，先看[三个案例](../START-HERE.md#先体验一个案例)。GitHub 的 HTML 链接显示源码。
2. 整轮任务从[生命周期说明](lifecycle.md)开始；先读合成输入，再生成自己的新目录。
3. 想准备自己的输入，可以打开[任务准备页面](../prepare.html)，或用 `pm_task.py init` 创建待填写材料。
4. 本地依赖不齐时看[环境诊断](support-tools.md)；失败/升级看[维护说明](maintenance.md)和[FAQ](faq.md)。

## 按任务找说明

| 任务 | 文档 | 对应材料 |
|---|---|---|
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

## 跑通同一版

在工具包根目录运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python pm_doctor.py
.venv/bin/python pm_task.py build --source examples/lifecycle/before.json --output ../reading-before
.venv/bin/python pm_task.py check --source examples/lifecycle/before.json --output ../reading-before
```

打开输出的 `journey.html`。Word 与 PRD 的内容来自同一任务版本；实际界面、Word 排版和业务适用性仍需核对。Windows 将虚拟环境命令替换为 `.venv\Scripts\python.exe`，不由此推定该环境已验收。

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

历史命令保留，完整任务走新适配器。生成、内容一致性、浏览器、视觉与人工验收各自支持不同结论；[证据质量说明](../playbooks/evidence-quality.md)解释这些层次。当前技术链与 Skill 显式调用已验证；代理使用评测与未覆盖范围见[验证记录](verification-v1.md)，后续独立范围见[路线图](../ROADMAP.md)。

[当前验证与适用边界](verification-v1.md)
