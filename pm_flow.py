"""Generate same-source prototype/PRD/check plans; audit supplied review decisions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from flow_core import Invalid, build_payload, exact_directory, new_directory, read_json, review_payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for action in ("build", "check"):
        sub = subs.add_parser(action)
        sub.add_argument("--source", required=True, type=Path)
        sub.add_argument("--output", required=True, type=Path)
    for action in ("review", "review-check"):
        sub = subs.add_parser(action)
        for name in ("before", "after", "feedback", "decisions", "output"):
            sub.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in ("review", "review-check"):
            values, raws = {}, {}
            for name in ("before", "after", "feedback", "decisions"):
                values[name], raws[name + ".json"] = read_json(getattr(args, name))
            files, report = review_payload(**values, raws=raws)
            if args.command == "review":
                new_directory(args.output, files)
            else:
                exact_directory(args.output, files)
            status = report["status"]
            code = 3 if status == "HOLD" else 0
        else:
            spec, raw = read_json(args.source)
            files = build_payload(spec, raw)
            if args.command == "check":
                exact_directory(args.output, files)
                status = "CONSISTENT"
            else:
                new_directory(args.output, files)
                status = "CANDIDATE_GENERATED"
            code = 0
        print(json.dumps({"status": status, "files": len(files)}, ensure_ascii=False))
        return code
    except (Invalid, OSError, ValueError, RecursionError, OverflowError):
        # Never echo caller content, sensitive paths, or an input parser exception.
        print(json.dumps({"status": "ERROR", "reason": "Input/output contract failed; inspect local inputs and choose a new output directory."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
