#!/usr/bin/env python3
"""Create or verify a local synthetic review workspace; never invoke a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import audit_io
import keyed_snapshot_diff

SOURCE_NAMES = ("before.json", "after.json", "policy.json", "snapshots.json", "case.md", "prompts.md")
GUIDE = """# 评审变更工作目录

本目录来自全合成阅读清单案例。before/after 是提案声明，不是生产发现。
snapshot-diff.json 只比较给定稳定键、功能文字及载体标签；“未安置”是输入明示的标签。

1. 先阅读 case.md，核准本次可见范围。
2. 查看 snapshot-diff.json，区分已有项的载体变化与新增提议。
3. 将 prompts.md 的两个任务分别交给助手，并显式提供仓库中对应 SKILL.md。
4. 人工核对引用、缺失关系及功能承接，决定下一步需要补充什么。

脚本没有调用AI，也没有把草案作为批准。不要从此报告推断真实UI已修改或验收通过。
若批准未来的原型变更，需另行同步需求与检查计划并提供实际浏览器证据。
输入和输出保留调用者内容，本工具不负责脱敏。manifest.json 只用于一致性核对，不是签名。
"""


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def payload():
    source = audit_io.input_root(ROOT / "examples/review-change")
    files = {}
    for name in SOURCE_NAMES:
        path = audit_io.input_path(source, name)
        if path.lstat().st_nlink != 1:
            raise ValueError("Source links are unsupported")
        files[name] = audit_io.read_bytes(source, name, 65536)
    report = keyed_snapshot_diff.audit(source, "snapshots.json", "policy.json", include_values=True)
    files["snapshot-diff.json"] = encode(report)
    files["WORKSPACE.md"] = GUIDE.encode("utf-8")
    records = [{"path": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in sorted(files.items())]
    files["manifest.json"] = encode({"schema": "pm-review-workspace/v1", "case": "synthetic-reading-list-review", "files": records,
                                    "proof": "consistency only;no approval,execution,identity or anonymization proof"})
    return files


def fresh_directory(target):
    absolute = Path(os.path.abspath(target))
    parent = audit_io._plain_path(absolute.parent)
    if not parent.is_dir() or absolute.exists() or absolute.is_symlink():
        raise ValueError("Output must be a new directory with an existing plain parent")
    absolute.mkdir()
    return absolute


def verify(target, expected):
    root = audit_io.input_root(target)
    actual = set()
    for path in root.rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            raise ValueError("Unexpected output directory")
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Output links or special files are unsupported")
        actual.add(path.name)
    if actual != set(expected):
        raise ValueError("Output file set differs")
    for name, raw in expected.items():
        if audit_io.read_bytes(root, name, max(len(raw), 1)) != raw:
            raise ValueError("Output content differs from the current case")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "check"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        files = payload()
        if args.command == "demo":
            target = fresh_directory(args.output)
            marker = target / "INCOMPLETE.txt"
            marker.write_text("Generation incomplete;not a delivery.\n", encoding="utf-8")
            for name, raw in files.items():
                with (target / name).open("xb") as stream:
                    stream.write(raw)
            marker.unlink()
            verify(target, files)
        else:
            verify(args.output, files)
        print(json.dumps({"status": "REVIEW_WORKSPACE_CREATED" if args.command == "demo" else "PASS_CURRENT_SYNTHETIC_WORKSPACE",
                          "files": len(files), "model_called": False, "approval_proved": False}))
        return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError, OverflowError, UnicodeError):
        print(json.dumps({"status": "ERROR", "code": "INPUT_OUTPUT_OR_CONTENT_ERROR"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
