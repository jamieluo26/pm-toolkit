"""Generate/check a bounded single-form and four-state local demonstration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from form_core import Invalid, build_payload, exact_directory, new_directory, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        spec, raw = read_json(args.source)
        files = build_payload(spec, raw)
        if args.command == "build":
            new_directory(args.output, files)
            status = "FORM_CANDIDATE_GENERATED"
        else:
            exact_directory(args.output, files)
            status = "CONSISTENT"
        print(json.dumps({"status": status, "files": len(files)}))
        return 0
    except (Invalid, ValueError, OSError, TypeError, RecursionError, OverflowError):
        print(json.dumps({"status": "ERROR", "reason": "Input/output contract failed;inspect local material and choose a new output directory."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
