"""One task identity across a bounded prototype, PRD, DOCX and supplied evidence.

Input declarations are never authentication, business approval or runtime proof.
"""
from __future__ import annotations

from copy import deepcopy
import html
import json
from pathlib import Path
import re

import flow_core as flow

ROOT = Path(__file__).resolve().parent
Invalid = flow.Invalid
encoded, sha, require, read_json = flow.encoded, flow.sha, flow.require, flow.read_json


def obj(value, fields):
    flow.keys(value, fields)


def text(value, limit=3000, empty=False):
    require(type(value) is str and len(value) <= limit and (empty or bool(value.strip())))
    require(all(ord(c) >= 32 or c in "\n\t" for c in value))


def rows(value, maximum=100, empty=True):
    require(type(value) is list and len(value) <= maximum and (empty or bool(value)))


def refs(value, available, empty=False):
    rows(value, empty=empty)
    require(all(type(x) is str for x in value) and len(set(value)) == len(value))
    require(set(value) <= available)


def unique_ids(values):
    answer = set()
    for row in values:
        flow.identifier(row["id"])
        require(row["id"] not in answer)
        answer.add(row["id"])
    return answer


def prototype_module(spec):
    require(type(spec) is dict)
    if spec.get("schema") == "pm-collection/v1":
        return flow
    if spec.get("schema") == "pm-request/v1":
        import form_core
        return form_core
    raise Invalid("unsupported prototype family")


def validate_task(task):
    obj(task, "schema id version parent_task_sha256 source_kind title brief evidence decisions scope rules requirements prototype pending")
    require(task["schema"] == "pm-task/v1")
    flow.identifier(task["id"])
    for k in ("version", "title"):
        text(task[k], 120)
    if task["parent_task_sha256"] is not None:
        flow.digest(task["parent_task_sha256"])
    require(task["source_kind"] in ("synthetic", "user-supplied"))
    obj(task["brief"], "audience problem positioning value_hypothesis goal success_metric priority_basis")
    for k in ("audience", "problem", "positioning", "value_hypothesis", "goal", "priority_basis"):
        text(task["brief"][k])
    obj(task["brief"]["success_metric"], "statement baseline target measurement")
    for v in task["brief"]["success_metric"].values():
        text(v)
    rows(task["evidence"], empty=False)
    for r in task["evidence"]:
        obj(r, "id kind text source")
        require(r["kind"] in ("supplied_observation", "hypothesis", "synthetic"))
        text(r["text"])
        text(r["source"])
    evidence_ids = unique_ids(task["evidence"])
    rows(task["decisions"], empty=False)
    for r in task["decisions"]:
        obj(r, "id statement status evidence_ids")
        text(r["statement"])
        require(r["status"] in ("declared", "proposed", "pending", "conflict"))
        refs(r["evidence_ids"], evidence_ids)
    decision_ids = unique_ids(task["decisions"])
    obj(task["scope"], "included excluded consumers")
    for k in ("included", "excluded"):
        flow.strings(task["scope"][k])
    rows(task["scope"]["consumers"], empty=False)
    for r in task["scope"]["consumers"]:
        obj(r, "id included reason evidence_ids")
        require(type(r["included"]) is bool)
        text(r["reason"])
        refs(r["evidence_ids"], evidence_ids)
    consumer_ids = unique_ids(task["scope"]["consumers"])
    rows(task["rules"], empty=False)
    rule_ids = unique_ids(task["rules"])
    rows(task["requirements"], empty=False)
    requirement_ids = unique_ids(task["requirements"])
    check_ids = set()
    for r in task["rules"]:
        obj(r, "id statement default exception boundary evidence_ids requirement_ids")
        for k in ("statement", "default", "exception", "boundary"):
            text(r[k])
        refs(r["evidence_ids"], evidence_ids)
        refs(r["requirement_ids"], requirement_ids)
    for r in task["requirements"]:
        obj(r, "id statement priority priority_reason evidence_ids decision_ids rule_ids checks")
        text(r["statement"])
        require(r["priority"] in ("must", "should", "could"))
        text(r["priority_reason"])
        refs(r["evidence_ids"], evidence_ids)
        refs(r["decision_ids"], decision_ids)
        refs(r["rule_ids"], rule_ids)
        rows(r["checks"], 20, empty=False)
        for i, c in enumerate(r["checks"], 1):
            obj(c, "id condition expected evidence_level")
            require(c["id"] == f"{r['id']}_c{i}" and c["id"] not in check_ids)
            check_ids.add(c["id"])
            text(c["condition"])
            text(c["expected"])
            require(c["evidence_level"] in ("browser", "manual", "content", "static"))
        require(all(r["id"] in x["requirement_ids"] for x in task["rules"] if x["id"] in r["rule_ids"]))
    require(all(rule["id"] in req["rule_ids"] for rule in task["rules"] for req in task["requirements"] if req["id"] in rule["requirement_ids"]))
    all_ids = [evidence_ids, decision_ids, consumer_ids, rule_ids, requirement_ids, check_ids]
    require(sum(map(len, all_ids)) == len(set().union(*all_ids)))
    spec = task["prototype"]
    prototype_module(spec).validate_spec(spec)
    require(spec["id"] == task["id"] and spec["version"] == task["version"])
    require((task["parent_task_sha256"] is None) == (spec["parent_sha256"] is None))
    require(spec["positioning"] == task["brief"]["positioning"])
    require(spec["pain"] == task["brief"]["problem"])
    require(spec["value"] == task["brief"]["value_hypothesis"])
    expected = [{"id": r["id"], "statement": r["statement"],
                 "acceptance": [f"{c['condition']}；预期：{c['expected']}" for c in r["checks"]]}
                for r in task["requirements"]]
    require(spec["requirements"] == expected)
    flow.strings(task["pending"], empty=True)
    return task


def task_issues(task):
    issues = ["PENDING:" + str(i) for i, _ in enumerate(task["pending"], 1)]
    issues += ["DECISION_" + r["status"].upper() + ":" + r["id"]
               for r in task["decisions"] if r["status"] != "declared"]
    return issues


def markdown_section(title, paragraphs):
    return "\n".join([f"## {title}", "", *[flow.md(x) for x in paragraphs], ""])


def document_model(task, task_sha, spec_sha, prd):
    blocks = [{"type": "paragraph", "text": f"任务 {task['id']} 版本 {task['version']}"},
              {"type": "paragraph", "text": "用途：评审与交接本版需求背景、规则、同源原型和检查计划。输入来源由调用者声明，工具不证明真人审批或实际业务验收。"},
              {"type": "paragraph", "text": "任务源 SHA256 " + task_sha},
              {"type": "paragraph", "text": "原型规格 SHA256 " + spec_sha}]
    # The whole generated PRD is projected in order. No selective summary or second source.
    for line in prd.splitlines():
        if not line.strip():
            continue
        # Markdown escapes protect the Markdown surface; Word displays literal identifiers.
        line = html.unescape(re.sub(r"\\([\\`|*_\[\]])", r"\1", line))
        if line.startswith("# "):
            blocks.append({"type": "heading", "level": 1, "text": line[2:]})
        elif line.startswith("## "):
            blocks.append({"type": "heading", "level": 1, "text": line[3:]})
        elif line.startswith("### "):
            blocks.append({"type": "heading", "level": 2, "text": line[4:]})
        else:
            blocks.append({"type": "paragraph", "text": line})
    return {"version": "structured-docx/v1", "title": task["title"] + "需求交接", "author": "",
            "language": "zh-CN", "createdAt": "2000-01-01T00:00:00Z", "blocks": blocks}


def docx_component():
    # Existing provenance guard verifies immutable upstream copies before import.
    from pm_toolkit import components
    return components()[1]


def task_payload(task, raw):
    validate_task(task)
    ts = sha(raw)
    spec_raw = encoded(task["prototype"])
    ss = sha(spec_raw)
    proto = prototype_module(task["prototype"]).build_payload(task["prototype"], spec_raw)
    heading = f"# {flow.md(task['title'])}\n\n任务：{task['id']}；版本：{flow.md(task['version'])}\n任务源 SHA-256：{ts}\n规格 SHA-256：{ss}\n\n"
    notice = "来源类型仅为调用者声明；工具不核验来源或脱敏。价值与收益仍是待证假设，给定决定不证明真人审批。\n\n"
    brief = heading + notice + markdown_section("定位与目标", [
        "目标用户：" + task["brief"]["audience"], "问题：" + task["brief"]["problem"],
        "定位：" + task["brief"]["positioning"], "价值假设：" + task["brief"]["value_hypothesis"],
        "目标：" + task["brief"]["goal"], "优先级依据：" + task["brief"]["priority_basis"]])
    brief += markdown_section("成功指标与待验证项", [k + "：" + v for k, v in task["brief"]["success_metric"].items()])
    brief += markdown_section("本轮范围", task["scope"]["included"])
    brief += markdown_section("排除范围", task["scope"]["excluded"])
    evidence = heading + notice + markdown_section("给定证据", [f"{r['id']} [{r['kind']}] {r['text']} 来源：{r['source']}" for r in task["evidence"]])
    evidence += markdown_section("给定决定", [f"{r['id']} [{r['status']}] {r['statement']} 依据：{', '.join(r['evidence_ids'])}" for r in task["decisions"]])
    evidence += markdown_section("未决事项", task["pending"] or ["本输入没有声明未决项；不证明真实项目不存在未知项。"])
    rules = heading + markdown_section("给定消费者与排除理由", [f"{r['id']}：{'纳入' if r['included'] else '排除'}；{r['reason']}；依据 {', '.join(r['evidence_ids'])}" for r in task["scope"]["consumers"]])
    for r in task["rules"]:
        rules += markdown_section(r["id"] + " " + r["statement"], ["默认：" + r["default"], "异常：" + r["exception"],
                  "边界：" + r["boundary"], "需求：" + ", ".join(r["requirement_ids"]), "依据：" + ", ".join(r["evidence_ids"])])
    prd = brief + "\n" + evidence + "\n" + rules + "\n" + proto["PRD.md"].decode()
    checks = [{"requirement_id": r["id"], "id": c["id"], "condition": c["condition"], "expected": c["expected"],
               "prototype_check_id": f"{r['id']}-c{i}", "evidence_level": c["evidence_level"], "status": "NOT_EXECUTED"}
              for r in task["requirements"] for i, c in enumerate(r["checks"], 1)]
    tracing = {"schema": "pm-task-trace/v1", "task_id": task["id"], "version": task["version"],
               "task_sha256": ts, "spec_sha256": ss, "checks": checks,
               "requirements": [{k: r[k] for k in ("id", "priority", "priority_reason", "evidence_ids", "decision_ids", "rule_ids")} for r in task["requirements"]]}
    model = encoded(document_model(task, ts, ss, prd))
    docx = docx_component()
    rendered = docx.render_docx(model)
    verified = docx.verify_docx(model, rendered.docx_bytes, expected_docx_sha256=rendered.docx_sha256,
                                expected_render_profile_sha256=docx.RENDER_PROFILE_SHA256)
    require(verified.status == "PASS")
    files = {"task.json": raw, "spec.json": spec_raw, "prototype.html": proto["prototype.html"],
             "prototype-PRD.md": proto["PRD.md"], "product-brief.md": brief.encode(), "evidence.md": evidence.encode(),
             "rules.md": rules.encode(), "PRD.md": prd.encode(), "acceptance.md": proto["acceptance.md"],
             "trace.json": encoded(tracing), "document-source.json": model, "handoff.docx": rendered.docx_bytes,
             "document-verification.json": encoded({"status": verified.status, "task_sha256": ts,
                    "spec_sha256": ss, "document_source_sha256": sha(model), "docx_sha256": rendered.docx_sha256,
                    "ordered_content_items": len(verified.observed), "visual_render": "NOT_RUN_BY_GENERATOR"})}
    files["handoff.md"] = (heading + "打开 prototype.html 体验；对照 PRD.md 与 rules.md；handoff.docx 完整投影同版 PRD。\n\n"
          + "工具的一致性检查不执行检查计划、不证明实际交互或排版。接手者须使用当前版本记录观察，并复核来源、规则与业务质量。\n\n"
          + "待处理：" + (" / ".join(task_issues(task)) or "没有输入内未决声明；未知事项仍由人核对。") + "\n").encode()
    files["observations-template.json"] = encoded({"schema": "pm-task-observations/v1", "task_sha256": ts,
          "prototype_sha256": sha(files["prototype.html"]),
          "rows": [{"id": f"obs_{i}", "check_id": c["id"], "status": "not_run", "level": c["evidence_level"],
                    "observed": "", "evidence_ref": "", "supersedes": None, "defect": None}
                   for i, c in enumerate(files_to_checks(task), 1)]})
    files["journey.html"] = journey(task, ts, brief, rules, evidence)
    files["manifest.json"] = manifest(task, ts, ss, files)
    return files


def manifest(task, ts, ss, files):
    paths = ["task_core.py", "task_revision.py", "pm_task.py", "flow_core.py", "pm_flow.py", "assets/collection.html",
             "pm_toolkit.py", "UPSTREAM.json", "components/structured-docx/tools/structured_docx.py"]
    if task["prototype"]["schema"] == "pm-request/v1":
        paths += ["form_core.py", "pm_form.py", "assets/request-form.html"]
    return encoded({"schema": "pm-task-artifacts/v1", "task_id": task["id"], "version": task["version"],
          "task_sha256": ts, "spec_sha256": ss, "status": "HOLD" if task_issues(task) else "GENERATED_NOT_ACCEPTED",
          "issues": task_issues(task), "generator": {p: sha((ROOT / p).read_bytes()) for p in paths},
          "files": {k: sha(v) for k, v in sorted(files.items()) if k != "manifest.json"}})


def journey(task, ts, brief, rules, evidence):
    esc = html.escape
    panels = [("01 需求澄清", brief), ("02 范围与规则", rules), ("03 决定与依据", evidence)]
    sections = "".join(f"<details><summary>{esc(title)}</summary><pre>{esc(body)}</pre></details>" for title, body in panels)
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
       + "<link rel='icon' href='data:,'><title>产品任务工作包</title><style>body{font:16px/1.8 system-ui;background:#f7f7f2;color:#263a31;max-width:1100px;margin:40px auto;padding:24px}h1{font-size:38px}nav{display:flex;gap:12px;flex-wrap:wrap}a{color:#2d6247;padding:12px;border:1px solid #cbd5c7;border-radius:8px}details{margin:24px 0;border:1px solid #ccd5c7;border-radius:8px;padding:18px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 system-ui}small{overflow-wrap:anywhere}</style>"
       + f"<p>PM TOOLKIT / TASK WORKPACK</p><h1>{esc(task['title'])}</h1><p>任务 {esc(task['id'])} · {esc(task['version'])}</p>"
       + "<p>先读需求与规则，再体验原型、核对文档；按检查计划记录实际观察。这里的生成结果尚未获得业务验收。</p>"
       + "<nav><a href='prototype.html'>体验当前原型 ↗</a><a href='handoff.docx'>带走同版 Word ↓</a><a href='PRD.md' download>PRD ↓</a><a href='acceptance.md' download>待执行检查计划 ↓</a><a href='trace.json' download>关系与版本 ↓</a></nav>"
       + sections + "<details><summary>04 评审到复盘</summary><p>按 docs/lifecycle.md 从反馈与人工决定生成修订核对；每次生成新目录。用当前任务SHA绑定观察记录，再生成交付说明、问题复验、版本说明、产品手册与复盘。</p><p>无法确定的结论保持待定，失败或未执行不升级成通过。</p></details>"
       + f"<small>任务源 SHA-256：{ts}。输入来自调用者，工具不核验来源或脱敏；本地会话操作不等于业务审批。</small></html>").encode()


def review_tasks(before, after, feedback, decisions, raws):
    validate_task(before)
    validate_task(after)
    obj(feedback, "schema before_task_sha256 items")
    require(feedback["schema"] == "pm-task-feedback/v1")
    flow.digest(feedback["before_task_sha256"])
    rows(feedback["items"], empty=False)
    for r in feedback["items"]:
        obj(r, "id text source")
        text(r["text"])
        text(r["source"])
    fids = unique_ids(feedback["items"])
    obj(decisions, "schema before_task_sha256 after_task_sha256 feedback_sha256 items")
    require(decisions["schema"] == "pm-task-decisions/v1")
    for k in ("before_task_sha256", "after_task_sha256", "feedback_sha256"):
        flow.digest(decisions[k])
    rows(decisions["items"], empty=False)
    ids = set()
    for r in decisions["items"]:
        obj(r, "feedback_id status rationale paths")
        require(r["feedback_id"] in fids and r["feedback_id"] not in ids)
        ids.add(r["feedback_id"])
        require(r["status"] in ("adopted", "declined", "pending", "conflict"))
        text(r["rationale"])
        flow.strings(r["paths"], empty=True)
        require(all(p.startswith("/") for p in r["paths"]))
        require(r["status"] == "adopted" or not r["paths"])
    issues = []
    hashes = {k: sha(v) for k, v in raws.items()}
    def hold(condition, reason):
        if condition:
            issues.append(reason)
    hold(feedback["before_task_sha256"] != hashes["before.json"], "STALE_FEEDBACK")
    for k, name in (("before_task_sha256", "before.json"), ("after_task_sha256", "after.json"), ("feedback_sha256", "feedback.json")):
        hold(decisions[k] != hashes[name], "STALE_DECISIONS:" + k)
    hold(after["parent_task_sha256"] != hashes["before.json"], "AFTER_PARENT_MISMATCH")
    hold(before["id"] != after["id"], "TASK_ID_CHANGED")
    hold(before["version"] == after["version"], "VERSION_NOT_CHANGED")
    hold(after["prototype"]["parent_sha256"] != sha(encoded(before["prototype"])), "PROTOTYPE_PARENT_MISMATCH")
    ignored = {"/version", "/parent_task_sha256", "/prototype/version", "/prototype/parent_sha256"}
    changed = [p for p in flow.differences(before, after) if p not in ignored]
    hold(not changed, "NO_CHANGE")
    cover = {p: [] for p in changed}
    for fid in sorted(fids):
        r = next((x for x in decisions["items"] if x["feedback_id"] == fid), None)
        hold(r is None, "MISSING_DECISION:" + fid)
        if r is None:
            continue
        hold(r["status"] in ("pending", "conflict"), "UNRESOLVED_FEEDBACK:" + fid)
        if r["status"] == "adopted":
            hold(not r["paths"], "ADOPTED_WITHOUT_CHANGE:" + fid)
            for path in r["paths"]:
                hold(path not in cover, "UNMATCHED_PATH:" + path)
                if path in cover:
                    cover[path].append(fid)
    for path, owners in cover.items():
        hold(len(owners) != 1, "CHANGE_COVERAGE:" + path)
    issues += ["AFTER_" + x for x in task_issues(after)]
    report = {"schema": "pm-task-review/v1", "status": "HOLD" if issues else "DECLARED_CHANGE_COVERED",
              "meaning": "Supplied literal change coverage; not human approval or functional intent proof.",
              "task_id": after["id"], "before_version": before["version"], "after_version": after["version"],
              "input_sha256": hashes, "changed_paths": changed, "coverage": cover, "issues": issues}
    lines = ["# 评审修订核对", "", "状态：" + report["status"], "",
             "只核对给定文本差异和处理决定。采纳/拒绝标签由调用者提供，不证明真人批准；功能意图仍需审阅。", "",
             "## 反馈去向", ""]
    for f in feedback["items"]:
        d = next((x for x in decisions["items"] if x["feedback_id"] == f["id"]), None)
        lines.append(f"- {f['id']}：{flow.md(f['text'])}；来源：{flow.md(f['source'])}；处理：{d['status'] if d else 'missing'}；理由：{flow.md(d['rationale']) if d else '缺失'}")
    lines += ["", "## 变更与承接", ""] + [f"- {flow.md(p)} ← {', '.join(v) or '未承接'}" for p, v in cover.items()]
    lines += ["", "## 待处理", ""] + (["- " + flow.md(x) for x in issues] or ["给定范围无未覆盖项；真实评审与实际行为仍由人核对。"])
    return {**raws, "review.json": encoded(report), "REVIEW.md": ("\n".join(lines) + "\n").encode()}, report


def evidence_report(task, raw, observations, expected_prototype):
    obj(observations, "schema task_sha256 prototype_sha256 rows")
    require(observations["schema"] == "pm-task-observations/v1")
    for k in ("task_sha256", "prototype_sha256"):
        flow.digest(observations[k])
    # Up to 600 declared checks, with room for retained failure/recheck history.
    rows(observations["rows"], maximum=10000)
    check_ids = {c["id"] for r in task["requirements"] for c in r["checks"]}
    levels = {c["id"]: c["evidence_level"] for c in files_to_checks(task)}
    seen, latest, failures = {}, {}, []
    issues = task_issues(task)
    if observations["task_sha256"] != sha(raw):
        issues.append("STALE_TASK_OBSERVATIONS")
    if observations["prototype_sha256"] != sha(expected_prototype):
        issues.append("STALE_PROTOTYPE_OBSERVATIONS")
    for r in observations["rows"]:
        obj(r, "id check_id status level observed evidence_ref supersedes defect")
        flow.identifier(r["id"])
        require(r["id"] not in seen and r["check_id"] in check_ids)
        require(r["status"] in ("pass", "fail", "not_run"))
        require(r["level"] in ("browser", "manual", "content", "static"))
        text(r["observed"], empty=r["status"] == "not_run")
        text(r["evidence_ref"], empty=r["status"] == "not_run")
        require(r["supersedes"] == latest.get(r["check_id"]))
        if r["defect"] is not None:
            text(r["defect"])
        require(r["status"] != "fail" or bool(r["defect"]))
        if r["status"] == "fail":
            failures.append(r)
        seen[r["id"]] = r
        latest[r["check_id"]] = r["id"]
    for cid in sorted(check_ids):
        if cid not in latest or seen[latest[cid]]["status"] != "pass":
            issues.append("CHECK_NOT_REPORTED_PASS:" + cid)
        elif seen[latest[cid]]["level"] != levels[cid]:
            issues.append("EVIDENCE_LEVEL_MISMATCH:" + cid)
    defects = [{"observation": r["id"], "check_id": r["check_id"], "description": r["defect"],
                "status": "RECHECK_REPORTED" if seen[latest[r["check_id"]]]["status"] == "pass" else "OPEN",
                "latest_observation": latest[r["check_id"]]} for r in failures]
    return {"schema": "pm-task-evidence-report/v1", "status": "HOLD" if issues else "SUPPLIED_EVIDENCE_COVERED",
            "meaning": "Caller-provided observations; not independently executed or authenticated by this command.",
            "task_id": task["id"], "version": task["version"], "task_sha256": sha(raw),
            "prototype_sha256": sha(expected_prototype), "observations": observations["rows"],
            "latest": latest, "defects": defects, "issues": issues}


def delivery_payload(task, raw, observations, observations_raw, review_files=None, review=None):
    files = task_payload(task, raw)
    report = evidence_report(task, raw, observations, files["prototype.html"])
    issues = report["issues"][:]
    if review is not None:
        require(review["input_sha256"]["after.json"] == sha(raw))
        issues += review["issues"]
    elif task["parent_task_sha256"] is not None:
        issues.append("MISSING_REVIEW_FOR_REVISION")
    report["issues"] = issues
    report["status"] = "HOLD" if issues else "SUPPLIED_EVIDENCE_COVERED"
    files["observations.json"] = observations_raw
    files["acceptance-results.json"] = encoded(report)
    common = f"任务 {task['id']}；版本 {task['version']}；任务源 SHA-256 {sha(raw)}。\n\n"
    common += "以下汇总来自调用者给定的材料与观察声明。工具不执行浏览器、不核实引用指向的事实，也不代表真人验收或生产发布。\n\n"
    lines = ["# 实际检查与问题复验记录", "", common, "状态：" + report["status"], ""]
    for c in files_to_checks(task):
        last = next((x for x in report["observations"] if x["id"] == report["latest"].get(c["id"])), None)
        lines += [f"## {c['id']}", f"条件：{flow.md(c['condition'])}", f"预期：{flow.md(c['expected'])}",
                  "给定最新状态：" + (last["status"] if last else "not_run"),
                  "观察与引用：" + (flow.md(last["observed"] + " / " + last["evidence_ref"]) if last else "未提供"), ""]
    files["acceptance-results.md"] = ("\n".join(lines) + "\n").encode()
    files["defects.json"] = encoded({"schema": "pm-task-defects/v1", "task_sha256": sha(raw), "rows": report["defects"]})
    files["delivery.md"] = ("# 版本交接\n\n" + common + "状态：" + report["status"] + "\n\n"
          + "接手入口：journey.html；运行原型：prototype.html；需求：PRD.md；同版交接：handoff.docx；检查：acceptance-results.md。\n\n"
          + "未闭合：" + (" / ".join(issues) or "输入内无未覆盖声明。业务适用性、来源真实性、真人验收和部署未由工具证明。") + "\n").encode()
    changes = review["changed_paths"] if review else []
    files["release-notes.md"] = ("# 版本变更说明\n\n" + common + "本文件描述给定版本材料，不声明已经上线。\n\n"
          + "\n".join("- " + flow.md(x) for x in changes or ["初始版本；没有给定前版比较。"])
          + "\n\n检查汇总：" + report["status"] + "\n").encode()
    files["product-handbook.md"] = ("# 当前任务的产品资产手册\n\n" + common
          + "给定材料状态：" + report["status"] + "。以下需求是声明，不能据此认定已经实现；实际已给观察及覆盖情况见 acceptance-results.md。\n\n"
          + markdown_section("给定定位与需求声明", [task["brief"]["positioning"], *[r["id"] + "：" + r["statement"] for r in task["requirements"]]])
          + markdown_section("当前排除范围", task["scope"]["excluded"])
          + markdown_section("给定决定与状态", [r["id"] + " [" + r["status"] + "]：" + r["statement"] + " 依据 " + ", ".join(r["evidence_ids"]) for r in task["decisions"]])
          + markdown_section("当前证据与接手", ["观察：acceptance-results.md；问题复验：defects.json；本次材料状态：" + report["status"],
                      "本目录体现给定离线任务，不认证生产当前态。"])).encode()
    files["retrospective.md"] = ("# 版本复盘与下一轮输入\n\n" + common
          + markdown_section("本次已给定的变化", changes or ["初始版，无给定前版。"])
          + markdown_section("失败与复验", [r["description"] + "：" + r["status"] for r in report["defects"]] or ["输入未声明失败记录，不证明从未发生失败。"])
          + markdown_section("目标结果", ["业务指标未由本工具采集。", *[k + "：" + v for k, v in task["brief"]["success_metric"].items()]])
          + markdown_section("下一轮问题", task["pending"] + issues or ["向目标用户验证价值假设；收集指标基线；据此形成下一轮产品简报。"])).encode()
    if review_files:
        for name, content in review_files.items():
            files["review-" + name] = content
    files["manifest.json"] = manifest(task, sha(raw), sha(encoded(task["prototype"])), files)
    return files, report


def files_to_checks(task):
    return [c for r in task["requirements"] for c in r["checks"]]


def initialize_payload():
    sample, _ = read_json(ROOT / "templates/task.json")
    return {"task.json": encoded(sample), "START.md": (
        "# 开始自己的产品任务\n\n先填写 task.json：用户、问题、价值假设、范围与来源；再修改规格字段与样例。"
        "保留未确定事项，不能把占位值当事实。同步修改 requirements 与 prototype.requirements，具体合同见 docs/task-spec.md。\n\n"
        "在工具包根目录运行 pm_task.py build --source 新目录/task.json --output 另一个新目录。"
        "生成时会保留待定项并返回 HOLD；先补齐来源与决定，再进入评审和检查。\n").encode()}
