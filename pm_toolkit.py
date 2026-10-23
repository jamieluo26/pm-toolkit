#!/usr/bin/env python3
"""PM Toolkit v0.1: bounded local preparation and consistency checks, no network."""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
VERSION = "pm-toolkit/0.1"
MAX_SOURCE = 96000
ID = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,47}$")
OUTPUTS = {"case.json", "product-brief.md", "requirements.md", "handoff.md",
           "decision-map.json", "decision-map.html", "document-source.json",
           "handoff.docx", "prototype.html", "journey.html"}


class ToolkitError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def unique_object(pairs):
    answer = {}
    for key, value in pairs:
        if key in answer:
            raise ToolkitError("DUPLICATE_JSON_KEY")
        answer[key] = value
    return answer


def decode(raw):
    if len(raw) > MAX_SOURCE:
        raise ToolkitError("SOURCE_TOO_LARGE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ToolkitError("NON_FINITE_JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ToolkitError("INVALID_JSON") from None


def text(value, cap=1200):
    if not isinstance(value, str) or not 1 <= len(value) <= cap or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ToolkitError("INVALID_TEXT")


def validate_case(case):
    keys = {"schema", "caseId", "title", "edition", "sourceKind", "context", "evidence",
            "decisions", "requirements", "pending", "excluded", "themes", "books"}
    if not isinstance(case, dict) or set(case) != keys or case["schema"] != "pm-toolkit-case/v1":
        raise ToolkitError("CASE_SCHEMA")
    if not isinstance(case["caseId"], str) or not ID.fullmatch(case["caseId"]):
        raise ToolkitError("CASE_ID")
    text(case["title"], 30); text(case["edition"], 40)
    if case["sourceKind"] not in ("synthetic", "user-supplied"):
        raise ToolkitError("SOURCE_KIND")
    if not isinstance(case["context"], dict) or set(case["context"]) != {"audience", "pain", "value", "goal", "hypothesis"}:
        raise ToolkitError("CONTEXT_FIELDS")
    for v in case["context"].values():
        text(v)
    schemas = {"evidence": {"id", "text"}, "decisions": {"id", "text", "source"},
               "requirements": {"id", "text", "source", "checkId", "check", "expected"},
               "pending": {"id", "text", "source"}}
    groups = {}
    for group, fields in schemas.items():
        rows = case[group]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
            raise ToolkitError("ROW_LIMIT")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ToolkitError("ROW_FIELDS")
            for key, value in row.items():
                text(value)
                if key in ("id", "checkId", "source") and not ID.fullmatch(value):
                    raise ToolkitError("ROW_ID")
            if row["id"] in seen:
                raise ToolkitError("DUPLICATE_ROW_ID")
            seen.add(row["id"])
        groups[group] = seen
    all_ids = [row["id"] for g in schemas for row in case[g]]
    if len(set(all_ids)) != len(all_ids):
        raise ToolkitError("CROSS_GROUP_ID_COLLISION")
    for group in ("decisions", "requirements", "pending"):
        if any(row["source"] not in groups["evidence"] for row in case[group]):
            raise ToolkitError("UNKNOWN_EVIDENCE")
    checks = [r["checkId"] for r in case["requirements"]]
    if len(set(checks)) != len(checks):
        raise ToolkitError("DUPLICATE_CHECK_ID")
    if not isinstance(case["excluded"], list) or not 1 <= len(case["excluded"]) <= 6:
        raise ToolkitError("EXCLUDED_LIMIT")
    for v in case["excluded"]:
        text(v)
    themes = case["themes"]
    if not isinstance(themes, list) or not 1 <= len(themes) <= 8:
        raise ToolkitError("THEME_LIMIT")
    for v in themes:
        text(v, 24)
    if len(set(themes)) != len(themes) or "全部" in themes:
        raise ToolkitError("THEME_COLLISION")
    if not isinstance(case["books"], list) or not 1 <= len(case["books"]) <= 30:
        raise ToolkitError("BOOK_LIMIT")
    seen = set()
    for row in case["books"]:
        if not isinstance(row, dict) or set(row) != {"id", "title", "themes"}:
            raise ToolkitError("BOOK_FIELDS")
        text(row["title"], 80)
        if not isinstance(row["id"], str) or not ID.fullmatch(row["id"]) or row["id"] in seen:
            raise ToolkitError("BOOK_ID")
        seen.add(row["id"])
        if not isinstance(row["themes"], list) or not row["themes"] or any(t not in themes for t in row["themes"]) or len(set(row["themes"])) != len(row["themes"]):
            raise ToolkitError("BOOK_THEMES")
    # Frozen upstream templates reserve these markers. Reject explicitly instead
    # of letting their sequential expansion alter a caller's literal content.
    if re.search(r"__MAP_|__MINDMAP_|__DOCUMENT_TITLE__|__CONTENT__", json.dumps(case, ensure_ascii=False)):
        raise ToolkitError("RESERVED_UPSTREAM_TOKEN")
    return case


def capture(path):
    try:
        with Path(path).open("rb") as f:
            raw = f.read(MAX_SOURCE + 1)
    except OSError:
        raise ToolkitError("SOURCE_READ_FAILED") from None
    return raw, validate_case(decode(raw))


def load_component(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise ToolkitError("COMPONENT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def components():
    provenance = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    allowed = {"components/product-mindmap/scripts/build_map.py", "components/product-mindmap/assets/mindmap.html",
               "components/product-mindmap/assets/standalone.html", "components/structured-docx/tools/structured_docx.py"}
    if {r["distributed_path"] for r in provenance["files"]} != allowed or len(provenance["files"]) != 4:
        raise ToolkitError("UPSTREAM_SCOPE")
    for row in provenance["files"]:
        p = ROOT / row["distributed_path"]
        if p.is_symlink() or digest(p.read_bytes()) != row["sha256"]:
            raise ToolkitError("UPSTREAM_BYTES_CHANGED")
    return (load_component("toolkit_mindmap", "components/product-mindmap/scripts/build_map.py"),
            load_component("toolkit_docx", "components/structured-docx/tools/structured_docx.py"))


def model(case):
    blocks = [{"type": "paragraph", "text": "用途：供评审者核对本版定位、需求、检查计划与待定事项。来源类型为 " + case["sourceKind"] + "；文本关系和文档生成不等于业务验收。"},
              {"type": "paragraph", "text": "版本 " + case["edition"]}]
    def section(title, paragraphs):
        blocks.append({"type": "heading", "level": 1, "text": title})
        blocks.extend({"type": "paragraph", "text": p} for p in paragraphs)
    labels = {"audience": "定位", "pain": "痛点", "value": "价值", "goal": "目标", "hypothesis": "待证假设"}
    section("定位与价值", [labels[k] + "：" + v for k, v in case["context"].items()])
    section("讨论依据", [r["id"] + "：" + r["text"] for r in case["evidence"]])
    section("本版设定中的决定", [r["id"] + "：" + r["text"] + " 依据 " + r["source"] for r in case["decisions"]])
    section("需求与检查计划", [r["id"] + "：" + r["text"] + " 依据 " + r["source"] + "\n" + r["checkId"] + " 关联 " + r["id"] + "：" + r["check"] + "\n预期：" + r["expected"] + "\n状态：计划；需另有当前版本实际观察才能记录通过。" for r in case["requirements"]])
    section("排除范围", case["excluded"])
    section("待定事项", [r["id"] + "：" + r["text"] + " 依据 " + r["source"] for r in case["pending"]])
    section("交接与验收边界", ["prototype.html 是本地演示，默认、空态和重复选择仅属演示合同，不代表真实项目批准。静态关系、工具运行、界面观察、内容回读、排版及人的验收分别记录；无证据保留未验证。"])
    return {"version": "structured-docx/v1", "title": case["title"] + " 需求交接说明", "author": "", "language": "zh-CN", "createdAt": "2000-01-01T00:00:00Z", "blocks": blocks}


def map_model(case):
    def node(id_, title, status, facts, children=None):
        return {"id": id_, "title": title, "status": status, "facts": facts, "children": children or []}
    root = node("root", case["title"], "suggested", [["来源类型", case["sourceKind"]], ["注意", "图中的确认仅指给定设定；不证明真实人的批准。"]], [
        node("context", "定位与价值", "suggested", [[k, v] for k, v in case["context"].items()]),
        node("decisions", "决定与依据", "confirmed", [["层级", "给定设定内"]], [node("decision-" + r["id"], r["id"], "confirmed", [["决定", r["text"]], ["来源", r["source"]]]) for r in case["decisions"]]),
        node("requirements", "需求与检查计划", "suggested", [["状态", "需要实际观察"]], [node("requirement-" + r["id"], r["id"] + " / " + r["checkId"], "suggested", [["需求", r["text"]], ["检查", r["check"]], ["预期", r["expected"]], ["来源", r["source"]]]) for r in case["requirements"]]),
        node("pending", "待定与排除", "pending", [["排除", "；".join(case["excluded"])]], [node("pending-" + r["id"], r["id"], "pending", [["问题", r["text"]], ["来源", r["source"]]]) for r in case["pending"]])])
    return {"schema": "interactive-mindmap/v1", "rootId": "pm-toolkit-map", "edition": case["edition"], "kind": "给定材料的决策图", "root": root, "initialSelected": "root", "initialExpanded": ["root", "requirements", "pending"]}


def md_text(value):
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


def documents(case):
    notice = "来源类型：" + case["sourceKind"] + "。这是材料与演示合同，不构成真实业务批准或验收。\n\n"
    brief = "# " + md_text(case["title"]) + " 产品简报\n\n" + notice + "版本：" + md_text(case["edition"]) + "\n\n"
    for k, v in case["context"].items():
        brief += "- " + k + "：" + md_text(v) + "\n"
    brief += "\n## 决定与来源\n\n" + "\n".join("- " + md_text(r["id"] + " " + r["text"] + " ← " + r["source"]) for r in case["decisions"]) + "\n"
    req = "# 需求与检查计划\n\n" + notice + "| 需求 | 内容 | 来源 | 检查 | 动作与预期 |\n|---|---|---|---|---|\n"
    for r in case["requirements"]:
        req += "| " + " | ".join(md_text(v) for v in (r["id"], r["text"], r["source"], r["checkId"], r["check"] + "；预期 " + r["expected"])) + " |\n"
    req += "\n各检查仍为计划。实际浏览器证据单独记录，不由本表自动判定通过。\n"
    handoff = "# 评审交接\n\n" + notice + "## 先看真实制品\n\n[决策图](decision-map.html) · [可操作演示原型](prototype.html) · [可编辑交接文档](handoff.docx)\n\n## 待定事项\n\n"
    handoff += "\n".join("- " + md_text(r["id"] + " " + r["text"] + " ← " + r["source"]) for r in case["pending"])
    handoff += "\n\n## 本轮排除\n\n" + "\n".join("- " + md_text(v) for v in case["excluded"])
    handoff += "\n\n## 接收者逐项核对\n\n核对定位与价值、R/C 双向关系、默认与空态；逐个实际操作后记录当前版本证据。文档内容核对 PASS 只支持其有序正文与给定模型一致。工具本身不脱敏，也不上传、安装、调用模型或部署。\n"
    return {"product-brief.md": brief.encode(), "requirements.md": req.encode(), "handoff.md": handoff.encode()}


def expand_template(template, replacements):
    """Replace markers in the original template once, never in inserted values."""
    pattern = "|".join(re.escape(key) for key in replacements)
    return re.sub(pattern, lambda match: replacements[match.group(0)], template)


def prototype(case):
    template = (ROOT / "src/prototype.html").read_text(encoding="utf-8")
    data = {k: case[k] for k in ("caseId", "title", "edition", "sourceKind", "themes", "books")}
    safe = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return expand_template(template, {"__TITLE__": html.escape(case["title"]), "__CASE_DATA__": safe}).encode()


def journey(case):
    esc = html.escape
    parts = ["<section id='brief'><small>01 / 产品简报</small><h2>先明确要帮助谁</h2>"]
    labels = {"audience": "定位", "pain": "痛点", "value": "价值", "goal": "目标", "hypothesis": "待证假设"}
    for k, v in case["context"].items():
        parts.append("<p><strong>" + labels[k] + "：</strong>" + esc(v) + "</p>")
    parts.append("</section><section><small>02 / 决策与范围</small><h2>让决定有来源</h2><details><summary>展开全部给定讨论</summary>")
    parts.extend("<p><strong>" + esc(r["id"]) + "</strong> " + esc(r["text"]) + "</p>" for r in case["evidence"])
    parts.append("</details>")
    parts.extend("<p><strong>" + esc(r["id"]) + "</strong> " + esc(r["text"]) + " <span>← " + esc(r["source"]) + "</span></p>" for r in case["decisions"])
    parts.append("<p>排除：" + esc("；".join(case["excluded"])) + "</p></section><section><small>03 / 原型与需求</small><h2>看看方案怎样回应要求</h2><div class='links'><a href='decision-map.html'>打开交互决策图 ↗</a><a href='prototype.html'>操作阅读清单原型 ↗</a></div><div class='table-wrap'><table><thead><tr><th>需求与来源</th><th>检查计划</th><th>预期结果</th></tr></thead><tbody>")
    for r in case["requirements"]:
        parts.append("<tr><td><strong>" + esc(r["id"]) + "</strong> " + esc(r["text"]) + "<br><span>来源 " + esc(r["source"]) + "</span></td><td><strong>" + esc(r["checkId"]) + "</strong> " + esc(r["check"]) + "</td><td>" + esc(r["expected"]) + "</td></tr>")
    parts.append("</tbody></table></div><p>表中是计划；打开原型操作后，另记当前版本的实际观察。图中的“确认”仅指给定设定。</p></section><section><small>04 / 交付与核对</small><h2>把同一版材料交出去</h2><div class='links'><a href='handoff.docx'>下载可编辑 Word</a><a href='requirements.md' download>下载需求追踪表</a><a href='handoff.md' download>下载交接记录</a></div><p>Word 和导图来自同一份 case.json。CLI check 对新制品的字节和有序正文做核对，不替代浏览器行为、排版和人的验收。</p></section><section><small>05 / 未决问题与复盘</small><h2>把缺口留给下一版</h2>")
    parts.extend("<p><strong>" + esc(r["id"]) + "</strong> " + esc(r["text"]) + " <span>← " + esc(r["source"]) + "</span></p>" for r in case["pending"])
    parts.append("<p>当前交付是本地演示原型和审阅材料。没有真实用户研究、生产上线、协作存储或 AI 运行证明。复盘时分别记录实际实现、观察和仍未执行的检查。</p></section>")
    template = (ROOT / "src/journey.html").read_text(encoding="utf-8")
    return expand_template(template, {"__TITLE__": esc(case["title"]), "__EDITION__": esc(case["edition"]), "__SOURCE_KIND__": esc(case["sourceKind"]), "__STEPS__": "".join(parts)}).encode()


def projections(raw, case, mindmap):
    result = documents(case)
    mm = map_model(case)
    result.update({"case.json": raw, "decision-map.json": encode(mm), "decision-map.html": mindmap.build(mm, standalone=True).encode(),
                   "document-source.json": encode(model(case)), "prototype.html": prototype(case), "journey.html": journey(case)})
    return result


def publish_new_directory(output, files):
    out = Path(output)
    if not out.parent.is_dir() or os.path.lexists(out):
        raise ToolkitError("OUTPUT_MUST_BE_NEW_DIRECTORY_WITH_EXISTING_PARENT")
    try:
        out.mkdir()  # Exclusive reservation; never replaces even an existing empty directory.
    except OSError:
        raise ToolkitError("OUTPUT_RESERVATION_FAILED") from None
    marker = out / "INCOMPLETE.txt"
    try:
        marker.write_text("INCOMPLETE: do not treat this directory as a successful build.\n")
        for name, content in files.items():
            with (out / name).open("xb") as f:
                f.write(content)
        if any((out / k).read_bytes() != v for k, v in files.items()):
            raise ToolkitError("OUTPUT_READBACK_FAILED")
        marker.unlink()
    except (OSError, ToolkitError):
        raise ToolkitError("OUTPUT_INCOMPLETE_KEEP_FOR_INSPECTION") from None


def build(raw, case, output):
    mm, docx = components()
    files = projections(raw, case, mm)
    rendered = docx.render_docx(files["document-source.json"])
    files["handoff.docx"] = rendered.docx_bytes
    verified = docx.verify_docx(files["document-source.json"], files["handoff.docx"], expected_docx_sha256=rendered.docx_sha256, expected_render_profile_sha256=docx.RENDER_PROFILE_SHA256)
    if verified.status != "PASS":
        raise ToolkitError("DOCX_NOT_VERIFIED")
    receipt = {"version": VERSION, "caseId": case["caseId"], "source_sha256": digest(raw), "files": {k: {"bytes": len(v), "sha256": digest(v)} for k, v in sorted(files.items())},
               "docx_profile_sha256": docx.RENDER_PROFILE_SHA256,
               "claims": {"content_readback": "PASS", "browser_behavior": "NOT_RUN", "visual_layout": "NOT_RUN", "human_acceptance": "NOT_RUN", "public_release": "NOT_RUN", "anonymization": "NONE", "authenticity": "NONE"}}
    files["manifest.json"] = encode(receipt)
    publish_new_directory(output, files)
    return {"status": "BUILT_CONTENT_CHECKED", "files": len(files), "source_sha256": digest(raw), "browser_and_visual": "REQUIRE_SEPARATE_OBSERVATION"}


def check(raw, case, output):
    mm, docx = components()
    out = Path(output)
    if out.is_symlink() or not out.is_dir():
        raise ToolkitError("OUTPUT_NOT_DIRECTORY")
    actual = list(out.rglob("*"))
    if any(p.is_symlink() or not p.is_file() for p in actual) or {p.relative_to(out).as_posix() for p in actual} != OUTPUTS | {"manifest.json"}:
        raise ToolkitError("OUTPUT_SET_MISMATCH")
    expected = projections(raw, case, mm)
    manifest = decode((out / "manifest.json").read_bytes())
    if not isinstance(manifest, dict) or manifest.get("version") != VERSION or manifest.get("source_sha256") != digest(raw) or manifest.get("caseId") != case["caseId"] or set(manifest.get("files", {})) != OUTPUTS:
        raise ToolkitError("MANIFEST_SOURCE_MISMATCH")
    for name in OUTPUTS:
        if (out / name).stat().st_size > 8 * 1024 * 1024:
            raise ToolkitError("OUTPUT_TOO_LARGE")
        got = (out / name).read_bytes()
        if len(got) > 8 * 1024 * 1024:
            raise ToolkitError("OUTPUT_TOO_LARGE")
        if manifest["files"][name] != {"bytes": len(got), "sha256": digest(got)} or (name in expected and got != expected[name]):
            raise ToolkitError("OUTPUT_CONTENT_MISMATCH")
    v = docx.verify_docx(expected["document-source.json"], (out / "handoff.docx").read_bytes(), expected_docx_sha256=manifest["files"]["handoff.docx"]["sha256"], expected_render_profile_sha256=docx.RENDER_PROFILE_SHA256)
    if v.status != "PASS" or manifest.get("docx_profile_sha256") != docx.RENDER_PROFILE_SHA256:
        raise ToolkitError("DOCX_CONTENT_MISMATCH")
    return {"status": "PASS_CONTENT_AND_IDENTITIES", "files": 11, "source_sha256": digest(raw), "browser_and_visual": "NOT_PROVEN_BY_THIS_COMMAND", "authenticity": "NONE"}


def main():
    parser = argparse.ArgumentParser(description="Local PM preparation; no network, model or publishing.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "build", "check", "init"):
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, required=True)
        if name in ("build", "check"):
            p.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            files = {p.name: p.read_bytes() for p in sorted((ROOT / "templates").glob("*.md"))}
            files["START-HERE.md"] = (ROOT / "docs/personal-use.md").read_bytes()
            publish_new_directory(args.output, files)
            result = {"status": "BLANK_WORKSPACE_CREATED", "files": len(files), "content_decisions": "MANUAL"}
        else:
            source = ROOT / "examples/reading-list/case.json" if args.command == "demo" else args.source
            raw, case = capture(source)
            result = check(raw, case, args.output) if args.command == "check" else build(raw, case, args.output)
    except (ToolkitError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        code = str(exc) if isinstance(exc, ToolkitError) else "INPUT_COMPONENT_OR_DEPENDENCY_ERROR"
        print(json.dumps({"status": "FAIL", "code": code}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
