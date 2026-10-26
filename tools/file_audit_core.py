"""Read-only file audit helpers. Callers supply roots and exclusion rules.

Manifests describe selected regular files only, not permissions, empty directories,
links or ignored entries. Use on stable local inputs; an audit is not permission
to copy or delete the inputs. No personal folders are chosen automatically.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import os
from pathlib import Path
import re
import stat


def _plain_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if path.resolve(strict=True) != path:
        raise ValueError("Input links are not supported")
    return path


def path_within_root(path: Path, root: Path) -> bool:
    """Check resolved containment and existing ancestor identities.

    Physical directory identity catches case-insensitive aliases without
    case-folding names on case-sensitive filesystems. Missing output parents
    are allowed: their nearest existing ancestor and its parents are checked.
    An absent future root has no inode evidence; callers must check it again
    after creating it and before writing reports. Unexpected I/O errors raise
    rather than certifying that an output is outside the root.
    """
    path = Path(path).resolve(strict=False)
    root = Path(root).resolve(strict=False)
    if path.is_relative_to(root):
        return True
    try:
        info = root.stat()
        root_identity = (info.st_dev, info.st_ino)
    except FileNotFoundError:
        root_identity = None
    ancestor = path
    while True:
        try:
            info = ancestor.stat()
            break
        except FileNotFoundError:
            parent = ancestor.parent
            if parent == ancestor:
                raise
            ancestor = parent
    while True:
        if root_identity is not None and (info.st_dev, info.st_ino) == root_identity:
            return True
        parent = ancestor.parent
        if parent == ancestor:
            return False
        ancestor = parent
        info = ancestor.stat()


def _files(root: Path, *, skip_names=(), exclude_paths=()):
    root = _plain_path(root)
    if not root.is_dir():
        raise ValueError("Root must be a directory")
    skipped = set(skip_names)
    excluded = set()
    for value in exclude_paths:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Exclusions must be root-relative paths")
        excluded.add(relative.as_posix())
    def excluded_path(path):
        rel = path.relative_to(root)
        return any(parent.as_posix() in excluded for parent in (rel, *rel.parents))
    def walk_error(error):
        raise error
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs if name not in skipped
                         and not (base / name).is_symlink()
                         and not excluded_path(base / name))
        for name in sorted(names):
            path = base / name
            if name in skipped or excluded_path(path):
                continue
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                yield path


def _read_file(path: Path, max_bytes: int | None = None):
    path = _plain_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Input must be a regular file")
    if max_bytes is not None and before.st_size > max_bytes:
        raise ValueError("File exceeds byte limit")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) != signature(os.fstat(stream.fileno())):
            raise ValueError("Input changed before reading")
        total = 0
        while chunk := stream.read(1024 * 1024 if max_bytes is None else min(1024 * 1024, max_bytes - total + 1)):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ValueError("File grew beyond byte limit")
            yield chunk
        if signature(before) != signature(os.fstat(stream.fileno())) or signature(before) != signature(path.lstat()):
            raise ValueError("Input changed during reading")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in _read_file(path):
        digest.update(chunk)
    return digest.hexdigest()


def path_size(path: Path) -> int:
    """Logical bytes of regular files; links are skipped, errors are raised."""
    path = Path(path)
    if path.is_symlink():
        return 0
    path = _plain_path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in _files(path))


def directory_manifest(path: Path, ignore_names=None) -> dict[str, str]:
    path = _plain_path(path)
    return {item.relative_to(path).as_posix(): sha256(item)
            for item in sorted(_files(path, skip_names=ignore_names or ())) }


def directory_tree_digest(path: Path, ignore_names=None) -> str:
    digest = hashlib.sha256()
    for relative, value in directory_manifest(path, ignore_names).items():
        digest.update(relative.encode("utf-8") + b"\0" + value.encode("ascii") + b"\n")
    return digest.hexdigest()


def build_workspace_size_index(workspace: Path, *, skip_names=(), exclude_paths=()) -> dict[int, list[Path]]:
    by_size = defaultdict(list)
    for path in _files(workspace, skip_names=skip_names, exclude_paths=exclude_paths):
        by_size[path.stat().st_size].append(path)
    return dict(by_size)


def build_workspace_reference_index(workspace: Path, paths: list[str], *, text_suffixes,
                                    skip_names=(), exclude_paths=(),
                                    max_file_bytes=16 * 1024 * 1024) -> dict[str, list[str]]:
    """Literal UTF-8 byte matches in selected text files; return relative paths.

    Oversize files and links are outside this scan. Other I/O errors are raised.
    Matching is not semantic reference analysis or proof of unused files.
    """
    if max_file_bytes < 0 or any(not item for item in paths):
        raise ValueError("Nonempty needles and a nonnegative byte limit are required")
    root = _plain_path(workspace)
    needles = {value: value.encode("utf-8") for value in paths}
    references = {value: [] for value in needles}
    suffixes = {value.casefold() for value in text_suffixes}
    for candidate in _files(root, skip_names=skip_names, exclude_paths=exclude_paths):
        if candidate.suffix.casefold() not in suffixes or candidate.stat().st_size > max_file_bytes:
            continue
        content = b"".join(_read_file(candidate, max_file_bytes))
        for source_path, needle in needles.items():
            if needle in content:
                references[source_path].append(candidate.relative_to(root).as_posix())
    return references


def duplicate_base_name(name: str) -> str | None:
    candidate = re.sub(r" \([0-9]+\)(?=\.[^./]+$)", "", name)
    return candidate if candidate != name else None


def human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def markdown_table(records: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    if not records:
        return ["None"]
    def escape(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
    lines = ["| " + " | ".join(escape(title) for title, _ in columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for record in records:
        values = []
        for _, key in columns:
            value = record.get(key, "")
            if key == "bytes":
                value = human_bytes(int(value))
            elif isinstance(value, list):
                value = "<br>".join(escape(item) for item in value)
            values.append(escape(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines
