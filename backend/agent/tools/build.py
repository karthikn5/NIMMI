"""The tool that starts "create an agent for me" (agent/builder.py does the steps, with cards in the panel)."""
from fastapi import HTTPException

from agent.registry import MANAGERS, ToolError, tool


@tool("start_agent_builder", "Build a whole new assistant from their website (or a description of the business): it "
      "reads the site, writes the knowledge, instructions, flow and lead capture, then they pick its name and look and "
      "whether it answers phone calls, in cards in the panel. Use it when they ask to create, build or make an "
      "assistant, chatbot, bot or agent.", "Starting the assistant builder", roles=MANAGERS,
      routes=("POST /api/bots/create", "GET /api/bots/templates"))
async def start_agent_builder(tc, db):
    import plans
    from backend.models import AgentJob
    try:
        await plans.require_room_for_assistant(db, tc.ctx.owner_id)
    except HTTPException as e:
        raise ToolError(f"{e.detail} They can choose a plan on Billing, or delete an assistant they don't use.")
    job = AgentJob(owner_id=tc.ctx.owner_id, user_id=tc.ctx.user_id, thread_id=tc.thread_id, step="source",
                   status="waiting", state={})
    db.add(job)
    await db.commit()
    tc.act("card", {"kind": "source", "jobId": job.id})
    return {"started": "A card in the panel now asks for their website address (or a description of the business). "
                       "Tell them in one line to fill it in there; the builder does the rest, step by step."}
