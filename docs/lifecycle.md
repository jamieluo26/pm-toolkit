# 完成一轮产品任务

这条路径把给定问题、规格、原型、PRD、Word、评审和复盘放在同一任务与版本中。你负责提供证据、作产品决定、操作原型和记录实际观察；工具负责生成与有界一致性核对。六项文字 Skill 可辅助审阅，不是这条本地路径的执行权限或审批来源。

## 准备环境

下载整个工具包并解压，在目录内打开终端。Python 3.10+；原型模块用标准库，完整任务的 Word 输出使用 requirements.txt 中的 python-docx。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows 使用 `.venv\Scripts\python.exe` 替换 `.venv/bin/python`。下文所有输出目录都必须是新目录，父目录先存在；检查命令可使用同一已生成目录。不要把输出指向工具包根目录。

## 先走合成案例

打开 [阅读任务案例](../examples/lifecycle/README.md)，阅读源讨论、before.json 与 after.json。先制作前版：

```sh
.venv/bin/python pm_task.py build --source examples/lifecycle/before.json --output ../reading-before
.venv/bin/python pm_task.py check --source examples/lifecycle/before.json --output ../reading-before
```

双击输出目录的 journey.html。检查产品定位、痛点、价值假设和范围，打开 prototype.html 实际操作，再对照 PRD.md 和 handoff.docx。本版 Word 是这份任务 PRD 的完整有序投影，任务 ID、版本与源标识对应。页面操作只保留在当前会话，刷新恢复样例。

## 处理一次评审

反馈和处理决定分别存放。after.json 同时更新必要的需求、规则和界面规格。运行：

```sh
.venv/bin/python pm_task.py review --before examples/lifecycle/before.json --after examples/lifecycle/after.json --feedback examples/lifecycle/feedback.json --decisions examples/lifecycle/decisions.json --output ../reading-review
.venv/bin/python pm_task.py build --source examples/lifecycle/after.json --output ../reading-after
.venv/bin/python pm_task.py check --source examples/lifecycle/after.json --output ../reading-after
```

阅读 REVIEW.md，核对合成采纳/拒绝理由与变更路径。实际打开修订原型，确认移动筛选载体后原功能仍存在。声明覆盖只检查输入关系，功能意图与实际行为需人核对。

把上面决定文件替换为 pending-decisions.json 或 conflict-decisions.json，并换新输出目录；应退出 3、显示 HOLD。不要为了得到绿色状态删除未决反馈。

## 检查、记录问题并复验

复制 `../reading-after/observations-template.json` 到自己的工作材料目录，按 acceptance.md 和 trace.json 中的条件逐项操作。真实完成后填写 observed、evidence_ref、status；未执行保持 not_run。

如发现问题，先追加 fail 和 defect 描述。修复后先生成并检查准确新版本，再为该版本建立新的观察材料；同版复验则追加 supersedes 指向上一观察的记录。不要把旧版本观察直接改 SHA 冒充新版执行。

当已具备当前版本的实际记录时，生成交接包：

```sh
.venv/bin/python pm_task.py deliver --source examples/lifecycle/after.json --observations path/to/observations.json --before examples/lifecycle/before.json --feedback examples/lifecycle/feedback.json --decisions examples/lifecycle/decisions.json --output ../reading-delivery
.venv/bin/python pm_task.py deliver-check --source examples/lifecycle/after.json --observations path/to/observations.json --before examples/lifecycle/before.json --feedback examples/lifecycle/feedback.json --decisions examples/lifecycle/decisions.json --output ../reading-delivery
```

观察缺失或不匹配时得到 HOLD；合法 HOLD 目录仍可阅读与交接待处理项。它不会运行浏览器或认证引用中的事实。交付包里的 acceptance-results.md 保留检查结果，defects.json 保留失败与复验，delivery.md 说明当前范围和未闭合项。复制状态标签不等于完成真实检查。

## 形成版本说明与复盘

同一交接包还提供 release-notes.md、product-handbook.md 和 retrospective.md，分别汇总给定变更、当前能力与历史决定、失败/复验及下一轮问题。版本说明描述的是给定离线制品，不表示已经部署上线。实际业务指标未采集时继续写未采集；用户反馈和收益仍需实际验证。

## 换成自己的任务

```sh
.venv/bin/python pm_task.py init --output ../my-task-input
```

也可双击 [任务配置入口](../prepare.html)，填写材料后下载首版 task.json。填写用户、问题、定位、来源、价值假设、目标、范围和规则；明确默认、异常、边界及检查。替换 prototype 中的字段/样例，并保持需求关系一致；具体字段见 [输入合同](task-spec.md)。占位任务带 pending，会生成 HOLD，提醒你补齐来源与决定。每次修订保留前版文件并使用新输出目录。

## 修订自己的任务，无需手填哈希

先用自己的 task.json 执行 build/check，生成 `../my-v1`。复制该目录的 task.json 到 `../my-edit.json`，在编辑器中修改本轮要调整的背景、需求、规则和 prototype 界面字段。任务 ID 保持原值。只修改任务权威层的定位、痛点、价值和需求；修订准备会同步这些字段到 prototype，前版及原稿均保留。

```sh
.venv/bin/python pm_task.py prepare-review --before ../my-v1/task.json --after ../my-edit.json --version 1.1 --output ../my-review-draft
```

首次返回 3/HOLD 是正常结果：所有反馈均待人工处理。打开 `changed-paths.json` 查看准确字面变更。把该目录的 `review-notes.json` 复制为 `../my-review-notes.json`，保留生成目录不变，再编辑副本的 items：填写反馈原意、来源、处理状态和理由。每项反馈用不同 id；采纳项的 paths 从变更路径中选择，每条变更恰好由一项采纳承接。拒绝、待定、冲突项的 paths 为空数组。数组按整体比较，不能只填某个数组元素的子路径。

确认自己填写的处理记录后，运行第二阶段：

```sh
.venv/bin/python pm_task.py prepare-review --before ../my-review-draft/before.json --after ../my-review-draft/after.json --version 1.1 --notes ../my-review-notes.json --output ../my-review-ready
.venv/bin/python pm_task.py prepare-review-check --before ../my-review-draft/before.json --after ../my-review-draft/after.json --version 1.1 --notes ../my-review-notes.json --output ../my-review-ready
.venv/bin/python pm_task.py build --source ../my-review-ready/after.json --output ../my-v11
.venv/bin/python pm_task.py check --source ../my-review-ready/after.json --output ../my-v11
```

工具会生成 feedback.json/decisions.json 的准确引用；不用编辑任何 SHA 字段。第二阶段如果仍有未决、冲突、缺失映射或无实际改动，会继续 HOLD。已采纳和已拒绝仅表示你给定的处理决定，仍需核对真实意图和原型行为。

若在生成草案后又修改 after 内容，旧 notes 会因前后配对不符被拒绝。使用修改后的 after 不带 `--notes` 另建草案，再人工重新核对处理决定，不能更新 notes 顶层哈希绕过此检查。`edited-input.json` 保留每次的编辑原稿；`preparation.json` 列出自动对齐路径。

实际操作 `../my-v11/prototype.html`，按其检查计划填写该目录 observations-template.json 的副本。完成真实观察后，再交付和复核：

```sh
.venv/bin/python pm_task.py deliver --source ../my-review-ready/after.json --observations ../my-observations.json --before ../my-review-ready/before.json --feedback ../my-review-ready/feedback.json --decisions ../my-review-ready/decisions.json --output ../my-delivery
.venv/bin/python pm_task.py deliver-check --source ../my-review-ready/after.json --observations ../my-observations.json --before ../my-review-ready/before.json --feedback ../my-review-ready/feedback.json --decisions ../my-review-ready/decisions.json --output ../my-delivery
```

阅读 delivery.md、acceptance-results.md、defects.json、release-notes.md、product-handbook.md 和 retrospective.md，核对实际执行、未决项及下一轮问题。没有执行的观察保持 not_run；HOLD 目录可以继续处理，不能视为已完成验收。

想先试界面定制，可从 [个人任务板](../examples/personal-tasks/spec.json) 运行 pm_flow.py；第二类表单见 [表单说明](form-cli.md)。这些是独立有限模块；整轮交接使用 pm_task.py 的统一 task.json。已有 v0.1/v0.2/v0.3 命令继续保留。

## 六个工作包入口

- [需求澄清](../playbooks/workpacks/01-discover.md)
- [范围与规格](../playbooks/workpacks/02-specify.md)
- [原型与 PRD](../playbooks/workpacks/03-prototype.md)
- [评审修订](../playbooks/workpacks/04-review.md)
- [验证交付](../playbooks/workpacks/05-deliver.md)
- [复盘资产](../playbooks/workpacks/06-retrospect.md)
