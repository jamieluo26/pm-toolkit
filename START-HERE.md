# 从你手头的任务开始

这份目录是 **PM Toolkit v1.0 本地工作包**。使用完整副本，打开本地 `index.html`。GitHub 的 HTML 链接展示源码，交互在本地体验。四项新增 Skill 的完整治理和六次显式调用已通过；实际验证与代理使用评测见[验证记录](docs/verification-v1.md)。真人反馈及业务效果未采集。

## 先体验一个案例

| 想先看看什么 | 入口 | 重点看 |
|---|---|---|
| 一次完整产品迭代 | [阅读任务](examples/lifecycle/README.md) · [前版](examples/lifecycle/before-output/journey.html) · [后版](examples/lifecycle/after-output/prototype.html) | 同任务的简报/规则、原型/PRD/Word、评审、观察、交接和复盘 |
| 有限表单流程 | [请求表单](examples/request-flow/output/prototype.html) · [使用说明](docs/form-cli.md) | 必填/数值、提交、退回、重提、只读终态，配置后导出新规格 |
| 自己的集合 | [个人任务板](examples/personal-tasks/output/prototype.html) · [规格](examples/personal-tasks/spec.json) | 字段、搜索、交集筛选、详情与当前会话编辑 |

案例全部人工合成。先看[实际操作短演示](demo.html)，再到原型里自己操作。阅读案例的[实际观察摘要](examples/lifecycle/browser-observations.md)有明确覆盖条件，不代表真实业务效果或独立用户试用。

## 把任务换成自己的

| 你现在的问题 | 从哪里开始 | 拿到什么 |
|---|---|---|
| 还没讲清楚为什么做 | [需求澄清](playbooks/workpacks/01-discover.md) · [简报模板](templates/product-brief.md) | 定位、痛点、价值假设、目标、优先级与待定项 |
| 讨论多，决定混在一起 | [决定模板](templates/decision-evidence.md) · [会议 Skill](docs/skills-v1.md) | 有引用的决定、分歧和上下文 |
| 范围、默认、异常和规则不清楚 | [范围与规格](playbooks/workpacks/02-specify.md) · [任务合同](docs/task-spec.md) | 给定消费者、规则、需求和检查关系 |
| 想做同源原型与文档 | [任务准备页面](prepare.html) · [完整步骤](docs/lifecycle.md) | 自己的 task.json，再生成原型、PRD、Word |
| 评审后需要修改 | [评审修订](playbooks/workpacks/04-review.md) | 反馈与处理决定分开、准确差异与未决项 |
| 要核对需求关系或功能承接 | [六项 Skill 使用说明](docs/skills-v1.md) | 给定范围内带引用的文字审阅草案 |
| 要验证并交接 | [验证交付](playbooks/workpacks/05-deliver.md) | 实际观察、失败/复验、交接与版本说明 |
| 要复盘或交给下一位 | [复盘资产](playbooks/workpacks/06-retrospect.md) | 需求声明、当前观察、决定状态及下一轮问题 |

## 选一条运行路径

1. **只浏览：** 在本地打开 `index.html`，选择预制案例，无需 Python 或账号。
2. **整轮任务：** 按[完整步骤](docs/lifecycle.md)准备环境，使用 `pm_task.py init/build/check/review/deliver`。
3. **独立集合：** 用 `pm_flow.py build/check` 生成轻量集合，仅需标准库。[说明](docs/prototype-loop.md)
4. **独立表单：** 用 `pm_form.py build/check` 生成单表单与有限状态流，仅需标准库。[说明](docs/form-cli.md)
5. **辅助文字审阅：** 向自己的助手提供完整 Skill 和指定材料，人工核对引用与结论。[说明](docs/skills-v1.md)

输出选择新目录。整轮任务包含 Word，需按 `requirements.txt` 安装依赖；先用 `python3 pm_doctor.py` 查看本地声明条件。工具保留内容，不自动脱敏。

## 保留的旧版入口

- [v0.1 手动交接与 Word CLI](docs/cli.md)，以及[旧走读案例](examples/reading-list/output/journey.html)。
- [v0.2 评审变更工作包](docs/review-workpack.md)，以及[页面](review.html)。
- [v0.3 集合原型与给定评审核对](docs/prototype-loop.md)，以及[页面](flow.html)。

旧版输入合同继续保留。整轮任务使用新的同任务适配器，不应将旧版独立 Word 和另一份规格的原型拼成同版证据。
