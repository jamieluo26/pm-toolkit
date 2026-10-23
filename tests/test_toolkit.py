"""Synthetic integration checks for the W1 CLI; no browser, network or upstream suites."""
import copy
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "pm_toolkit.py"
BASE_SOURCE = ROOT / "examples/reading-list/case.json"
PYTHON = sys.executable
EVENTS = []
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
OUTPUTS = {
    "case.json", "product-brief.md", "requirements.md", "handoff.md",
    "decision-map.json", "decision-map.html", "document-source.json",
    "handoff.docx", "prototype.html", "journey.html", "manifest.json",
}
TEMPLATES = {
    "product-brief.md", "decision-evidence.md", "requirement-and-interaction.md",
    "design-handoff.md", "delivery-and-release.md", "retrospective.md",
}
# Hand-authored full document oracle for the supplied synthetic case. It does not
# call model(), projections(), the renderer, or the verifier to make expectations.
DOCX_ORACLE = [
    ("Title", "个人阅读清单 需求交接说明"),
    ("Normal", "用途：供评审者核对本版定位、需求、检查计划与待定事项。来源类型为 synthetic；文本关系和文档生成不等于业务验收。"),
    ("Normal", "版本 v0.1 synthetic"),
    ("Heading1", "定位与价值"),
    ("Normal", "定位：为想按主题找回待读内容的个人读者，提供一个本地阅读清单演示。"),
    ("Normal", "痛点：设定中的痛点是零散记录不便按主题浏览，未经过真实访谈。"),
    ("Normal", "价值：价值假设是减少找回内容的步骤；本例不声称效率提升或采用率。"),
    ("Normal", "目标：让评审者能够讨论范围、操作筛选，并核对同版交接材料。"),
    ("Normal", "待证假设：主题是否符合读者习惯、是否需要跨设备使用，仍待真实研究。"),
    ("Heading1", "讨论依据"),
    ("Normal", "S1：人工合成背景：读者把待读内容写在多处，希望按主题找回。没有真实访谈。"),
    ("Normal", "S2：合成讨论：角色A建议主题筛选；角色B同意把书目展示和主题筛选放入演示首版。"),
    ("Normal", "S3：合成样本为四本虚构书目，主题配置为产品、技术、研究、历史；历史暂无书目。"),
    ("Normal", "S4：为本次可操作演示新增的合成设定：默认全部；一次选一个主题；多主题书目按包含关系匹配；重复选择不改变结果；空结果给出提示。此设定补齐旧文字草案的缺口，不是实际业务批准。"),
    ("Normal", "S5：合成讨论：首版不含登录、云同步、多人协作。是否需要跨设备另行研究。"),
    ("Normal", "S6：合成讨论：不在阅读清单原型中提供业务数据导出，导出字段和格式尚未决定。工具包下载交接Word是另一项文档操作。"),
    ("Heading1", "本版设定中的决定"),
    ("Normal", "D1：合成设定内将书目展示和主题筛选纳入本地演示。 依据 S2"),
    ("Normal", "D2：本演示采用默认全部、单主题包含匹配、重复选择稳定及空态提示。 依据 S4"),
    ("Heading1", "需求与检查计划"),
    ("Normal", "R1：默认展示四本给定书目，保留其标题和全部主题。 依据 S3\nC1 关联 R1：打开演示原型并观察默认清单。\n预期：4本；方法卡片、界面笔记、工程日记、调研手册均出现。\n状态：计划；需另有当前版本实际观察才能记录通过。"),
    ("Normal", "R2：单选主题筛选；选择全部恢复；重复选择保持结果。 依据 S4\nC2 关联 R2：选择技术两次，再选择全部。\n预期：技术两次均为工程日记1本；返回全部为4本。\n状态：计划；需另有当前版本实际观察才能记录通过。"),
    ("Normal", "R3：无匹配书目时显示空态，仍可切回全部。 依据 S4\nC3 关联 R3：选择历史，然后切回全部。\n预期：历史0本并显示提示；全部恢复4本。\n状态：计划；需另有当前版本实际观察才能记录通过。"),
    ("Heading1", "排除范围"),
    ("Normal", "用户登录、云同步和多人协作"),
    ("Normal", "阅读清单业务数据导出"),
    ("Normal", "真实在线数据接入和生产上线"),
    ("Heading1", "待定事项"),
    ("Normal", "Q1：是否需要跨设备使用，尚无真实用户研究。 依据 S5"),
    ("Normal", "Q2：阅读清单未来的业务导出字段和格式未定，本版不实现。 依据 S6"),
    ("Heading1", "交接与验收边界"),
    ("Normal", "prototype.html 是本地演示，默认、空态和重复选择仅属演示合同，不代表真实项目批准。静态关系、工具运行、界面观察、内容回读、排版及人的验收分别记录；无证据保留未验证。"),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def fingerprint(path):
    path = Path(path)
    if path.is_symlink():
        return ("symlink", os.readlink(path))
    if path.is_file():
        b = path.read_bytes()
        return ("file", len(b), sha(b))
    return ("directory", tuple(
        (p.relative_to(path).as_posix(), fingerprint(p))
        for p in sorted(path.iterdir(), key=lambda x: x.name)
    ))


def source_snapshot():
    paths = [CLI, BASE_SOURCE, ROOT / "UPSTREAM.json", ROOT / "docs/personal-use.md",
             ROOT / "src/prototype.html", ROOT / "src/journey.html"]
    paths += sorted((ROOT / "templates").glob("*.md"))
    paths += sorted(p for p in (ROOT / "components").rglob("*") if p.is_file())
    result = {}
    for p in paths:
        s = p.lstat()
        result[p.relative_to(ROOT).as_posix()] = {
            "bytes": s.st_size, "sha256": sha(p.read_bytes()),
            "native7": [s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
                        s.st_mtime_ns, s.st_ctime_ns],
        }
    return result


def invoke(mode, output, source=None):
    if len([e for e in EVENTS if e.get("kind") == "cli"]) >= 150:
        raise AssertionError("bounded CLI-call budget exhausted")
    args = [PYTHON, "-B", str(CLI), mode, "--output", str(output)]
    if source is not None:
        args += ["--source", str(source)]
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONPATH="")
    r = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                       timeout=30)
    event = {"kind": "cli", "argv": args, "exit_code": r.returncode,
             "stdout": r.stdout.decode("utf-8", "replace"),
             "stderr": r.stderr.decode("utf-8", "replace")}
    EVENTS.append(event)
    stream = r.stdout if r.returncode == 0 else r.stderr
    try:
        value = json.loads(stream)
    except (ValueError, UnicodeDecodeError):
        value = None
    return r, value


class ParsedHTML(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.tags, self.event_attrs, self.scripts, self.titles = [], [], [], []
        self.in_title = False
        self.current_script = None
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.event_attrs += [(tag, key, value) for key, value in attrs
                             if key.lower().startswith("on")]
        if tag == "title":
            self.in_title = True
            self.titles.append("")
        if tag == "script":
            self.current_script = {"attrs": dict(attrs), "text": ""}
            self.scripts.append(self.current_script)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.current_script = None

    def handle_data(self, data):
        if self.in_title:
            self.titles[-1] += data
        if self.current_script is not None:
            self.current_script["text"] += data


def docx_rows(data):
    # Read exact actual OOXML in document order, resolving explicit paragraph styles.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    result = []
    for p in root.find(W + "body"):
        if p.tag == W + "sectPr":
            continue
        if p.tag != W + "p":
            raise AssertionError("extra main-body structure outside paragraph contract")
        style = p.find("./" + W + "pPr/" + W + "pStyle")
        sid = "Normal" if style is None else style.get(W + "val")
        text = []
        for e in p.iter():
            if e.tag == W + "t":
                text.append(e.text or "")
            elif e.tag == W + "tab":
                text.append("\t")
            elif e.tag in (W + "br", W + "cr"):
                text.append("\n")
        result.append((sid, "".join(text)))
    return result


def replace_docx_xml(data, change):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        parts = {i.filename: z.read(i) for i in z.infolist()}
    root = ET.fromstring(parts["word/document.xml"])
    change(root)
    parts["word/document.xml"] = ET.tostring(root, encoding="utf-8",
                                            xml_declaration=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
    return output.getvalue()


class ToolkitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = source_snapshot()
        cls.base_raw = BASE_SOURCE.read_bytes()
        cls.case = json.loads(cls.base_raw)
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix="pm-toolkit-fixture-")
        cls.fixture_root = Path(cls.fixture_temp.name)
        cls.source = cls.fixture_root / "source.json"
        cls.source.write_bytes(cls.base_raw)
        cls.demo_out, cls.build_out = cls.fixture_root / "demo", cls.fixture_root / "build"
        cls.initial_results = []
        for mode, out, source in (
            ("demo", cls.demo_out, None), ("build", cls.build_out, cls.source),
            ("check", cls.demo_out, cls.source), ("check", cls.build_out, cls.source),
        ):
            r, value = invoke(mode, out, source)
            cls.initial_results.append((mode, r.returncode, value))
            if r.returncode != 0:
                raise AssertionError("valid baseline blocked: " + repr((mode, value)))

    @classmethod
    def tearDownClass(cls):
        after = source_snapshot()
        EVENTS.append({"kind": "source_guards", "before": cls.before, "after": after,
                       "unchanged": after == cls.before})
        try:
            if after != cls.before:
                raise AssertionError("CLI input or frozen upstream/source changed during integration")
        finally:
            cls.fixture_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-toolkit-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "case.json"
        self.source.write_bytes(self.base_raw)
        self.sources = [self.source]

    def tearDown(self):
        if self.source.exists():
            self.assertEqual(self.source.read_bytes(), self.base_raw)

    def write_case(self, case, name="custom.json"):
        p = self.work / name
        p.write_bytes(json_bytes(case))
        return p

    def copy_bundle(self, name="out"):
        out = self.work / name
        shutil.copytree(self.demo_out, out)
        return out

    def succeeds(self, mode, out, source=None):
        source_before = None if source is None else fingerprint(source)
        r, value = invoke(mode, out, source)
        self.assertEqual(r.returncode, 0, value)
        self.assertIsInstance(value, dict)
        if source is not None:
            self.assertEqual(fingerprint(source), source_before)
        return value

    def fails(self, mode, out, source=None, code=None):
        out_before = fingerprint(out) if os.path.lexists(out) else None
        source_before = fingerprint(source) if source is not None and source.exists() else None
        r, value = invoke(mode, out, source)
        self.assertEqual(r.returncode, 2, (r.stdout, r.stderr))
        self.assertIsInstance(value, dict)
        self.assertEqual(value.get("status"), "FAIL")
        if code is not None:
            self.assertEqual(value.get("code"), code)
        self.assertNotIn("Traceback", r.stderr.decode())
        if out_before is not None:
            self.assertEqual(fingerprint(out), out_before, "failed check/output rejection mutated data")
        else:
            self.assertFalse(os.path.lexists(out), "invalid input produced partial success artifacts")
        if source_before is not None:
            self.assertEqual(fingerprint(source), source_before)
        return value

    def forge_manifest_file_identity(self, out, name):
        p = out / name
        manifest = json.loads((out / "manifest.json").read_bytes())
        b = p.read_bytes()
        manifest["files"][name] = {"bytes": len(b), "sha256": sha(b)}
        (out / "manifest.json").write_bytes(json_bytes(manifest))
        EVENTS.append({"kind": "mutation", "test": self.id(), "member": name,
                       "actual_bytes": len(b), "actual_sha256": sha(b),
                       "manifest_identity_recomputed": True})

    def test_01_demo_build_check_exact_eleven_and_same_bytes(self):
        self.assertEqual({p.name for p in self.demo_out.iterdir()}, OUTPUTS)
        self.assertEqual(fingerprint(self.demo_out), fingerprint(self.build_out))
        self.assertEqual((self.demo_out / "case.json").read_bytes(), self.base_raw)
        self.assertEqual((ROOT / "examples/reading-list/output/case.json").read_bytes(),
                         self.base_raw)
        self.assertEqual(fingerprint(self.demo_out),
                         fingerprint(ROOT / "examples/reading-list/output"))
        for mode, code, result in self.initial_results:
            self.assertEqual(code, 0)
            self.assertEqual(result["files"], 11)

    def test_02_docx_complete_ordered_manual_oracle(self):
        actual = docx_rows((self.demo_out / "handoff.docx").read_bytes())
        EVENTS.append({"kind": "ordered_docx_oracle", "expected": DOCX_ORACLE,
                       "observed": actual})
        self.assertEqual(actual, DOCX_ORACLE)
        from docx import Document
        doc = Document(io.BytesIO((self.demo_out / "handoff.docx").read_bytes()))
        self.assertEqual([p.text for p in doc.paragraphs], [x[1] for x in DOCX_ORACLE])
        source = json.loads((self.demo_out / "document-source.json").read_bytes())
        projected = [("Title", source["title"])] + [
            ("Heading1" if b["type"] == "heading" and b["level"] == 1 else "Normal",
             b["text"]) for b in source["blocks"]]
        self.assertEqual(projected, DOCX_ORACLE)

    def test_03_map_states_and_references_are_explicit(self):
        data = json.loads((self.demo_out / "decision-map.json").read_bytes())
        stack = [data["root"]]
        nodes = []
        while stack:
            node = stack.pop()
            nodes.append((node["id"], node["status"]))
            stack.extend(reversed(node["children"]))
        self.assertEqual(nodes, [
            ("root", "suggested"), ("context", "suggested"),
            ("decisions", "confirmed"), ("decision-D1", "confirmed"),
            ("decision-D2", "confirmed"), ("requirements", "suggested"),
            ("requirement-R1", "suggested"), ("requirement-R2", "suggested"),
            ("requirement-R3", "suggested"), ("pending", "pending"),
            ("pending-Q1", "pending"), ("pending-Q2", "pending")])
        pending = data["root"]["children"][3]["children"]
        self.assertEqual([n["facts"] for n in pending], [
            [["问题", self.case["pending"][0]["text"]], ["来源", "S5"]],
            [["问题", self.case["pending"][1]["text"]], ["来源", "S6"]]])

    def test_04_init_seven_files_and_six_unfilled_templates(self):
        out = self.work / "blank"
        value = self.succeeds("init", out)
        self.assertEqual(value, {"status": "BLANK_WORKSPACE_CREATED", "files": 7,
                                 "content_decisions": "MANUAL"})
        self.assertEqual({p.name for p in out.iterdir()}, TEMPLATES | {"START-HERE.md"})
        for name in TEMPLATES:
            b = (out / name).read_bytes()
            self.assertEqual(b, (ROOT / "templates" / name).read_bytes())
            self.assertIn("待填写", b.decode())
            for forbidden in ("个人阅读清单", "方法卡片", "工程日记",
                              self.case["decisions"][0]["text"]):
                self.assertNotIn(forbidden, b.decode())
        self.assertEqual((out / "START-HERE.md").read_bytes(),
                         (ROOT / "docs/personal-use.md").read_bytes())
        self.assertFalse((out / "case.json").exists())

    def test_05_existing_directory_file_and_symlink_never_replaced(self):
        for mode in ("init", "demo", "build"):
            for kind in ("directory", "file", "symlink", "dangling"):
                with self.subTest(mode=mode, kind=kind):
                    out = self.work / (mode + "-" + kind)
                    if kind == "directory":
                        out.mkdir(); (out / "keep.txt").write_text("KEEP")
                    elif kind == "file":
                        out.write_text("KEEP")
                    else:
                        target = self.work / (mode + "-" + kind + "-target")
                        if kind == "symlink":
                            target.write_text("KEEP")
                        out.symlink_to(target)
                    self.fails(mode, out, self.source if mode == "build" else None,
                               "OUTPUT_MUST_BE_NEW_DIRECTORY_WITH_EXISTING_PARENT")

    def test_06_missing_output_parent_rejected(self):
        for mode in ("init", "demo", "build"):
            with self.subTest(mode=mode):
                self.fails(mode, self.work / ("missing-" + mode) / "out",
                           self.source if mode == "build" else None,
                           "OUTPUT_MUST_BE_NEW_DIRECTORY_WITH_EXISTING_PARENT")

    def test_07_invalid_json_and_utf8(self):
        for i, raw in enumerate((b"{", b"\xff", b"[]", b"null", b"{} {}", b"{}")):
            with self.subTest(raw_sha=sha(raw)):
                src = self.work / ("invalid-" + str(i) + ".json")
                src.write_bytes(raw)
                self.fails("build", self.work / ("bad-" + str(i)), src)

    def test_08_duplicate_json_keys_root_and_nested(self):
        raw = self.base_raw.decode()
        nested = raw.replace('"audience":', '"audience":"duplicate", "audience":', 1)
        duplicate = raw.replace('"schema":', '"schema":"duplicate", "schema":', 1)
        for i, content in enumerate((duplicate, nested)):
            with self.subTest(kind=i):
                src = self.work / ("duplicate-" + str(i) + ".json")
                src.write_text(content)
                self.fails("build", self.work / ("baddup-" + str(i)), src,
                           "DUPLICATE_JSON_KEY")

    def test_09_nonfinite_json(self):
        for i, value in enumerate(("NaN", "Infinity", "-Infinity")):
            with self.subTest(value=value):
                raw = self.base_raw.decode().replace('"caseId": "reading-list"',
                                                    '"caseId": ' + value, 1)
                src = self.work / ("nonfinite-" + str(i) + ".json")
                src.write_text(raw)
                self.fails("build", self.work / ("badfinite-" + str(i)), src,
                           "NON_FINITE_JSON")

    def test_10_source_exact_limit_and_one_byte_over(self):
        exact = self.base_raw + b" " * (96000 - len(self.base_raw))
        src = self.work / "exact.json"; src.write_bytes(exact)
        out = self.work / "exact"
        self.succeeds("build", out, src)
        self.assertEqual((out / "case.json").read_bytes(), exact)
        self.succeeds("check", out, src)
        over = self.work / "over.json"; over.write_bytes(exact + b" ")
        self.fails("build", self.work / "over", over, "SOURCE_TOO_LARGE")

    def test_11_unknown_evidence_references(self):
        for group in ("decisions", "requirements", "pending"):
            with self.subTest(group=group):
                case = copy.deepcopy(self.case); case[group][0]["source"] = "S999"
                self.fails("build", self.work / group,
                           self.write_case(case, group + ".json"), "UNKNOWN_EVIDENCE")

    def test_12_duplicate_ids_check_ids_and_unknown_fields(self):
        variants = []
        case = copy.deepcopy(self.case); case["pending"][0]["id"] = "D1"; variants.append(case)
        case = copy.deepcopy(self.case); case["requirements"][1]["checkId"] = "C1"; variants.append(case)
        case = copy.deepcopy(self.case); case["unknown"] = "ignored"; variants.append(case)
        case = copy.deepcopy(self.case); case["evidence"][0]["hidden"] = "ignored"; variants.append(case)
        for i, case in enumerate(variants):
            with self.subTest(variant=i):
                self.fails("build", self.work / ("badids-" + str(i)),
                           self.write_case(case, "ids-" + str(i) + ".json"))

    def test_13_invalid_themes_books_and_text_boundaries(self):
        variants = []
        case = copy.deepcopy(self.case); case["themes"] = ["全部"]; variants.append(case)
        case = copy.deepcopy(self.case); case["themes"].append(case["themes"][0]); variants.append(case)
        case = copy.deepcopy(self.case); case["books"][0]["themes"] = ["未声明"]; variants.append(case)
        case = copy.deepcopy(self.case); case["books"][0]["themes"] = ["产品", "产品"]; variants.append(case)
        case = copy.deepcopy(self.case); case["title"] = "字"*31; variants.append(case)
        case = copy.deepcopy(self.case); case["context"]["pain"] = "字"*1201; variants.append(case)
        case = copy.deepcopy(self.case); case["evidence"] = []; variants.append(case)
        for i, case in enumerate(variants):
            with self.subTest(variant=i):
                self.fails("build", self.work / ("badshape-" + str(i)),
                           self.write_case(case, "shape-" + str(i) + ".json"))

    def test_14_wrong_case_and_changed_raw_bytes_refused(self):
        out = self.copy_bundle()
        changed = copy.deepcopy(self.case); changed["caseId"] = "other-case"
        self.fails("check", out, self.write_case(changed), "MANIFEST_SOURCE_MISMATCH")
        raw = self.work / "same-model-new-raw.json"
        raw.write_bytes(self.base_raw + b" ")
        self.fails("check", out, raw, "MANIFEST_SOURCE_MISMATCH")

    def test_15_actual_docx_wrong_body_with_forged_manifest(self):
        out = self.copy_bundle()
        def change(root):
            body = root.find(W + "body")
            body[1].find(".//" + W + "t").text = "WRONG_BODY_SAME_TITLE"
        data = replace_docx_xml((out / "handoff.docx").read_bytes(), change)
        (out / "handoff.docx").write_bytes(data)
        self.forge_manifest_file_identity(out, "handoff.docx")
        self.fails("check", out, self.source, "DOCX_CONTENT_MISMATCH")

    def test_16_actual_docx_reordered_requirements_with_forged_manifest(self):
        out = self.copy_bundle()
        def change(root):
            body = root.find(W + "body")
            first = next(p for p in body if "C1 关联 R1" in "".join(p.itertext()))
            second = next(p for p in body if "C2 关联 R2" in "".join(p.itertext()))
            a, b = list(body).index(first), list(body).index(second)
            body.remove(first); body.remove(second)
            body.insert(a, second); body.insert(b, first)
        (out / "handoff.docx").write_bytes(
            replace_docx_xml((out / "handoff.docx").read_bytes(), change))
        self.forge_manifest_file_identity(out, "handoff.docx")
        self.fails("check", out, self.source, "DOCX_CONTENT_MISMATCH")

    def test_17_stale_other_case_docx_and_forged_manifest(self):
        case = copy.deepcopy(self.case)
        case["caseId"], case["title"] = "new-reading", "新版阅读清单"
        src = self.write_case(case)
        out = self.work / "new"
        self.succeeds("build", out, src)
        (out / "handoff.docx").write_bytes((self.demo_out / "handoff.docx").read_bytes())
        self.forge_manifest_file_identity(out, "handoff.docx")
        self.fails("check", out, src, "DOCX_CONTENT_MISMATCH")

    def test_18_diagram_json_and_html_with_forged_manifest(self):
        for i, name in enumerate(("decision-map.json", "decision-map.html")):
            with self.subTest(name=name):
                out = self.copy_bundle("map-" + str(i))
                p = out / name
                if name.endswith(".json"):
                    data = json.loads(p.read_bytes())
                    data["root"]["children"][3]["status"] = "confirmed"
                    p.write_bytes(json_bytes(data))
                else:
                    b = p.read_bytes()
                    self.assertIn("个人阅读清单".encode(), b)
                    p.write_bytes(b.replace("个人阅读清单".encode(), "错误旧版本".encode(), 1))
                self.forge_manifest_file_identity(out, name)
                self.fails("check", out, self.source, "OUTPUT_CONTENT_MISMATCH")

    def test_19_prototype_function_changed_with_forged_manifest(self):
        out = self.copy_bundle(); p = out / "prototype.html"; b = p.read_bytes()
        target = b".filter(b=>b.themes.includes(selected))"
        self.assertIn(target, b)
        p.write_bytes(b.replace(target, b".filter(b=>true)", 1))
        self.forge_manifest_file_identity(out, "prototype.html")
        self.fails("check", out, self.source, "OUTPUT_CONTENT_MISMATCH")

    def test_20_journey_changed_with_forged_manifest(self):
        out = self.copy_bundle(); p = out / "journey.html"; b = p.read_bytes()
        p.write_bytes(b.replace("表中是计划".encode(), "全部已经验收".encode(), 1))
        self.assertNotEqual(p.read_bytes(), b)
        self.forge_manifest_file_identity(out, "journey.html")
        self.fails("check", out, self.source, "OUTPUT_CONTENT_MISMATCH")

    def test_21_extra_file_directory_and_missing_output(self):
        for i, kind in enumerate(("file", "directory", "missing")):
            with self.subTest(kind=kind):
                out = self.copy_bundle("extra-" + str(i))
                if kind == "file": (out / "unexpected.txt").write_text("extra")
                elif kind == "directory": (out / "unexpected").mkdir()
                else: (out / "requirements.md").unlink()
                self.fails("check", out, self.source, "OUTPUT_SET_MISMATCH")

    def test_22_output_root_and_members_symlinks_rejected(self):
        out = self.copy_bundle()
        linked = self.work / "linked"; linked.symlink_to(out, target_is_directory=True)
        self.fails("check", linked, self.source, "OUTPUT_NOT_DIRECTORY")
        for i, kind in enumerate(("file", "directory", "dangling")):
            with self.subTest(kind=kind):
                target = self.copy_bundle("links-" + str(i))
                if kind == "file":
                    outside = self.work / "outside.txt"
                    outside.write_bytes((target / "handoff.md").read_bytes())
                    (target / "handoff.md").unlink()
                    (target / "handoff.md").symlink_to(outside)
                elif kind == "directory":
                    (target / "extra-dir").symlink_to(out, target_is_directory=True)
                else:
                    (target / "handoff.md").unlink()
                    (target / "handoff.md").symlink_to(self.work / "absent")
                self.fails("check", target, self.source, "OUTPUT_SET_MISMATCH")

    def test_23_manifest_source_profile_and_member_identity(self):
        for i, field in enumerate(("version", "source_sha256", "caseId", "docx_profile_sha256", "files")):
            with self.subTest(field=field):
                out = self.copy_bundle("manifest-" + str(i))
                p = out / "manifest.json"; m = json.loads(p.read_bytes())
                if field == "files":
                    m[field]["handoff.md"]["sha256"] = "0"*64
                else:
                    m[field] = "wrong" if field in ("version", "caseId") else "0"*64
                p.write_bytes(json_bytes(m))
                self.fails("check", out, self.source)

    def test_24_duplicate_and_nonfinite_manifest_json(self):
        for i, kind in enumerate(("duplicate", "nonfinite")):
            with self.subTest(kind=kind):
                out = self.copy_bundle("badmanifest-" + str(i))
                p = out / "manifest.json"; text = p.read_text()
                if kind == "duplicate":
                    text = text.replace('"version":', '"version":"duplicate", "version":', 1)
                    code = "DUPLICATE_JSON_KEY"
                else:
                    text = text.replace('"version": "pm-toolkit/0.1"', '"version": NaN', 1)
                    code = "NON_FINITE_JSON"
                p.write_text(text)
                self.fails("check", out, self.source, code)

    def test_25_forged_claims_cannot_upgrade_check_response(self):
        out = self.copy_bundle(); p = out / "manifest.json"
        m = json.loads(p.read_bytes())
        m["claims"] = {"browser_behavior": "PASS", "human_acceptance": "PASS",
                       "public_release": "PASS", "authenticity": "SIGNED"}
        p.write_bytes(json_bytes(m))
        before = fingerprint(out)
        checked = self.succeeds("check", out, self.source)
        self.assertEqual(checked["browser_and_visual"], "NOT_PROVEN_BY_THIS_COMMAND")
        self.assertEqual(checked["authenticity"], "NONE")
        self.assertEqual(fingerprint(out), before)

    def test_26_malicious_literals_safe_in_HTML_and_script_JSON(self):
        case = copy.deepcopy(self.case)
        case["title"] = "</title><svg/onload=1>"
        case["edition"] = 'v1 "</script><script>x</script>'
        payload = '<img src=x onerror=1> & "\' </script><script>alert(1)</script>\u2028\u2029\n\t尾'
        case["context"]["audience"] = payload
        for group in ("evidence", "decisions", "requirements", "pending"):
            case[group][0]["text"] = payload
        case["excluded"][0] = payload
        case["books"][0]["title"] = '</script><img src=x onerror=1>\u2028\u2029'
        out = self.work / "malicious"; src = self.write_case(case)
        self.succeeds("build", out, src)
        self.succeeds("check", out, src)
        for name in ("prototype.html", "journey.html", "decision-map.html"):
            with self.subTest(page=name):
                actual = ParsedHTML((out / name).read_text())
                baseline = ParsedHTML((self.demo_out / name).read_text())
                self.assertEqual(actual.tags, baseline.tags, "input escaped its HTML context")
                self.assertEqual(actual.event_attrs, baseline.event_attrs)
                self.assertEqual(len(actual.scripts), len(baseline.scripts))
                self.assertTrue(actual.titles[0].startswith(case["title"]))
        parsed = ParsedHTML((out / "prototype.html").read_text())
        data_scripts = [s for s in parsed.scripts if s["attrs"].get("id") == "case-data"]
        self.assertEqual(len(data_scripts), 1)
        data = json.loads(data_scripts[0]["text"])
        self.assertEqual(data["title"], case["title"])
        self.assertEqual(data["edition"], case["edition"])
        self.assertEqual(data["books"], case["books"])
        self.assertNotIn("<", data_scripts[0]["text"])
        parsed_map = ParsedHTML((out / "decision-map.html").read_text())
        assignment = next(re.search(r"const settings = (.*?);\s*\n", s["text"], re.S)
                          for s in parsed_map.scripts if "const settings = " in s["text"])
        settings = json.loads(assignment.group(1))
        self.assertEqual(settings["root"]["title"], case["title"])
        self.assertEqual(settings["root"]["children"][0]["facts"][0][1], payload)
        self.assertEqual(docx_rows((out / "handoff.docx").read_bytes())[0][1],
                         case["title"] + " 需求交接说明")

    def test_27_literal_template_token_in_prototype_title_preserved(self):
        case = copy.deepcopy(self.case); case["title"] = "__CASE_DATA__"
        out = self.work / "literal-prototype"; src = self.write_case(case)
        self.succeeds("build", out, src)
        self.succeeds("check", out, src)
        parsed = ParsedHTML((out / "prototype.html").read_text())
        self.assertEqual(parsed.titles, ["__CASE_DATA__ 演示原型"])

    def test_28_literal_template_token_in_journey_title_preserved(self):
        case = copy.deepcopy(self.case); case["title"] = "__STEPS__"
        out = self.work / "literal-journey"; src = self.write_case(case)
        self.succeeds("build", out, src)
        self.succeeds("check", out, src)
        parsed = ParsedHTML((out / "journey.html").read_text())
        self.assertEqual(parsed.titles, ["__STEPS__ 完整案例走读"])


    def test_29_reserved_upstream_tokens_explicitly_rejected_without_output(self):
        tokens = ("__MAP_", "__MINDMAP_", "__DOCUMENT_TITLE__", "__CONTENT__")
        for field in ("title", "context"):
            for i, token in enumerate(tokens):
                with self.subTest(field=field, token=token):
                    case = copy.deepcopy(self.case)
                    if field == "title":
                        case["title"] = token
                    else:
                        case["context"]["audience"] = "Before " + token + " after"
                    name = "reserved-" + field + "-" + str(i)
                    src = self.write_case(case, name + ".json")
                    self.fails("build", self.work / name, src,
                               "RESERVED_UPSTREAM_TOKEN")


if __name__ == "__main__":
    unittest.main(verbosity=2)

