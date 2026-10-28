"""Real CLI regression tests using a fresh two-field, two-check synthetic task."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
from pm_workbench import Workbench, APIError, ROOT, read, load_json
from workbench_adapter import to_task, DraftError


def draft(kind="collection"):
    return {"kind": kind, "title": "合成样本登记", "audience": "本地测试人员", "problem": "合成记录需要按状态查找。",
            "positioning": "用于本地验证的合成样本管理", "value_hypothesis": "集中查看可能减少查找步骤，尚未实测。",
            "goal": "核对同源生成和修订记录", "priority_basis": "先覆盖核心查找及填写。", "source_kind": "synthetic",
            "source_note": "全新人工合成输入，无客户记录。", "success_metric": {"statement": "找到指定记录", "baseline": "未采集", "target": "待试用确定", "measurement": "记录实际完成情况"},
            "included": ["本地登记与查找"], "excluded": ["远程同步"], "pending": [], "decision_status": "declared",
            "fields": [{"key": "label", "label": "样本名称", "type": "text", "required": True, "choices": [], "minimum": None, "maximum": None},
                       {"key": "phase", "label": "状态", "type": "choice", "required": False, "choices": ["准备", "完成"], "minimum": None, "maximum": None}],
            "collection": {"search_fields": ["label"], "filters": ["phase"], "layout": "sidebar", "items": [{"id": "sample_one", "values": {"label": "合成样本甲", "phase": "准备"}}]},
            "form": {"initial_values": {"label": "用户给定初值", "phase": "准备"}, "initial_state": "draft"},
            "requirement": {"statement": "按状态查找并查看给定内容", "priority": "must", "checks": [
                {"condition": "选择准备状态", "expected": "显示合成样本甲", "evidence_level": "browser"},
                {"condition": "查看样本内容", "expected": "与给定初值相同", "evidence_level": "content"}]},
            "rule": {"statement": "按给定条件展示", "default": "初始显示给定记录", "exception": "无结果保留重置入口", "boundary": "仅当前离线原型"},
            "legacy_notes": ["旧原型标注observed/retested；未核验，不作为pass。"]}


class AdapterTests(unittest.TestCase):
    def test_pending_and_values_are_literal(self):
        d = draft(); d["problem"] = ""; d["rule"]["boundary"] = ""
        task = to_task(d, "fresh_task", "1")
        self.assertTrue(task["pending"])
        self.assertEqual(task["decisions"][0]["status"], "pending")
        self.assertEqual(task["prototype"]["items"], d["collection"]["items"])
        self.assertNotIn("observations", task)
        self.assertEqual(task["evidence"][-1]["kind"], "hypothesis")
        self.assertIn("未核验", task["evidence"][-1]["text"])
        form = to_task(draft("form"), "fresh_form", "1")
        self.assertEqual(form["prototype"]["initial_values"]["label"], "用户给定初值")

    def test_rejects_unsupported_types_and_bounds(self):
        for unsupported in ("date", "longtext"):
            d = draft(); d["fields"][0]["type"] = unsupported
            with self.assertRaises(DraftError): to_task(d, "fresh_task", "1")
        d = draft(); d["fields"][0]["minimum"] = 1
        with self.assertRaises(DraftError): to_task(d, "fresh_task", "1")
        d = draft(); d["collection"]["items"][0]["values"]["phase"] = "非法状态"
        with self.assertRaises(DraftError): to_task(d, "fresh_task", "1")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get("PM_WORKBENCH_TEST_EVIDENCE")
        if evidence:
            self.store = Path(evidence) / self._testMethodName
            self.store.mkdir(parents=True, exist_ok=False)
            self.tmp = type("EvidenceStore", (), {"name": str(self.store)})()
        else:
            self.tmp = tempfile.TemporaryDirectory(prefix="pm_workbench_test_", dir=Path(tempfile.gettempdir()).resolve())
            self.addCleanup(self.tmp.cleanup)
        self.wb = Workbench(Path(self.tmp.name) / "workspace", timeout=30)
        self.core = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [ROOT / n for n in ("pm_task.py", "task_core.py", "task_revision.py", "flow_core.py", "form_core.py", "UPSTREAM.json")]}
        self.addCleanup(self.assert_core_unchanged)

    def assert_core_unchanged(self):
        self.assertEqual(self.core, {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in self.core})

    def create_build(self, kind="collection"):
        p = self.wb.create(draft(kind))["project"]
        result = self.wb.mutate(p["id"], "build", {"draft": p["draft"], "expected_revision": p["revision"], "version": "1"})
        self.assertEqual(result["operation"]["status"], "GENERATED_NOT_ACCEPTED")
        self.assertEqual(result["operation"]["check"], {"status": "CONSISTENT", "exit_code": 0})
        return result["project"], result["operation"]

    def test_actual_build_revision_hold_adoption_retest_delivery(self):
        p, first = self.create_build()
        names = {a["name"] for a in first["artifacts"]}
        self.assertTrue({"PRD.md", "handoff.docx", "document-verification.json"} <= names)
        self.assertTrue(read(self.wb.artifact_path(p["id"], first["id"], "handoff.docx")).startswith(b"PK"))
        self.assertEqual([r["status"] for r in first["checks"]], ["not_run", "not_run"])
        d = deepcopy(p["draft"]); d["collection"]["layout"] = "toolbar"
        r = self.wb.mutate(p["id"], "prepare-review", {"draft": d, "expected_revision": p["revision"], "base_run_id": first["id"], "version": "2"})
        p, prep = r["project"], r["operation"]
        self.assertEqual(prep["status"], "HOLD"); self.assertEqual(prep["exit_code"], 3)
        self.assertEqual([c["path"] for c in prep["changes"]], ["/prototype/layout"])
        after = load_json(self.wb.artifact_path(p["id"], prep["id"], "after.json"))
        before_raw = read(self.wb.artifact_path(p["id"], first["id"], "task.json"))
        self.assertEqual(after["parent_task_sha256"], hashlib.sha256(before_raw).hexdigest())
        self.assertIsNotNone(after["prototype"]["parent_sha256"])
        feedback = [{"id": "feedback_one", "text": "调整筛选位置", "source": "合成测试反馈", "status": "pending", "rationale": "尚待确认", "paths": []}]
        r = self.wb.mutate(p["id"], "review", {"preparation_run_id": prep["id"], "expected_revision": p["revision"], "feedback": feedback})
        p = r["project"]
        self.assertEqual(r["operation"]["status"], "HOLD")
        pending_review_id = r["operation"]["id"]
        pending_snapshot = deepcopy(feedback)
        self.assertEqual(r["operation"]["feedback"], pending_snapshot)
        hold_build = next(x for x in p["runs"] if x["id"] == r["operation"]["build_run_id"])
        self.assertTrue(hold_build["artifacts"])
        self.assertTrue(all(c["status"] == "not_run" for c in hold_build["checks"]))
        feedback[0].update(status="adopted", rationale="使用者明确采纳此位置调整", paths=["/prototype/layout"])
        r = self.wb.mutate(p["id"], "review", {"preparation_run_id": prep["id"], "expected_revision": p["revision"], "feedback": feedback})
        p = r["project"]; self.assertEqual(r["operation"]["status"], "DECLARED_CHANGE_COVERED")
        adopted_review_id = r["operation"]["id"]
        self.assertEqual(r["operation"]["feedback"], feedback)
        reopened = Workbench(self.wb.workspace, timeout=30).project(p["id"])
        recovered_pending = next(run for run in reopened["runs"] if run["id"] == pending_review_id)
        recovered_adopted = next(run for run in reopened["runs"] if run["id"] == adopted_review_id)
        self.assertEqual(recovered_pending["preparation_run_id"], prep["id"])
        self.assertEqual(recovered_adopted["preparation_run_id"], prep["id"])
        self.assertEqual(recovered_pending["feedback"], pending_snapshot)
        self.assertEqual(recovered_adopted["feedback"], feedback)
        latest = p["latest_build_run_id"]
        self.assertNotEqual(latest, first["id"])
        old_d = self.wb.mutate(p["id"], "deliver", {"build_run_id": latest})
        self.assertEqual(old_d["operation"]["status"], "HOLD")
        failure = {"check_id": "main_c1", "status": "fail", "level": "browser", "observed": "合成观察显示错误状态", "evidence_ref": "local-evidence:test-1", "defect": "筛选显示不符"}
        r = self.wb.mutate(p["id"], "observations", {"build_run_id": latest, "rows": [failure]})
        self.assertEqual(r["operation"]["status"], "HOLD")
        passes = [{**failure, "status": "pass", "observed": "重新核对给定显示", "evidence_ref": "local-evidence:test-retest", "defect": None},
                  {"check_id": "main_c2", "status": "pass", "level": "content", "observed": "给定内容已逐项一致", "evidence_ref": "local-evidence:test-content", "defect": None}]
        r = self.wb.mutate(p["id"], "observations", {"build_run_id": latest, "rows": passes})
        self.assertEqual(r["operation"]["status"], "SUPPLIED_EVIDENCE_COVERED")
        run = next(x for x in r["project"]["runs"] if x["id"] == latest)
        self.assertEqual([x["status"] for x in run["checks"][0]["history"]], ["not_run", "fail", "pass"])
        self.assertEqual(run["checks"][0]["history"][-1]["supersedes"], run["checks"][0]["history"][-2]["id"])
        r = self.wb.mutate(p["id"], "deliver", {"build_run_id": latest})
        self.assertEqual(r["operation"]["status"], "SUPPLIED_EVIDENCE_COVERED")
        self.assertEqual(r["operation"]["check"], {"status": "SUPPLIED_EVIDENCE_COVERED", "exit_code": 0})
        defects = load_json(self.wb.artifact_path(p["id"], r["operation"]["id"], "defects.json"))
        self.assertEqual(defects["rows"][0]["status"], "RECHECK_REPORTED")
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(self.wb.package(p["id"], r["operation"]["id"]))) as z:
            self.assertIn("handoff.docx", z.namelist()); self.assertIn("acceptance-results.json", z.namelist())
            self.assertFalse(any(".." in n or n.startswith("/") for n in z.namelist()))
        # A draft edit invalidates the frozen pair and current-source guard.
        d["title"] += "修订"
        changed = self.wb.mutate(p["id"], "save", {"draft": d, "expected_revision": p["revision"]})["project"]
        with self.assertRaises(APIError) as stale:
            self.wb.mutate(p["id"], "review", {"preparation_run_id": prep["id"], "expected_revision": changed["revision"], "feedback": feedback})
        self.assertEqual(stale.exception.status, 409)
        with self.assertRaises(APIError): self.wb.mutate(p["id"], "deliver", {"build_run_id": latest})
        self.assertFalse(next(x for x in changed["runs"] if x["id"] == latest)["current_source"])
        self.assertEqual(next(x for x in changed["runs"] if x["id"] == first["id"])["checks"][0]["status"], "not_run")

    def test_form_real_initial_values_and_pending_hold(self):
        p, first = self.create_build("form")
        source = load_json(self.wb.artifact_path(p["id"], first["id"], "task.json"))
        self.assertEqual(source["prototype"]["initial_values"]["label"], "用户给定初值")
        p = self.wb.create({**draft(), "decision_status": "pending"})["project"]
        r = self.wb.mutate(p["id"], "build", {"draft": p["draft"], "expected_revision": p["revision"], "version": "1"})
        self.assertEqual(r["operation"]["status"], "HOLD"); self.assertEqual(r["operation"]["check"]["exit_code"], 3)

    def test_timeout_concurrency_symlink_and_cas(self):
        p = self.wb.create(draft())["project"]
        with self.assertRaises(APIError) as stale: self.wb.mutate(p["id"], "save", {"draft": p["draft"], "expected_revision": 0})
        self.assertEqual(stale.exception.status, 409)
        self.wb.lock.acquire()
        try:
            with self.assertRaises(APIError) as busy: self.wb.mutate(p["id"], "save", {"draft": p["draft"], "expected_revision": 1})
            self.assertEqual(busy.exception.code, "BUSY")
        finally: self.wb.lock.release()
        with patch("pm_workbench.subprocess.run", side_effect=subprocess.TimeoutExpired(["fixed"], 1)) as process:
            r = self.wb.mutate(p["id"], "build", {"draft": p["draft"], "expected_revision": 1, "version": "1"})
        argv, = process.call_args.args
        self.assertEqual(argv[:3], [sys.executable, str(ROOT / "pm_task.py"), "build"])
        self.assertFalse(process.call_args.kwargs["shell"])
        operation = r["operation"]
        self.assertEqual(operation["status"], "ERROR"); self.assertEqual(operation["exit_code"], 2)
        self.assertEqual(operation["issues"], ["TIMEOUT"])
        self.assertTrue((self.wb.run_path(p["id"], operation["id"]) / "INCOMPLETE.txt").exists())
        self.assertIsNone(r["project"]["latest_build_run_id"])
        real_timeout_dir = self.wb.run_path(p["id"], "r_timeout_real")
        real_timeout_dir.mkdir()
        self.wb.timeout = 0.000001
        receipt = self.wb.command(real_timeout_dir, "check", source=real_timeout_dir / "missing.json", output=real_timeout_dir / "missing")
        self.assertTrue(receipt["timed_out"])
        self.assertEqual(receipt["exit_code"], 2)
        with self.assertRaises(APIError): self.wb.path("../private")
        q = self.wb.projects_dir / "p_link"; q.symlink_to(self.tmp.name)
        with self.assertRaises(APIError): self.wb.state("p_link")


if __name__ == "__main__": unittest.main(verbosity=2)
