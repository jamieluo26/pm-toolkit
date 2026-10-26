# 通用集合原型与同源 PRD（v0.3 本地候选）

适合个人清单、任务板、轻量记录库的桌面方向讨论。它把明确的结构化规格生成可点击原型、PRD、待执行检查计划和追踪表。它不是任意应用开发器：只支持下面列出的集合交互。

Python 3.10+ 标准库即可运行本模块，无须安装依赖、联网或模型。原型 HTML 可离线打开。工具保留调用者内容，本身不脱敏；使用自己的资料前需自行清理。

## 三条实际路径

```sh
python3 pm_flow.py build --source examples/personal-tasks/spec.json --output ../my-task-board
python3 pm_flow.py check --source examples/personal-tasks/spec.json --output ../my-task-board
```

复制并编辑 `examples/personal-tasks/spec.json`，换成自己的字段、选项、样例、定位、痛点、价值假设及需求。指定的输出目录必须不存在且父目录已存在；绝不覆盖既有制品。中断留下 INCOMPLETE.txt 的目录不是成功输出，保留它并选一个新目录重试。

阅读清单的评审增量：

```sh
python3 pm_flow.py review --before examples/prototype-loop/before.json --after examples/prototype-loop/after.json --feedback examples/prototype-loop/feedback.json --decisions examples/prototype-loop/decisions.json --output ../reading-review
python3 pm_flow.py review-check --before examples/prototype-loop/before.json --after examples/prototype-loop/after.json --feedback examples/prototype-loop/feedback.json --decisions examples/prototype-loop/decisions.json --output ../reading-review
python3 pm_flow.py build --source examples/prototype-loop/after.json --output ../reading-next
python3 pm_flow.py check --source examples/prototype-loop/after.json --output ../reading-next
```

`review` 不修改源规格、不生成应用、不调用模型，也不批准决定。先由调用者给定决定与后版本，再核对文字覆盖；通过后另行生成候选并进行浏览器检查。`review-check` 从同一四份输入重算六份证据，检查证据有无篡改。

返回码：0 表示本命令的有限核对成立；2 表示结构、输入或输出合同失败；3 表示合法评审记录仍有 HOLD。HOLD 会输出完整证据，不能称为评审完成。错误信息不会回显调用者正文或路径。

## 固定支持范围

字段支持 text、绝对值不超过 9007199254740991 的有限 number、choice、tags；1–16 个字段，0–500 条初始记录。搜索字段必选至少一个，按单个标量值或单个标签作不区分大小写的字面子串匹配（不跨标签拼接）；choice/tags 可作精确筛选，标签按成员关系匹配。搜索与多个筛选取交集。

列表、详情、会话内新增/编辑、必填校验、空态和重置；筛选可选 sidebar 或 toolbar。刷新恢复给定初始记录。没有删除、账号、网络、数据库、跨设备同步、导入任意 HTML 或生产业务执行。桌面浏览器是本轮验证目标，移动端未验收。

## 同步方向与版本

`spec.json → prototype.html / PRD.md / acceptance.md / trace.json`。结构化规格是唯一权威；不能手改 HTML 后要求程序反推 PRD，也不能任意编辑 PRD 后反推页面。需要改动时改规格并生成一个新目录，保留前版。

六份输出包含原始输入字节副本 source.json 与 manifest.json。源 SHA、版本同时写入原型、PRD 和检查计划。`check` 根据当前输入和当前生成器重新生成所有预期字节，要求目录文件集合完全相同；不把可改写的 manifest 当作可信证据。

trace 的每一行都保持 NOT_EXECUTED。它只是给定需求与检查项的文字对应，不证明页面实现了任意自定义业务要求。新增文字超出固定交互范围时必须人工识别，另做实现和验收。

## 评审合同

feedback 单独保存原始反馈。decisions 单独保存调用者给定的 adopted / declined / pending 标签、理由和精确 JSON 路径；标签不证明真人或公司审批，也不证明理由合理。

四份文件按原始字节 SHA 绑定：反馈绑定前规格；决定绑定前规格、后规格和反馈。后规格 parent_sha256 必须等于前规格 SHA；version 必须变化，产品 id 必须不变。

对象递归按键比较，数组整体为一个路径（例如 `/requirements`），不猜测条目语义身份。除 `/version` 与 `/parent_sha256` 外，每条变更路径必须由恰好一条 adopted 决定精确覆盖；不接受上层路径代替子路径。declined/pending 不携带变更路径。缺失决定、pending、重叠、未承接变更、无实际变更、陈旧 SHA 均为 HOLD；错误结构为 ERROR。

数组整体覆盖只证明声明关系，不能检验每一句意图是否被保留。继续使用原有[反馈意图审阅 Skill](../skills/feedback-intent-preservation-review/SKILL.md)和[需求验收追踪 Skill](../skills/requirement-acceptance-trace-review/SKILL.md)辅助逐条审阅，再由人判断。没有新增 Skill 名称；反馈审阅 Skill 仅补强给定记录编号的引用保留要求。该新增说明将列入本次准确公开范围，既有内容资格不重复询问。

输入协议与失败示例见 [规格合同](prototype-spec.md)，完整操作见 [闭环说明](../playbooks/prototype-loop.md)。
