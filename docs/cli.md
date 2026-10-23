# 本地命令和有限输入

Python 3.10+。init与check只需标准库；build/demo还需requirements.txt指定的python-docx及其依赖。命令不会自动安装依赖或联网。首页和预制案例可直接双击HTML使用。

## 命令

```bash
python3 pm_toolkit.py init --output ../my-task
python3 pm_toolkit.py demo --output ../reading-demo
python3 pm_toolkit.py build --source examples/reading-list/case.json --output ../another-demo
python3 pm_toolkit.py check --source examples/reading-list/case.json --output ../another-demo
```

init/build/demo要求一个不存在的新目录，且父目录已存在；目录、文件、符号链接或并发占用均拒绝替换。先准备全部制品，再独占创建输出目录并逐个写入及回读。它不是多文件事务：写入失败可能留下INCOMPLETE.txt及部分新文件，不报告成功，也不清理用户既有资料。换一个新目录重试。

check只读给定源与输出目录，要求固定11文件，重算图、网页、文字和文档模型投影，再独立核对DOCX完整有序内容。清单不是签名，不证明来源真实或真人批准。它不运行浏览器或排版器。返回码0表示该命令说明的层通过，2表示输入、依赖或输出错误。

## 输入范围

示例case.json是唯一输入格式：pm-toolkit-case/v1。顶层字段固定，caseId用英文字母开头的短标识，title不超过30字符，edition不超过40字符，sourceKind为synthetic或user-supplied。context含audience/pain/value/goal/hypothesis。evidence/decisions/requirements/pending每组1–6项，每项id唯一，source须引用evidence中已有id；需求有唯一checkId。excluded为1–6条文字。

themes为1–8个唯一主题，不含保留词“全部”；books为1–30本，id唯一，title不超过80字符，每本有已声明主题且不重复。文本字段最多1200字符。原始UTF-8 JSON最多96000字节，拒绝重复JSON键和非有限数。冻结上游导图保留`__MAP_`、`__MINDMAP_`、`__DOCUMENT_TITLE__`和`__CONTENT__`标记；输入出现这些标记会明确拒绝，不通过替换改写其含义。新入口自身的模板标记可以作为合法文字保留。

这里的网页只实现“给定书目＋单主题筛选＋空态”。需求文字供审阅，不会被编译成任意应用功能。修改题目、需求或数据后，应自行判断是否仍适合这个演示合同；本工具不能证明你的新业务需求已实现。

## 11个输出

case.json为捕获的原始输入；product-brief.md、requirements.md、handoff.md为文字；decision-map.json/html为导图；document-source.json、handoff.docx为文档；prototype.html为固定交互演示；journey.html为可读走读；manifest.json记录版本及输出身份。输出会保留输入内容，不进行脱敏。

四个组件文件均固定到UPSTREAM.json中的公开提交与SHA；不通过全局安装或sys.path寻找同名私有Skill。组件导入只发生在显式build/check操作。
