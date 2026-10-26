# 评审变更工作包运行说明

本版为v0.2本地工作包。稳定键工具为通用归档快照的三文件固定分发；stdlib即可运行。输入原样保留，指纹不等于脱敏，比较不证明批准。Skill验证范围另见[验证边界](skills-v02.md)。

在工具包根运行：

```sh
python3 pm_review.py demo --output ../my-review
python3 pm_review.py check --output ../my-review
```

输出目录必须尚不存在，父目录须既有且无软链。demo创建9文件：六份本例输入、snapshot-diff.json、WORKSPACE.md与manifest.json。check会按当前仓库的同一合成案例重新生成预期，核对精确文件集与全部内容；伪造manifest不能代替正文。修改输出后check失败是预期，它不是对任意项目的真假评判。中断后的INCOMPLETE.txt和非零退出不能当作交付；没有事务或自动回滚保证。

## 用自己的双快照

准备before.json、after.json两个对象数组与两份控制JSON，字段名和状态词显式提供。参考[policy](../examples/review-change/policy.json)和[快照清单](../examples/review-change/snapshots.json)，在仓库根调用：

```sh
python3 tools/keyed_snapshot_diff.py --root examples/review-change --manifest snapshots.json --policy policy.json
```

默认只输出指纹、位置与计数，不是匿名化。确认自己的输入可披露后可加`--include-values`显示给定值。稳定ID为非空字符串或整数；bool/int/float/null等状态按类型区分；不做Unicode归一化或身份推断。一个ID只能出现一次，状态必须来自显式词表，至少一份快照非空。默认上限和错误码见工具开头，不适用时不能默默提高或放宽。

报告默认stdout；需要保存时使用`--json`指定输入根之外、父目录已存在的新文件；不覆盖既有结果。不扫描工作区，不访问平台，不读取未指定资料。

## Skill与人工操作

将[两个任务](../examples/review-change/prompts.md)及相关准确SKILL.md、case.md/JSON提供给能读取材料的助手。实际草案：[追踪](../examples/review-change/skill-drafts/trace-draft.md)、[意图保留](../examples/review-change/skill-drafts/feedback-draft.md)。草案仍需核对引用与适用范围，不是审批或原型回写。

首页可通过本地HTTP浏览。例如在根目录运行`python3 -m http.server 8765 --bind 127.0.0.1`，再打开`http://127.0.0.1:8765/review.html`。制作验收使用限定文件只读服务器；file协议双击不在本轮实测范围。
