"""Read-only local readiness checks; no installation or Skill execution."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from audit_io import input_root, read_bytes, read_json  # noqa: E402

PIN = "1.2.0"
UPSTREAM_FILES = {
    "components/product-mindmap/scripts/build_map.py",
    "components/product-mindmap/assets/mindmap.html",
    "components/product-mindmap/assets/standalone.html",
    "components/structured-docx/tools/structured_docx.py",
}
RESOURCES = (
    "templates/product-brief.md", "templates/decision-evidence.md",
    "templates/requirement-and-interaction.md", "templates/design-handoff.md",
    "templates/delivery-and-release.md", "templates/retrospective.md",
    "templates/task.json", "assets/collection.html", "assets/request-form.html",
)
SKILLS = (
    "requirement-acceptance-trace-review", "feedback-intent-preservation-review",
    "meeting-decision-evidence", "declared-impact-coverage-review",
    "supplied-acceptance-evidence-review", "product-asset-handbook",
)


class InputError(ValueError):
    """Never expose caller paths or parser messages in a CLI error."""


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise InputError("ARGUMENT_CONTRACT")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def dependency_report():
    """Check metadata and discoverability without importing third-party code."""
    try:
        version = importlib.metadata.version("python-docx")
    except importlib.metadata.PackageNotFoundError:
        version = None
    available = importlib.util.find_spec("docx") is not None
    # Metadata is environment-controlled. Do not echo arbitrary metadata text.
    displayed = version if version and re.fullmatch(r"[0-9A-Za-z.+_-]{1,80}", version) else None
    return {"name": "python-docx", "required_version": PIN,
            "installed_version": displayed, "module_discoverable": available,
            "matches_pin": version == PIN and available,
            "meaning": "Distribution metadata and module discoverability only; import/render not executed."}


def file_presence(root, relative):
    try:
        raw = read_bytes(root, relative, max_bytes=2 * 1024 * 1024)
        return {"path": relative, "status": "PRESENT" if raw else "EMPTY",
                "bytes": len(raw), "sha256": digest(raw)}
    except (OSError, ValueError, RuntimeError):
        return {"path": relative, "status": "MISSING_OR_UNREADABLE"}


def upstream_report(root):
    """Compare a bounded local declaration, not a signature or provenance proof."""
    value = read_json(root, "UPSTREAM.json", max_bytes=128 * 1024)
    if type(value) is not dict or type(value.get("files")) is not list or len(value["files"]) != 4:
        raise InputError("UPSTREAM_CONTRACT")
    rows = value["files"]
    if any(type(row) is not dict for row in rows):
        raise InputError("UPSTREAM_CONTRACT")
    paths = [row.get("distributed_path") for row in rows]
    if any(type(path) is not str for path in paths) or set(paths) != UPSTREAM_FILES or len(set(paths)) != 4:
        raise InputError("UPSTREAM_CONTRACT")
    result = []
    for row in sorted(rows, key=lambda r: r["distributed_path"]):
        relative, expected = row["distributed_path"], row.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise InputError("UPSTREAM_CONTRACT")
        if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
            raise InputError("UPSTREAM_CONTRACT")
        observed = file_presence(root, relative)
        observed["expected_sha256"] = expected
        if observed["status"] == "PRESENT":
            observed["status"] = "MATCH" if observed["sha256"] == expected else "MISMATCH"
        result.append(observed)
    return {"status": "MATCH" if all(r["status"] == "MATCH" for r in result) else "ATTENTION",
            "meaning": "Agrees with local UPSTREAM.json only; no trusted provenance/signature or license proof.",
            "files": result}


def inspect_environment(root, *, version=None, dependency=None):
    root = input_root(Path(root))
    actual_version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    python = {"version": ".".join(map(str, actual_version)),
              "minimum": "3.10", "supported": actual_version >= (3, 10)}
    dependency = dependency_report() if dependency is None else dependency
    upstream = upstream_report(root)
    resources = [file_presence(root, name) for name in RESOURCES]
    skills = [file_presence(root, f"skills/{name}/SKILL.md") for name in SKILLS]
    ready = (python["supported"] and dependency["matches_pin"] and upstream["status"] == "MATCH"
             and all(row["status"] == "PRESENT" for row in resources + skills))
    return {"schema": "pm-local-doctor/v1",
            "status": "READY_FOR_DECLARED_LOCAL_REQUIREMENTS" if ready else "ATTENTION",
            "meaning": "Selected files and declared environment only; no commands, models, Skills or renderers executed.",
            "python": python, "dependency": dependency, "upstream": upstream,
            "resources": resources, "skill_entries": skills,
            "claims": {"skill_governance_verified": False, "skill_installed": False,
                       "host_compatibility_verified": False, "workflow_accepted": False,
                       "browser_verified": False, "license_verified": False}}


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Explicit toolkit root; defaults to this script's directory.")
    try:
        args = parser.parse_args(argv)
        report = inspect_environment(args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "READY_FOR_DECLARED_LOCAL_REQUIREMENTS" else 3
    except (InputError, OSError, ValueError, RuntimeError, ImportError, RecursionError):
        print(json.dumps({"status": "ERROR", "reason": "Local input or declaration contract failed."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
