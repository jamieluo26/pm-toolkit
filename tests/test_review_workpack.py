"""Behavioral checks for the local review workspace and snapshot CLI.

Run with: python3 -B -m unittest discover -s tests -p test_review_workpack.py -v
Only synthetic files in a temporary directory are modified. No model is called.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAMES = ("before.json", "after.json", "policy.json", "snapshots.json", "case.md", "prompts.md")
LEAVES = ("pm_review.py", "tools/keyed_snapshot_diff.py", "tools/audit_io.py", "tools/file_audit_core.py")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def file_state(root):
    return {p.relative_to(root).as_posix(): (sha(p.read_bytes()), p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-review-test-")
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def run_cli(self, script, *args):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run([sys.executable, "-B", str(script), *map(str, args)],
                              cwd=self.tmp, env=env, capture_output=True, timeout=30)
        event = {"argv": [sys.executable, "-B", str(script), *map(str, args)], "exit": proc.returncode,
                 "stdout": proc.stdout.decode("utf-8", errors="replace"),
                 "stderr": proc.stderr.decode("utf-8", errors="replace"),
                 "stdout_sha256": sha(proc.stdout), "stderr_sha256": sha(proc.stderr)}
        log = os.environ.get("PM_REVIEW_TEST_EVENTS")
        if log:
            with Path(log).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        return proc

    def assert_error(self, proc, secret=None):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["status"], "ERROR")
        self.assertEqual(proc.stderr, b"")
        if secret:
            self.assertNotIn(secret.encode(), proc.stdout + proc.stderr)

    def review(self, command, target, package=ROOT):
        return self.run_cli(package / "pm_review.py", command, "--output", target)

    def demo(self):
        out = self.tmp / "workspace"
        result = self.review("demo", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return out

    def package_copy(self):
        package = self.tmp / "isolated-package"
        for relative in LEAVES:
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        case = package / "examples/review-change"
        case.mkdir(parents=True)
        for name in SOURCE_NAMES:
            shutil.copyfile(ROOT / "examples/review-change" / name, case / name)
        return package, case

    def snapshots(self, before=None, after=None, states=None):
        root = self.tmp / "inputs"
        root.mkdir()
        before = before if before is not None else [{"key": "old", "meaning": "old meaning", "carrier": "panel"}]
        after = after if after is not None else [{"key": "old", "meaning": "old meaning", "carrier": "menu"}]
        values = {"before.json": before, "after.json": after,
                  "manifest.json": {"schema": "keyed-snapshot-manifest/v1", "before": "before.json", "after": "after.json"},
                  "policy.json": {"schema": "keyed-snapshot-policy/v1", "id_field": "key", "identity_field": "meaning",
                                  "state_field": "carrier", "states": states if states is not None else ["panel", "menu"]}}
        for name, data in values.items():
            (root / name).write_bytes(encoded(data))
        return root

    def compare(self, root, *extra):
        return self.run_cli(ROOT / "tools/keyed_snapshot_diff.py", "--root", root,
                            "--manifest", "manifest.json", "--policy", "policy.json", *extra)

    def forge_manifest(self, root, leaf):
        manifest = json.loads((root / "manifest.json").read_bytes())
        raw = (root / leaf).read_bytes()
        for row in manifest["files"]:
            if row["path"] == leaf:
                row["sha256"], row["bytes"] = sha(raw), len(raw)
        (root / "manifest.json").write_bytes(encoded(manifest))


class WorkspaceTests(LocalCase):
    def test_demo_roundtrip_exact_nine_and_case_semantics(self):
        source = ROOT / "examples/review-change"
        before = {name: ((source / name).read_bytes(), (source / name).stat().st_mtime_ns) for name in SOURCE_NAMES}
        out = self.demo()
        names = set(SOURCE_NAMES) | {"snapshot-diff.json", "WORKSPACE.md", "manifest.json"}
        self.assertEqual({p.name for p in out.iterdir()}, names)
        for name, (raw, _) in before.items():
            self.assertEqual((out / name).read_bytes(), raw)
        report = json.loads((out / "snapshot-diff.json").read_bytes())
        self.assertEqual(report["counts"], {"before_records": 2, "after_records": 3, "union_records": 3,
                                           "retained": 2, "added": 1, "removed": 0, "shared_identity_changed": 0})
        rows = {row["id"]: row for row in report["records"]}
        self.assertEqual(rows["F-reset"]["before"]["state"], "侧栏全部按钮")
        self.assertEqual(rows["F-reset"]["after"]["state"], "未安置")
        self.assertEqual(rows["F-count"]["kind"], "added")
        self.assertFalse(report["contract"]["business_approval_proved"])
        self.assertFalse(report["contract"]["anonymization_proved"])
        verified = self.review("check", out)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        status = json.loads(verified.stdout)
        self.assertEqual(status["files"], 9)
        self.assertIs(status["model_called"], False)
        self.assertIs(status["approval_proved"], False)
        for name, (raw, stamp) in before.items():
            self.assertEqual((source / name).read_bytes(), raw)
            self.assertEqual((source / name).stat().st_mtime_ns, stamp)

    def test_existing_directory_and_file_not_overwritten(self):
        for kind in ("directory", "file"):
            with self.subTest(kind=kind):
                out = self.tmp / kind
                if kind == "directory":
                    out.mkdir()
                    (out / "sentinel").write_text("caller data")
                    expected = file_state(out)
                else:
                    out.write_bytes(b"caller data")
                    expected = out.read_bytes()
                self.assert_error(self.review("demo", out))
                self.assertEqual(file_state(out) if out.is_dir() else out.read_bytes(), expected)

    def test_missing_parent_and_symlink_parent_rejected(self):
        out = self.tmp / "missing" / "new"
        self.assert_error(self.review("demo", out))
        self.assertFalse(out.parent.exists())
        real = self.tmp / "real"
        real.mkdir()
        alias = self.tmp / "alias"
        alias.symlink_to(real, target_is_directory=True)
        self.assert_error(self.review("demo", alias / "new"))
        self.assertEqual(list(real.iterdir()), [])

    def test_forged_manifest_does_not_hide_report_or_source_tampering(self):
        for leaf in ("snapshot-diff.json", "before.json"):
            with self.subTest(leaf=leaf):
                out = self.tmp / leaf.replace(".", "-")
                self.assertEqual(self.review("demo", out).returncode, 0)
                body = json.loads((out / leaf).read_bytes())
                if leaf == "snapshot-diff.json":
                    body["counts"]["added"] = 0
                else:
                    body[0]["meaning"] = "forged text"
                (out / leaf).write_bytes(encoded(body))
                self.forge_manifest(out, leaf)
                unchanged = file_state(out)
                self.assert_error(self.review("check", out))
                self.assertEqual(file_state(out), unchanged)

    def test_extra_file_and_nested_directory_rejected(self):
        out = self.demo()
        (out / "extra.txt").write_bytes(b"extra")
        self.assert_error(self.review("check", out))
        (out / "extra.txt").unlink()
        (out / "nested").mkdir()
        self.assert_error(self.review("check", out))

    def test_output_symlink_and_hardlink_rejected(self):
        out = self.demo()
        leaf = out / "case.md"
        saved = self.tmp / "saved-case.md"
        leaf.rename(saved)
        leaf.symlink_to(saved)
        self.assert_error(self.review("check", out))
        leaf.unlink()
        os.link(saved, leaf)
        self.assert_error(self.review("check", out))
        self.assertEqual(saved.read_bytes(), (ROOT / "examples/review-change/case.md").read_bytes())

    def test_packaged_source_symlink_and_hardlink_rejected_without_output(self):
        package, source = self.package_copy()
        leaf = source / "case.md"
        saved = self.tmp / "saved-source.md"
        leaf.rename(saved)
        leaf.symlink_to(saved)
        out = self.tmp / "new-out"
        self.assert_error(self.review("demo", out, package))
        self.assertFalse(out.exists())
        leaf.unlink()
        os.link(saved, leaf)
        self.assert_error(self.review("demo", out, package))
        self.assertFalse(out.exists())

    def test_invalid_source_json_is_rejected_before_output(self):
        package, source = self.package_copy()
        (source / "before.json").write_text('[{"key":"SECRET-CALLER-CONTENT","key":"x"}]', encoding="utf-8")
        out = self.tmp / "new-out"
        self.assert_error(self.review("demo", out, package), "SECRET-CALLER-CONTENT")
        self.assertFalse(out.exists())

    def test_bad_output_path_does_not_disclose_caller_path(self):
        out = self.tmp / "PRIVATE-CALLER-NAME" / "new"
        self.assert_error(self.review("demo", out), "PRIVATE-CALLER-NAME")


class SnapshotTests(LocalCase):
    def test_full_outer_counts_identity_changes_and_unmodified_inputs(self):
        before = [{"key": "same", "meaning": "old", "carrier": "panel"},
                  {"key": "removed", "meaning": "removed", "carrier": "panel"}]
        after = [{"key": "same", "meaning": "new", "carrier": "menu"},
                 {"key": "added", "meaning": "added", "carrier": "menu"}]
        root = self.snapshots(before, after)
        untouched = file_state(root)
        proc = self.compare(root, "--include-values")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        c = report["counts"]
        self.assertEqual(c, {"before_records": 2, "after_records": 2, "union_records": 3,
                             "retained": 1, "added": 1, "removed": 1, "shared_identity_changed": 1})
        self.assertEqual(c["retained"] + c["removed"], c["before_records"])
        self.assertEqual(c["retained"] + c["added"], c["after_records"])
        self.assertEqual(sum(t["records"] for t in report["transitions"]), c["union_records"])
        self.assertEqual({r["id"]: r["kind"] for r in report["records"]}, {"same": "retained", "removed": "removed", "added": "added"})
        self.assertEqual(file_state(root), untouched)

    def test_integer_and_string_ids_remain_distinct(self):
        rows = [{"key": 0, "meaning": "int", "carrier": "panel"},
                {"key": "0", "meaning": "string", "carrier": "panel"}]
        root = self.snapshots(rows, list(reversed(rows)))
        proc = self.compare(root, "--include-values")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = json.loads(proc.stdout)
        self.assertEqual(r["counts"]["retained"], 2)
        ids = r["records"]
        self.assertEqual({(type(x["id"]).__name__, x["id"]) for x in ids}, {("int", 0), ("str", "0")})
        self.assertEqual(len({x["id_sha256"] for x in ids}), 2)

    def test_null_boolean_integer_float_and_unicode_states_remain_distinct(self):
        states = [None, False, 0, 0.0, "é", "e\u0301"]
        before = [{"key": str(i), "meaning": 0, "carrier": value} for i, value in enumerate(states)]
        after = deepcopy(before)
        after[0]["meaning"] = False
        root = self.snapshots(before, after, states)
        proc = self.compare(root, "--include-values")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = json.loads(proc.stdout)
        self.assertEqual(len({x["before"]["state_sha256"] for x in r["records"]}), 6)
        self.assertEqual(r["counts"]["shared_identity_changed"], 1)
        self.assertEqual(len(r["transitions"]), 6)

    def test_default_fingerprints_hide_selected_values_but_claim_no_anonymization(self):
        marker = "SECRET-SYNTHETIC-VALUE"
        rows = [{"key": marker, "meaning": marker, "carrier": marker}]
        root = self.snapshots(rows, rows, [marker])
        proc = self.compare(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn(marker.encode(), proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertFalse(report["contract"]["values_included"])
        self.assertFalse(report["contract"]["anonymization_proved"])
        self.assertFalse(report["contract"]["business_approval_proved"])
        self.assertNotIn("id", report["records"][0])

    def test_duplicate_id_rejected_without_content_disclosure(self):
        marker = "PRIVATE-DUPLICATE-ID"
        rows = [{"key": marker, "meaning": "x", "carrier": "panel"}] * 2
        self.assert_error(self.compare(self.snapshots(rows, [])), marker)

    def test_undeclared_state_and_boolean_id_rejected(self):
        marker = "PRIVATE-UNDECLARED-STATE"
        root = self.snapshots([{ "key": "a", "meaning": "x", "carrier": marker}], [])
        self.assert_error(self.compare(root), marker)
        (root / "before.json").write_bytes(encoded([{ "key": False, "meaning": "x", "carrier": "panel"}]))
        self.assert_error(self.compare(root))

    def test_duplicate_json_keys_rejected(self):
        root = self.snapshots()
        (root / "before.json").write_text('[{"key":"PRIVATE-DUP-KEY","key":"other","meaning":"x","carrier":"panel"}]')
        self.assert_error(self.compare(root), "PRIVATE-DUP-KEY")

    def test_nonfinite_json_constants_and_overflow_rejected(self):
        root = self.snapshots()
        for value in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(value=value):
                (root / "before.json").write_text('[{"key":"private","meaning":' + value + ',"carrier":"panel"}]')
                self.assert_error(self.compare(root), "private")

    def test_input_symlink_and_hardlink_rejected(self):
        root = self.snapshots()
        leaf = root / "before.json"
        saved = self.tmp / "saved-before.json"
        leaf.rename(saved)
        leaf.symlink_to(saved)
        self.assert_error(self.compare(root))
        leaf.unlink()
        os.link(saved, leaf)
        self.assert_error(self.compare(root))

    def test_manifest_traversal_and_absolute_path_rejected(self):
        root = self.snapshots()
        outside = self.tmp / "outside.json"
        outside.write_bytes((root / "before.json").read_bytes())
        for selected in ("../outside.json", str(outside), "./before.json"):
            with self.subTest(selected=selected):
                (root / "manifest.json").write_bytes(encoded({"schema": "keyed-snapshot-manifest/v1", "before": selected, "after": "after.json"}))
                self.assert_error(self.compare(root))

    def test_report_target_is_new_and_outside_input_root(self):
        root = self.snapshots()
        untouched = file_state(root)
        existing = self.tmp / "existing.json"
        existing.write_bytes(b"caller report")
        self.assert_error(self.compare(root, "--json", existing))
        self.assertEqual(existing.read_bytes(), b"caller report")
        self.assert_error(self.compare(root, "--json", root / "new-report.json"))
        self.assertFalse((root / "new-report.json").exists())
        new = self.tmp / "new-report.json"
        proc = self.compare(root, "--json", new)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout, b"")
        self.assertEqual(json.loads(new.read_bytes())["status"], "COMPARISON_BUILT")
        self.assertEqual(file_state(root), untouched)

    def test_empty_input_and_lowered_record_ceiling_rejected(self):
        root = self.snapshots([], [])
        self.assert_error(self.compare(root))
        (root / "before.json").write_bytes(encoded([{"key": "a", "meaning": "x", "carrier": "panel"}]))
        (root / "after.json").write_bytes(encoded([{"key": "a", "meaning": "x", "carrier": "panel"}]))
        p = json.loads((root / "policy.json").read_bytes())
        p["limits"] = {"max_records": 1}
        (root / "policy.json").write_bytes(encoded(p))
        self.assert_error(self.compare(root))

    def test_boolean_or_increased_limit_not_accepted(self):
        root = self.snapshots()
        p = json.loads((root / "policy.json").read_bytes())
        for value in (True, 10001):
            with self.subTest(value=value):
                p["limits"] = {"max_records": value}
                (root / "policy.json").write_bytes(encoded(p))
                self.assert_error(self.compare(root))

    def test_missing_input_error_does_not_disclose_path_or_contents(self):
        root = self.snapshots()
        (root / "manifest.json").write_bytes(encoded({"schema": "keyed-snapshot-manifest/v1", "before": "PRIVATE-PATH.json", "after": "after.json"}))
        self.assert_error(self.compare(root), "PRIVATE-PATH")


if __name__ == "__main__":
    unittest.main()
