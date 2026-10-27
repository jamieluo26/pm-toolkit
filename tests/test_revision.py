"""Public CLI regressions for preparing a caller's own two-version review."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


class RevisionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pm-revision-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.before = json.loads((ROOT / "examples/lifecycle/before.json").read_bytes())
        self.source = self.write("before.json", self.before)
        self.edited = deepcopy(self.before)
        self.edited["brief"]["goal"] = "全新合成修订目标，尚未实际测量。"
        self.edited["brief"]["problem"] = "需要更直接地找到给定记录。"
        self.edited["prototype"]["layout"] = "toolbar"
        self.draft = self.write("edit.json", self.edited)

    def write(self, name, value):
        target = self.root / name
        target.write_bytes(raw(value))
        return target

    def cli(self, action, **args):
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONPATH="")
        argv = [sys.executable, "-B", str(ROOT / "pm_task.py"), action]
        for key, value in args.items():
            argv += ["--" + key, str(value)]
        proc = subprocess.run(argv, cwd=self.root, env=env, capture_output=True, timeout=30)
        self.assertEqual(proc.stderr, b"")
        return proc.returncode, json.loads(proc.stdout)

    def prepare(self, name="prepared", **extra):
        dest = self.root / name
        args = dict(before=self.source, after=self.draft, version="3.0", output=dest)
        args.update(extra)
        return self.cli("prepare-review", **args), dest

    def filled_notes(self, dest):
        notes = json.loads((dest / "review-notes.json").read_bytes())
        paths = json.loads((dest / "changed-paths.json").read_bytes())["paths"]
        notes["items"] = [{"id": "change_toolbar", "text": "让给定记录筛选更直接。",
            "source": "合成评审记录A", "status": "adopted", "rationale": "给定目标与界面一起调整。", "paths": paths},
            {"id": "reject_cloud", "text": "增加云账号。", "source": "合成评审记录B",
             "status": "declined", "rationale": "本地有限场景之外。", "paths": []}]
        return self.write("filled-notes.json", notes)

    def test_pending_draft_preserves_inputs_and_aligns_authoritative_projection(self):
        saved = (self.source.read_bytes(), self.draft.read_bytes())
        (code, report), dest = self.prepare()
        self.assertEqual((code, report["status"]), (3, "HOLD"))
        after = json.loads((dest / "after.json").read_bytes())
        self.assertEqual(after["version"], "3.0")
        self.assertEqual(after["prototype"]["version"], "3.0")
        self.assertEqual(after["parent_task_sha256"], hashlib.sha256(saved[0]).hexdigest())
        self.assertEqual(after["prototype"]["pain"], after["brief"]["problem"])
        self.assertEqual((dest / "edited-input.json").read_bytes(), saved[1])
        self.assertEqual(saved, (self.source.read_bytes(), self.draft.read_bytes()))
        notes = json.loads((dest / "review-notes.json").read_bytes())
        self.assertTrue(all(r["status"] == "pending" and not r["paths"] for r in notes["items"]))

    def test_filled_notes_bind_without_hash_edits_and_existing_review_accepts(self):
        _, draft = self.prepare()
        notes = self.filled_notes(draft)
        args = dict(before=draft / "before.json", after=draft / "after.json", version="3.0", notes=notes)
        ready = self.root / "ready"
        self.assertEqual(self.cli("prepare-review", **args, output=ready)[0], 0)
        self.assertEqual(self.cli("prepare-review-check", **args, output=ready)[0], 0)
        review = {k: ready / (k + ".json") for k in ("before", "after", "feedback", "decisions")}
        self.assertEqual(self.cli("review", **review, output=self.root / "review")[0], 0)
        feedback = (ready / "feedback.json").read_bytes()
        decisions = json.loads((ready / "decisions.json").read_bytes())
        self.assertEqual(decisions["feedback_sha256"], hashlib.sha256(feedback).hexdigest())

    def test_changed_after_or_before_rejects_old_notes_without_output(self):
        _, draft = self.prepare()
        notes = self.filled_notes(draft)
        after = json.loads((draft / "after.json").read_bytes())
        after["brief"]["goal"] = "再次修改，旧处理记录不可沿用。"
        modified = self.write("again.json", after)
        for name, before, edited in (("stale_after", self.source, modified),
             ("stale_before", self.write("different-before.json", {**self.before, "title": "其他前版"}), self.draft)):
            result, dest = self.prepare(name, before=before, after=edited, notes=notes)
            self.assertEqual(result[0], 2)
            self.assertFalse(dest.exists())

    def test_pending_conflict_and_uncovered_changes_remain_hold(self):
        _, draft = self.prepare()
        path = self.filled_notes(draft)
        notes = json.loads(path.read_bytes())
        for state in ("pending", "conflict", "declined"):
            changed = deepcopy(notes)
            changed["items"][0].update(status=state, paths=[])
            result, _ = self.prepare(state, notes=self.write(state + ".json", changed))
            self.assertEqual((result[0], result[1]["status"]), (3, "HOLD"))

    def test_placeholder_cannot_become_an_adopted_or_declined_decision(self):
        _, draft = self.prepare()
        notes = json.loads((draft / "review-notes.json").read_bytes())
        notes["items"][0]["status"] = "declined"
        result, dest = self.prepare("placeholder", notes=self.write("placeholder.json", notes))
        self.assertEqual(result[0], 2)
        self.assertFalse(dest.exists())

    def test_version_only_is_hold_foreign_parent_and_id_are_errors(self):
        result, _ = self.prepare("unchanged", after=self.source)
        self.assertEqual(result[0], 3)
        for key, value in (("id", "another_task"), ("parent_task_sha256", "f" * 64)):
            changed = deepcopy(self.edited)
            changed[key] = value
            result, dest = self.prepare(key, after=self.write(key + ".json", changed))
            self.assertEqual(result[0], 2)
            self.assertFalse(dest.exists())
        result, dest = self.prepare("same_version", version=self.before["version"])
        self.assertEqual(result[0], 2)
        self.assertFalse(dest.exists())

    def test_check_rederives_output_and_rejects_overwrite_symlink_and_null_notes(self):
        _, draft = self.prepare()
        args = dict(before=self.source, after=self.draft, version="3.0", output=draft)
        self.assertEqual(self.cli("prepare-review-check", **args)[0], 3)
        (draft / "changed-paths.json").write_text("{}")
        self.assertEqual(self.cli("prepare-review-check", **args)[0], 2)
        self.assertEqual(self.cli("prepare-review", **args)[0], 2)
        linked = self.root / "linked.json"
        linked.symlink_to(self.source)
        self.assertEqual(self.prepare("linked-output", before=linked)[0][0], 2)
        self.assertEqual(self.prepare("null-notes", notes=self.write("null.json", None))[0][0], 2)


if __name__ == "__main__":
    unittest.main()
