"""Black-box checks for finite collection builds and declared change reviews.

Run: python3 -B -m unittest discover -s tests -p test_flow.py -v
All mutation is confined to synthetic temporary inputs and outputs. No model,
browser, network, Skill, original project, or existing artifact is changed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "pm_flow.py"
BUILD_NAMES = {"source.json", "prototype.html", "PRD.md", "acceptance.md", "trace.json", "manifest.json"}
REVIEW_NAMES = {"before.json", "after.json", "feedback.json", "decisions.json", "review.json", "REVIEW.md"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def snapshot(path):
    return {p.relative_to(path).as_posix(): (sha(p.read_bytes()), p.stat().st_mtime_ns, p.stat().st_size)
            for p in path.rglob("*") if p.is_file() and not p.is_symlink()}


def reading_case():
    return {
        "schema": "pm-collection/v1", "id": "reading_board", "version": "v1", "parent_sha256": None,
        "title": "个人阅读清单", "positioning": "供个人按主题找回待读内容。",
        "pain": "零散记录不便找回，这是合成假设。", "value": "减少找回步骤，仍需真实研究验证。",
        "fields": [
            {"key": "title", "label": "书名", "type": "text", "required": True, "choices": []},
            {"key": "score", "label": "评分", "type": "number", "required": False, "choices": []},
            {"key": "topic", "label": "主题", "type": "choice", "required": True,
             "choices": ["产品", "技术", "研究", "历史"]},
            {"key": "tags", "label": "阅读状态", "type": "tags", "required": False,
             "choices": ["待看", "已看"]},
        ],
        "search_fields": ["title"], "filters": ["topic", "tags"], "layout": "sidebar",
        "items": [
            {"id": "method_notes", "values": {"title": "方法卡片", "score": 0, "topic": "产品", "tags": ["待看"]}},
            {"id": "engineering_notes", "values": {"title": "工程日记", "score": 7.5, "topic": "技术", "tags": ["已看"]}},
            {"id": "research_notes", "values": {"title": "调研手册", "score": None, "topic": "研究", "tags": []}},
        ],
        "requirements": [
            {"id": "r_display", "statement": "默认展示给定三本合成书目。", "acceptance": ["三本书目都可见。", "零分保持为数值零。"]},
            {"id": "r_filter", "statement": "允许筛选后恢复全部。", "acceptance": ["选择历史显示空态。", "重置恢复三本书目。"]},
        ],
    }


def ideas_case():
    return {
        "schema": "pm-collection/v1", "id": "ideas_board", "version": "rev1", "parent_sha256": None,
        "title": "灵感收集板", "positioning": "供个人整理待验证的产品想法。",
        "pain": "想法与验证状态分散，这是人工合成背景。", "value": "让未验证想法和已讨论想法分开。",
        "fields": [
            {"key": "idea", "label": "想法", "type": "text", "required": True, "choices": []},
            {"key": "state", "label": "讨论状态", "type": "choice", "required": True,
             "choices": ["新建", "评审", "搁置"]},
            {"key": "labels", "label": "平台", "type": "tags", "required": False, "choices": ["移动", "桌面"]},
        ],
        "search_fields": ["idea", "state"], "filters": ["state", "labels"], "layout": "toolbar",
        "items": [
            {"id": "capture", "values": {"idea": "快速记录", "state": "新建", "labels": ["移动", "桌面"]}},
            {"id": "review", "values": {"idea": "每周回顾", "state": "评审", "labels": ["桌面"]}},
        ],
        "requirements": [
            {"id": "r_ideas", "statement": "展示本次给定的想法与状态。", "acceptance": ["两条想法与给定状态均可见。"]},
        ],
    }


class Surface(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.handlers = []
        self.tags = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "script":
            self.scripts.append(dict(attrs))
        self.handlers.extend(value or "" for name, value in attrs if name.lower().startswith("on"))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-flow-blackbox-")
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.counter = 0

    def file(self, name, data):
        path = self.tmp / name
        path.write_bytes(data if type(data) is bytes else encoded(data))
        return path

    def run_cli(self, command, **paths):
        argv = [sys.executable, "-B", str(CLI), command]
        for name, value in paths.items():
            argv += ["--" + name, str(value)]
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONPATH="")
        process = subprocess.run(argv, cwd=self.tmp, env=env, capture_output=True, timeout=30)
        event = {"argv": argv, "exit": process.returncode,
                 "stdout": process.stdout.decode("utf-8", errors="replace"),
                 "stderr": process.stderr.decode("utf-8", errors="replace"),
                 "stdout_sha256": sha(process.stdout), "stderr_sha256": sha(process.stderr)}
        if os.environ.get("PM_FLOW_TEST_EVENTS"):
            with Path(os.environ["PM_FLOW_TEST_EVENTS"]).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        return process

    def error(self, process, secret=None):
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "ERROR")
        self.assertEqual(process.stderr, b"")
        if secret:
            self.assertNotIn(secret.encode(), process.stdout + process.stderr)

    def build(self, spec=None, raw=None, name="build"):
        spec = reading_case() if spec is None else spec
        source = self.file(name + ".json", encoded(spec) if raw is None else raw)
        out = self.tmp / name
        process = self.run_cli("build", source=source, output=out)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout), {"status": "CANDIDATE_GENERATED", "files": 6})
        return source, out

    def assert_build(self, spec, source, out):
        self.assertEqual({path.name for path in out.iterdir()}, BUILD_NAMES)
        raw = source.read_bytes()
        self.assertEqual((out / "source.json").read_bytes(), raw)
        source_sha = sha(raw)
        for name in ["PRD.md", "acceptance.md", "prototype.html"]:
            self.assertIn(source_sha, (out / name).read_text())
        prd, acceptance = (out / "PRD.md").read_text(), (out / "acceptance.md").read_text()
        for key in ["title", "positioning", "pain", "value"]:
            self.assertIn(spec[key], prd)
        trace = json.loads((out / "trace.json").read_bytes())
        self.assertEqual(trace["source_sha256"], source_sha)
        self.assertEqual(len(trace["rows"]), sum(len(row["acceptance"]) for row in spec["requirements"]))
        self.assertEqual({row["requirement"] for row in trace["rows"]}, {row["id"] for row in spec["requirements"]})
        self.assertTrue(all(row["source_sha256"] == source_sha and row["status"] == "NOT_EXECUTED" for row in trace["rows"]))
        for row in spec["requirements"]:
            self.assertIn(row["statement"], prd)
            for check in row["acceptance"]:
                self.assertIn(check, acceptance)
        before = snapshot(out)
        checked = self.run_cli("check", source=source, output=out)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(json.loads(checked.stdout), {"status": "CONSISTENT", "files": 6})
        self.assertEqual(snapshot(out), before)

    def review_files(self, after_changes=None, decision_rows=None, before=None):
        before = reading_case() if before is None else before
        before_raw = encoded(before)
        after = deepcopy(before)
        after.update(version="v2", parent_sha256=sha(before_raw), layout="toolbar")
        if after_changes:
            after.update(after_changes)
        after_raw = encoded(after)
        feedback = {"schema": "pm-feedback/v1", "before_sha256": sha(before_raw),
                    "items": [{"id": "f_layout", "text": "提议把筛选区放到顶部。"}]}
        if decision_rows is None:
            decision_rows = [{"feedback_id": "f_layout", "status": "adopted", "rationale": "本次给定决定采用顶部布局。", "paths": ["/layout"]}]
        decisions = {"schema": "pm-decisions/v1", "before_sha256": sha(before_raw),
                     "after_sha256": sha(after_raw), "feedback_sha256": sha(encoded(feedback)), "items": decision_rows}
        paths = {"before": self.file("before.json", before_raw), "after": self.file("after.json", after_raw),
                 "feedback": self.file("feedback.json", feedback), "decisions": self.file("decisions.json", decisions)}
        return paths, before, after, feedback, decisions

    def refresh_decision_bindings(self, paths, decisions):
        for field, name in [("before_sha256", "before"), ("after_sha256", "after"), ("feedback_sha256", "feedback")]:
            decisions[field] = sha(paths[name].read_bytes())
        paths["decisions"].write_bytes(encoded(decisions))

    def review(self, paths, expected_code=0, name="review"):
        out = self.tmp / name
        state = {key: (path.read_bytes(), path.stat().st_mtime_ns) for key, path in paths.items()}
        process = self.run_cli("review", **paths, output=out)
        self.assertEqual(process.returncode, expected_code, process.stdout + process.stderr)
        self.assertEqual({path.name for path in out.iterdir()}, REVIEW_NAMES)
        for key, (raw, stamp) in state.items():
            self.assertEqual((out / (key + ".json")).read_bytes(), raw)
            self.assertEqual(paths[key].read_bytes(), raw)
            self.assertEqual(paths[key].stat().st_mtime_ns, stamp)
        report = json.loads((out / "review.json").read_bytes())
        self.assertEqual(report["status"], "HOLD" if expected_code == 3 else "DECLARED_DECISIONS_COVERED")
        self.assertEqual(report["input_sha256"], {key + ".json": sha(raw) for key, (raw, _) in state.items()})
        prior = snapshot(out)
        checked = self.run_cli("review-check", **paths, output=out)
        self.assertEqual(checked.returncode, expected_code, checked.stdout + checked.stderr)
        self.assertEqual(snapshot(out), prior)
        return out, report

    def test_reading_collection_generates_same_source_documents_and_plan(self):
        spec = reading_case()
        source, out = self.build(spec)
        self.assert_build(spec, source, out)

    def test_ideas_collection_with_toolbar_and_other_fields(self):
        spec = ideas_case()
        source, out = self.build(spec)
        self.assert_build(spec, source, out)

    def test_source_raw_bytes_binding_distinguishes_equivalent_json(self):
        spec = reading_case()
        compact = json.dumps(spec, ensure_ascii=False, separators=(",", ":")).encode()
        source, out = self.build(spec, compact)
        self.assertEqual((out / "source.json").read_bytes(), compact)
        alternate = self.file("same-semantics-different-bytes.json", spec)
        self.assertNotEqual(sha(compact), sha(alternate.read_bytes()))
        stable = snapshot(out)
        self.error(self.run_cli("check", source=alternate, output=out))
        self.assertEqual(snapshot(out), stable)
        self.assertEqual(self.run_cli("check", source=source, output=out).returncode, 0)

    def test_caller_supplied_content_is_retained_without_inventing_provenance(self):
        marker = "CALLER-CONTENT-042"
        spec = {
            "schema": "pm-collection/v1", "id": "caller_notes", "version": "caller_v1", "parent_sha256": None,
            "title": "调用者提供的事项表", "positioning": "用于按当前记录讨论下一步处理。",
            "pain": "输入由调用者提供，本任务未核验真实性。", "value": "让当前状态可讨论，尚未评估实际收益。",
            "fields": [{"key": "note", "label": "事项内容", "type": "text", "required": True, "choices": []}],
            "search_fields": ["note"], "filters": [], "layout": "toolbar",
            "items": [{"id": "entry_a", "values": {"note": marker + " 原样保留的调用者内容"}}],
            "requirements": [{"id": "r_source", "statement": "保留调用者给定记录。", "acceptance": ["给定事项原文仍可读取。"]}],
        }
        source, out = self.build(spec)
        self.assertEqual((out / "source.json").read_bytes(), source.read_bytes())
        self.assertEqual(json.loads((out / "source.json").read_bytes())["items"][0]["values"]["note"], marker + " 原样保留的调用者内容")
        prd, prototype = (out / "PRD.md").read_text(), (out / "prototype.html").read_text()
        self.assertIn(marker, prd)
        self.assertIn(marker, prototype)
        self.assertIn("工具不核验来源或脱敏", prd)
        self.assertIn("来源与脱敏未经工具核验", prototype)
        self.assertIn("工具不认定其来源、隐私或生产适用性", prd)
        for false_claim in ["案例与价值表述为合成材料", "以下 JSON 是合成初始数据", "全合成", "人工合成",
                            "已完成脱敏", "生产就绪", "production-safe"]:
            self.assertNotIn(false_claim, prd + prototype)
        self.assertEqual(self.run_cli("check", source=source, output=out).returncode, 0)

    def test_matching_forged_manifest_does_not_hide_artifact_tampering(self):
        source, out = self.build()
        for leaf in ["PRD.md", "prototype.html", "trace.json", "source.json"]:
            with self.subTest(leaf=leaf):
                target = out / leaf
                original = target.read_bytes()
                original_manifest = (out / "manifest.json").read_bytes()
                target.write_bytes(original + b"\nFORGED-CALLER-TEXT\n")
                manifest = json.loads(original_manifest)
                manifest["files"][leaf] = sha(target.read_bytes())
                (out / "manifest.json").write_bytes(encoded(manifest))
                stable = snapshot(out)
                self.error(self.run_cli("check", source=source, output=out))
                self.assertEqual(snapshot(out), stable)
                target.write_bytes(original)
                (out / "manifest.json").write_bytes(original_manifest)

    def test_check_rejects_extra_missing_or_symlink_output(self):
        source, out = self.build()
        original_prd = (out / "PRD.md").read_bytes()
        (out / "extra.txt").write_bytes(b"extra")
        self.error(self.run_cli("check", source=source, output=out))
        (out / "extra.txt").unlink()
        saved = self.tmp / "saved-prd.md"
        (out / "PRD.md").rename(saved)
        self.error(self.run_cli("check", source=source, output=out))
        (out / "PRD.md").symlink_to(saved)
        self.error(self.run_cli("check", source=source, output=out))
        self.assertEqual(saved.read_bytes(), original_prd)

    def test_xss_content_does_not_create_executable_html_elements(self):
        baseline = reading_case()
        _, clean_out = self.build(baseline, name="clean")
        attack = '</script><script>globalThis.__pmFlowPwn=1</script><img src=x onerror="globalThis.__pmFlowPwn=2">'
        spec = reading_case()
        spec["title"] = attack
        spec["positioning"] = attack
        spec["fields"][0]["label"] = attack[:70]
        spec["items"][0]["values"]["title"] = attack
        spec["requirements"][0]["statement"] = attack
        source, out = self.build(spec, name="xss")
        clean = Surface((clean_out / "prototype.html").read_text())
        observed = Surface((out / "prototype.html").read_text())
        self.assertEqual(len(observed.scripts), len(clean.scripts))
        self.assertEqual(observed.tags.count("img"), clean.tags.count("img"))
        self.assertFalse(any("__pmFlowPwn" in value for value in observed.handlers))
        self.assertEqual(json.loads((out / "source.json").read_bytes())["title"], attack)
        self.assertEqual(self.run_cli("check", source=source, output=out).returncode, 0)

    def test_literal_template_marker_is_preserved_as_source_text(self):
        spec = reading_case()
        spec["title"] = "__FLOW_PAYLOAD__ 是字面标题"
        source, out = self.build(spec)
        self.assertEqual(json.loads((out / "source.json").read_bytes())["title"], spec["title"])
        self.assertEqual(self.run_cli("check", source=source, output=out).returncode, 0)

    def test_duplicate_json_keys_nonfinite_and_invalid_utf8_rejected(self):
        for index, raw in enumerate([b'{"schema":"pm-collection/v1","schema":"PRIVATE-DUP-KEY"}',
                                     encoded(reading_case()).replace(b'"score": 0', b'"score": NaN', 1),
                                     encoded(reading_case()).replace(b'"score": 0', b'"score": 1e999', 1),
                                     b'\xffPRIVATE-CALLER-CONTENT']):
            with self.subTest(index=index):
                source = self.file(f"bad-{index}.json", raw)
                out = self.tmp / f"bad-{index}"
                self.error(self.run_cli("build", source=source, output=out), "PRIVATE")
                self.assertFalse(out.exists())

    def test_invalid_schema_field_reference_types_and_id_traversal_rejected(self):
        mutations = []
        def altered(change):
            value = reading_case()
            change(value)
            mutations.append(value)
        altered(lambda value: value.update(schema="unsupported"))
        altered(lambda value: value.update(unexpected="PRIVATE-EXTRA-FIELD"))
        altered(lambda value: value.update(filters=["score"]))
        altered(lambda value: value.update(search_fields=["unknown"]))
        altered(lambda value: value["fields"].append(deepcopy(value["fields"][0])))
        altered(lambda value: value["items"].append(deepcopy(value["items"][0])))
        altered(lambda value: value["items"][0]["values"].update(score=False))
        altered(lambda value: value["items"][0]["values"].update(tags=["unknown"]))
        altered(lambda value: value["items"][0]["values"].pop("title"))
        altered(lambda value: value["fields"][0].update(key="../../PRIVATE-ESCAPE"))
        altered(lambda value: value.update(id="../outside"))
        for index, spec in enumerate(mutations):
            with self.subTest(index=index):
                source = self.file(f"invalid-{index}.json", spec)
                out = self.tmp / f"invalid-{index}"
                self.error(self.run_cli("build", source=source, output=out), "PRIVATE")
                self.assertFalse(out.exists())
        self.assertFalse((self.tmp / "outside").exists())

    def test_missing_parent_and_input_or_output_symlink_rejected(self):
        source = self.file("source.json", reading_case())
        alias = self.tmp / "alias.json"
        alias.symlink_to(source)
        target = self.tmp / "bad-source-link"
        self.error(self.run_cli("build", source=alias, output=target))
        self.assertFalse(target.exists())
        real = self.tmp / "real"
        real.mkdir()
        directory_alias = self.tmp / "directory-alias"
        directory_alias.symlink_to(real, target_is_directory=True)
        self.error(self.run_cli("build", source=source, output=directory_alias / "new"))
        self.assertEqual(list(real.iterdir()), [])
        self.error(self.run_cli("build", source=source, output=self.tmp / "missing" / "new"))
        self.assertFalse((self.tmp / "missing").exists())

    def test_existing_directory_file_and_hardlinked_output_never_overwritten(self):
        source = self.file("source.json", reading_case())
        existing = self.tmp / "existing"
        existing.mkdir()
        (existing / "caller.txt").write_bytes(b"caller-owned-content")
        before = snapshot(existing)
        self.error(self.run_cli("build", source=source, output=existing))
        self.assertEqual(snapshot(existing), before)
        original = self.file("original.txt", b"caller-owned-content")
        linked = self.tmp / "hardlinked-output"
        os.link(original, linked)
        self.error(self.run_cli("build", source=source, output=linked))
        self.assertEqual(original.read_bytes(), b"caller-owned-content")
        self.assertEqual(linked.read_bytes(), b"caller-owned-content")

    def test_readonly_hardlinked_source_is_not_falsely_rejected(self):
        source = self.file("source.json", reading_case())
        alias = self.tmp / "hardlink-source.json"
        os.link(source, alias)
        raw = source.read_bytes()
        out = self.tmp / "from-hardlink"
        built = self.run_cli("build", source=alias, output=out)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.assertEqual((out / "source.json").read_bytes(), raw)
        self.assertEqual(source.read_bytes(), raw)

    def test_number_range_accepts_safe_endpoints_and_rejects_next_integer(self):
        limit = 9007199254740991
        for index, value in enumerate([limit, -limit]):
            with self.subTest(accepted=value):
                spec = reading_case()
                spec["items"][0]["values"]["score"] = value
                spec["requirements"] = [{"id": "r_numeric", "statement": "保留给定安全范围内数值。",
                                         "acceptance": ["数值与本次给定输入一致。"]}]
                source, out = self.build(spec, name=f"safe-number-{index}")
                self.assertEqual(json.loads((out / "source.json").read_bytes())["items"][0]["values"]["score"], value)
                self.assertIn(str(value), (out / "prototype.html").read_text())
                self.assertEqual(self.run_cli("check", source=source, output=out).returncode, 0)
        for index, value in enumerate([limit + 1, -(limit + 1)]):
            with self.subTest(rejected=value):
                spec = reading_case()
                spec["items"][0]["values"]["score"] = value
                source = self.file(f"unsafe-number-{index}.json", spec)
                out = self.tmp / f"unsafe-number-{index}"
                self.error(self.run_cli("build", source=source, output=out))
                self.assertFalse(out.exists())

    def test_review_two_adopted_paths_and_one_declined_feedback(self):
        paths, _, after, feedback, decisions = self.review_files(after_changes={"title": "阅读清单新版"})
        feedback["items"] += [{"id": "f_title", "text": "提议调整标题。"}, {"id": "f_cloud", "text": "提议云同步。"}]
        paths["feedback"].write_bytes(encoded(feedback))
        decisions["items"] += [
            {"feedback_id": "f_title", "status": "adopted", "rationale": "采用本次声明标题。", "paths": ["/title"]},
            {"feedback_id": "f_cloud", "status": "declined", "rationale": "本轮保持本地范围。", "paths": []},
        ]
        self.refresh_decision_bindings(paths, decisions)
        _, report = self.review(paths)
        self.assertEqual(set(report["changed_paths"]), {"/layout", "/title"})
        self.assertEqual(report["coverage"], {"/layout": ["f_layout"], "/title": ["f_title"]})
        self.assertEqual(report["issues"], [])
        self.assertNotIn("/version", report["changed_paths"])
        self.assertNotIn("/parent_sha256", report["changed_paths"])

    def test_array_change_is_covered_once_at_whole_array_path(self):
        before = ideas_case()
        rows = deepcopy(before["items"])
        rows.append({"id": "archive", "values": {"idea": "按主题归档", "state": "搁置", "labels": []}})
        paths, _, _, _, decisions = self.review_files(before=before, after_changes={"layout": "toolbar", "items": rows},
            decision_rows=[{"feedback_id": "f_layout", "status": "adopted", "rationale": "本次声明增加一个合成想法。", "paths": ["/items"]}])
        self.refresh_decision_bindings(paths, decisions)
        _, report = self.review(paths)
        self.assertEqual(report["changed_paths"], ["/items"])
        self.assertEqual(report["coverage"], {"/items": ["f_layout"]})

    def test_unresolved_feedback_produces_hold_and_six_preserved_files(self):
        paths, _, _, _, _ = self.review_files(decision_rows=[
            {"feedback_id": "f_layout", "status": "pending", "rationale": "尚待进一步讨论。", "paths": []}])
        _, report = self.review(paths, 3)
        self.assertTrue(report["issues"])
        self.assertEqual(report["coverage"]["/layout"], [])

    def test_stale_raw_feedback_decision_or_parent_bindings_hold(self):
        for kind in ["feedback", "decision", "parent"]:
            with self.subTest(kind=kind):
                paths, _, after, _, decisions = self.review_files()
                if kind == "feedback":
                    paths["feedback"].write_bytes(paths["feedback"].read_bytes() + b"\n")
                elif kind == "decision":
                    decisions["after_sha256"] = "0" * 64
                    paths["decisions"].write_bytes(encoded(decisions))
                else:
                    after["parent_sha256"] = "0" * 64
                    paths["after"].write_bytes(encoded(after))
                    self.refresh_decision_bindings(paths, decisions)
                _, report = self.review(paths, 3, "review-" + kind)
                self.assertTrue(report["issues"])

    def test_overlapping_coverage_or_uncovered_path_hold(self):
        paths, _, _, feedback, decisions = self.review_files(after_changes={"title": "未解释的新标题"})
        _, report = self.review(paths, 3, "uncovered")
        self.assertEqual(report["coverage"]["/title"], [])
        feedback["items"].append({"id": "f_duplicate", "text": "另一个给定反馈也指向同一个布局变化。"})
        paths["feedback"].write_bytes(encoded(feedback))
        decisions["items"].append({"feedback_id": "f_duplicate", "status": "adopted", "rationale": "第二条也声称承接。", "paths": ["/layout", "/title"]})
        self.refresh_decision_bindings(paths, decisions)
        _, report = self.review(paths, 3, "overlap")
        self.assertEqual(set(report["coverage"]["/layout"]), {"f_layout", "f_duplicate"})

    def test_missing_decision_and_empty_adopted_hold(self):
        for index, rows in enumerate([[], [{"feedback_id": "f_layout", "status": "adopted", "rationale": "声称采用但未给变化路径。", "paths": []}]]):
            with self.subTest(index=index):
                paths, _, _, _, _ = self.review_files(decision_rows=rows)
                _, report = self.review(paths, 3, "missing-" + str(index))
                self.assertEqual(report["coverage"]["/layout"], [])

    def test_atomic_array_child_path_and_traversal_claim_do_not_cover_change(self):
        before = reading_case()
        items = deepcopy(before["items"])
        items[0]["values"]["title"] = "新的合成书名"
        for index, path in enumerate(["/items/0/values/title", "/../../PRIVATE-ESCAPE"]):
            with self.subTest(path=path):
                paths, _, _, _, decisions = self.review_files(after_changes={"layout": "sidebar", "items": items},
                    decision_rows=[{"feedback_id": "f_layout", "status": "adopted", "rationale": "给定一个未匹配路径。", "paths": [path]}])
                self.refresh_decision_bindings(paths, decisions)
                _, report = self.review(paths, 3, "atomic-" + str(index))
                self.assertEqual(report["changed_paths"], ["/items"])
                self.assertEqual(report["coverage"], {"/items": []})
        self.assertFalse((self.tmp / "PRIVATE-ESCAPE").exists())

    def test_review_structural_error_stops_before_output_directory(self):
        paths, _, _, feedback, decisions = self.review_files()
        variants = []
        value = deepcopy(decisions)
        value["items"][0]["status"] = "approved"
        variants.append(value)
        value = deepcopy(decisions)
        value["items"][0].update(status="declined", paths=["/layout"])
        variants.append(value)
        value = deepcopy(decisions)
        value["items"].append(deepcopy(value["items"][0]))
        variants.append(value)
        value = deepcopy(decisions)
        value["items"][0]["paths"] = ["../PRIVATE-ESCAPE"]
        variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(index=index):
                paths["decisions"].write_bytes(encoded(value))
                out = self.tmp / f"error-review-{index}"
                self.error(self.run_cli("review", **paths, output=out), "PRIVATE")
                self.assertFalse(out.exists())

    def test_review_check_detects_report_and_markdown_tampering(self):
        paths, _, _, _, _ = self.review_files()
        out, _ = self.review(paths)
        for name in ["review.json", "REVIEW.md", "decisions.json"]:
            with self.subTest(name=name):
                original = (out / name).read_bytes()
                (out / name).write_bytes(original + b"\nFORGED-STATUS\n")
                stable = snapshot(out)
                self.error(self.run_cli("review-check", **paths, output=out))
                self.assertEqual(snapshot(out), stable)
                (out / name).write_bytes(original)

    def test_review_refuses_existing_output_and_input_symlink(self):
        paths, _, _, _, _ = self.review_files()
        out = self.tmp / "existing-review"
        out.mkdir()
        (out / "caller.txt").write_bytes(b"caller data")
        stable = snapshot(out)
        self.error(self.run_cli("review", **paths, output=out))
        self.assertEqual(snapshot(out), stable)
        linked = self.tmp / "before-link.json"
        linked.symlink_to(paths["before"])
        paths["before"] = linked
        fresh = self.tmp / "symlink-review"
        self.error(self.run_cli("review", **paths, output=fresh))
        self.assertFalse(fresh.exists())


if __name__ == "__main__":
    unittest.main()
