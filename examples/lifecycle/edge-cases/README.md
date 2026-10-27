# 六工作包的缺失与冲突回放

所有材料为合成反例。每次使用新输出目录；工具只核给定结构/标签/关系，不自动发现真实业务冲突。正常主路径见上一层 README 和 docs/lifecycle.md。

| 工作包 | 材料与动作 | 预期 |
|---|---|---|
| A 需求澄清 | build missing-brief.json | 3/HOLD，来源待补与未决保留 |
| B 范围规则 | build unresolved-rule.json | 3/HOLD，明确声明的默认态冲突保留 |
| C 原型PRD | build stale-prototype-version.json | 2/ERROR，不生成输出，任务与规格版本不一致 |
| D 评审修订 | review使用上一层pending-decisions.json或conflict-decisions.json | 3/HOLD，其他路径覆盖也不能取消未决反馈 |
| E 验证交付 | deliver使用上一层after.json+本目录not-run-observations.json或stale-observations.json，并提供准确前版/反馈/决定 | 3/HOLD；未执行与过期证据不当成通过 |
| F 复盘资产 | deliver使用handbook-proposal-task.json+handbook-proposal-observations.json | 3/HOLD；手册保留proposed状态，需求仍称声明 |

示例（在工具包根目录）：

```sh
python3 pm_task.py build --source examples/lifecycle/edge-cases/missing-brief.json --output ../missing-brief
python3 pm_task.py build --source examples/lifecycle/edge-cases/stale-prototype-version.json --output ../stale-spec
python3 pm_task.py deliver --source examples/lifecycle/edge-cases/handbook-proposal-task.json --observations examples/lifecycle/edge-cases/handbook-proposal-observations.json --output ../proposal-handbook
```

有合法HOLD产物可供继续处理；结构ERROR时不应产生看似成功的目录。不能为获得退出0删除未知项或把not_run改成没有实际依据的pass。
