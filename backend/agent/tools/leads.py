"""Tools about leads (the Leads section, instagram_plan.md): what needs attention, finding a lead, one lead's story, how leads are going. They reach what the person may reach: an agent only their own."""
from agent.registry import ToolError, tool
from agent.screens import AREAS
from auth import get_owned_bot


async def _assistant(tc, db, assistant_id: str) -> str:
    return (await get_owned_bot(assistant_id, tc.ctx, db)).bot_id if assistant_id else ""


@tool("leads_attention", "What needs attention now across leads: overdue tasks, tasks due today, new leads nobody looks after, leads with no next step, people who asked for a person, meetings to approve.",
      "Checking what needs attention", {"type": "object", "properties": {"assistant_id": {"type": "string"}}}, screens=AREAS["leads"], routes=("GET /api/crm/queues",))
async def leads_attention(tc, db, assistant_id=""):
    from leads.api import queues
    return await queues(bot_id=await _assistant(tc, db, assistant_id), ctx=tc.ctx, db=db)


@tool("find_leads", "Find leads by name, number or email, or by stage (new, contacted, interested, meeting, customer, lost), source or owner. Owner: me, nobody, or a person's id. "
      "Returns up to 25, with each one's next task and where it came from (an ad, a campaign, the website's tags). Junk is left out, unless junk is true: then only the leads the "
      "junk filter marked (a number nobody has, a throwaway email), and how many there are.",
      "Finding leads", {"type": "object", "properties": {"search": {"type": "string"}, "stage": {"type": "string"}, "source": {"type": "string"}, "owner": {"type": "string"},
                                                         "assistant_id": {"type": "string"}, "junk": {"type": "boolean"}}},
      screens=AREAS["leads"], routes=("GET /api/crm/leads",))
async def find_leads(tc, db, search="", stage="", source="", owner="", assistant_id="", junk=False):
    from leads.api import list_leads
    found = await list_leads(q=search, stage=stage, owner=owner, source=source, bot_id=await _assistant(tc, db, assistant_id), quality="junk" if junk else "", limit=25, ctx=tc.ctx, db=db)
    return {"total": found["total"], "junk": found["junk"], "leads": found["items"], "team": found["team"]}


@tool("lead_details", "One lead's whole story: who they are, who looks after them, open tasks, outcomes, days left in the 7-day enquiry window, whether calls, WhatsApp and email may reach them by themselves and why not (reach), what they said about being contacted (permissions), and everything that happened (forms, calls, emails, meetings, notes).",
      "Reading a lead", {"type": "object", "required": ["lead_id"], "properties": {"lead_id": {"type": "string"}}}, screens=AREAS["leads"], routes=("GET /api/crm/leads/{contact_id}",))
async def lead_details(tc, db, lead_id):
    from fastapi import HTTPException
    from leads.api import one_lead
    try:
        lead = await one_lead(lead_id, ctx=tc.ctx, db=db)
    except HTTPException:
        raise ToolError("There's no such lead here")
    return {k: v for k, v in lead.items() if k not in ("team", "stages", "lost_reasons", "results", "kinds", "e164")}


@tool("leads_report", "How leads did over the last days: leads, reached, won and lost by source, value won, how fast people were first tried, each person's tasks, why leads were lost.",
      "Reading the leads report", {"type": "object", "properties": {"days": {"type": "integer"}, "assistant_id": {"type": "string"}}}, screens=AREAS["leads"], routes=("GET /api/crm/reports",))
async def leads_report(tc, db, days=30, assistant_id=""):
    from leads.api import reports
    return await reports(days=days, bot_id=await _assistant(tc, db, assistant_id), ctx=tc.ctx, db=db)
