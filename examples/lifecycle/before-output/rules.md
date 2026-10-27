# 阅读清单产品任务

任务：reading_lifecycle；版本：2.0
任务源 SHA-256：1063894a54ffee5dd8acfd920876fa23184337bd772e5b00278d55844ea136fc
规格 SHA-256：0f9acbd47e05b48c5bc706c95a34d9fba856ad0eed5381b38a8af8baefea9290

## 给定消费者与排除理由

consumer\_reader：纳入；本例唯一目标使用者，覆盖整理与查看路径。；依据 ev\_reading
consumer\_team：排除；团队协作不在个人本地演示范围。；依据 ev\_reading
## rule_1 按进度和主题整理书目

默认：默认显示全部3条；进度与主题均不限制。
异常：无命中显示空态，仍可重置。
边界：本地合成演示，不持久化、不访问网络。
需求：browse
依据：ev\_reading
## rule_2 查看与维护当前会话书目

默认：详情从给定样例显示；改动仅当前页会话保留。
异常：必填为空或数值非法时阻止保存。
边界：本地合成演示，不持久化、不访问网络。
需求：maintain
依据：ev\_reading
## rule_3 侧栏承载筛选

默认：筛选位于左侧。
异常：空态保留筛选与重置入口。
边界：本地合成演示，不持久化、不访问网络。
需求：layout
依据：ev\_reading
