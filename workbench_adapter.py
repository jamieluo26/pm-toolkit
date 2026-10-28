"""Explicit UI draft -> the unchanged finite pm-task/v1 contract.

No example is imported. Unknown critical prose is represented as pending input,
never as an approval or an observation.
"""
from copy import deepcopy
import re

import task_core

KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
DRAFT_KEYS = set("kind title audience problem positioning value_hypothesis goal priority_basis source_kind source_note success_metric included excluded pending decision_status fields collection form requirement rule legacy_notes".split())


class DraftError(ValueError):
    def __init__(self, message, fields=None):
        super().__init__(message)
        self.fields = fields or []


def insist(ok, message, field=""):
    if not ok:
        raise DraftError(message, [field] if field else [])


def string(value, field, limit=3000, single=False):
    insist(type(value) is str and len(value) <= limit, "文字类型或长度不符合范围。", field)
    insist(all((ord(c) >= 32 or c in "\n\t") and not 0xD800 <= ord(c) <= 0xDFFF for c in value), "文字包含非法控制字符。", field)
    insist(not single or all(c not in "\n\r\t\u2028\u2029" for c in value), "此栏只支持单行文字。", field)
    return value


def object_keys(value, keys, field):
    insist(type(value) is dict and set(value) == set(keys.split()), "对象字段不符合当前工作台合同。", field)


def validate_draft(draft):
    insist(type(draft) is dict and set(draft) == DRAFT_KEYS, "草稿字段不符合当前工作台合同。")
    insist(draft["kind"] in ("collection", "form"), "仅支持集合与表单。", "kind")
    pending = []
    def prose(value, field, limit=1000, single=False):
        string(value, field, limit, single)
        if not value.strip():
            pending.append("待确认：" + field)
            return "待确认：" + field
        return value
    cleaned = deepcopy(draft)
    for key in ("title", "audience", "problem", "positioning", "value_hypothesis", "goal", "priority_basis", "source_note"):
        cleaned[key] = prose(draft[key], key, 120 if key == "title" else 1000,
                             key in ("problem", "positioning", "value_hypothesis"))
    insist(draft["source_kind"] in ("synthetic", "user-supplied"), "必须声明来源类型。", "source_kind")
    insist(draft["decision_status"] in ("declared", "proposed", "pending", "conflict"), "决定状态无效。", "decision_status")
    object_keys(draft["success_metric"], "statement baseline target measurement", "success_metric")
    for k, v in draft["success_metric"].items():
        cleaned["success_metric"][k] = prose(v, "success_metric." + k)
    for key in ("included", "excluded", "pending", "legacy_notes"):
        values = draft[key]
        insist(type(values) is list and len(values) <= 50, "此列表最多50项。", key)
        for value in values:
            string(value, key, 1000, True)
            insist(bool(value.strip()), "列表中不能有空白项。", key)
        insist(len(set(values)) == len(values), "列表中存在重复项。", key)
        if key in ("included", "excluded") and not values:
            cleaned[key] = [prose("", key)]
    object_keys(draft["requirement"], "statement priority checks", "requirement")
    cleaned["requirement"]["statement"] = prose(draft["requirement"]["statement"], "requirement.statement")
    insist(draft["requirement"]["priority"] in ("must", "should", "could"), "优先级无效。", "requirement.priority")
    checks = draft["requirement"]["checks"]
    insist(type(checks) is list and 1 <= len(checks) <= 20, "需给出1至20个检查点。", "requirement.checks")
    for i, check in enumerate(checks):
        object_keys(check, "condition expected evidence_level", "requirement.checks")
        for key in ("condition", "expected"):
            cleaned["requirement"]["checks"][i][key] = prose(check[key], f"requirement.checks.{i}.{key}", 450)
        insist(check["evidence_level"] in ("browser", "manual", "content", "static"), "检查证据层级无效。", "requirement.checks")
    object_keys(draft["rule"], "statement default exception boundary", "rule")
    for k, v in draft["rule"].items():
        cleaned["rule"][k] = prose(v, "rule." + k)
    fields = draft["fields"]
    insist(type(fields) is list and 1 <= len(fields) <= 16, "字段数需为1至16个。", "fields")
    names = set()
    for row in fields:
        object_keys(row, "key label type required choices minimum maximum", "fields")
        insist(type(row["key"]) is str and KEY.fullmatch(row["key"]) and row["key"] not in names, "字段标识需唯一且为小写字母/数字/下划线。", "fields")
        names.add(row["key"])
        string(row["label"], "fields.label", 80, True)
        insist(bool(row["label"].strip()), "字段名称不能为空。", "fields.label")
        insist(row["type"] in ("text", "number", "choice", "tags"), "不支持的字段类型；请使用 text/number/choice/tags。", "fields.type")
        insist(type(row["required"]) is bool, "必填属性需为布尔值。", "fields.required")
        if draft["kind"] == "collection":
            insist(row["minimum"] is None and row["maximum"] is None, "集合字段不支持数值上下限。", "fields.minimum")
        elif row["type"] != "number":
            insist(row["minimum"] is None and row["maximum"] is None, "只有数字字段支持上下限。", "fields.minimum")
    object_keys(draft["collection"], "search_fields filters layout items", "collection")
    if draft["kind"] == "collection":
        insist(type(draft["collection"]["search_fields"]) is list and bool(draft["collection"]["search_fields"]),
                "当前集合核心至少需要1个明确选择的搜索字段。", "collection.search_fields")
    object_keys(draft["form"], "initial_values initial_state", "form")
    insist(draft["form"]["initial_state"] == "draft", "本地工作台仅从草稿状态开始。", "form.initial_state")
    cleaned["pending"] = list(dict.fromkeys(cleaned["pending"] + pending))
    if pending:
        cleaned["decision_status"] = "pending"
    return cleaned


def to_task(draft, task_id, version):
    """Preserve all supplied values; only explicit pending prose may be filled."""
    d = validate_draft(draft)
    string(version, "version", 120, True)
    insist(bool(version.strip()), "版本不能为空。", "version")
    insist(type(task_id) is str and KEY.fullmatch(task_id), "内部任务标识无效。")
    req = {"id": "main", "statement": d["requirement"]["statement"],
           "priority": d["requirement"]["priority"], "priority_reason": d["priority_basis"],
           "evidence_ids": ["source_note"], "decision_ids": ["decision_main"], "rule_ids": ["rule_main"],
           "checks": [{"id": f"main_c{i}", **c} for i, c in enumerate(d["requirement"]["checks"], 1)]}
    fields = []
    for f in d["fields"]:
        row = {k: deepcopy(f[k]) for k in ("key", "label", "type", "required", "choices")}
        if d["kind"] == "form" and f["type"] == "number":
            row.update(minimum=f["minimum"], maximum=f["maximum"])
        fields.append(row)
    spec = {"schema": "pm-collection/v1" if d["kind"] == "collection" else "pm-request/v1",
            "id": task_id, "version": version, "parent_sha256": None, "title": d["title"],
            "positioning": d["positioning"], "pain": d["problem"], "value": d["value_hypothesis"],
            "fields": fields, "requirements": [{"id": "main", "statement": req["statement"],
                "acceptance": [c["condition"] + "；预期：" + c["expected"] for c in req["checks"]]}]}
    spec.update(deepcopy(d["collection"] if d["kind"] == "collection" else d["form"]))
    task = {"schema": "pm-task/v1", "id": task_id, "version": version, "parent_task_sha256": None,
            "source_kind": d["source_kind"], "title": d["title"],
            "brief": {k: deepcopy(d[k]) for k in ("audience", "problem", "positioning", "value_hypothesis", "goal", "success_metric", "priority_basis")},
            "evidence": [{"id": "source_note", "kind": "synthetic" if d["source_kind"] == "synthetic" else "hypothesis",
                          "text": d["source_note"], "source": "本地工作台使用者声明；来源真实性未由工具核验。"}],
            "decisions": [{"id": "decision_main", "statement": req["statement"], "status": d["decision_status"], "evidence_ids": ["source_note"]}],
            "scope": {"included": d["included"], "excluded": d["excluded"], "consumers": [{"id": "consumer_main", "included": True,
                      "reason": d["audience"], "evidence_ids": ["source_note"]}]},
            "rules": [{"id": "rule_main", **d["rule"], "evidence_ids": ["source_note"], "requirement_ids": ["main"]}],
            "requirements": [req], "prototype": spec, "pending": d["pending"]}
    # Imported old notes stay explicitly unverified in the same-version handoff.
    task["evidence"].extend({"id": f"legacy_note_{i}", "kind": "hypothesis", "text": "未核验旧记录备注：" + note,
        "source": "旧原型导入备注；不是当前版本的观察或验收证据。"} for i, note in enumerate(d["legacy_notes"], 1))
    try:
        task_core.validate_task(task)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise DraftError("草稿的字段、类型、初值或检查项不符合核心合同。", ["fields", "collection", "form", "requirement"]) from exc
    return task
