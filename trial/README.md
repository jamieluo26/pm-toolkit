# 首批真人 PM 试用包

先启动实际的本地工作台，再做「个人灵感收集箱」任务。这个包用于招募首批 5–10 位 PM 试用；目前没有真人试用结果，也没有公司审批或业务验收结论。

## 1. 启动工作台

在工具包根目录打开终端。需要 Python 3.10+ 与 macOS 或具备 `fcntl` 的 Unix；这个服务入口尚不支持 Windows。首次运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python pm_workbench.py --workspace ../my-pm-trial-workspace --port 8841
```

在 Chrome 打开 `http://127.0.0.1:8841`，确认出现「已连接本地服务」。终端保持运行；结束后按 Ctrl+C。端口占用时，使用另一个空闲端口并打开终端给出的准确地址。已有虚拟环境且依赖已安装时，直接运行最后一条命令。

每位试用者使用自己的仓库外工作目录；同一个工作目录只由一个工作台进程写入。不要把服务监听地址改成局域网或公网地址。完整启动说明见 [本地工作台说明](../docs/local-workbench.md)。

## 2. 按任务卡试用

1. 打开 [TASK-CARD.md](TASK-CARD.md)，从创建任务走到实际交接。
2. 在工作台点「导入已有草案」，选择 [TASK-INPUT.json](TASK-INPUT.json)。这是原生草案，不是旧操作原型 JSON，不含观察或通过记录。
3. 只使用给定的三条合成灵感。不必填写个人工作、公司、客户、项目、账号或任何敏感资料。
4. [EXPECTED-RESULTS.md](EXPECTED-RESULTS.md)仅辅助核对，不能当作已执行的观察；执行后用自己的描述记录。
5. 结束或中途卡住，都填写 [FEEDBACK.md](FEEDBACK.md)。不要求完成或给好评；HOLD、失败和无法独立完成都是有效反馈。

主持人另读 [FACILITATOR.md](FACILITATOR.md)。其中的邀请文案只是草稿，没有发送，也没有建立参与者名单。

## 本次体验的边界

- 生成由本地 Python 实际执行；页面编辑、保存、生成、修订、观察、交接是不同步骤。
- 这个任务验证列表查找、交集筛选、一次布局修订及材料交接。它不连接真实业务后台，不调用模型。
- 草案的决定状态初始为「提议 · 待确认」。试用者可以声明自己采用本次虚构练习方案；这只说明本次练习的个人选择。不同意则保留待决并记录 HOLD，无需伪造审批。
- 浏览器检查初始均为未执行；系统保存使用者提供的观察，不认证观察的真实性。文件一致性通过不能替代亲自操作。
- 请自行保留本地工作目录和下载包。本次材料不要求上传，不自动联系任何人，也不涉及 Git 提交或发布。

## 文件索引

| 文件 | 用途 |
|---|---|
| TASK-CARD.md | 创建 → 真实生成 → 修订 → 实际观察 → 交接 |
| TASK-INPUT.json | 可导入当前本地工作台的合成草案 |
| EXPECTED-RESULTS.md | 逐阶段辅助核对与三项检查预期 |
| FEEDBACK.md | 匿名反馈空表 |
| FACILITATOR.md | 首批 5–10 人组织计划与邀请文案草稿 |

## 先看本次代理实操的结果

[完整交接页面](demo-output/journey.html)、[修订后原型](demo-output/prototype.html)、[PRD](demo-output/PRD.md)、[Word](demo-output/handoff.docx)和[交付记录](demo-output/delivery.md)来自本次同一合成任务1.1的真实下载包。31份文件原字节保留，观察由代理实际操作后填写，仅证明所列条件，不是真人试用或业务验收。不要将这些已填结果作为自己的试用观察；自己的新任务仍须实际执行并如实记录。
