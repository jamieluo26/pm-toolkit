"""Finite local request-form specifications, transitions and same-source artifacts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent
MAX_NUMBER = 9007199254740991
KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
STATES = {"draft": "草稿", "submitted": "已提交", "needs_info": "待补充", "done": "已完成"}
TRANSITIONS = (
    {"from": "draft", "action": "submit", "to": "submitted", "label": "提交"},
    {"from": "submitted", "action": "return", "to": "needs_info", "label": "退回补充"},
    {"from": "needs_info", "action": "resubmit", "to": "submitted", "label": "重新提交"},
    {"from": "submitted", "action": "complete", "to": "done", "label": "完成"},
)
OUTPUTS = {"source.json", "prototype.html", "PRD.md", "acceptance.md", "trace.json", "manifest.json"}


class Invalid(ValueError):
    """The finite local form contract was not met."""


def require(ok):
    if not ok:
        raise Invalid("Request-form contract failed")


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


def plain(path):
    path = Path(path).absolute()
    require(not path.is_symlink() and all(not p.is_symlink() for p in path.parents))
    return path


def read_json(path):
    path = plain(path)
    require(path.is_file() and path.stat().st_size <= 2_000_000)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(stamp(before) == stamp(after) and len(raw) <= 2_000_000)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Invalid("Invalid JSON") from error
    return value, raw


def string(value, maximum=1000, empty=False):
    return (type(value) is str and len(value) <= maximum and (empty or bool(value.strip()))
            and all(ord(c) >= 32 and c not in "\u2028\u2029" and not 0xD800 <= ord(c) <= 0xDFFF for c in value))


def identifier(value):
    return type(value) is str and KEY.fullmatch(value) is not None


def number(value):
    return type(value) in (int, float) and abs(value) <= MAX_NUMBER and math.isfinite(value)


def keys(value, required):
    require(type(value) is dict and set(value) == set(required.split()))


def validate_values(spec, values, complete=False):
    """Return field-local errors without mutating the supplied values."""
    fields = spec["fields"]
    if type(values) is not dict or set(values) != {field["key"] for field in fields}:
        return [{"field": "", "message": "值必须与给定字段逐项对应。"}]
    errors = []
    for field in fields:
        key, value = field["key"], values[field["key"]]
        kind = field["type"]
        missing = value is None if kind == "number" else not value if kind == "tags" else type(value) is str and not value.strip()
        if complete and field["required"] and missing:
            errors.append({"field": key, "message": "请填写此必填项。"})
            continue
        valid = True
        if kind == "number":
            valid = value is None or number(value)
            if valid and value is not None:
                lower, upper = field.get("minimum"), field.get("maximum")
                valid = (lower is None or value >= lower) and (upper is None or value <= upper)
        elif kind == "tags":
            valid = (type(value) is list and len(value) <= 30 and all(string(item) for item in value)
                     and len(set(value)) == len(value) and set(value) <= set(field["choices"])) if type(value) is list else False
        else:
            valid = string(value, empty=True)
            if valid and kind == "choice":
                valid = value == "" or value in field["choices"]
        if not valid:
            errors.append({"field": key, "message": "内容不符合该字段的类型、允许值或范围。"})
    return errors


def validate_spec(spec):
    keys(spec, "schema id version parent_sha256 title positioning pain value fields initial_values initial_state requirements")
    require(spec["schema"] == "pm-request/v1" and identifier(spec["id"]))
    require(all(string(spec[key]) for key in ("version", "title", "positioning", "pain", "value")))
    require(spec["parent_sha256"] is None or type(spec["parent_sha256"]) is str and SHA.fullmatch(spec["parent_sha256"]))
    require(type(spec["initial_state"]) is str and spec["initial_state"] in STATES)
    require(type(spec["fields"]) is list and 1 <= len(spec["fields"]) <= 16)
    names = set()
    for field in spec["fields"]:
        require(type(field) is dict and set("key label type required choices".split()) <= set(field)
                and set(field) <= set("key label type required choices minimum maximum".split()))
        require(identifier(field["key"]) and field["key"] not in names)
        names.add(field["key"])
        require(string(field["label"], 80) and field["type"] in ("text", "number", "choice", "tags")
                and type(field["required"]) is bool)
        choices = field["choices"]
        require(type(choices) is list and len(choices) <= 30 and all(string(item) for item in choices))
        require(len(set(choices)) == len(choices) and bool(choices) == (field["type"] in ("choice", "tags")))
        if field["type"] == "number":
            lower, upper = field.get("minimum"), field.get("maximum")
            require((lower is None or number(lower)) and (upper is None or number(upper)))
            require(lower is None or upper is None or lower <= upper)
        else:
            require("minimum" not in field and "maximum" not in field)
    require(not validate_values(spec, spec["initial_values"], complete=spec["initial_state"] in ("submitted", "done")))
    require(type(spec["requirements"]) is list and 1 <= len(spec["requirements"]) <= 30)
    names = set()
    for row in spec["requirements"]:
        keys(row, "id statement acceptance")
        require(identifier(row["id"]) and row["id"] not in names and string(row["statement"]))
        names.add(row["id"])
        checks = row["acceptance"]
        require(type(checks) is list and 1 <= len(checks) <= 20 and all(string(item) for item in checks))
        require(len(checks) == len(set(checks)))
    return spec


def transition(spec, state, values, action, reason=""):
    """Pure finite demonstration transition; not approval or a backend operation."""
    validate_spec(spec)
    require(type(state) is str and state in STATES and type(action) is str)
    require(not validate_values(spec, values, complete=state in ("submitted", "done")))
    choices = [row for row in TRANSITIONS if row["from"] == state and row["action"] == action]
    require(len(choices) == 1)
    require(string(reason, empty=action != "return"))
    target = choices[0]["to"]
    require(not validate_values(spec, values, complete=target in ("submitted", "done")))
    return {"state": target, "values": deepcopy(values), "action": action,
            "reason": reason if action == "return" else "", "meaning": "LOCAL_SESSION_DEMO_ONLY"}


def md(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|").replace("*", "\\*").replace("_", "\\_").replace("[", "\\[").replace("]", "\\]")


def build_payload(spec, raw):
    validate_spec(spec)
    # The supplied bytes must be the exact specification being projected.
    parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: require(False))
    require(json.dumps(parsed, sort_keys=True, ensure_ascii=True, allow_nan=False)
            == json.dumps(spec, sort_keys=True, ensure_ascii=True, allow_nan=False))
    source_sha = sha(raw)
    template = (ROOT / "assets/request-form.html").read_text(encoding="utf-8")
    require(template.count("__REQUEST_PAYLOAD__") == 1)
    payload = json.dumps({"spec": spec, "source_sha256": source_sha, "states": STATES,
                          "transitions": TRANSITIONS}, ensure_ascii=False, allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    prototype = template.replace("__REQUEST_PAYLOAD__", payload).encode("utf-8")
    intro = [f"# {md(spec['title'])}", "", f"版本：{md(spec['version'])}", f"源文件 SHA-256：{source_sha}", "",
             "结构化规格单向生成本原型、PRD与待执行检查计划；手工改制品不会回灌规格。",
             "输入由调用者提供，来源、脱敏与真实适用性未经工具核验。所有状态只是本地演示，不证明真人审批或实际验收。", "",
             "## 定位、痛点与价值", "", f"定位：{md(spec['positioning'])}", f"痛点：{md(spec['pain'])}",
             f"价值假设：{md(spec['value'])}", "", "## 固定交互", "",
             "单表单、必填/类型/允许值/数值范围检查、四状态与四种转换。草稿和待补充可编辑，已提交和已完成只读；终态不能继续转换。",
             "退回补充必须填写理由。提交/重提必须满足必填。数据只在本页面会话中变化，刷新恢复给定初值与初始状态。",
             "字段配置生成新规格JSON，不修改当前演示或同步PRD；下载新规格后需重新build/check。无后台、存储、账号、真实审批、任意条件引擎。", "",
             "## 字段合同", "", "|字段|名称|类型|必填|允许值|数值范围|", "|---|---|---|---|---|---|"]
    for field in spec["fields"]:
        bounds = f"{field.get('minimum')} ～ {field.get('maximum')}" if field["type"] == "number" else "—"
        intro.append(f"|{field['key']}|{md(field['label'])}|{field['type']}|{'是' if field['required'] else '否'}|{md(' / '.join(field['choices']))}|{md(bounds)}|")
    intro += ["", "text为最长1000字符的单行文本；number须有限且绝对值≤9007199254740991，另受声明minimum/maximum约束；choice与tags须在给定集合内。可选数值允许null、单选允许空字符串、标签允许空数组。", "",
              "## 状态与转换", "", f"给定初始状态：{STATES[spec['initial_state']]}（只是输入声明）", "",
              "|前状态|动作|后状态|", "|---|---|---|"]
    for row in TRANSITIONS:
        intro.append(f"|{STATES[row['from']]}|{row['label']}|{STATES[row['to']]}|")
    acceptance = [f"# {md(spec['title'])} · 待执行检查计划", "", f"版本：{md(spec['version'])}", f"源文件 SHA-256：{source_sha}", "",
                  "以下是声明与检查计划，均未因生成或check而自动执行。实际观察须另记版本、条件、结果和证据。", ""]
    trace = []
    intro += ["", "## 需求与检查声明", ""]
    for row in spec["requirements"]:
        intro += [f"### {row['id']} · {md(row['statement'])}", ""]
        for index, text in enumerate(row["acceptance"], 1):
            check_id = f"{row['id']}-c{index}"
            intro.append(f"- {check_id}：{md(text)}")
            acceptance.append(f"- [ ] {check_id}：{md(text)}")
            trace.append({"requirement": row["id"], "check": check_id, "declared_text": text,
                          "status": "NOT_EXECUTED", "source_sha256": source_sha})
    acceptance += ["", "## 固定交互回归", "",
                   "- [ ] 必填为空、非法选项、越界/非有限数值均阻止提交，且字段值和状态不被无声改写。",
                   "- [ ] 提交→退回补充→编辑→重提→完成可操作；退回缺理由被阻止。",
                   "- [ ] 已提交不可编辑；已完成只读且不提供继续转换；非法转换被拒绝。",
                   "- [ ] 刷新恢复源初值与初始状态；重置按钮的整页会话恢复边界明确。",
                   "- [ ] 可填写字段配置并导出新版本规格；当前演示仍绑定原SHA，重新生成后才有新制品。",
                   "- [ ] 原型、PRD、计划与源SHA/版本相符；浏览器无运行错误。", ""]
    intro += ["", "## 给定初值", "", "调用者给定内容被保留，工具不作脱敏或来源认定。", "", "```json",
              json.dumps(spec["initial_values"], ensure_ascii=False, indent=2).replace("<", "\\u003c"), "```", ""]
    files = {"source.json": raw, "prototype.html": prototype, "PRD.md": "\n".join(intro).encode("utf-8"),
             "acceptance.md": "\n".join(acceptance).encode("utf-8"),
             "trace.json": encoded({"schema": "pm-form-trace/v1", "version": spec["version"], "source_sha256": source_sha,
                                     "meaning": "declared requirements only;not executed acceptance", "rows": trace})}
    closure = {name: sha((ROOT / name).read_bytes()) for name in ("form_core.py", "pm_form.py", "assets/request-form.html")}
    files["manifest.json"] = encoded({"schema": "pm-form-artifacts/v1", "source_sha256": source_sha,
                                      "generator": closure, "files": {name: sha(value) for name, value in sorted(files.items())}})
    return files


def new_directory(output, files):
    out = plain(output)
    require(not out.exists() and out.parent.is_dir())
    out.mkdir()
    marker = out / "INCOMPLETE.txt"
    marker.write_text("Incomplete generation. Preserve this directory and choose a new output path.\n", encoding="utf-8")
    for name, raw in files.items():
        with (out / name).open("xb") as stream:
            stream.write(raw)
        (out / name).chmod(0o644)
    marker.unlink()


def exact_directory(output, expected):
    out = plain(output)
    require(out.is_dir() and {p.name for p in out.iterdir()} == set(expected))
    for name, raw in expected.items():
        path = out / name
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == raw)
