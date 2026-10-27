"""Black-box task lifecycle regressions, independent DOCX ordered readback."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "pm_task.py"


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class TaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix="pm-task-test-")
        self.addCleanup(self.t.cleanup)
        self.tmp = Path(self.t.name).resolve()
        self.seq = 0
        self.before = json.loads((ROOT / "examples/lifecycle/before.json").read_bytes())
        self.after = json.loads((ROOT / "examples/lifecycle/after.json").read_bytes())

    def file(self, name, value):
        p = self.tmp / name
        p.write_bytes(value if type(value) is bytes else raw(value))
        return p

    def cli(self, command, **kwargs):
        argv = [sys.executable, "-B", str(CLI), command]
        for k, v in kwargs.items():
            argv += ["--" + k, str(v)]
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONPATH="")
        proc = subprocess.run(argv, cwd=self.tmp, env=env, capture_output=True, timeout=30)
        if os.environ.get("PM_TASK_TEST_EVENTS"):
            with open(os.environ["PM_TASK_TEST_EVENTS"], "a") as f:
                f.write(json.dumps({"argv": argv, "exit": proc.returncode,
                                   "stdout": proc.stdout.decode(errors="replace"),
                                   "stderr": proc.stderr.decode(errors="replace")}) + "\n")
        self.assertEqual(proc.stderr, b"", proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def build(self, task=None, name="built"):
        source = self.file(name + ".json", self.before if task is None else task)
        out = self.tmp / name
        code, report = self.cli("build", source=source, output=out)
        self.assertEqual(code, 0, report)
        return source, out

    def observations(self, out, status="pass"):
        obs = json.loads((out / "observations-template.json").read_bytes())
        for r in obs["rows"]:
            r.update(status=status, observed="测试夹具声明；不是实际浏览器观察。", evidence_ref="synthetic fixture", defect=None)
        return obs

    def review_args(self, decision_file="decisions.json"):
        return {k: ROOT / "examples/lifecycle" / n for k, n in {
            "before": "before.json", "after": "after.json", "feedback": "feedback.json", "decisions": decision_file}.items()}

    def test_complete_same_version_artifacts_and_ordered_docx(self):
        source, out = self.build()
        ts = sha(source.read_bytes())
        ss = sha((out / "spec.json").read_bytes())
        for name in ("PRD.md", "product-brief.md", "rules.md", "evidence.md", "handoff.md"):
            content = (out / name).read_text()
            self.assertIn(ts, content)
            self.assertIn(ss, content)
        model = json.loads((out / "document-source.json").read_bytes())
        expected = [model["title"], *[b["text"] for b in model["blocks"]]]
        with zipfile.ZipFile(out / "handoff.docx") as z:
            doc = ET.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        observed = ["".join(t.text or "" for t in p.findall(".//w:t", ns)) for p in doc.findall(".//w:body/w:p", ns)]
        self.assertEqual(observed, expected)
        self.assertEqual(json.loads((out / "document-verification.json").read_bytes())["status"], "PASS")
        self.assertTrue(all(r["status"] == "NOT_EXECUTED" for r in json.loads((out / "trace.json").read_bytes())["checks"]))
        self.assertEqual(self.cli("check", source=source, output=out)[0], 0)

    def test_check_reconstructs_tampered_manifest_and_preserves_files(self):
        source, out = self.build()
        (out / "PRD.md").write_text("tampered")
        manifest = json.loads((out / "manifest.json").read_bytes())
        manifest["files"]["PRD.md"] = sha(b"tampered")
        (out / "manifest.json").write_bytes(raw(manifest))
        snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
        self.assertEqual(self.cli("check", source=source, output=out)[0], 2)
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_relational_contract_rejects_dangling_and_mismatched_inputs(self):
        bads = []
        x = deepcopy(self.before); x["requirements"][0]["evidence_ids"] = ["unknown"]; bads.append(x)
        x = deepcopy(self.before); x["prototype"]["version"] = "stale"; bads.append(x)
        x = deepcopy(self.before); x["prototype"]["requirements"][0]["acceptance"][0] = "drift"; bads.append(x)
        x = deepcopy(self.before); x["rules"][0]["requirement_ids"] = ["maintain"]; bads.append(x)
        x = deepcopy(self.before); x["requirements"][0]["checks"][0]["id"] = "layout_c1"; bads.append(x)
        for i, task in enumerate(bads):
            with self.subTest(i=i):
                out = self.tmp / f"bad{i}"
                self.assertEqual(self.cli("build", source=self.file(f"bad{i}.json", task), output=out)[0], 2)
                self.assertFalse(out.exists())

    def test_init_keeps_unresolved_work_visible(self):
        out = self.tmp / "init"
        self.assertEqual(self.cli("init", output=out)[0], 0)
        generated = self.tmp / "draft"
        code, report = self.cli("build", source=out / "task.json", output=generated)
        self.assertEqual((code, report["status"]), (3, "HOLD"))
        self.assertTrue((generated / "handoff.docx").is_file())

    def test_review_adopted_declined_pending_and_conflict(self):
        for i, (name, expected) in enumerate((("decisions.json", 0), ("pending-decisions.json", 3), ("conflict-decisions.json", 3))):
            args = self.review_args(name)
            code, report = self.cli("review", **args, output=self.tmp / f"review{i}")
            self.assertEqual(code, expected, report)
            self.assertEqual(self.cli("review-check", **args, output=self.tmp / f"review{i}")[0], expected)

    def test_stale_review_and_uncovered_changes_hold(self):
        args = self.review_args()
        decisions = json.loads(args["decisions"].read_bytes())
        decisions["after_task_sha256"] = "0" * 64
        args["decisions"] = self.file("stale.json", decisions)
        code, _ = self.cli("review", **args, output=self.tmp / "stale-review")
        self.assertEqual(code, 3)
        report = json.loads((self.tmp / "stale-review/review.json").read_bytes())
        self.assertIn("STALE_DECISIONS:after_task_sha256", report["issues"])

    def test_missing_observations_and_wrong_evidence_layer_hold(self):
        source, out = self.build()
        obs = json.loads((out / "observations-template.json").read_bytes())
        code, report = self.cli("deliver", source=source, observations=self.file("not-run.json", obs), output=self.tmp / "not-run")
        self.assertEqual((code, report["status"]), (3, "HOLD"))
        obs = self.observations(out)
        obs["rows"][0]["level"] = "static"
        code, _ = self.cli("deliver", source=source, observations=self.file("wrong-level.json", obs), output=self.tmp / "wrong-level")
        self.assertEqual(code, 3)
        report = json.loads((self.tmp / "wrong-level/acceptance-results.json").read_bytes())
        self.assertTrue(any(x.startswith("EVIDENCE_LEVEL_MISMATCH:") for x in report["issues"]))

    def test_stale_task_and_prototype_observations_hold(self):
        source, out = self.build()
        for i, field in enumerate(("task_sha256", "prototype_sha256")):
            obs = self.observations(out); obs[field] = "0" * 64
            self.assertEqual(self.cli("deliver", source=source, observations=self.file(f"stale{i}.json", obs), output=self.tmp / f"stale{i}")[0], 3)

    def test_fail_recheck_chain_is_retained_without_asserting_acceptance(self):
        source, out = self.build()
        obs = self.observations(out)
        first = obs["rows"][0]
        first.update(status="fail", defect="测试夹具中的首次失败。")
        followup = deepcopy(first)
        followup.update(id="obs_recheck", status="pass", supersedes=first["id"], defect=None)
        obs["rows"].append(followup)
        obsfile = self.file("observed.json", obs)
        dest = self.tmp / "delivered"
        code, report = self.cli("deliver", source=source, observations=obsfile, output=dest)
        self.assertEqual((code, report["status"]), (0, "SUPPLIED_EVIDENCE_COVERED"))
        result = json.loads((dest / "acceptance-results.json").read_bytes())
        self.assertEqual(len(result["observations"]), len(obs["rows"]))
        self.assertEqual(result["defects"][0]["status"], "RECHECK_REPORTED")
        self.assertIn("Caller-provided", result["meaning"])
        self.assertEqual(self.cli("deliver-check", source=source, observations=obsfile, output=dest)[0], 0)
        obs["rows"][-1]["supersedes"] = None
        self.assertEqual(self.cli("deliver", source=source, observations=self.file("broken-chain.json", obs), output=self.tmp / "broken-chain")[0], 2)

    def test_revision_requires_exact_review_inputs(self):
        source, out = self.build(self.after)
        obs = self.file("after-observations.json", self.observations(out))
        code, _ = self.cli("deliver", source=source, observations=obs, output=self.tmp / "missing-review")
        self.assertEqual(code, 3)
        args = self.review_args(); args.pop("after")
        code, report = self.cli("deliver", source=source, observations=obs, **args, output=self.tmp / "after-delivery")
        self.assertEqual((code, report["status"]), (0, "SUPPLIED_EVIDENCE_COVERED"))

    def test_cannot_clear_only_task_parent_to_bypass_revision_review(self):
        task = deepcopy(self.after)
        task["parent_task_sha256"] = None
        code, _ = self.cli("build", source=self.file("parent-bypass.json", task), output=self.tmp / "parent-bypass")
        self.assertEqual(code, 2)

    def test_explicit_hold_review_also_blocks_first_version_delivery(self):
        source, out = self.build()
        obs = self.file("first-observations.json", self.observations(out))
        args = self.review_args("pending-decisions.json")
        args.pop("after")
        args["before"] = ROOT / "examples/lifecycle/after.json"
        code, report = self.cli("deliver", source=source, observations=obs, **args, output=self.tmp / "first-with-hold")
        self.assertEqual((code, report["status"]), (3, "HOLD"))

    def test_large_legal_check_plan_retains_failure_and_recheck(self):
        task = deepcopy(self.before)
        reqs, rules, proto_reqs = [], [], []
        for i in range(6):
            rid, ruleid = f"check_group_{i}", f"large_rule_{i}"
            checks = [{"id": f"{rid}_c{j}", "condition": f"给定条件{j}", "expected": "给定结果",
                       "evidence_level": "manual"} for j in range(1,21)]
            reqs.append({"id": rid, "statement": "检查组", "priority": "must", "priority_reason": "有限合同回归",
                         "evidence_ids": ["ev_reading"], "decision_ids": ["dec_1"], "rule_ids": [ruleid], "checks": checks})
            rules.append({"id": ruleid, "statement": "给定规则", "default": "给定默认", "exception": "给定异常",
                          "boundary": "有限回归", "evidence_ids": ["ev_reading"], "requirement_ids": [rid]})
            proto_reqs.append({"id": rid, "statement": "检查组", "acceptance": [f"{c['condition']}；预期：{c['expected']}" for c in checks]})
        task.update(requirements=reqs, rules=rules)
        task["prototype"]["requirements"] = proto_reqs
        source, out = self.build(task, "large")
        obs = self.observations(out)
        self.assertEqual(len(obs["rows"]), 120)
        failed = deepcopy(obs["rows"][0]); failed.update(id="large_fail", status="fail", supersedes=obs["rows"][0]["id"], defect="合成失败")
        recheck = deepcopy(failed); recheck.update(id="large_recheck", status="pass", supersedes="large_fail", defect=None)
        obs["rows"] += [failed, recheck]
        code, report = self.cli("deliver", source=source, observations=self.file("large-obs.json", obs), output=self.tmp / "large-delivery")
        self.assertEqual((code, report["status"]), (0, "SUPPLIED_EVIDENCE_COVERED"))
        report = json.loads((self.tmp / "large-delivery/acceptance-results.json").read_bytes())
        self.assertEqual(len(report["observations"]), 122)
        self.assertEqual(report["defects"][0]["status"], "RECHECK_REPORTED")

    def test_asset_handbook_retains_proposed_and_conflicting_decision_status(self):
        task = deepcopy(self.before)
        task["decisions"][0]["status"] = "proposed"
        task["decisions"][1]["status"] = "conflict"
        source = self.file("unresolved-task.json", task)
        generated = self.tmp / "unresolved-generated"
        self.assertEqual(self.cli("build", source=source, output=generated)[0], 3)
        obsfile = self.file("unresolved-observations.json", self.observations(generated))
        dest = self.tmp / "unresolved-delivery"
        self.assertEqual(self.cli("deliver", source=source, observations=obsfile, output=dest)[0], 3)
        handbook = (dest / "product-handbook.md").read_text()
        display = re.sub(r"\\([\\`|*_\[\]])", r"\1", handbook)
        self.assertIn("dec_1 [proposed]", display)
        self.assertIn("dec_2 [conflict]", display)
        self.assertIn("HOLD", handbook)
        self.assertIn("需求声明", handbook)
        self.assertNotIn("当前定位与能力", handbook)

    def test_no_overwrite_or_symlink_following(self):
        source, out = self.build()
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        self.assertEqual(self.cli("build", source=source, output=out)[0], 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
        link = self.tmp / "source-link.json"; link.symlink_to(source)
        self.assertEqual(self.cli("build", source=link, output=self.tmp / "linked")[0], 2)

    def test_private_input_parse_errors_do_not_echo_content(self):
        sensitive = 'PRIVATE_SENTINEL_TEST_ONLY'
        bad = b'{"schema":"' + sensitive.encode() + b'", "schema":null}'
        source = self.file("parse.json", bad)
        code, report = self.cli("build", source=source, output=self.tmp / "invalid")
        self.assertEqual(code, 2)
        self.assertNotIn(sensitive, json.dumps(report))


if __name__ == "__main__":
    unittest.main()
