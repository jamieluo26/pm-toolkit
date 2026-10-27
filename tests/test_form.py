"""Functional checks for the bounded local form; no browser/approval claims."""
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
sys.path.insert(0, str(ROOT))
import form_core as core


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.events = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.events.extend(key for key in attributes if key.lower().startswith("on"))
        if tag == "script":
            self.active = {"attrs": attributes, "text": ""}
            self.scripts.append(self.active)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = None

    def handle_data(self, data):
        if self.active is not None:
            self.active["text"] += data


class FormTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-form-", dir=Path(tempfile.gettempdir()).resolve())
        self.base = Path(self.temp.name)
        self.spec = json.loads((ROOT / "examples/request-flow/spec.json").read_text(encoding="utf-8"))
        self.source = self.base / "input.json"
        self.write(self.spec)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, spec, name="input.json"):
        path = self.base / name
        path.write_bytes(core.encoded(spec))
        return path

    def cli(self, command="build", source=None, output=None, package=None):
        root = package or ROOT
        return subprocess.run([sys.executable, "-B", str(root / "pm_form.py"), command,
                               "--source", str(source or self.source),
                               "--output", str(output or self.base / "output")],
                              cwd=self.base, text=True, capture_output=True, check=False)

    def fail_build(self, spec):
        self.write(spec)
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ERROR")
        self.assertFalse((self.base / "output").exists())
        return result

    def build(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.base / "output"

    def test_build_check_exact_six_same_source_artifacts(self):
        before = self.source.read_bytes()
        out = self.build()
        self.assertEqual({p.name for p in out.iterdir()}, core.OUTPUTS)
        self.assertEqual((out / "source.json").read_bytes(), before)
        manifest = json.loads((out / "manifest.json").read_bytes())
        self.assertEqual(manifest["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(set(manifest["files"]), core.OUTPUTS - {"manifest.json"})
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
        trace = json.loads((out / "trace.json").read_bytes())
        self.assertTrue(trace["rows"])
        self.assertEqual({row["status"] for row in trace["rows"]}, {"NOT_EXECUTED"})
        self.assertIn("待执行检查计划", (out / "acceptance.md").read_text())
        self.assertEqual(self.cli("check").returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)

    def test_four_transitions_and_copy_isolation(self):
        original = deepcopy(self.spec)
        values = deepcopy(self.spec["initial_values"])
        step = core.transition(self.spec, "draft", values, "submit")
        self.assertEqual(step["state"], "submitted")
        step["values"]["request_title"] = "修改副本"
        self.assertEqual(values, self.spec["initial_values"])
        step = core.transition(self.spec, "submitted", values, "return", "补充交接条件")
        self.assertEqual(step["state"], "needs_info")
        self.assertEqual(step["reason"], "补充交接条件")
        values["description"] = "已在本地补充说明"
        step = core.transition(self.spec, step["state"], values, "resubmit")
        self.assertEqual(step["state"], "submitted")
        step = core.transition(self.spec, step["state"], values, "complete")
        self.assertEqual(step["state"], "done")
        self.assertEqual(step["meaning"], "LOCAL_SESSION_DEMO_ONLY")
        self.assertEqual(self.spec, original)

    def test_all_undeclared_and_terminal_transitions_rejected(self):
        allowed = {(row["from"], row["action"]) for row in core.TRANSITIONS}
        for state in core.STATES:
            for action in ("submit", "return", "resubmit", "complete", "approve", "reset"):
                if (state, action) not in allowed:
                    with self.subTest(state=state, action=action), self.assertRaises(core.Invalid):
                        core.transition(self.spec, state, self.spec["initial_values"], action, "理由")

    def test_required_blank_and_return_reason_block_transition(self):
        for value in ("", "  "):
            values = deepcopy(self.spec["initial_values"])
            values["request_title"] = value
            with self.subTest(value=value), self.assertRaises(core.Invalid):
                core.transition(self.spec, "draft", values, "submit")
        for reason in ("", "  ", "two\nlines", None):
            with self.subTest(reason=reason), self.assertRaises(core.Invalid):
                core.transition(self.spec, "submitted", self.spec["initial_values"], "return", reason)

    def test_initial_incomplete_allowed_only_in_editable_states(self):
        self.spec["initial_values"]["request_title"] = ""
        for state in ("draft", "needs_info"):
            self.spec["initial_state"] = state
            self.assertIs(core.validate_spec(self.spec), self.spec)
        for state in ("submitted", "done"):
            self.spec["initial_state"] = state
            with self.subTest(state=state), self.assertRaises(core.Invalid):
                core.validate_spec(self.spec)

    def test_optional_null_empty_choice_tags_and_zero_are_distinct(self):
        for field in self.spec["fields"]:
            field["required"] = False
        values = {"request_title": "", "category": "", "effort_hours": None, "audiences": [], "description": ""}
        self.spec["initial_values"] = values
        self.assertFalse(core.validate_values(self.spec, values, True))
        values["effort_hours"] = 0
        self.assertFalse(core.validate_values(self.spec, values, True))
        for wrong in (False, "0", [], ""):
            values["effort_hours"] = wrong
            self.assertTrue(core.validate_values(self.spec, values, True))

    def test_number_safe_boundaries_and_declared_range(self):
        field = next(row for row in self.spec["fields"] if row["type"] == "number")
        field.pop("minimum"); field.pop("maximum")
        for value in (-core.MAX_NUMBER, core.MAX_NUMBER, 0, 1.25):
            self.spec["initial_values"][field["key"]] = value
            with self.subTest(value=value):
                self.assertIs(core.validate_spec(self.spec), self.spec)
        for value in (-core.MAX_NUMBER - 1, core.MAX_NUMBER + 1, 10**1000, float("nan"), float("inf"), True):
            self.spec["initial_values"][field["key"]] = value
            with self.subTest(value=str(value)[:30]), self.assertRaises(core.Invalid):
                core.validate_spec(self.spec)
        field["minimum"], field["maximum"] = 0, 2
        for value in (0, 2):
            self.spec["initial_values"][field["key"]] = value
            self.assertIs(core.validate_spec(self.spec), self.spec)
        for value in (-1, 3):
            self.spec["initial_values"][field["key"]] = value
            with self.assertRaises(core.Invalid): core.validate_spec(self.spec)

    def test_reject_unknown_duplicate_and_wrong_field_schema(self):
        variants = []
        changed = deepcopy(self.spec); changed["unknown"] = "not supported"; variants.append(changed)
        changed = deepcopy(self.spec); changed["schema"] = "pm-request/v2"; variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"].append(deepcopy(changed["fields"][0])); variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"][0]["type"] = "date"; variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"][0]["required"] = 1; variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"][0]["minimum"] = 0; variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"][1]["choices"].append(changed["fields"][1]["choices"][0]); variants.append(changed)
        changed = deepcopy(self.spec); changed["initial_values"]["category"] = "不在允许范围"; variants.append(changed)
        changed = deepcopy(self.spec); changed["initial_values"]["audiences"] = ["产品", "产品"]; variants.append(changed)
        changed = deepcopy(self.spec); del changed["initial_values"]["description"]; variants.append(changed)
        for index, spec in enumerate(variants):
            with self.subTest(index=index): self.fail_build(spec)

    def test_invalid_requirements_state_parent_and_text(self):
        variants = []
        changed = deepcopy(self.spec); changed["initial_state"] = "approved"; variants.append(changed)
        changed = deepcopy(self.spec); changed["parent_sha256"] = "not a digest"; variants.append(changed)
        changed = deepcopy(self.spec); changed["requirements"].append(deepcopy(changed["requirements"][0])); variants.append(changed)
        changed = deepcopy(self.spec); changed["requirements"][0]["acceptance"] = []; variants.append(changed)
        changed = deepcopy(self.spec); changed["title"] = "two\nlines"; variants.append(changed)
        changed = deepcopy(self.spec); changed["initial_values"]["description"] = "x" * 1001; variants.append(changed)
        changed = deepcopy(self.spec); changed["fields"][2]["minimum"] = 100; variants.append(changed)
        for index, spec in enumerate(variants):
            with self.subTest(index=index): self.fail_build(spec)
        changed = deepcopy(self.spec); changed["title"] = "\ud800"
        with self.assertRaises(core.Invalid): core.validate_spec(changed)

    def test_duplicate_json_keys_and_nonfinite_constants_fail_before_output(self):
        original = self.source.read_text()
        invalid = [original.replace('"schema":', '"schema":"pm-request/v1","schema":', 1),
                   original.replace('"effort_hours": 2', '"effort_hours": NaN'),
                   original.replace('"effort_hours": 2', '"effort_hours": Infinity')]
        for raw in invalid:
            self.source.write_text(raw)
            result = self.cli()
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.base / "output").exists())

    def test_invalid_utf8_and_oversized_input_rejected(self):
        for raw in (b"\xff", b" " * 2_000_001):
            self.source.write_bytes(raw)
            self.assertEqual(self.cli().returncode, 2)
            self.assertFalse((self.base / "output").exists())

    def test_existing_directory_and_file_not_overwritten(self):
        out = self.base / "existing"
        out.mkdir(); marker = out / "mine.txt"; marker.write_text("caller file")
        before = marker.stat()
        self.assertEqual(self.cli(output=out).returncode, 2)
        self.assertEqual(marker.read_text(), "caller file")
        self.assertEqual(marker.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual({p.name for p in out.iterdir()}, {"mine.txt"})
        file = self.base / "file"; file.write_text("private caller data")
        self.assertEqual(self.cli(output=file).returncode, 2)
        self.assertEqual(file.read_text(), "private caller data")

    def test_existing_hardlink_output_never_overwrites_input(self):
        out = self.base / "hardlink"
        os.link(self.source, out)
        before = self.source.read_bytes()
        self.assertEqual(self.cli(output=out).returncode, 2)
        self.assertEqual(out.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), before)

    def test_input_and_parent_symlinks_rejected_but_hardlink_readonly(self):
        linked = self.base / "linked.json"; linked.symlink_to(self.source)
        self.assertEqual(self.cli(source=linked).returncode, 2)
        self.assertFalse((self.base / "output").exists())
        real = self.base / "real"; real.mkdir()
        linkdir = self.base / "linkdir"; linkdir.symlink_to(real, target_is_directory=True)
        self.assertEqual(self.cli(output=linkdir / "output").returncode, 2)
        self.assertFalse((real / "output").exists())
        source_link = self.base / "hard.json"; os.link(self.source, source_link)
        before = self.source.read_bytes()
        self.assertEqual(self.cli(source=source_link).returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_parent_and_output_traversal_do_not_escape(self):
        self.assertEqual(self.cli(output=self.base / "missing" / "out").returncode, 2)
        self.assertFalse((self.base / "missing").exists())
        # A lexical .. remains a path inside the caller's selected parent, not a field-derived name.
        nested = self.base / "nested"; nested.mkdir()
        out = nested / ".." / "inside"
        self.assertEqual(self.cli(output=out).returncode, 0)
        self.assertTrue((self.base / "inside" / "source.json").is_file())

    def test_check_detects_content_tamper_even_with_forged_manifest(self):
        out = self.build()
        target = out / "PRD.md"; target.write_bytes(target.read_bytes() + b"\nFORGED\n")
        manifest = json.loads((out / "manifest.json").read_bytes())
        manifest["files"]["PRD.md"] = hashlib.sha256(target.read_bytes()).hexdigest()
        (out / "manifest.json").write_bytes(core.encoded(manifest))
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        self.assertEqual(self.cli("check").returncode, 2)
        self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, before)

    def test_check_requires_precise_files_and_no_output_symlinks(self):
        out = self.build()
        extra = out / "EXTRA"; extra.write_text("caller file")
        self.assertEqual(self.cli("check").returncode, 2)
        extra.unlink()
        saved = (out / "PRD.md").read_bytes(); (out / "PRD.md").unlink()
        self.assertEqual(self.cli("check").returncode, 2)
        external = self.base / "prd-copy"; external.write_bytes(saved)
        (out / "PRD.md").symlink_to(external)
        self.assertEqual(self.cli("check").returncode, 2)
        self.assertEqual(external.read_bytes(), saved)

    def test_semantically_same_source_bytes_still_require_regeneration(self):
        out = self.build()
        original = self.source.read_bytes()
        self.source.write_text(json.dumps(self.spec, ensure_ascii=False, separators=(",", ":")))
        self.assertNotEqual(self.source.read_bytes(), original)
        self.assertEqual(self.cli("check").returncode, 2)
        self.assertEqual((out / "source.json").read_bytes(), original)

    def test_build_payload_rejects_different_values_and_bool_number_alias(self):
        spec = deepcopy(self.spec); spec["initial_values"]["effort_hours"] = 0
        raw_spec = deepcopy(spec); raw_spec["initial_values"]["effort_hours"] = False
        with self.assertRaises(core.Invalid): core.build_payload(spec, core.encoded(raw_spec))
        changed = deepcopy(self.spec); changed["title"] = "different title"
        with self.assertRaises(core.Invalid): core.build_payload(changed, self.source.read_bytes())

    def test_generator_change_requires_regeneration_in_isolated_copy(self):
        package = self.base / "isolated"; (package / "assets").mkdir(parents=True)
        for name in ("form_core.py", "pm_form.py", "assets/request-form.html"):
            (package / name).write_bytes((ROOT / name).read_bytes())
        self.assertEqual(self.cli(package=package).returncode, 0)
        template = package / "assets/request-form.html"
        template.write_bytes(template.read_bytes() + b"\n<!-- revised template -->\n")
        self.assertEqual(self.cli("check", package=package).returncode, 2)

    def test_html_payload_cannot_close_script_or_inject_handlers(self):
        probe = '</script><img src=x onerror="window.formAttack=1"> __REQUEST_PAYLOAD__ & <tag>'
        self.spec["title"] = probe
        self.spec["initial_values"]["description"] = probe
        payload = core.build_payload(self.spec, core.encoded(self.spec))
        document = Scripts(); document.feed(payload["prototype.html"].decode())
        baseline = Scripts(); baseline.feed((ROOT / "assets/request-form.html").read_text())
        self.assertEqual(len(document.scripts), len(baseline.scripts))
        self.assertEqual(document.events, baseline.events)
        source = json.loads(next(row["text"] for row in document.scripts if row["attrs"].get("id") == "request-payload"))
        self.assertEqual(source["spec"]["title"], probe)
        self.assertEqual(source["spec"]["initial_values"]["description"], probe)
        self.assertNotIn(probe, payload["prototype.html"].decode())

    def test_caller_material_retained_without_synthetic_or_safe_claim(self):
        marker = "调用者提供的待核验材料_ABC123"
        self.spec["title"] = "调用者请求"
        self.spec["positioning"] = "调用者自定定位"
        self.spec["pain"] = "调用者自述问题"
        self.spec["value"] = "调用者假设"
        self.spec["initial_values"]["description"] = marker
        payload = core.build_payload(self.spec, core.encoded(self.spec))
        for name in ("prototype.html", "PRD.md"):
            rendered = payload[name].decode()
            self.assertIn(marker, rendered)
            self.assertNotIn("全合成", rendered)
            self.assertNotIn("生产安全", rendered)
            self.assertIn("未经", rendered)
        self.assertEqual(json.loads(payload["source.json"])["initial_values"]["description"], marker)

    def test_stdout_never_echoes_caller_content_on_success_or_error(self):
        marker = "CALLER_SECRET_DO_NOT_ECHO_9328"
        self.spec["title"] = marker; self.write(self.spec)
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout + result.stderr)
        error = self.cli()
        self.assertEqual(error.returncode, 2)
        self.assertNotIn(marker, error.stdout + error.stderr)
        self.assertEqual(error.stderr, "")


if __name__ == "__main__":
    unittest.main()
