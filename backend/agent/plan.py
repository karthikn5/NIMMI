"""
The plan of a task with several parts: the steps Nimmi works through, shown in the panel as a checklist and kept with
the run (agent_runs.plan), so a reload shows it too. The answering model makes it and keeps it current with
update_plan (agent/tools/work.py); an answer while steps of a plan it follows are still open sends it back to them
(loop.py), and the review sets each step's status from what the tools really did (check.py).
"""
STATUSES = ("pending", "doing", "done", "failed", "skipped", "waiting")
OPEN = ("pending", "doing")
MAX_STEPS = 10


def clean(steps) -> list[dict]:
    """Steps as the panel shows them: a title, a status, and a note when one helps (why it failed, what it waits for)."""
    out = []
    for step in steps if isinstance(steps, list) else []:
        step = {"title": step} if isinstance(step, str) else step
        if not isinstance(step, dict):
            continue
        title = " ".join(str(step.get("title") or "").split())[:100]
        if not title:
            continue
        item = {"title": title, "status": step.get("status") if step.get("status") in STATUSES else "pending"}
        if note := " ".join(str(step.get("note") or "").split())[:200]:
            item["note"] = note
        out.append(item)
    return out[:MAX_STEPS]


def unfinished(steps: list[dict]) -> list[dict]:
    return [s for s in steps or [] if s["status"] in OPEN]


def text(steps: list[dict]) -> str:
    """The plan in the model's note, so every round knows where the work is."""
    if not steps:
        return ""
    lines = [f"{i}. [{s['status']}] {s['title']}" + (f" ({s['note']})" if s.get("note") else "") for i, s in enumerate(steps, 1)]
    return "<plan>\nThe plan for this request; keep it current with update_plan:\n" + "\n".join(lines) + "\n</plan>"
