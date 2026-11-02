本草案仅依据本页提供的 input.md L1–L19 文本，核对声明之间的一致性；未打开原文件、发现源码消费者或认证真实审批。

**核对口径**

- 对象为 `OBJ:FILTER-BAR:desktop`；`OBJ:FILTER-BAR:mobile` 是独立身份，不合并比较（input.md L4）。
- 消费者按完整入口引用识别。桌面对象的每条给定消费者关系，须明确纳入，或提供适用于该关系的排除依据（input.md L5）。
- `SCOPE-01` 将比较范围限定为母表中的桌面对象消费者，并明确没有真实系统其他消费者的证据（input.md L17）。

**逐关系草案**

| 给定关系与来源 | 拟议处理与来源 | 供产品经理核对的判断 |
|---|---|---|
| `REL-01`：`OBJ:FILTER-BAR:desktop → ENTRY:reading-list`（input.md L8） | `INC-01`：纳入 `REL-01 / ENTRY:reading-list`（input.md L13） | **已明确纳入**，关系与入口引用对应。 |
| `REL-02`：`OBJ:FILTER-BAR:desktop → ENTRY:favorites-list`（input.md L9） | 给定方案未提供对应纳入或排除记录（input.md L12–L17） | **HOLD：处理缺失**。按给定覆盖方法，该关系尚未得到解释。 |
| `REL-03`：`OBJ:FILTER-BAR:mobile → ENTRY:reading-list-mobile`，母表标明本次对象范围外（input.md L10） | `EX-01`：排除 `OBJ:FILTER-BAR:mobile / ENTRY:reading-list-mobile`，理由为“本次仅桌面”，并引用 `SCOPE-01`（input.md L14、L17） | **有声明范围依据的范围外关系**。依据仅支持本次不比较该移动关系，不构成真实权限或审批认证，也不能覆盖桌面关系。 |

**排除项与摘要问题**

- **孤立排除 `EX-02`**：其引用为 `OBJ:ACCOUNT-PANEL:desktop / ENTRY:account-settings`，给定母表没有对应消费者关系（input.md L7–L10、L15）。理由“账号页本次不改”解释了提议动机，但未提供对应关系或审批映射。该项不能抵消 `REL-02` 的处理缺口，也不能据此推断账号对象没有其他消费者。
- **`SUMMARY-01` 依据不足**：“桌面筛选条影响范围完整”（input.md L16）与尚未处理的 `REL-02` 不一致。即使补齐该关系，结论也只能限定为“给定母表中的桌面消费者关系处理完整”，不能扩展为真实系统全量覆盖（input.md L3、L17）。
- 在本次给定条目中，未见重复关系身份、冲突入口引用或重复排除项。此判断仅限所提供文本。

**最小下一步**

1. 为 `REL-02 / ENTRY:favorites-list` 补充明确纳入记录；若拟排除，补充排除理由、适用关系及支持该范围的依据，并说明是否存在相应批准证据。
2. 将 `EX-02` 标记为“未对应给定母表关系”，不计入桌面覆盖核对。
3. 修订 `SUMMARY-01`。当前可写为：“给定桌面关系中，`REL-01` 已纳入，`REL-02` 待明确处理；整体覆盖结论为 **HOLD**。”