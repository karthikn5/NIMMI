"""Tools about email (the Email section, mail_plan.md): how sending is going, the business's own domains, who each
assistant's emails come from (undoable), addresses that aren't emailed, history and bulk email."""
from auth import get_owned_bot
from agent.registry import MANAGERS, Change, ToolError, adapter, tool
from agent.screens import AREAS


@tool("email_overview", "Email over the last 30 days: sent, delivered, bounced, reported as spam, failed, queued; "
      "which automatic emails are on; their own sending domains; how many addresses aren't emailed; recent problems.",
      "Checking email", roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/overview",))
async def email_overview(tc, db):
    from mail.api import overview
    o = await overview(ctx=tc.ctx, db=db)
    return {"server": o["server"], "last_30_days": o["last_30_days"], "automations": o["automations"],
            "domains": o["domains"], "addresses_not_emailed": o["stopped"], "spam_report_rate": o["complaint_rate"],
            "problems": [{k: p.get(k) for k in ("to", "subject", "label", "status", "error", "event", "event_detail")}
                         for p in o["problems"]]}


@tool("email_domains", "Their own sending domains: status (waiting for DNS records, verified...), the DNS records to "
      "add at their DNS provider, and how many bulk emails a new domain may send today.", "Checking sending domains",
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/domains",))
async def email_domains(tc, db):
    from mail.api import list_domains
    return await list_domains(ctx=tc.ctx, db=db)


@tool("email_senders", "Who customer emails come from: the workspace's default and each assistant's own (From name, "
      "address, where replies go), what each actually sends as now, and the domains they can send from.",
      "Checking email senders", roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/senders",))
async def email_senders(tc, db):
    from mail.api import list_senders
    return await list_senders(ctx=tc.ctx, db=db)


@tool("email_stopped_addresses", "Addresses this workspace doesn't email, and why: unsubscribed, reported spam, "
      "bounced, or stopped by the team. Optional search.", "Checking stopped addresses",
      {"type": "object", "properties": {"search": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/suppressions",))
async def email_stopped_addresses(tc, db, search=""):
    from mail.api import list_suppressions
    found = await list_suppressions(q=search or "", ctx=tc.ctx, db=db)
    return {"total": found["total"], "by_reason": found["counts"],
            "addresses": [{k: r[k] for k in ("email", "text", "created_at")} for r in found["items"][:30]]}


@tool("email_history", "Emails sent to customers (automatic and bulk), newest first: to, subject, status, and what "
      "happened after sending (delivered, bounced, reported as spam). Filter by status or search; or one email's full "
      "text by its id.", "Reading email history",
      {"type": "object", "properties": {
          "status": {"type": "string", "enum": ["", "queued", "sent", "failed", "cancelled"]},
          "search": {"type": "string"}, "email_id": {"type": "string", "description": "One email's id, for its text."}}},
      roles=MANAGERS, screens=AREAS["email"],
      routes=("GET /api/integrations/email/history", "GET /api/integrations/email/jobs/{job_id}"))
async def email_history(tc, db, status="", search="", email_id=None):
    from routers.email_center import history, job_detail
    if email_id:
        return await job_detail(email_id, ctx=tc.ctx, db=db)
    h = await history(status=status or "", q=search or "", limit=30, ctx=tc.ctx, db=db)
    keep = ("id", "to", "subject", "label", "step", "status", "error", "event", "event_detail", "send_at", "sent_at")
    return {"counts": h["counts"], "total": h["total"], "emails": [{k: e.get(k) for k in keep} for e in h["items"]]}


@tool("email_bulk_sends", "Their bulk emails: subject, who they went to, when, and how many were sent, failed or are "
      "still waiting.", "Checking bulk emails", roles=MANAGERS, screens=AREAS["email"],
      routes=("GET /api/integrations/email/broadcasts",))
async def email_bulk_sends(tc, db):
    from routers.email_center import list_broadcasts
    return await list_broadcasts(ctx=tc.ctx, db=db)


@tool("email_audience", "How many people a bulk email would reach: leads who shared an email in chat or on calls "
      "(source all / chat / calls), in the last N days (0 = any time), optionally only hot leads; unsubscribed, "
      "bounced and throwaway addresses are left out. Sends nothing.", "Counting who a bulk email would reach",
      {"type": "object", "properties": {"source": {"type": "string", "enum": ["all", "chat", "calls"]},
                                        "days": {"type": "integer"}, "hot_only": {"type": "boolean"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("POST /api/integrations/email/audience",))
async def email_audience(tc, db, source="all", days=90, hot_only=False):
    from routers.email_center import AudienceIn, audience
    try:
        found = await audience(AudienceIn(source=source or "all", days=int(days), hot_only=bool(hot_only)), ctx=tc.ctx, db=db)
    except ValueError as e:
        raise ToolError(str(e))
    return {"people": found["count"], "left_out_as_unsubscribed": found["unsubscribed"], "limit": found["limit"]}


# ─── Who an assistant's emails come from (undoable) ─────────────────

SENDER_KEYS = ("from_name", "local_part", "domain_id", "reply_to")


async def _read_sender(ctx, db, entity: str, keys: list) -> dict:
    from mail.api import list_senders
    s = await list_senders(ctx=ctx, db=db)
    row = s["default"] if entity == "default" else next((a for a in s["assistants"] if a["bot_id"] == entity), None)
    if row is None:
        raise ToolError("Assistant not found.")
    return {k: row[k] for k in SENDER_KEYS}


async def _write_sender(ctx, db, entity: str, values: dict) -> None:
    from mail.api import SenderIn, save_sender
    current = await _read_sender(ctx, db, entity, list(SENDER_KEYS))
    await save_sender(entity, SenderIn(**{**current, **values}), ctx=ctx, db=db)


adapter("email_sender", _read_sender, _write_sender, lambda entity: {"kind": "email_sender", "id": entity})


@tool("set_email_sender", "Change who customer emails come from: the From name, the part before the @ and the domain "
      "(one of their verified domains from email_senders; '' = Nimmi's sending address), and where replies go. "
      "assistant_id 'default' sets the workspace's own, which every assistant uses for what it leaves empty.",
      "Changing who emails come from",
      {"type": "object", "required": ["assistant_id"], "properties": {
          "assistant_id": {"type": "string"}, "from_name": {"type": "string"}, "local_part": {"type": "string"},
          "domain_id": {"type": "string"}, "reply_to": {"type": "string"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/senders/{bot_id}",))
async def set_email_sender(tc, db, assistant_id, from_name=None, local_part=None, domain_id=None, reply_to=None):
    entity = "default" if assistant_id == "default" else (await get_owned_bot(assistant_id, tc.ctx, db)).bot_id
    changes = {k: v.strip() for k, v in (("from_name", from_name), ("local_part", local_part), ("domain_id", domain_id),
                                         ("reply_to", reply_to)) if v is not None}
    if not changes:
        raise ToolError("Say what to change: the From name, the address or where replies go.")
    before = await _read_sender(tc.ctx, db, entity, list(changes))
    from fastapi import HTTPException
    try:
        await _write_sender(tc.ctx, db, entity, changes)
    except HTTPException as e:
        raise ToolError(str(e.detail))
    after = await _read_sender(tc.ctx, db, entity, list(changes))
    from mail.api import list_senders
    s = await list_senders(ctx=tc.ctx, db=db)
    row = s["default"] if entity == "default" else next(a for a in s["assistants"] if a["bot_id"] == entity)
    sends = row["sends_as"]
    return Change(f"Emails {'by default' if entity == 'default' else 'from ' + row['bot_name']} now come from "
                  f"{sends['name']} <{sends['address']}>" + (f", replies to {sends['reply_to']}" if sends["reply_to"] else ""),
                  "email_sender", entity, {k: before[k] for k in changes}, {k: after[k] for k in changes},
                  {"kind": "email_sender", "id": entity})
