#!/usr/bin/env python3
"""Compare explicitly configured JSON snapshots by unique typed stable IDs.

Default reports contain counts, canonical positions and versioned fingerprints.
--include-values exposes the selected ID/identity/state values. Fingerprints are
not anonymization, and a completed comparison is not a business approval.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat

import audit_io


DEFAULT_LIMITS = {"max_records": 10000, "max_states": 256, "max_depth": 32,
                  "max_nodes": 100000, "max_string_chars": 4096,
                  "max_input_bytes": 1048576, "max_output_bytes": 4194304}
MAX_CONTROL_BYTES = 65536
DOMAIN = b"keyed-snapshot-diff/v1\0"


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _string(value, maximum, nonempty=False):
    if type(value) is not str or len(value) > maximum or (nonempty and not value):
        raise ValueError("Invalid bounded string")
    value.encode("utf-8", errors="strict")
    return value


def _typed(value):
    """A local versioned scalar encoding; bool, int and float remain distinct."""
    kind = type(value)
    if value is None: return ["null"]
    if kind is bool: return ["bool", value]
    if kind is int: return ["int", value]
    if kind is float and math.isfinite(value): return ["float", value.hex()]
    if kind is str: return ["str", value]
    raise ValueError("Selected fields must be finite JSON scalars")


def _id(value):
    if type(value) not in (str, int) or (type(value) is str and not value):
        raise ValueError("Stable IDs must be nonempty strings or integers")
    return _encode(_typed(value))


def _limits(policy):
    limits = dict(DEFAULT_LIMITS)
    supplied = policy.get("limits", {})
    if type(supplied) is not dict or set(supplied) - set(limits):
        raise ValueError("Invalid limits")
    for name, value in supplied.items():
        if type(value) is not int or not 1 <= value <= limits[name]:
            raise ValueError("Limits must be lower positive integers")
        limits[name] = value
    return limits


def _validate_json(value, limits):
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop(); count += 1
        if depth > limits["max_depth"] or count > limits["max_nodes"]:
            raise ValueError("JSON depth or node ceiling")
        kind = type(item)
        if kind in (dict, list) and count + len(stack) + len(item) > limits["max_nodes"]:
            raise ValueError("JSON node ceiling")
        if kind is dict:
            for key, child in item.items():
                _string(key, limits["max_string_chars"])
                stack.append((child, depth + 1))
        elif kind is list:
            stack.extend((child, depth + 1) for child in item)
        elif kind is str: _string(item, limits["max_string_chars"])
        elif kind is float:
            if not math.isfinite(item): raise ValueError("Nonfinite JSON number")
        elif item is None or kind in (int, bool): pass
        else: raise ValueError("Unsupported JSON type")
    if len(_encode(value)) > limits["max_input_bytes"]:
        raise ValueError("Aggregate JSON byte ceiling")


def validate_policy(policy):
    required = {"schema", "id_field", "identity_field", "state_field", "states"}
    if (type(policy) is not dict or set(policy) - required - {"limits"}
            or not required <= set(policy) or policy["schema"] != "keyed-snapshot-policy/v1"):
        raise ValueError("Invalid snapshot policy")
    limits = _limits(policy)
    fields = [_string(policy[key], 128, True) for key in ("id_field", "identity_field", "state_field")]
    if len(set(fields)) != 3: raise ValueError("Selected fields must be distinct")
    states = policy["states"]
    if type(states) is not list or not 1 <= len(states) <= limits["max_states"]:
        raise ValueError("An explicit bounded state vocabulary is required")
    _validate_json(policy, limits)
    state_keys = [_encode(_typed(value)) for value in states]
    if len(set(state_keys)) != len(state_keys): raise ValueError("Duplicate typed states")
    return limits, fields, set(state_keys)


def _fingerprint(role, encoded):
    return hashlib.sha256(DOMAIN + role.encode("ascii") + b"\0" + encoded).hexdigest()


def _bounded_report(result, limits):
    raw = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > limits["max_output_bytes"]: raise ValueError("Report byte ceiling")


def compare(before, after, policy, include_values=False):
    """Return a fresh full-outer comparison; caller inputs are never modified."""
    if type(include_values) is not bool: raise ValueError("Invalid disclosure flag")
    limits, fields, allowed_states = validate_policy(policy)
    if type(before) is not list or type(after) is not list or not before and not after:
        raise ValueError("At least one nonempty snapshot is required")
    if len(before) + len(after) > limits["max_records"]:
        raise ValueError("Aggregate record ceiling")
    _validate_json([before, after], limits)
    id_field, identity_field, state_field = fields

    def index(records):
        result = {}
        for row in records:
            if type(row) is not dict or not all(field in row for field in fields):
                raise ValueError("Selected record fields are required")
            key = _id(row[id_field])
            identity = _encode(_typed(row[identity_field]))
            state = _encode(_typed(row[state_field]))
            if state not in allowed_states: raise ValueError("Undeclared state")
            if key in result: raise ValueError("Duplicate typed stable ID")
            result[key] = (row, identity, state)
        return result

    left, right = index(before), index(after)

    def side(entry, with_identity):
        if entry is None: return {"presence": "absent"}
        row, identity, state = entry
        result = {"presence": "present", "state_sha256": _fingerprint("state", state)}
        if with_identity: result["identity_sha256"] = _fingerprint("identity", identity)
        if include_values:
            result["state"] = deepcopy(row[state_field])
            if with_identity: result["identity"] = deepcopy(row[identity_field])
        return result

    counts = {"before_records": len(left), "after_records": len(right), "union_records": 0,
              "retained": 0, "added": 0, "removed": 0, "shared_identity_changed": 0}
    rows, transitions = [], {}
    for position, key in enumerate(sorted(left.keys() | right.keys()), 1):
        old, new = left.get(key), right.get(key)
        kind = "added" if old is None else "removed" if new is None else "retained"
        changed = old[1] != new[1] if old is not None and new is not None else None
        counts[kind] += 1
        if changed: counts["shared_identity_changed"] += 1
        row = {"position": position, "id_sha256": _fingerprint("id", key), "kind": kind,
               "identity_changed": changed, "before": side(old, True), "after": side(new, True)}
        if include_values: row["id"] = deepcopy((old or new)[0][id_field])
        rows.append(row)
        # Presence is structural: absent is never a guessed state or a string sentinel.
        pair = _encode([["absent"] if entry is None else ["present", _typed(entry[0][state_field])]
                        for entry in (old, new)])
        if pair not in transitions:
            transitions[pair] = {"before": side(old, False), "after": side(new, False), "records": 0}
        transitions[pair]["records"] += 1
    counts["union_records"] = len(rows)
    result = {"schema": "keyed-snapshot-report/v1", "status": "COMPARISON_BUILT", "counts": counts,
              "transitions": [transitions[key] for key in sorted(transitions)], "records": rows,
              "limits": limits,
              "contract": {"ordering": "typed ID encoding bytes; positions are union ordinals, not input row numbers",
                           "encoding": "local v1 typed JSON scalars; exact Unicode; float hex; no normalization",
                           "denominator": "each union ID exactly once; retained+removed=before; retained+added=after",
                           "values_included": include_values, "input_mutated": False,
                           "anonymization_proved": False, "business_approval_proved": False}}
    _bounded_report(result, limits)
    return result


def _selected(root, relative, maximum, seen, bindings, role):
    path = audit_io.input_path(root, relative)
    if PurePosixPath(relative).as_posix() != relative or relative == ".":
        raise ValueError("Noncanonical selected path")
    before = path.lstat()
    identity = (before.st_dev, before.st_ino)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or identity in seen:
        raise ValueError("Selected files must be distinct regular files without links")
    raw = audit_io.read_bytes(root, relative, maximum)
    after = path.lstat()
    stamp = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
                          item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if stamp(before) != stamp(after): raise ValueError("Selected file changed")
    seen.add(identity)
    bindings.append({"role": role, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return raw


def _json(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=audit_io._unique_object,
                      parse_constant=audit_io._invalid_constant)


def audit(root, manifest_path, policy_path, include_values=False):
    root = audit_io.input_root(root); seen, bindings = set(), []
    manifest = _json(_selected(root, manifest_path, MAX_CONTROL_BYTES, seen, bindings, "manifest"))
    policy = _json(_selected(root, policy_path, MAX_CONTROL_BYTES, seen, bindings, "policy"))
    if (type(manifest) is not dict or set(manifest) != {"schema", "before", "after"}
            or manifest["schema"] != "keyed-snapshot-manifest/v1"):
        raise ValueError("Invalid snapshot manifest")
    limits = validate_policy(policy)[0]
    before = _json(_selected(root, manifest["before"], limits["max_input_bytes"], seen, bindings, "before"))
    after = _json(_selected(root, manifest["after"], limits["max_input_bytes"], seen, bindings, "after"))
    result = compare(before, after, policy, include_values); result["inputs"] = bindings
    _bounded_report(result, limits)
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid command arguments")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--include-values", action="store_true")
    try:
        args = parser.parse_args(argv)
        root = audit_io.input_root(args.root); target = audit_io.output_path(root, args.json)
        result = audit(root, args.manifest, args.policy, args.include_values)
        audit_io.emit_report(result, target, root)
        return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError, OverflowError, UnicodeError):
        print(json.dumps({"schema": "keyed-snapshot-report/v1", "status": "ERROR",
                          "errors": [{"code": "CONFIG_INPUT_OR_OUTPUT_ERROR"}]}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
