"""Explicit local input and exclusive JSON report helpers.

Paths are portable and root-relative. Inputs must be stable regular files, with
no symlink components. Report parents must exist; reports are new files outside
the input root. These helpers do not scan directories or choose personal paths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys

from file_audit_core import _plain_path, _read_file, path_within_root


MAX_BYTES = 8 * 1024 * 1024


def input_root(path: Path) -> Path:
    try:
        root = _plain_path(Path(path))
        if not root.is_dir():
            raise ValueError("Input root must be an existing directory")
        return root
    except (OSError, RuntimeError) as error:
        raise ValueError("Cannot resolve the explicit input root") from error


def input_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or any(ord(char) < 32 for char in relative)):
        raise ValueError("Input path must be a nonempty portable relative string")
    value = PurePosixPath(relative)
    if value.is_absolute() or PureWindowsPath(relative).drive or ".." in value.parts or not value.parts:
        raise ValueError("Input path must stay inside the explicit root")
    root = input_root(root)
    current = root
    for part in value.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Input symlink components are not followed")
    return current


def read_bytes(root: Path, relative: str, max_bytes: int = MAX_BYTES) -> bytes:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise ValueError("Byte limit must be a nonnegative integer")
    path = input_path(root, relative)
    try:
        return b"".join(_read_file(path, max_bytes))
    except (OSError, RuntimeError) as error:
        raise ValueError("Cannot read the selected relative input (" + type(error).__name__ + ")") from error


def read_text(root: Path, relative: str, max_bytes: int = MAX_BYTES) -> str:
    try:
        return read_bytes(root, relative, max_bytes).decode("utf-8")
    except UnicodeError as error:
        raise ValueError("Selected text input must be valid UTF-8") from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Nonfinite constants are not valid JSON")


def read_json(root: Path, relative: str, max_bytes: int = MAX_BYTES):
    return json.loads(read_text(root, relative, max_bytes), object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant)


def output_path(root: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    root = input_root(root)
    absolute = Path(os.path.abspath(path))
    try:
        parent = _plain_path(absolute.parent)
    except (OSError, RuntimeError) as error:
        raise ValueError("Report parent must be an existing directory without links") from error
    target = parent / absolute.name
    try:
        inside = path_within_root(target, root)
    except OSError as error:
        raise ValueError("Cannot verify report directory ancestry") from error
    if (not parent.is_dir() or target.exists() or target.is_symlink() or inside):
        raise ValueError("Report must be a new file outside the input root")
    return target


def emit_report(payload: dict, path: Path | None, root: Path) -> None:
    target = output_path(root, path)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if target is None:
        sys.stdout.write(text)
    else:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text)
