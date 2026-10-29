"""
Tools for Nimmi's own work rather than the dashboard's: keeping a task's plan current (update_plan) and bringing in
more of its tools, by group (load_tools; agent/groups.py). They act on the run (ToolContext.run), are never offered
over MCP and don't show as steps in the panel (registry `internal`).
"""
from agent import groups, plan
from agent.registry import ToolError, tool


@tool("update_plan", "Keep this request's plan current in the panel: all its steps, each with a status and a short "
      "note when it failed, was skipped or waits for them. Done only once its tool worked. Make a plan this way when a "
      "request has several parts and none was given.", "Updating the plan",
      {"type": "object", "required": ["steps"], "properties": {"steps": {"type": "array", "items": {
          "type": "object", "required": ["title", "status"], "properties": {
              "title": {"type": "string"}, "status": {"type": "string", "enum": list(plan.STATUSES)},
              "note": {"type": "string"}}}}}},
      internal=True)
async def update_plan(tc, db, steps):
    if tc.run is None:
        raise ToolError("There's no plan to keep here.")
    new = plan.clean(steps)
    if not new:
        raise ToolError("Give the steps, each with a title and a status.")
    # Done means a tool did it: in an answer where none has worked yet, a step marked done stays as it was (models were
    # seen ticking steps off without doing anything). Which tool did which step is the review's to judge (check.py).
    was = {s["title"]: s["status"] for s in tc.run.plan}
    unearned = [s for s in new if s["status"] == "done" and was.get(s["title"]) != "done"] if not tc.run.used else []
    for s in unearned:
        s["status"] = was.get(s["title"]) if was.get(s["title"]) in plan.OPEN else "pending"
    tc.run.plan = new
    await tc.run.save_plan()
    tc.act("plan", {"steps": new})
    out = {"plan": "updated in the panel", "still_open": len(plan.unfinished(new))}
    if unearned:
        out["not_done"] = (f"{', '.join(s['title'] for s in unearned)}: not marked done, because none of your tools "
                           "has done anything yet in this answer. Do it with your tools first.")
    return out


@tool("load_tools", "Bring more of your tools into this answer when the ones you have can't do it. Groups: "
      + groups.described() + ". They come with your next step.", "Getting the tools for that",
      {"type": "object", "required": ["group"], "properties": {"group": {"type": "string", "enum": list(groups.GROUPS)}}},
      internal=True)
async def load_tools(tc, db, group):
    if tc.run is None:
        raise ToolError("Open that part of the dashboard with go_to instead.")
    tc.run.groups.add(group)
    return {"loaded": group, "tools": sorted(groups.tools_of([group]))}
