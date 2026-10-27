"""Bounded behavior and privacy checks for local doctor and HTML source audit."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pm_doctor as doctor  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
import html_static_audit as audit  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SupportCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-support-")
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name).resolve()

    def file(self, name, text):
        target = self.tmp / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return target

    def cli(self, script, *args):
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONPATH="")
        proc = subprocess.run([sys.executable, "-B", str(ROOT / script), *map(str, args)],
                              cwd=self.tmp, env=env, capture_output=True, timeout=30)
        target = os.environ.get("PM_SUPPORT_TEST_EVENTS")
        if target:
            with Path(target).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"script": script, "argv": list(map(str, args)),
                    "exit": proc.returncode, "stdout": proc.stdout.decode("utf-8", errors="replace"),
                    "stderr": proc.stderr.decode("utf-8", errors="replace")}, ensure_ascii=False) + "\n")
        return proc

    def error(self, proc, secret=None):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "ERROR")
        self.assertEqual(proc.stderr, b"")
        if secret:
            self.assertNotIn(secret.encode("utf-8"), proc.stdout + proc.stderr)

    def toolkit(self):
        root = self.tmp / "fixture-toolkit"
        root.mkdir()
        rows = []
        for i, name in enumerate(sorted(doctor.UPSTREAM_FILES)):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = f"bounded frozen fixture {i}".encode()
            target.write_bytes(raw)
            rows.append({"distributed_path": name, "sha256": sha(raw)})
        (root / "UPSTREAM.json").write_text(json.dumps({"files": rows}))
        for name in doctor.RESOURCES:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Fixture resource only; no governance claim.\n")
        for name in doctor.SKILLS:
            target = root / "skills" / name / "SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("Fixture entry only.\n")
        return root

    def dependency(self):
        return {"name": "python-docx", "required_version": "1.2.0",
                "installed_version": "1.2.0", "module_discoverable": True, "matches_pin": True}


class HtmlStaticTests(SupportCase):
    def test_local_anchors_and_nonempty_ids_are_literal(self):
        path = self.file("page.html", '<h1 id="大纲">题目</h1><a href="#%E5%A4%A7%E7%BA%B2">跳转</a><a name="legacy"></a><a href="#legacy">旧锚</a><a href="#">顶部</a>')
        result = audit.inspect_inputs([path])
        self.assertEqual(result["status"], "STATIC_CHECKED")
        row = result["files"][0]
        self.assertEqual([x["status"] for x in row["local_fragments"]], ["PRESENT", "PRESENT", "DOCUMENT_TOP"])
        self.assertEqual(row["sha256"], sha(path.read_bytes()))
        self.assertFalse(result["claims"]["runtime_verified"])

    def test_duplicates_and_missing_fragments_report_locations_without_content(self):
        secret = "private-identity-value"
        path = self.file("private-filename.html", f'<p id="{secret}"></p>\n<div id="{secret}"></div>\n<a href="#missing-private-value">链接</a>')
        proc = self.cli("tools/html_static_audit.py", "--input", path)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        row = data["files"][0]
        self.assertEqual(row["counts"]["duplicate_id_groups"], 1)
        self.assertEqual(row["duplicate_ids"][0]["occurrences"], [{"line": 1, "column": 0}, {"line": 2, "column": 0}])
        self.assertEqual(row["counts"]["missing_local_fragments"], 1)
        for value in (secret, "missing-private-value", "private-filename", str(self.tmp)):
            self.assertNotIn(value.encode(), proc.stdout + proc.stderr)

    def test_scripts_external_links_and_forms_are_observations_not_vulnerabilities(self):
        path = self.file("links.html", '<script type="application/json">{"x":"<not-a-tag>"}</script><script src="https://example.invalid/app.js?private=hidden"></script><script>document.secret=1</script><a href="//example.invalid/a">A</a><form method="post" action="https://example.invalid/save"></form><form></form><button formmethod="dialog"></button>')
        data = audit.inspect_inputs([path])
        self.assertEqual(data["status"], "STATIC_CHECKED")
        row = data["files"][0]
        self.assertEqual(row["counts"]["script_elements"], 3)
        self.assertEqual(row["counts"]["external_urls"], 3)
        self.assertEqual([s["type_category"] for s in row["scripts"]], ["JSON_DATA", "EXECUTABLE_TYPE", "EXECUTABLE_TYPE"])
        self.assertEqual([f["method"] for f in row["forms"]], ["post", "get"])
        self.assertEqual(row["formmethod_overrides"][0]["method"], "dialog")
        self.assertFalse(data["claims"]["external_links_are_vulnerabilities"])
        self.assertNotIn("hidden", json.dumps(data))
        self.assertNotIn("example.invalid", json.dumps(data))

    def test_base_makes_local_fragment_resolution_unknown(self):
        path = self.file("base.html", '<base href="https://example.invalid/"><p id="x"></p><a href="#x">跳转</a><a href="#">顶部</a>')
        report = audit.inspect_inputs([path])
        self.assertEqual(report["status"], "STATIC_REVIEW_NEEDED")
        self.assertTrue(all(r["status"] == "UNRESOLVED_BASE_ELEMENT" for r in report["files"][0]["local_fragments"]))

    def test_invalid_methods_active_urls_and_duplicate_attributes_need_review(self):
        path = self.file("review.html", '<div id="first" id="secret-second"></div><a href="#first">A</a><form method="TRACE"></form><button formmethod="bad"></button><a href="javascript:privateCall()">B</a><a href="http://[bad">C</a>')
        row = audit.inspect_inputs([path])["files"][0]
        self.assertEqual(row["status"], "STATIC_REVIEW_NEEDED")
        self.assertEqual(row["counts"]["invalid_form_methods"], 2)
        self.assertEqual(row["counts"]["active_scheme_urls"], 1)
        self.assertEqual(row["counts"]["duplicate_attribute_groups"], 1)
        self.assertEqual(row["local_fragments"][0]["status"], "PRESENT")
        self.assertEqual(row["counts"]["malformed_urls"], 1)

    def test_selected_manifest_is_deterministic_and_does_not_scan_siblings(self):
        a = self.file("one/a.html", '<p id="a">A</p>')
        b = self.file("two/b.html", '<p>B</p>')
        ignored = self.file("one/not-selected.html", '<p id="bad"></p><p id="bad"></p>')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (a, b, ignored)}
        report = audit.inspect_inputs([a, b])
        self.assertEqual(report, audit.inspect_inputs([a, b]))
        self.assertEqual(report["selected_files"], 2)
        self.assertEqual(len(report["directories"]), 2)
        self.assertFalse(report["claims"]["directory_fully_scanned"])
        self.assertEqual(report["status"], "STATIC_CHECKED")
        for path, state in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state)

    def test_no_script_or_external_resource_execution(self):
        sentinel = self.tmp / "must-not-exist"
        path = self.file("inert-read.html", f'<script>throw new Error("{sentinel}")</script><img src="https://example.invalid/private"><script src="file:///private/script.js"></script>')
        report = audit.inspect_inputs([path])
        self.assertEqual(report["status"], "STATIC_CHECKED")
        self.assertFalse(sentinel.exists())
        self.assertFalse(report["claims"]["runtime_verified"])
        self.assertNotIn(str(sentinel), json.dumps(report))

    def test_input_contract_errors_do_not_echo_paths_or_values(self):
        secret = "private-input-name"
        utf8 = self.file(secret + ".html", b"\xff")
        big = self.file("oversized.html", b" " * (audit.MAX_FILE_BYTES + 1))
        wrong = self.file("wrong.txt", "<p>text</p>")
        missing = self.tmp / (secret + "-missing.html")
        for path in (utf8, big, wrong, missing):
            with self.subTest(path=path.name):
                self.error(self.cli("tools/html_static_audit.py", "--input", path), secret)
        self.error(self.cli("tools/html_static_audit.py", "--unknown", secret), secret)

    def test_symlink_files_parents_and_duplicate_inputs_rejected(self):
        path = self.file("real/page.html", "<p>text</p>")
        link = self.tmp / "linked.html"
        link.symlink_to(path)
        parent = self.tmp / "alias"
        parent.symlink_to(path.parent, target_is_directory=True)
        for selected in (link, parent / "page.html"):
            with self.subTest(selected=str(selected)):
                self.error(self.cli("tools/html_static_audit.py", "--input", selected))
        self.error(self.cli("tools/html_static_audit.py", "--input", path, "--input", path))

    def test_file_and_element_limits_are_enforced(self):
        path = self.file("elements.html", "<p>" * (audit.MAX_ELEMENTS + 1))
        self.error(self.cli("tools/html_static_audit.py", "--input", path))
        with self.assertRaises(audit.AuditError):
            audit.inspect_inputs([])
        with self.assertRaises(audit.AuditError):
            audit.inspect_inputs([path] * (audit.MAX_FILES + 1))

    def test_total_byte_limit_is_checked_across_selected_files(self):
        paths = [self.file(f"batch/{n}.html", b" " * audit.MAX_FILE_BYTES) for n in range(9)]
        with self.assertRaises(audit.AuditError):
            audit.inspect_inputs(paths)


class DoctorTests(SupportCase):
    def inspect(self, root, **kwargs):
        return doctor.inspect_environment(root, version=(3, 12, 0), dependency=self.dependency(), **kwargs)

    def test_exact_files_and_dependency_readiness_has_no_governance_claim(self):
        root = self.toolkit()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
        report = self.inspect(root)
        self.assertEqual(report["status"], "READY_FOR_DECLARED_LOCAL_REQUIREMENTS")
        self.assertEqual(report["upstream"]["status"], "MATCH")
        self.assertEqual(len(report["skill_entries"]), 6)
        self.assertTrue(all(v is False for v in report["claims"].values()))
        for path, state in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state)

    def test_missing_skill_and_empty_resource_are_attention(self):
        root = self.toolkit()
        (root / "skills" / doctor.SKILLS[0] / "SKILL.md").unlink()
        (root / doctor.RESOURCES[0]).write_bytes(b"")
        report = self.inspect(root)
        self.assertEqual(report["status"], "ATTENTION")
        self.assertEqual(report["resources"][0]["status"], "EMPTY")
        self.assertEqual(report["skill_entries"][0]["status"], "MISSING_OR_UNREADABLE")

    def test_dependency_mismatch_and_python_version_are_not_ready(self):
        root = self.toolkit()
        dependency = self.dependency()
        dependency.update(installed_version="0.0.1", matches_pin=False)
        report = doctor.inspect_environment(root, version=(3, 9, 9), dependency=dependency)
        self.assertEqual(report["status"], "ATTENTION")
        self.assertFalse(report["python"]["supported"])
        self.assertFalse(report["dependency"]["matches_pin"])

    def test_modified_upstream_or_symlink_resource_never_matches(self):
        root = self.toolkit()
        frozen = root / sorted(doctor.UPSTREAM_FILES)[0]
        frozen.write_text("modified")
        resource = root / doctor.RESOURCES[0]
        resource.unlink()
        resource.symlink_to(frozen)
        report = self.inspect(root)
        self.assertEqual(report["status"], "ATTENTION")
        self.assertEqual(report["upstream"]["status"], "ATTENTION")
        self.assertEqual(report["resources"][0]["status"], "MISSING_OR_UNREADABLE")

    def test_upstream_declaration_cannot_select_another_file(self):
        root = self.toolkit()
        value = json.loads((root / "UPSTREAM.json").read_text())
        value["files"][0]["distributed_path"] = "../private-file"
        (root / "UPSTREAM.json").write_text(json.dumps(value))
        with self.assertRaises(doctor.InputError):
            self.inspect(root)
        proc = self.cli("pm_doctor.py", "--root", root)
        self.error(proc, "private-file")

    def test_cli_errors_and_reports_do_not_echo_selected_root(self):
        secret = "private-root-location"
        self.error(self.cli("pm_doctor.py", "--root", self.tmp / secret), secret)
        self.error(self.cli("pm_doctor.py", "--unknown", secret), secret)
        root = self.toolkit()
        proc = self.cli("pm_doctor.py", "--root", root)
        self.assertIn(proc.returncode, (0, 3), proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        self.assertIn(body["status"], ("READY_FOR_DECLARED_LOCAL_REQUIREMENTS", "ATTENTION"))
        self.assertNotIn(str(root).encode(), proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, b"")


if __name__ == "__main__":
    unittest.main()
