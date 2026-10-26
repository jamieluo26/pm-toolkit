"""Bounded collection specifications and literal review evidence. Standard library only."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
BUILD_FILES = {"source.json", "prototype.html", "PRD.md", "acceptance.md", "trace.json", "manifest.json"}
REVIEW_FILES = {"before.json", "after.json", "feedback.json", "decisions.json", "review.json", "REVIEW.md"}
KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")


class Invalid(ValueError):
    """Input or artifact violates the declared local contract."""


def require(ok):
    if not ok:
        raise Invalid("contract violation")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file())
    require(all(not p.is_symlink() for p in path.absolute().parents))
    require(path.stat().st_size <= 2_000_000)
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Invalid("invalid JSON") from exc
    return value, raw


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()))


def string(value, limit=1000, empty=False):
    require(type(value) is str and len(value) <= limit and (empty or bool(value.strip())))
    require(all(ord(c) >= 32 and c not in "\u2028\u2029" for c in value))


def strings(value, maximum=100, empty=False):
    require(type(value) is list and len(value) <= maximum)
    if not empty:
        require(bool(value))
    for item in value:
        string(item)
    require(len(value) == len(set(value)))


def identifier(value):
    require(type(value) is str and bool(KEY.fullmatch(value)))


def digest(value):
    require(type(value) is str and bool(SHA.fullmatch(value)))


def validate_spec(spec):
    keys(spec, "schema id version parent_sha256 title positioning pain value fields search_fields filters layout items requirements")
    require(spec["schema"] == "pm-collection/v1")
    identifier(spec["id"])
    for key in ("version", "title", "positioning", "pain", "value"):
        string(spec[key])
    if spec["parent_sha256"] is not None:
        digest(spec["parent_sha256"])
    require(spec["layout"] in ("sidebar", "toolbar"))
    require(type(spec["fields"]) is list and 1 <= len(spec["fields"]) <= 16)
    fields = {}
    for field in spec["fields"]:
        keys(field, "key label type required choices")
        identifier(field["key"])
        require(field["key"] not in fields)
        string(field["label"], 80)
        require(field["type"] in ("text", "number", "choice", "tags"))
        require(type(field["required"]) is bool)
        strings(field["choices"], 30, empty=True)
        require(bool(field["choices"]) == (field["type"] in ("choice", "tags")))
        fields[field["key"]] = field
    strings(spec["search_fields"], 16)
    strings(spec["filters"], 16, empty=True)
    require(set(spec["search_fields"]) <= fields.keys())
    require(set(spec["filters"]) <= fields.keys())
    require(all(fields[k]["type"] in ("choice", "tags") for k in spec["filters"]))
    require(type(spec["items"]) is list and len(spec["items"]) <= 500)
    ids = set()
    for item in spec["items"]:
        keys(item, "id values")
        identifier(item["id"])
        require(item["id"] not in ids)
        ids.add(item["id"])
        require(type(item["values"]) is dict and item["values"].keys() == fields.keys())
        for key, value in item["values"].items():
            field = fields[key]
            if field["type"] == "number":
                require(value is None or (type(value) in (int, float) and math.isfinite(value) and abs(value) <= 9007199254740991))
                require(not field["required"] or value is not None)
            elif field["type"] == "tags":
                strings(value, 30, empty=not field["required"])
                require(set(value) <= set(field["choices"]))
            else:
                string(value, empty=not field["required"])
                if field["type"] == "choice":
                    require(value in field["choices"] or (not field["required"] and value == ""))
    require(type(spec["requirements"]) is list and 1 <= len(spec["requirements"]) <= 30)
    ids = set()
    for row in spec["requirements"]:
        keys(row, "id statement acceptance")
        identifier(row["id"])
        require(row["id"] not in ids)
        ids.add(row["id"])
        string(row["statement"])
        strings(row["acceptance"], 20)
    return spec


def md(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|").replace("*", "\\*").replace("_", "\\_").replace("[", "\\[").replace("]", "\\]")


def build_payload(spec, raw):
    validate_spec(spec)
    source_sha = sha(raw)
    template = (ROOT / "assets/collection.html").read_text(encoding="utf-8")
    require(template.count("__FLOW_PAYLOAD__") == 1)
    payload = json.dumps({"spec": spec, "source_sha256": source_sha}, ensure_ascii=False, allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    prototype = template.replace("__FLOW_PAYLOAD__", payload).encode("utf-8")
    title = md(spec["title"])
    intro = [f"# {title}", "", f"版本：{md(spec['version'])}", f"源文件 SHA-256：{source_sha}", "",
             "结构化规格为唯一权威。本文件与原型、检查计划同源生成；直接修改生成文件不会回灌规格。",
             "输入内容与来源由调用者提供，工具不核验来源或脱敏；价值是待证假设，要求是调用者声明，不是浏览器或业务验收结果。", "",
             "## 定位、痛点与价值", "", f"定位：{md(spec['positioning'])}", f"痛点：{md(spec['pain'])}",
             f"价值假设：{md(spec['value'])}", "", "## 固定支持范围", "",
             "集合列表、详情、字面搜索、精确筛选、重置，以及仅当前页面会话的新增/编辑；刷新恢复给定样例。",
             "搜索：对声明字段的显示值进行不区分大小写的子串匹配；多个筛选与搜索取交集。",
             f"筛选位置：{spec['layout']}；搜索字段：{', '.join(spec['search_fields'])}；筛选字段：{', '.join(spec['filters']) or '无'}。",
             "无删除、联网、身份认证、持久化或真实业务执行。桌面演示；移动端未验收。", "", "## 字段合同", "",
             "|字段|名称|类型|必填|可选值|", "|---|---|---|---|---|"]
    for f in spec["fields"]:
        intro.append(f"|{f['key']}|{md(f['label'])}|{f['type']}|{'是' if f['required'] else '否'}|{md(' / '.join(f['choices']))}|")
    intro += ["", "必填文本需含非空白字符；数值必须有限且绝对值不超过9007199254740991；选项及标签必须在给定集合内。可选数值允许null，可选单选允许空字符串。", "", "## 需求与验收声明", ""]
    acceptance = [f"# {title} · 检查计划", "", f"版本：{md(spec['version'])}", f"源文件 SHA-256：{source_sha}", "",
                  "这是待执行的检查计划。生成或哈希检查成功只证明同源一致；下列项目均未自动执行。", ""]
    trace = []
    for r in spec["requirements"]:
        intro += [f"### {r['id']} · {md(r['statement'])}", ""]
        for i, text in enumerate(r["acceptance"], 1):
            cid = f"{r['id']}-c{i}"
            intro.append(f"- {cid}：{md(text)}")
            acceptance.append(f"- [ ] {cid}：{md(text)}")
            trace.append({"requirement": r["id"], "check": cid, "declared_text": text,
                          "status": "NOT_EXECUTED", "source_sha256": source_sha})
        intro.append("")
    acceptance += ["", "## 通用交互回归", "",
                   "- [ ] 无结果后重置恢复全部样例；重复筛选结果稳定。",
                   "- [ ] 详情、有效新增、有效编辑及必填/有限数值错误提示可用。",
                   "- [ ] 新增/编辑仅在页面会话保留，刷新恢复给定数据。",
                   "- [ ] 原型版本、SHA、PRD和本计划一致；控制台无运行错误。", ""]
    intro += ["## 给定样例", "", "以下 JSON 为调用者给定的初始数据；工具不认定其来源、隐私或生产适用性。", "", "```json",
              json.dumps(spec["items"], ensure_ascii=False, indent=2).replace("<", "\\u003c"), "```", ""]
    files = {"source.json": raw, "prototype.html": prototype,
             "PRD.md": "\n".join(intro).encode(), "acceptance.md": "\n".join(acceptance).encode(),
             "trace.json": encoded({"schema": "pm-flow-trace/v1", "version": spec["version"], "source_sha256": source_sha,
                                     "meaning": "declared requirements only; no executed acceptance", "rows": trace})}
    closure = {p: sha((ROOT / p).read_bytes()) for p in ("flow_core.py", "pm_flow.py", "assets/collection.html")}
    files["manifest.json"] = encoded({"schema": "pm-flow-artifacts/v1", "source_sha256": source_sha,
                                      "generator": closure, "files": {k: sha(v) for k, v in sorted(files.items())}})
    return files


def pointer(key):
    return key.replace("~", "~0").replace("/", "~1")


def differences(a, b, path=""):
    # Arrays are atomic. No guessed row identity or semantic equivalence.
    if type(a) is dict and type(b) is dict:
        result = []
        for key in sorted(a.keys() | b.keys()):
            child = path + "/" + pointer(key)
            if key not in a or key not in b:
                result.append(child)
            else:
                result += differences(a[key], b[key], child)
        return result
    return [] if encoded(a) == encoded(b) else [path]


def review_payload(before, after, feedback, decisions, raws):
    validate_spec(before)
    validate_spec(after)
    keys(feedback, "schema before_sha256 items")
    require(feedback["schema"] == "pm-feedback/v1")
    digest(feedback["before_sha256"])
    require(type(feedback["items"]) is list and 1 <= len(feedback["items"]) <= 100)
    ids = set()
    for row in feedback["items"]:
        keys(row, "id text")
        identifier(row["id"])
        require(row["id"] not in ids)
        ids.add(row["id"])
        string(row["text"], 2000)
    keys(decisions, "schema before_sha256 after_sha256 feedback_sha256 items")
    require(decisions["schema"] == "pm-decisions/v1")
    for key in ("before_sha256", "after_sha256", "feedback_sha256"):
        digest(decisions[key])
    require(type(decisions["items"]) is list and len(decisions["items"]) <= 100)
    decisions_by_id = {}
    for row in decisions["items"]:
        keys(row, "feedback_id status rationale paths")
        identifier(row["feedback_id"])
        require(row["feedback_id"] in ids and row["feedback_id"] not in decisions_by_id)
        require(row["status"] in ("adopted", "declined", "pending"))
        string(row["rationale"], 2000)
        strings(row["paths"], 100, empty=True)
        require(all(p.startswith("/") for p in row["paths"]))
        require(row["status"] == "adopted" or row["paths"] == [])
        decisions_by_id[row["feedback_id"]] = row
    hashes = {k: sha(v) for k, v in raws.items()}
    issues = []
    def hold(condition, message):
        if condition:
            issues.append(message)
    hold(feedback["before_sha256"] != hashes["before.json"], "STALE_FEEDBACK_BASE")
    for key, file in (("before_sha256", "before.json"), ("after_sha256", "after.json"), ("feedback_sha256", "feedback.json")):
        hold(decisions[key] != hashes[file], "STALE_DECISION_" + key.upper())
    hold(after["parent_sha256"] != hashes["before.json"], "AFTER_PARENT_MISMATCH")
    hold(before["version"] == after["version"], "VERSION_NOT_ADVANCED")
    hold(before["id"] != after["id"], "PRODUCT_ID_CHANGED")
    changed = [p for p in differences(before, after) if p not in ("/version", "/parent_sha256")]
    hold(not changed, "NO_BEHAVIORAL_CHANGE")
    coverage = {p: [] for p in changed}
    for fid in sorted(ids):
        row = decisions_by_id.get(fid)
        hold(row is None, "MISSING_DECISION:" + fid)
        if row is None:
            continue
        hold(row["status"] == "pending", "UNRESOLVED_FEEDBACK:" + fid)
        if row["status"] == "adopted":
            hold(not row["paths"], "ADOPTED_WITHOUT_CHANGE:" + fid)
            for path in row["paths"]:
                hold(path not in coverage, "UNMATCHED_DECISION_PATH:" + fid + ":" + path)
                if path in coverage:
                    coverage[path].append(fid)
    for path, owners in coverage.items():
        hold(len(owners) != 1, "CHANGE_COVERAGE:" + path)
    result = {"schema": "pm-review-evidence/v1", "status": "HOLD" if issues else "DECLARED_DECISIONS_COVERED",
              "meaning": "Literal supplied decisions and change coverage only; not real human approval or executed acceptance.",
              "input_sha256": hashes, "before_version": before["version"], "after_version": after["version"],
              "changed_paths": changed, "coverage": coverage, "issues": issues, "decisions": decisions["items"]}
    lines = ["# 评审增量证据", "", f"状态：{result['status']}", "",
             "只核对给定决定与字面差异。声明标签不证明真实人员/公司审批，也不证明需求合理、意图完整或实际验收。",
             "冲突、缺失和待定保留为 HOLD。检查通过后仍需用 after.json 生成新目录并逐项检查原型。", "",
             f"前版本：{md(before['version'])}；后版本：{md(after['version'])}", "", "## 精确输入绑定", ""]
    lines += [f"- {name}：{value}" for name, value in hashes.items()]
    lines += ["", "## 字面变更路径", ""] + [f"- {md(p)} ← {', '.join(coverage[p]) or '未承接'}" for p in changed]
    lines += ["", "## 给定反馈与决定", ""]
    for row in feedback["items"]:
        decision = decisions_by_id.get(row["id"])
        lines += [f"- {row['id']}：{md(row['text'])}",
                  f"  状态：{decision['status'] if decision else 'missing'}；理由：{md(decision['rationale']) if decision else '未提供'}"]
    lines += ["", "## 待处理", ""] + ([f"- {md(issue)}" for issue in issues] or ["给定范围内无未覆盖路径或待定项；不代表真实评审完成。"])
    return {**raws, "review.json": encoded(result), "REVIEW.md": ("\n".join(lines) + "\n").encode()}, result


def new_directory(output, files):
    out = Path(output).absolute()
    require(not out.exists() and not out.is_symlink() and out.parent.is_dir())
    require(all(not p.is_symlink() for p in (out.parent, *out.parent.parents)))
    out.mkdir()
    marker = out / "INCOMPLETE.txt"
    marker.write_text("Incomplete generation. Preserve inputs and choose a new output directory.\n")
    try:
        for name, raw in files.items():
            with (out / name).open("xb") as stream:
                stream.write(raw)
            (out / name).chmod(0o644)
    except OSError:
        raise Invalid("incomplete output") from None
    marker.unlink()


def exact_directory(output, expected):
    out = Path(output).absolute()
    require(out.is_dir() and not out.is_symlink())
    require(all(not p.is_symlink() for p in out.parents))
    require({p.name for p in out.iterdir()} == set(expected))
    for name, raw in expected.items():
        p = out / name
        require(p.is_file() and not p.is_symlink() and p.read_bytes() == raw)
