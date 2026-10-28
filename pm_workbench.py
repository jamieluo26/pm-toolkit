#!/usr/bin/env python3
"""Loopback-only local workbench over the unchanged pm_task.py CLI.

The operator selects a workspace at startup. Web callers choose server IDs only.
Runs, frozen inputs, command receipts and failed output are retained.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit
import uuid
import zipfile

from workbench_adapter import DraftError, to_task, validate_draft

ROOT = Path(__file__).absolute().parent
MAX_BODY = 2_097_152
ID = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z")
COMMANDS = {"build", "check", "prepare-review", "prepare-review-check", "review", "review-check", "deliver", "deliver-check"}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(draft):
    return sha(json.dumps(draft, ensure_ascii=False, sort_keys=True, allow_nan=False).encode())


def unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("duplicate key")
        result[k] = v
    return result


def decode(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))


class APIError(ValueError):
    def __init__(self, code, message, status=400, fields=None):
        super().__init__(message)
        self.code, self.message, self.status, self.fields = code, message, status, fields


def check(ok, code, message, status=400):
    if not ok:
        raise APIError(code, message, status)


def plain(path):
    """Never resolve through a symbolic link, including any ancestor."""
    p = Path(path).absolute()
    check(not p.is_symlink() and all(not x.is_symlink() for x in p.parents), "UNSAFE_PATH", "符号链接路径不可用。", 400)
    return p


def read(path):
    path = plain(path)
    check(path.is_file(), "NOT_FOUND", "材料不存在。", 404)
    with path.open("rb") as stream:
        return stream.read()


def load_json(path):
    return decode(read(path))


def write_new(path, value, raw=False):
    path = plain(path)
    with path.open("xb") as stream:
        stream.write(value if raw else encoded(value))


class Workbench:
    def __init__(self, workspace, timeout=90):
        self.workspace = plain(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.projects_dir = plain(self.workspace / "projects")
        self.projects_dir.mkdir(exist_ok=True, mode=0o700)
        self.timeout = timeout
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)

    def path(self, project_id):
        check(type(project_id) is str and ID.fullmatch(project_id), "NOT_FOUND", "项目不存在。", 404)
        return plain(self.projects_dir / project_id)

    def state(self, project_id):
        return load_json(self.path(project_id) / "project.json")

    def persist(self, project):
        directory = self.path(project["id"])
        plain(directory / "project.json")
        temp = directory / ("state_" + uuid.uuid4().hex + ".json")
        write_new(temp, project)
        os.replace(temp, directory / "project.json")

    def run_path(self, project_id, run_id):
        check(type(run_id) is str and ID.fullmatch(run_id), "NOT_FOUND", "运行记录不存在。", 404)
        return plain(self.path(project_id) / "runs" / run_id)

    def run_meta(self, project_id, run_id):
        return load_json(self.run_path(project_id, run_id) / "run.json")

    def guard_revision(self, project, value):
        check(type(value) is int and value == project["revision"], "STALE_REVISION", "草稿已更新；当前输入已保留，请重新加载后核对。", 409)

    def acquire(self):
        check(self.lock.acquire(blocking=False), "BUSY", "另一项本地操作尚未结束，请稍后重试。", 409)

    def projects(self):
        result = []
        for p in sorted(self.projects_dir.iterdir()):
            if p.is_symlink():
                continue
            if p.is_dir() and ID.fullmatch(p.name):
                state = self.state(p.name)
                result.append({k: state[k] for k in ("id", "title", "revision", "latest_build_run_id", "latest_preparation_run_id")})
        return result

    def create(self, draft):
        validate_draft(draft)
        # Validate typed fields and samples before persisting a draft.
        to_task(draft, "validation", "draft")
        self.acquire()
        try:
            pid = "p_" + uuid.uuid4().hex
            directory = self.path(pid)
            directory.mkdir(mode=0o700)
            (directory / "runs").mkdir()
            (directory / "observations").mkdir()
            project = {"id": pid, "title": draft["title"], "revision": 1, "draft": deepcopy(draft),
                       "run_ids": [], "latest_build_run_id": None, "latest_preparation_run_id": None}
            self.persist(project)
            return {"ok": True, "project": self.project(pid)}
        finally:
            self.lock.release()

    def save(self, project, body):
        self.guard_revision(project, body.get("expected_revision"))
        draft = body.get("draft")
        to_task(draft, project["id"], "draft")
        project.update(draft=deepcopy(draft), title=draft["title"], revision=project["revision"] + 1)
        self.persist(project)

    def new_run(self, project, kind, version):
        rid = "r_" + uuid.uuid4().hex
        directory = self.run_path(project["id"], rid)
        directory.mkdir()
        (directory / "inputs").mkdir()
        write_new(directory / "INCOMPLETE.txt", b"Operation started; preserve all partial materials.\n", raw=True)
        meta = {"id": rid, "kind": kind, "version": version, "status": "ERROR", "exit_code": 2,
                "check": None, "issues": [], "steps": [], "source_fingerprint": fingerprint(project["draft"]),
                "source_revision": project["revision"], "artifact_files": {}, "changes": []}
        return directory, meta

    def command(self, run_dir, action, **arguments):
        check(action in COMMANDS, "INTERNAL", "不支持的核心操作。", 500)
        args = [sys.executable, str(plain(ROOT / "pm_task.py")), action]
        for key, value in arguments.items():
            args += ["--" + key.replace("_", "-"), str(value)]
        receipt = {"command": action, "status": "ERROR", "exit_code": 2}
        try:
            process = subprocess.run(args, shell=False, cwd=ROOT, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=self.timeout, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            stdout = process.stdout.decode("utf-8", "replace")
            try:
                result = decode(process.stdout)
            except (ValueError, UnicodeError):
                result = {"status": "ERROR"}
            receipt.update(status=result.get("status", "ERROR"), exit_code=process.returncode,
                           stdout=result, timed_out=False)
            # Raw streams stay local; API never echoes private subprocess paths.
            write_new(run_dir / (action + "-stdout.txt"), stdout.encode(), raw=True)
            write_new(run_dir / (action + "-stderr.txt"), process.stderr, raw=True)
        except subprocess.TimeoutExpired as exc:
            receipt.update(timed_out=True, reason="TIMEOUT")
            write_new(run_dir / (action + "-stdout.txt"), exc.stdout or b"", raw=True)
            write_new(run_dir / (action + "-stderr.txt"), exc.stderr or b"", raw=True)
        except OSError:
            receipt.update(reason="EXECUTION_FAILED", timed_out=False)
        write_new(run_dir / (action + "-receipt.json"), receipt)
        return receipt

    def finish_run(self, project, directory, meta, output=None):
        # Only regular, generated top-level files become public artifacts.
        if output and output.is_dir():
            plain(output)
            for file in sorted(output.iterdir()):
                plain(file)
                if file.is_file() and NAME.fullmatch(file.name):
                    meta["artifact_files"][file.name] = "output/" + file.name
            for candidate in ("acceptance-results.json", "review.json", "manifest.json"):
                if candidate in meta["artifact_files"]:
                    report = load_json(output / candidate)
                    meta["issues"] = list(dict.fromkeys(meta["issues"] + report.get("issues", [])))
        if meta["exit_code"] == 2:
            if not meta["issues"]:
                meta["issues"] = ["TIMEOUT" if any(s.get("timed_out") for s in meta["steps"]) else "CORE_ERROR"]
        else:
            (directory / "INCOMPLETE.txt").unlink()
        write_new(directory / "run.json", meta)
        project["run_ids"].append(meta["id"])
        self.persist(project)
        return meta

    def cli_pair(self, directory, meta, action, **arguments):
        result = self.command(directory, action, **arguments)
        meta["steps"].append(result)
        meta.update(status=result["status"], exit_code=result["exit_code"])
        if result["exit_code"] in (0, 3):
            verified = self.command(directory, action + "-check" if action != "build" else "check", **arguments)
            meta["steps"].append(verified)
            meta["check"] = {"status": verified["status"], "exit_code": verified["exit_code"]}
            if verified["exit_code"] == 2:
                meta.update(status="ERROR", exit_code=2)
        return result

    def build(self, project, body):
        check(project["latest_build_run_id"] is None, "USE_REVISION", "已有初版，请用准备修订流程生成后续版本。", 409)
        self.guard_revision(project, body.get("expected_revision"))
        task = to_task(body.get("draft"), project["id"], body.get("version"))
        self.save(project, body)
        directory, meta = self.new_run(project, "build", task["version"])
        source = directory / "inputs" / "task.json"
        write_new(source, task)
        self.cli_pair(directory, meta, "build", source=source, output=directory / "output")
        if meta["exit_code"] in (0, 3):
            project["latest_build_run_id"] = meta["id"]
        self.finish_run(project, directory, meta, directory / "output")
        return meta

    def prepare(self, project, body):
        self.guard_revision(project, body.get("expected_revision"))
        base_id = body.get("base_run_id")
        check(base_id == project["latest_build_run_id"] and base_id is not None, "STALE_BASE", "请选择当前最近生成版本作为前版。", 409)
        base = self.run_meta(project["id"], base_id)
        before = self.artifact_path(project["id"], base_id, "task.json")
        before_task = load_json(before)
        check(body.get("draft", {}).get("kind") == project["draft"]["kind"], "FAMILY_CHANGED", "同一项目修订不能更换原型类型。", 409)
        task = to_task(body.get("draft"), project["id"], body.get("version"))
        check(task["version"] != base["version"], "VERSION_UNCHANGED", "修订版本必须不同于前版。")
        self.save(project, body)
        directory, meta = self.new_run(project, "preparation", task["version"])
        write_new(directory / "inputs" / "before.json", read(before), raw=True)
        write_new(directory / "inputs" / "edited.json", task)
        self.cli_pair(directory, meta, "prepare-review", before=directory / "inputs" / "before.json",
                      after=directory / "inputs" / "edited.json", version=task["version"], output=directory / "output")
        meta["base_run_id"] = base_id
        if meta["exit_code"] in (0, 3):
            paths = load_json(directory / "output" / "changed-paths.json")["paths"]
            after = load_json(directory / "output" / "after.json")
            meta["changes"] = [{"path": p, "label": p, "before": pointer(before_task, p), "after": pointer(after, p)} for p in paths]
            project["latest_preparation_run_id"] = meta["id"]
        self.finish_run(project, directory, meta, directory / "output")
        return meta

    def review(self, project, body):
        self.guard_revision(project, body.get("expected_revision"))
        rid = body.get("preparation_run_id")
        check(rid == project["latest_preparation_run_id"] and rid is not None, "STALE_PREPARATION", "准备材料已过期，请重新准备。", 409)
        prep = self.run_meta(project["id"], rid)
        check(prep["source_fingerprint"] == fingerprint(project["draft"]) and prep["source_revision"] == project["revision"],
              "STALE_PREPARATION", "候选内容已改变；旧反馈绑定失效，请重新准备后逐项核对。", 409)
        feedback = body.get("feedback")
        check(type(feedback) is list and 1 <= len(feedback) <= 100, "FEEDBACK", "需填写1至100条反馈。")
        notes = load_json(self.artifact_path(project["id"], rid, "review-notes.json"))
        allowed = {c["path"] for c in prep["changes"]}
        ids = set()
        for row in feedback:
            check(type(row) is dict and set(row) == set("id text source status rationale paths".split()), "FEEDBACK", "反馈字段不完整。")
            check(type(row["id"]) is str and ID.fullmatch(row["id"]) and row["id"] not in ids, "FEEDBACK", "反馈标识需唯一且安全。")
            ids.add(row["id"])
            for k in ("text", "source", "rationale"):
                check(type(row[k]) is str and bool(row[k].strip()) and len(row[k]) <= 3000, "FEEDBACK", "请填写反馈原意、来源与处理理由。")
            check(row["status"] in ("adopted", "declined", "pending", "conflict"), "FEEDBACK", "反馈处理状态无效。")
            check(type(row["paths"]) is list and all(type(p) is str and p in allowed for p in row["paths"]) and len(set(row["paths"])) == len(row["paths"]), "FEEDBACK_PATH", "请从实际变更路径中选择。")
            check(row["status"] == "adopted" or not row["paths"], "FEEDBACK_PATH", "只有明确采纳的反馈可承接变更路径。")
        notes["items"] = deepcopy(feedback)
        directory, meta = self.new_run(project, "review", prep["version"])
        # Exact submitted feedback remains attached to this immutable review run;
        # a later pending/adopted submission creates another retained record.
        meta["feedback"] = deepcopy(feedback)
        pdir = self.run_path(project["id"], rid) / "output"
        for name in ("before.json", "after.json"):
            write_new(directory / "inputs" / name, read(pdir / name), raw=True)
        write_new(directory / "inputs" / "notes.json", notes)
        self.cli_pair(directory, meta, "prepare-review", before=directory / "inputs" / "before.json",
                      after=directory / "inputs" / "after.json", version=prep["version"], notes=directory / "inputs" / "notes.json",
                      output=directory / "prepared")
        meta["preparation_run_id"] = rid
        if meta["exit_code"] in (0, 3):
            args = {k: directory / "prepared" / (k + ".json") for k in ("before", "after", "feedback", "decisions")}
            self.cli_pair(directory, meta, "review", **args, output=directory / "output")
        if meta["exit_code"] in (0, 3):
            # HOLD review still produces its real candidate build, never a pass.
            bd, bm = self.new_run(project, "build", prep["version"])
            write_new(bd / "inputs" / "task.json", read(directory / "prepared" / "after.json"), raw=True)
            self.cli_pair(bd, bm, "build", source=bd / "inputs" / "task.json", output=bd / "output")
            bm["review_run_id"] = meta["id"]
            if bm["exit_code"] in (0, 3):
                project["latest_build_run_id"] = bm["id"]
                meta["build_run_id"] = bm["id"]
            self.finish_run(project, bd, bm, bd / "output")
        self.finish_run(project, directory, meta, directory / "output")
        return meta

    def observations_value(self, project_id, run_id):
        value = load_json(self.artifact_path(project_id, run_id, "observations-template.json"))
        directory = plain(self.path(project_id) / "observations")
        for event in sorted(directory.iterdir()):
            plain(event)
            data = load_json(event)
            if data["build_run_id"] == run_id:
                value["rows"].extend(data["rows"])
        return value

    def observe(self, project, body):
        rid = body.get("build_run_id")
        check(rid == project["latest_build_run_id"] and rid is not None, "STALE_BUILD", "旧版本的观察只读；请选当前生成版本。", 409)
        run = self.run_meta(project["id"], rid)
        check(run["source_fingerprint"] == fingerprint(project["draft"]), "STALE_BUILD", "当前草稿已变化，请先完成修订生成。", 409)
        value = self.observations_value(project["id"], rid)
        allowed = {r["check_id"] for r in value["rows"]}
        rows = body.get("rows")
        check(type(rows) is list and 1 <= len(rows) <= 20, "OBSERVATIONS", "请提交1至20条逐检查点观察。")
        latest = {r["check_id"]: r["id"] for r in value["rows"]}
        addition = []
        for row in rows:
            check(type(row) is dict and set(row) == set("check_id status level observed evidence_ref defect".split()), "OBSERVATIONS", "观察字段不完整。")
            check(row["check_id"] in allowed and row["status"] in ("pass", "fail", "not_run") and row["level"] in ("browser", "manual", "content", "static"), "OBSERVATIONS", "检查标识、状态或层级无效。")
            for k in ("observed", "evidence_ref"):
                check(type(row[k]) is str and len(row[k]) <= 3000 and (row["status"] == "not_run" or bool(row[k].strip())), "OBSERVATIONS", "执行观察需填写具体结果与证据引用。")
            check(row["defect"] is None or type(row["defect"]) is str and 0 < len(row["defect"]) <= 3000, "OBSERVATIONS", "问题描述无效。")
            check(row["status"] != "fail" or bool(row["defect"]), "OBSERVATIONS", "失败必须填写问题描述。")
            added = {"id": "obs_" + uuid.uuid4().hex, **deepcopy(row), "supersedes": latest[row["check_id"]]}
            latest[row["check_id"]] = added["id"]
            addition.append(added)
        # Validate core evidence semantics without generating another document.
        import task_core
        task = load_json(self.artifact_path(project["id"], rid, "task.json"))
        raw = read(self.artifact_path(project["id"], rid, "task.json"))
        value["rows"].extend(addition)
        try:
            report = task_core.evidence_report(task, raw, value, read(self.artifact_path(project["id"], rid, "prototype.html")))
        except ValueError as exc:
            raise APIError("OBSERVATIONS", "观察不符合核心证据合同。") from exc
        sequence = len(list((self.path(project["id"]) / "observations").iterdir()))
        oid = "o_" + uuid.uuid4().hex
        write_new(self.path(project["id"]) / "observations" / (f"{sequence:08d}_" + oid + ".json"), {"id": oid, "build_run_id": rid, "rows": addition})
        return {"id": oid, "kind": "observations", "status": report["status"], "exit_code": 3 if report["issues"] else 0,
                "issues": report["issues"], "build_run_id": rid, "artifacts": [], "check": None}

    def deliver(self, project, body):
        rid = body.get("build_run_id")
        check(rid == project["latest_build_run_id"] and rid is not None, "STALE_BUILD", "只能交接当前生成版本。", 409)
        build = self.run_meta(project["id"], rid)
        check(build["source_fingerprint"] == fingerprint(project["draft"]), "STALE_BUILD", "当前草稿与生成版本不同，请先完成修订。", 409)
        directory, meta = self.new_run(project, "delivery", build["version"])
        source = directory / "inputs" / "task.json"
        write_new(source, read(self.artifact_path(project["id"], rid, "task.json")), raw=True)
        obs = directory / "inputs" / "observations.json"
        write_new(obs, self.observations_value(project["id"], rid))
        args = {"source": source, "observations": obs, "output": directory / "output"}
        if build.get("review_run_id"):
            review_dir = self.run_path(project["id"], build["review_run_id"]) / "output"
            for key in ("before", "feedback", "decisions"):
                dest = directory / "inputs" / (key + ".json")
                write_new(dest, read(review_dir / (key + ".json")), raw=True)
                args[key] = dest
        self.cli_pair(directory, meta, "deliver", **args)
        meta["build_run_id"] = rid
        self.finish_run(project, directory, meta, directory / "output")
        return meta

    def mutate(self, project_id, action, body):
        self.acquire()
        try:
            project = self.state(project_id)
            if action == "save":
                self.save(project, body)
                return {"ok": True, "project": self.project(project_id)}
            operation = {"build": self.build, "prepare-review": self.prepare, "review": self.review,
                         "observations": self.observe, "deliver": self.deliver}[action](project, body)
            if "artifact_files" in operation:
                operation = self.summary(project, operation)
            return {"ok": True, "project": self.project(project_id), "operation": operation}
        finally:
            self.lock.release()

    def artifact_path(self, project_id, run_id, filename):
        check(type(filename) is str and NAME.fullmatch(filename) and ".." not in filename, "NOT_FOUND", "材料不存在。", 404)
        meta = self.run_meta(project_id, run_id)
        check(filename in meta["artifact_files"], "NOT_FOUND", "此文件未在运行材料白名单中。", 404)
        # Never use caller paths, nor unchecked relative metadata paths.
        check(meta["artifact_files"][filename] == "output/" + filename, "UNSAFE_PATH", "材料路径不符合白名单。")
        result = plain(self.run_path(project_id, run_id) / "output" / filename)
        check(result.is_file(), "NOT_FOUND", "材料不存在。", 404)
        return result

    def summary(self, project, meta):
        result = {k: deepcopy(v) for k, v in meta.items() if k not in ("artifact_files", "source_fingerprint")}
        result["current_source"] = (meta["kind"] == "build" and project["latest_build_run_id"] == meta["id"] and meta["source_fingerprint"] == fingerprint(project["draft"]))
        base = f"/api/projects/{project['id']}/runs/{meta['id']}"
        result["artifacts"] = []
        for name in meta["artifact_files"]:
            raw = read(self.artifact_path(project["id"], meta["id"], name))
            result["artifacts"].append({"name": name, "url": base + "/files/" + name, "sha256": sha(raw), "bytes": len(raw)})
        result["package_url"] = base + "/package.zip"
        result["checks"] = []
        if {"observations-template.json", "trace.json"} <= set(meta["artifact_files"]):
            value = self.observations_value(project["id"], meta["id"]) if meta["kind"] == "build" else load_json(self.artifact_path(project["id"], meta["id"], "observations.json" if "observations.json" in meta["artifact_files"] else "observations-template.json"))
            trace = load_json(self.artifact_path(project["id"], meta["id"], "trace.json"))
            for c in trace["checks"]:
                history = [r for r in value["rows"] if r["check_id"] == c["id"]]
                latest = history[-1] if history else None
                result["checks"].append({**c, "check_id": c["id"], "status": latest["status"] if latest else "not_run", "latest": latest, "history": history})
        return result

    def project(self, project_id):
        p = self.state(project_id)
        result = {k: deepcopy(v) for k, v in p.items() if k != "run_ids"}
        result["runs"] = [self.summary(p, self.run_meta(project_id, rid)) for rid in p["run_ids"]]
        return result

    def package(self, project_id, run_id):
        meta = self.run_meta(project_id, run_id)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(meta["artifact_files"]):
                archive.writestr(name, read(self.artifact_path(project_id, run_id, name)))
        return stream.getvalue()


def pointer(value, path):
    try:
        for part in path.lstrip("/").split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if type(value) is list else value[part]
        return deepcopy(value)
    except (ValueError, KeyError, IndexError, TypeError):
        return None


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, workbench):
        check(address[0] == "127.0.0.1", "BIND", "仅允许绑定127.0.0.1。")
        self.workbench = workbench
        super().__init__(address, Handler)
        self.expected_host = "127.0.0.1:" + str(self.server_address[1])
        self.expected_origin = "http://" + self.expected_host


class Handler(BaseHTTPRequestHandler):
    server_version = "PMWorkbench/1"
    def log_message(self, format, *args):
        pass  # Do not log private project content, tokens or user paths.

    def headers_safe(self, content_type, length, extra=None):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def send_json(self, value, status=200):
        raw = encoded(value)
        self.send_response(status)
        self.headers_safe("application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def guard(self, write=False, public_static=False):
        check(self.headers.get_all("Host") == [self.server.expected_host], "HOST", "Host不匹配本地工作台。", 403)
        # A link or Chrome extension may navigate to the public shell from a
        # different site. The fixed shell contains no token or private projects.
        # API, artifacts and every mutation still pass all origin checks below.
        if public_static:
            return
        origins = self.headers.get_all("Origin") or []
        check(not origins or origins == [self.server.expected_origin], "ORIGIN", "请求来源不符合本地同源限制。", 403)
        check(self.headers.get("Sec-Fetch-Site") not in ("cross-site", "none-cross-site"), "ORIGIN", "不接受跨站请求。", 403)
        if write:
            check(origins == [self.server.expected_origin], "ORIGIN", "写入请求必须包含准确同源Origin。", 403)
            tokens = self.headers.get_all("X-Workbench-Token") or []
            check(len(tokens) == 1 and secrets.compare_digest(tokens[0], self.server.workbench.token), "TOKEN", "工作台会话令牌无效。", 403)

    def parsed(self):
        parsed = urlsplit(self.path)
        check(not parsed.scheme and not parsed.netloc and not parsed.fragment, "PATH", "请求路径无效。")
        path = unquote(parsed.path)
        check("%" not in path and "\\" not in path and "\x00" not in path and not any(p in (".", "..") for p in path.split("/")), "PATH", "路径不符合本地白名单。")
        return path, parsed.query

    def body(self):
        check(not self.headers.get("Transfer-Encoding"), "BODY", "不支持分块请求。")
        check(self.headers.get_all("Content-Type") == ["application/json"], "CONTENT_TYPE", "仅接受application/json。", 415)
        lengths = self.headers.get_all("Content-Length") or []
        check(len(lengths) == 1 and lengths[0].isdigit(), "BODY", "请求长度无效。")
        size = int(lengths[0])
        check(0 < size <= MAX_BODY, "BODY_LIMIT", "请求超过本地工作台大小限制。", 413)
        raw = self.rfile.read(size)
        check(len(raw) == size, "BODY", "请求内容不完整。")
        try:
            result = decode(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise APIError("JSON", "JSON内容无效。") from None
        check(type(result) is dict, "JSON", "请求内容必须为JSON对象。")
        return result

    def dispatch(self, method):
        path, query = self.parsed()
        public_static = method == "GET" and path in ("/", "/workbench.html", "/workbench.css", "/workbench.js")
        self.guard(method == "POST", public_static=public_static)
        wb = self.server.workbench
        if method == "GET":
            check(query in ("", "preview=1"), "QUERY", "不支持此查询参数。")
            if path == "/api/session":
                self.send_json({"ok": True, "csrf_token": wb.token, "projects": wb.projects(), "capabilities": {
                    "version": "pm-local-workbench-api/v1", "field_types": ["text", "number", "choice", "tags"],
                    "kinds": ["collection", "form"], "max_fields": 16, "max_checks": 20,
                    "workflow": "Local generated consistency and supplied observations; no human approval inferred."}})
                return
            if path == "/api/projects":
                self.send_json({"ok": True, "projects": wb.projects()}); return
            match = re.fullmatch(r"/api/projects/([a-z0-9_]+)", path)
            if match:
                self.send_json({"ok": True, "project": wb.project(match[1])}); return
            match = re.fullmatch(r"/api/projects/([a-z0-9_]+)/runs/([a-z0-9_]+)/(?:files/([^/]+)|(package\.zip))", path)
            if match:
                pid, rid, filename, zipped = match.groups()
                if zipped:
                    raw, filename, content = wb.package(pid, rid), "package.zip", "application/zip"
                else:
                    raw = read(wb.artifact_path(pid, rid, filename))
                    content = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                extra = {"Content-Disposition": ('inline' if query == "preview=1" and filename.endswith(".html") else 'attachment') + '; filename="' + filename + '"'}
                if filename.endswith(".html"):
                    extra["Content-Security-Policy"] = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
                self.send_response(200); self.headers_safe(content, len(raw), extra); self.wfile.write(raw); return
            static = {"/": "index.html", "/workbench.html": "index.html", "/workbench.css": "workbench.css", "/workbench.js": "workbench.js"}
            if path in static:
                raw = read(ROOT / "workbench" / static[path])
                content = mimetypes.guess_type(static[path])[0] or "application/octet-stream"
                self.send_response(200)
                self.headers_safe(content + "; charset=utf-8", len(raw), {"Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                self.wfile.write(raw); return
        if method == "POST":
            check(not query, "QUERY", "写入请求不接受查询参数。")
            body = self.body()
            if path == "/api/projects":
                check(set(body) == {"draft"}, "BODY", "创建仅接受draft。")
                self.send_json(wb.create(body["draft"])); return
            match = re.fullmatch(r"/api/projects/([a-z0-9_]+)/(save|build|prepare-review|review|observations|deliver)", path)
            if match:
                schemas = {"save": {"draft", "expected_revision"}, "build": {"draft", "expected_revision", "version"},
                    "prepare-review": {"draft", "expected_revision", "base_run_id", "version"},
                    "review": {"preparation_run_id", "expected_revision", "feedback"},
                    "observations": {"build_run_id", "rows"}, "deliver": {"build_run_id"}}
                check(set(body) == schemas[match[2]], "BODY", "操作字段不符合合同；不接受路径或命令参数。")
                self.send_json(wb.mutate(match[1], match[2], body)); return
        raise APIError("NOT_FOUND", "本地工作台路由不存在。", 404)

    def handle_method(self, method):
        self.connection.settimeout(20)
        try:
            self.dispatch(method)
        except DraftError as exc:
            self.send_json({"ok": False, "error": {"code": "DRAFT", "message": str(exc), "fields": exc.fields}}, 400)
        except APIError as exc:
            self.send_json({"ok": False, "error": {"code": exc.code, "message": exc.message, **({"fields": exc.fields} if exc.fields else {})}}, exc.status)
        except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError):
            self.send_json({"ok": False, "error": {"code": "LOCAL_ERROR", "message": "本地操作失败；已保留现有材料，请核对输入和运行记录。"}}, 400)
        finally:
            self.close_connection = True

    def do_GET(self): self.handle_method("GET")
    def do_POST(self): self.handle_method("POST")
    def do_OPTIONS(self): self.handle_method("OPTIONS")
    def do_PUT(self): self.handle_method("PUT")
    def do_DELETE(self): self.handle_method("DELETE")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / ".pm-toolkit-workbench")
    parser.add_argument("--port", type=int, default=8841)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)
    check(0 <= args.port <= 65535 and 1 <= args.timeout <= 600, "OPTIONS", "端口或超时参数无效。")
    wb = Workbench(args.workspace, args.timeout)
    # Prevent two server processes writing the same project store.
    import fcntl
    lockfile = plain(wb.workspace / "server.lock").open("a+b")
    try:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Workspace already in use by another local workbench.") from None
    server = Server(("127.0.0.1", args.port), wb)
    print("Local PM workbench: " + server.expected_origin, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lockfile.close()


if __name__ == "__main__":
    main()
