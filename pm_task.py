"""Prepare a versioned product task and audit supplied review/check records locally."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from task_core import (Invalid, read_json, require, task_payload, task_issues, review_tasks,
                       delivery_payload, initialize_payload)
from flow_core import new_directory, exact_directory


def review_inputs(args, source_raw=None):
    names = ("before", "feedback", "decisions")
    if not any(getattr(args, k, None) for k in names):
        return None, None
    require(all(getattr(args, k, None) for k in names))
    values, raws = {}, {}
    for name in ("before", "after", "feedback", "decisions"):
        path = args.source if name == "after" and source_raw is not None else getattr(args, name)
        values[name], raws[name + ".json"] = read_json(path)
    return review_tasks(**values, raws=raws)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--output", type=Path, required=True)
    for action in ("build", "check", "deliver", "deliver-check"):
        command = sub.add_parser(action)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        if action.startswith("deliver"):
            command.add_argument("--observations", type=Path, required=True)
            for key in ("before", "feedback", "decisions"):
                command.add_argument("--" + key, type=Path)
    for action in ("review", "review-check"):
        command = sub.add_parser(action)
        for key in ("before", "after", "feedback", "decisions", "output"):
            command.add_argument("--" + key, type=Path, required=True)
    for action in ("prepare-review", "prepare-review-check"):
        command = sub.add_parser(action)
        for key in ("before", "after", "output"):
            command.add_argument("--" + key, type=Path, required=True)
        command.add_argument("--version", required=True)
        command.add_argument("--notes", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            files, status, code = initialize_payload(), "DRAFT_CREATED", 0
        elif args.command.startswith("prepare-review"):
            from task_revision import prepare_revision
            before, before_raw = read_json(args.before)
            edited, edited_raw = read_json(args.after)
            notes = read_json(args.notes)[0] if args.notes else None
            require(args.notes is None or type(notes) is dict)
            files, report = prepare_revision(before, before_raw, edited, edited_raw, args.version, notes)
            status = report["status"]
            code = 3 if status == "HOLD" else 0
        elif args.command.startswith("review"):
            files, report = review_inputs(args)
            status = report["status"]
            code = 3 if status == "HOLD" else 0
        else:
            task, raw = read_json(args.source)
            if args.command.startswith("deliver"):
                observations, obs_raw = read_json(args.observations)
                rf, rr = review_inputs(args, raw)
                files, report = delivery_payload(task, raw, observations, obs_raw, rf, rr)
                status = report["status"]
                code = 3 if status == "HOLD" else 0
            else:
                files = task_payload(task, raw)
                code = 3 if task_issues(task) else 0
                status = "HOLD" if code else "CONSISTENT" if args.command == "check" else "GENERATED_NOT_ACCEPTED"
        if args.command in ("check", "review-check", "deliver-check", "prepare-review-check"):
            exact_directory(args.output, files)
        else:
            new_directory(args.output, files)
        print(json.dumps({"status": status, "files": len(files)}, ensure_ascii=False))
        return code
    except (Invalid, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, ImportError):
        print(json.dumps({"status": "ERROR", "reason": "Input/output contract or dependency failed; inspect local input and docs/task-spec.md."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
