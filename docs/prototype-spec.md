# 原型规格与评审输入合同

所有 JSON 必须为 UTF-8，最大 2 MB；拒绝重复键、非有限数字、未知/缺失字段、符号链接文件及符号链接父目录。字符串不含控制字符；标识为小写字母起始的 `[a-z][a-z0-9_]{0,39}`。记录最多500、字段最多16、需求最多30，每条需求检查最多20。仅支持本文字段，直接复制合成样例修改最稳妥。

规格必须精确包含：

|字段|合同|
|---|---|
|schema|固定 pm-collection/v1|
|id / version|产品标识 / 非空版本文字|
|parent_sha256|初版 null，增量绑定前规格原始字节 SHA-256|
|title / positioning / pain / value|标题、定位、痛点、待证价值假设，非空|
|fields|key、label、type、required、choices；key唯一，required为布尔|
|search_fields|存在的字段key，至少一个且不重复|
|filters|choice或tags字段key，可为空，不重复|
|layout|sidebar 或 toolbar|
|items|id唯一；values含每一个已声明字段且不含其他键|
|requirements|id唯一、statement、acceptance字符串数组；均为调用者声明|

text 为文字，必填时需非空白；number 为绝对值不超过 9007199254740991 的有限数字（不是布尔），选填允许 null；choice 为给定单选值，选填允许空字符串；tags 为不重复的给定标签数组。仅 choice/tags 的 choices 非空，其余类型 choices 必须为空。选项数量最多30；文字通常最多1000字符，字段label最多80。

反馈必须精确包含 `schema: pm-feedback/v1`、`before_sha256`、`items`；items中每项精确包含 `id` 与 `text`。

决定必须精确包含 `schema: pm-decisions/v1`、`before_sha256`、`after_sha256`、`feedback_sha256`、`items`；items中每项精确包含 `feedback_id`、`status`、`rationale`、`paths`。每条反馈最多一条决定，状态仅 adopted / declined / pending；paths是精确变更 JSON Pointer，不接受通配符或父路径覆盖。

修改任一文件后需重新计算绑定。可用以下只读 Python 命令获取本地文件的原始字节哈希，再人工填写指定字段：

```sh
python3 -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("examples/prototype-loop/before.json").read_bytes()).hexdigest())'
```

在 `pending-decisions.json` 中，云端同步仍为 pending，即使其他路径承接完整，review 仍返回3/HOLD。修改后规格而不更新决定 SHA，也必须 HOLD。把 manifest 一起重写来掩盖制品篡改，check仍会按源规格重新生成并拒绝。

生成器安全编码 JSON 脚本上下文；页面通过文字节点显示调用者内容。它不清除隐私、不检查法律权属、不推断真实身份。请勿把真实公司、个人或客户材料当作公开样例。
