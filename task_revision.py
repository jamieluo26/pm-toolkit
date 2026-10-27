"""Prepare one explicitly versioned review without asking callers to edit hashes."""
from copy import deepcopy

import task_core as task


def prepare_revision(before, before_raw, edited, edited_raw, version, notes=None):
    task.validate_task(before)
    task.text(version, 120)
    task.require(version != before["version"])
    task.require(type(edited) is dict and edited.get("id") == before["id"])
    after = deepcopy(edited)
    spec = after.get("prototype")
    task.require(type(spec) is dict and spec.get("schema") == before["prototype"]["schema"])
    # A copy of the previous task and an already prepared draft are both allowed.
    # An unrelated non-null parent is rejected, never silently moved to this branch.
    task.require(after.get("parent_task_sha256") in (None, before["parent_task_sha256"], task.sha(before_raw)))
    task.require(spec.get("parent_sha256") in (None, before["prototype"]["parent_sha256"], task.sha(task.encoded(before["prototype"]))))
    after["version"] = version
    after["parent_task_sha256"] = task.sha(before_raw)
    spec.update(id=after["id"], version=version,
                parent_sha256=task.sha(task.encoded(before["prototype"])),
                positioning=after["brief"]["positioning"], pain=after["brief"]["problem"],
                value=after["brief"]["value_hypothesis"])
    spec["requirements"] = [{"id": r["id"], "statement": r["statement"],
        "acceptance": [f"{c['condition']}；预期：{c['expected']}" for c in r["checks"]]}
        for r in after["requirements"]]
    task.validate_task(after)
    after_raw = task.encoded(after)
    task.require(len(after_raw) <= 2_000_000)
    before_sha, after_sha = task.sha(before_raw), task.sha(after_raw)
    created_notes = notes is None
    if notes is None:
        notes = {"schema": "pm-task-review-notes/v1", "before_task_sha256": before_sha,
            "after_task_sha256": after_sha, "items": [{"id": "feedback_1",
                "text": "待填写反馈原意", "source": "待填写反馈来源",
                "status": "pending", "rationale": "待人工处理", "paths": []}]}
    task.obj(notes, "schema before_task_sha256 after_task_sha256 items")
    task.require(notes["schema"] == "pm-task-review-notes/v1")
    # Notes are frozen to a pair. Editing content later requires fresh pending notes,
    # so an old adopted decision cannot be carried to a new revision by rebinding.
    task.require(notes["before_task_sha256"] == before_sha and notes["after_task_sha256"] == after_sha)
    task.rows(notes["items"], empty=False)
    task.unique_ids(notes["items"])
    for row in notes["items"]:
        task.obj(row, "id text source status rationale paths")
        for key in ("text", "source", "rationale"):
            task.text(row[key])
        task.require(row["status"] in ("adopted", "declined", "pending", "conflict"))
        task.flow.strings(row["paths"], empty=True)
        if row["status"] in ("adopted", "declined"):
            task.require(row["text"] != "待填写反馈原意" and row["source"] != "待填写反馈来源"
                         and row["rationale"] != "待人工处理")
    feedback = {"schema": "pm-task-feedback/v1", "before_task_sha256": before_sha,
        "items": [{k: r[k] for k in ("id", "text", "source")} for r in notes["items"]]}
    feedback_raw = task.encoded(feedback)
    decisions = {"schema": "pm-task-decisions/v1", "before_task_sha256": before_sha,
        "after_task_sha256": after_sha, "feedback_sha256": task.sha(feedback_raw),
        "items": [{"feedback_id": r["id"], **{k: r[k] for k in ("status", "rationale", "paths")}}
                  for r in notes["items"]]}
    raws = {"before.json": before_raw, "after.json": after_raw,
            "feedback.json": feedback_raw, "decisions.json": task.encoded(decisions)}
    files, report = task.review_tasks(before, after, feedback, decisions, raws)
    files["edited-input.json"] = edited_raw
    files["review-notes.json"] = task.encoded(notes)
    files["changed-paths.json"] = task.encoded({"schema": "pm-task-changed-paths/v1",
        "before_task_sha256": before_sha, "after_task_sha256": after_sha,
        "paths": report["changed_paths"], "meaning": "Literal paths; caller must assign adopted feedback explicitly."})
    files["preparation.json"] = task.encoded({"schema": "pm-task-revision-preparation/v1",
        "status": report["status"], "notes_created_pending": created_notes,
        "before_task_sha256": before_sha, "edited_input_sha256": task.sha(edited_raw),
        "after_task_sha256": after_sha, "version": version,
        "aligned_paths": task.flow.differences(edited, after),
        "meaning": "Version and task-authoritative projections prepared; no adoption, observation or approval inferred.",
        "generator": {p: task.sha((task.ROOT / p).read_bytes())
                      for p in ("task_revision.py", "task_core.py", "pm_task.py")}})
    files["START.md"] = ("# 完成自己的修订评审\n\n"
        "before.json 是准确前版；edited-input.json 保留编辑原稿；after.json 是绑定前版的新候选。"
        "工具仅同步任务版本、前版引用，以及任务权威层到 prototype 的定位/痛点/价值/需求投影；"
        "其他规则、状态、字段、范围和决定仍由你填写。同步路径见 preparation.json。\n\n"
        "1. 把 review-notes.json 复制到自己的材料目录再填写，保留本生成目录不变。"
        "对照 changed-paths.json 与前后材料，在副本的 items 中填写反馈原意、来源、"
        "处理状态和理由；可增加反馈，每项 id 唯一。\n"
        "2. 采纳项的 paths 从准确变更路径中选择，每条变更恰有一个采纳项承接；"
        "拒绝、待定和冲突项的 paths 保持空数组。不得把未确定项改为已采纳来消除 HOLD。\n"
        "3. 保持前后版和 notes 顶层绑定不变，在工具包目录运行：\n\n"
        "```sh\n.venv/bin/python pm_task.py prepare-review --before path/to/draft/before.json "
        "--after path/to/draft/after.json --version VERSION --notes path/to/filled-review-notes.json "
        "--output path/to/new-review\n```\n\n"
        "VERSION 使用本目录 preparation.json 的 version。把路径换成本目录的真实位置；输出必须是新目录。"
        "填写反馈文字后，工具会重新生成准确 feedback/decisions 绑定，无需手改哈希。"
        "若再改 after 内容，先不带 --notes 生成另一份 pending 草案，再重新核对决定；旧 notes 会被拒绝。\n\n"
        "4. 阅读新目录 REVIEW.md；只有给定差异覆盖闭合才返回 0。用新目录 after.json 生成修订原型，"
        "实际操作后按 docs/lifecycle.md 记录观察和交付。生成与声明覆盖不代表真人批准或实际验收。\n").encode()
    return files, report
