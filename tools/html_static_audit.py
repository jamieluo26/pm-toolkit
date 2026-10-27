"""Audit explicitly selected UTF-8 HTML files without executing or fetching them."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

from audit_io import read_bytes

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 32
MAX_ELEMENTS = 30000
LINK_ATTRIBUTES = {"href", "src", "action", "formaction"}
KNOWN_TAGS = {"a", "img", "script", "link", "form", "iframe", "source", "video",
              "audio", "track", "base", "input", "button", "object", "embed"}


class AuditError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise AuditError("ARGUMENT_CONTRACT")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def text_sha(value):
    return sha(value.encode("utf-8"))


class Surface(HTMLParser):
    """Collect positions/counts only; no caller text is emitted in the report."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = defaultdict(list)
        self.named_anchors = set()
        self.links = []
        self.scripts = []
        self.forms = []
        self.overrides = []
        self.elements = 0
        self.empty_ids = 0
        self.base_count = 0
        self.event_attributes = 0
        self.active_urls = 0
        self.malformed_urls = 0
        self.duplicate_attribute_groups = 0

    def location(self):
        line, column = self.getpos()
        return {"line": line, "column": column}

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag, attrs):
        self.elements += 1
        if self.elements > MAX_ELEMENTS or len(attrs) > 256:
            raise AuditError("ELEMENT_LIMIT")
        location = self.location()
        a = {}
        for name, value in attrs:
            a.setdefault(name, value)
        self.duplicate_attribute_groups += sum(count > 1 for count in Counter(name for name, _ in attrs).values())
        if "id" in a:
            if a["id"]:
                self.ids[a["id"]].append(location)
            else:
                self.empty_ids += 1
        if tag == "a" and a.get("name"):
            self.named_anchors.add(a["name"])
        if tag == "base" and a.get("href"):
            self.base_count += 1
        self.event_attributes += sum(name.startswith("on") for name, _ in attrs)
        if tag == "script":
            kind = (a.get("type") or "").strip().lower()
            if kind in ("application/json", "application/ld+json"):
                category = "JSON_DATA"
            elif kind in ("", "module", "text/javascript", "application/javascript"):
                category = "EXECUTABLE_TYPE"
            else:
                category = "OTHER_TYPE_NOT_INTERPRETED"
            self.scripts.append({**location, "type_category": category, "has_src": bool(a.get("src"))})
        if tag == "form":
            method = (a.get("method") or "get").strip().lower()
            self.forms.append({**location, "method": method if method in ("get", "post", "dialog") else "INVALID",
                               "explicit_method": "method" in a, "has_action": bool(a.get("action"))})
        if "formmethod" in a:
            method = (a.get("formmethod") or "").strip().lower()
            self.overrides.append({**location, "method": method if method in ("get", "post", "dialog") else "INVALID"})
        for name, value in attrs:
            if name not in LINK_ATTRIBUTES or value is None:
                continue
            value = value.strip()
            try:
                parsed = urlsplit(value)
            except ValueError:
                self.malformed_urls += 1
                continue
            entry = {**location, "tag": tag if tag in KNOWN_TAGS else "other",
                     "attribute": name, "value_sha256": text_sha(value)}
            if value.startswith("#"):
                entry.update(kind="LOCAL_FRAGMENT", target=unquote(value[1:]))
            elif parsed.scheme in ("http", "https") or parsed.netloc:
                entry.update(kind="EXTERNAL_URL", scheme=parsed.scheme if parsed.scheme in ("http", "https") else "protocol-relative")
            elif parsed.scheme:
                if parsed.scheme in ("javascript", "vbscript"):
                    self.active_urls += 1
                    entry.update(kind="ACTIVE_SCHEME", scheme="active")
                else:
                    entry.update(kind="OTHER_SCHEME", scheme="other")
            else:
                entry.update(kind="RELATIVE_REFERENCE")
            self.links.append(entry)

    def report(self):
        duplicates = [{"id_sha256": text_sha(value), "occurrences": positions}
                      for value, positions in self.ids.items() if len(positions) > 1]
        fragments = []
        external = []
        relative_count = 0
        other_count = 0
        known = set(self.ids) | self.named_anchors
        for row in self.links:
            item = dict(row)
            if item["kind"] == "LOCAL_FRAGMENT":
                target = item.pop("target")
                item["target_sha256"] = text_sha(target)
                if self.base_count:
                    item["status"] = "UNRESOLVED_BASE_ELEMENT"
                elif not target:
                    item["status"] = "DOCUMENT_TOP"
                else:
                    item["status"] = "PRESENT" if target in known else "MISSING"
                fragments.append(item)
            elif item["kind"] == "EXTERNAL_URL":
                external.append(item)
            elif item["kind"] == "RELATIVE_REFERENCE":
                relative_count += 1
            else:
                other_count += 1
        missing = sum(row["status"] == "MISSING" for row in fragments)
        unresolved = sum(row["status"] == "UNRESOLVED_BASE_ELEMENT" for row in fragments)
        invalid_methods = sum(row["method"] == "INVALID" for row in self.forms + self.overrides)
        counts = {"elements": self.elements, "unique_nonempty_ids": len(self.ids),
                  "duplicate_id_groups": len(duplicates), "empty_id_attributes": self.empty_ids,
                  "local_fragments": len(fragments), "missing_local_fragments": missing,
                  "unresolved_local_fragments": unresolved, "script_elements": len(self.scripts),
                  "external_urls": len(external), "relative_references_not_resolved": relative_count,
                  "other_scheme_references": other_count, "form_elements": len(self.forms),
                  "invalid_form_methods": invalid_methods, "inline_event_attributes": self.event_attributes,
                  "active_scheme_urls": self.active_urls, "malformed_urls": self.malformed_urls,
                  "base_href_elements": self.base_count,
                  "duplicate_attribute_groups": self.duplicate_attribute_groups}
        needs_review = bool(duplicates or missing or unresolved or self.empty_ids or invalid_methods
                            or self.active_urls or self.malformed_urls or self.duplicate_attribute_groups)
        return {"status": "STATIC_REVIEW_NEEDED" if needs_review else "STATIC_CHECKED",
                "counts": counts, "duplicate_ids": duplicates, "local_fragments": fragments,
                "scripts": self.scripts, "external_urls": external,
                "forms": self.forms, "formmethod_overrides": self.overrides}


def inspect_inputs(paths):
    if not 1 <= len(paths) <= MAX_FILES:
        raise AuditError("INPUT_LIMIT")
    files = []
    seen = set()
    directory_ids = {}
    directory_rows = defaultdict(list)
    total = 0
    for ordinal, value in enumerate(paths, 1):
        path = Path(value).absolute()
        if path in seen:
            raise AuditError("DUPLICATE_INPUT")
        seen.add(path)
        if path.suffix.casefold() not in (".html", ".htm"):
            raise AuditError("HTML_SUFFIX_REQUIRED")
        raw = read_bytes(path.parent, path.name, max_bytes=MAX_FILE_BYTES)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise AuditError("TOTAL_LIMIT")
        text = raw.decode("utf-8")
        surface = Surface()
        surface.feed(text)
        surface.close()
        directory = directory_ids.setdefault(path.parent, len(directory_ids) + 1)
        row = {"input": ordinal, "directory": directory, "bytes": len(raw),
               "sha256": sha(raw), **surface.report()}
        files.append(row)
        directory_rows[directory].append({"input": ordinal, "bytes": len(raw), "sha256": sha(raw)})
    selected = [{"input": row["input"], "directory": row["directory"],
                 "bytes": row["bytes"], "sha256": row["sha256"]} for row in files]
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    directories = [{"directory": ident, "selected_files": len(rows),
                    "selected_bytes": sum(row["bytes"] for row in rows),
                    "selected_manifest_sha256": sha(canonical(rows))}
                   for ident, rows in sorted(directory_rows.items())]
    return {"schema": "pm-html-static-audit/v1",
            "status": "STATIC_REVIEW_NEEDED" if any(row["status"] != "STATIC_CHECKED" for row in files) else "STATIC_CHECKED",
            "meaning": "Only selected UTF-8 HTML text was parsed; no page, script, network, relative file or browser state was executed or fetched.",
            "report_privacy": "Input paths, ID text, URL text, form actions and caller content are not emitted; references use ordinal input, source position and SHA-256.",
            "selected_files": len(files), "selected_bytes": total,
            "selected_manifest_sha256": sha(canonical(selected)),
            "directories": directories, "files": files,
            "claims": {"external_links_are_vulnerabilities": False,
                       "html_conformance_verified": False, "runtime_verified": False,
                       "business_acceptance_verified": False, "directory_fully_scanned": False}}


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, action="append",
                        help="Explicit HTML file. Repeat for up to 32 selected files.")
    try:
        args = parser.parse_args(argv)
        report = inspect_inputs(args.input)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3 if report["status"] == "STATIC_REVIEW_NEEDED" else 0
    except (AuditError, OSError, ValueError, UnicodeError, RuntimeError, RecursionError):
        print(json.dumps({"status": "ERROR", "reason": "Selected HTML input contract failed."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
