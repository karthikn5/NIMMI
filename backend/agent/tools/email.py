"""Tools about email (the Email section, mail_plan.md): how sending is going, the business's own domains, who each
assistant's emails come from (undoable), addresses that aren't emailed, history and bulk email, each assistant's emails
and their designs (undoable), and the AI's after-call emails waiting for the team (changes undoable; sending and
discarding one need the person's Confirm)."""
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


# ─── An assistant's emails: which are on, and how each looks (undoable) ─────

@tool("assistant_emails", "One assistant's customer emails: the automatic ones (after a chat, after a call...) with their "
      "follow-ups, the AI after-call email's mode per direction, the other emails' switches, and which designs it saved.",
      "Checking an assistant's emails", {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/setup/{bot_id}",))
async def assistant_emails(tc, db, assistant_id):
    from mail.api import get_setup
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    s = await get_setup(bot.bot_id, ctx=tc.ctx, db=db)
    return {"assistant": s["bot_name"], "automations": {k: {"on": a["enabled"], "emails": len(a["steps"])} for k, a in s["automations"].items()},
            "settings": s["settings"], "designs_saved": {k["kind"]: k["saved"] for k in s["kinds"]}}


async def _read_setup(ctx, db, entity: str, keys: list) -> dict:
    from mail.api import get_setup
    s = await get_setup(entity, ctx=ctx, db=db)
    return {k: (s["automations"] if k.startswith("automations.") else s["settings"]).get(k.split(".", 1)[1]) for k in keys}


async def _write_setup(ctx, db, entity: str, values: dict) -> None:
    from mail.api import SetupIn, save_setup
    autos = {k.split(".", 1)[1]: v for k, v in values.items() if k.startswith("automations.") and v is not None}
    sets = {k.split(".", 1)[1]: v for k, v in values.items() if k.startswith("settings.") and v is not None}
    await save_setup(entity, SetupIn(automations=autos or None, settings=sets or None), ctx=ctx, db=db)


adapter("email_setup", _read_setup, _write_setup, lambda entity: {"kind": "email_setup", "id": entity})


@tool("set_assistant_emails", "Turn one of an assistant's emails on or off or change it: an automation (chat_lead after a "
      "chat, call_lead, goal_met, call_missed, handoff_done) with its emails (delay now/1h/1d/2d/3d/5d/7d/14d, subject, body), "
      "or a setting: after_call {inbound, outbound: off/review/auto}, welcome {ai_note, ai_files, max_files}.",
      "Changing an assistant's emails",
      {"type": "object", "required": ["assistant_id"], "properties": {
          "assistant_id": {"type": "string"},
          "automation": {"type": "string", "enum": ["chat_lead", "call_lead", "goal_met", "call_missed", "handoff_done"]},
          "enabled": {"type": "boolean"},
          "steps": {"type": "array", "items": {"type": "object", "properties": {
              "delay": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
          "setting": {"type": "string", "enum": ["after_call", "welcome"]},
          "values": {"type": "object"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/setup/{bot_id}",))
async def set_assistant_emails(tc, db, assistant_id, automation=None, enabled=None, steps=None, setting=None, values=None):
    from fastapi import HTTPException
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    change: dict = {}
    if automation:
        current = (await _read_setup(tc.ctx, db, bot.bot_id, [f"automations.{automation}"]))[f"automations.{automation}"]
        change[f"automations.{automation}"] = {"enabled": current["enabled"] if enabled is None else bool(enabled),
                                               "steps": steps or current["steps"]}
    if setting:
        change[f"settings.{setting}"] = dict(values or {})
    if not change:
        raise ToolError("Say which email to change: an automation, or a setting.")
    before = await _read_setup(tc.ctx, db, bot.bot_id, list(change))
    try:
        await _write_setup(tc.ctx, db, bot.bot_id, change)
    except HTTPException as e:
        raise ToolError(str(e.detail))
    after = await _read_setup(tc.ctx, db, bot.bot_id, list(change))
    what = ", ".join(k.split(".", 1)[1] for k in change)
    return Change(f"{bot.bot_name}'s emails changed: {what}", "email_setup", bot.bot_id, before, after,
                  {"kind": "email_setup", "id": bot.bot_id})


@tool("email_design", "How one of an assistant's emails looks: its subject and blocks (text, ai_note, files, buttons, "
      "signature...), in a language (en, ta, hi), and whether the business saved it or it's the ready-made one. Kinds: "
      "welcome, after_call.", "Reading an email's design",
      {"type": "object", "required": ["assistant_id", "kind"], "properties": {
          "assistant_id": {"type": "string"}, "kind": {"type": "string"}, "language": {"type": "string", "enum": ["en", "ta", "hi"]}}},
      roles=MANAGERS, screens=AREAS["email"],
      routes=("GET /api/email/designs/{bot_id}/{kind}", "POST /api/email/designs/{bot_id}/{kind}/preview"))
async def email_design(tc, db, assistant_id, kind, language="en"):
    from mail.api import DesignIn, get_design, preview_design
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    d = await get_design(bot.bot_id, kind, language=language, ctx=tc.ctx, db=db)
    shown = await preview_design(bot.bot_id, kind, DesignIn(language=d["language"], subject=d["subject"], blocks=d["blocks"]), ctx=tc.ctx, db=db)
    return {**d, "preview_text": shown["text"][:1500], "from": shown["from"]}


async def _read_design(ctx, db, entity: str, keys: list) -> dict:
    from mail.api import get_design
    bot_id, kind, language = entity.split(":")
    d = await get_design(bot_id, kind, language=language, ctx=ctx, db=db)
    return {"subject": d["subject"], "blocks": d["blocks"], "saved": d["saved"] and d["language"] == language}


async def _write_design(ctx, db, entity: str, values: dict) -> None:
    from mail.api import DesignIn, reset_design, save_design
    bot_id, kind, language = entity.split(":")
    if values.get("saved") is False:
        await reset_design(bot_id, kind, language=language, ctx=ctx, db=db)
    else:
        await save_design(bot_id, kind, DesignIn(language=language, subject=values["subject"], blocks=values["blocks"]), ctx=ctx, db=db)


adapter("email_design", _read_design, _write_design, lambda entity: {"kind": "email_design", "id": entity.split(":")[0]})


@tool("set_email_design", "Change how one of an assistant's emails looks in a language: its subject and blocks (text with "
      "{{placeholders|fallback}}, heading, ai_note {guidance}, files, button {label, action book/call/whatsapp/link/join/change/"
      "cancel, url}, details, signature, divider, image {url}), or reset it to the ready-made design. Read it with "
      "email_design first and send the whole list of blocks.", "Changing an email's design",
      {"type": "object", "required": ["assistant_id", "kind"], "properties": {
          "assistant_id": {"type": "string"}, "kind": {"type": "string"}, "language": {"type": "string", "enum": ["en", "ta", "hi"]},
          "subject": {"type": "string"}, "blocks": {"type": "array", "items": {"type": "object"}}, "reset": {"type": "boolean"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"],
      routes=("PUT /api/email/designs/{bot_id}/{kind}", "DELETE /api/email/designs/{bot_id}/{kind}"))
async def set_email_design(tc, db, assistant_id, kind, language="en", subject=None, blocks=None, reset=False):
    from fastapi import HTTPException
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    entity = f"{bot.bot_id}:{kind}:{language}"
    before = await _read_design(tc.ctx, db, entity, ["subject", "blocks", "saved"])
    values = {"saved": False} if reset else {"subject": subject or before["subject"], "blocks": blocks or before["blocks"], "saved": True}
    try:
        await _write_design(tc.ctx, db, entity, values)
    except HTTPException as e:
        raise ToolError(str(e.detail))
    after = await _read_design(tc.ctx, db, entity, ["subject", "blocks", "saved"])
    return Change(f"{bot.bot_name}'s {kind.replace('_', ' ')} email {'reset to the ready-made design' if reset else 'changed'}",
                  "email_design", entity, before, after, {"kind": "email_design", "id": bot.bot_id})


# ─── The AI's after-call emails waiting for the team ────────────────

@tool("email_drafts", "The AI's after-call emails waiting for the team (Email > Drafts): who each is to, what it says, why "
      "one was held for a person, and any offer to send them automatically. With draft_id, one draft in full. Sends nothing.",
      "Reading email drafts", {"type": "object", "properties": {"draft_id": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/drafts", "GET /api/email/drafts/{job_id}"))
async def email_drafts(tc, db, draft_id=None):
    from mail.api import get_draft, list_drafts
    if draft_id:
        return {k: v for k, v in (await get_draft(draft_id, ctx=tc.ctx, db=db)).items() if k != "html"}
    found = await list_drafts(limit=30, ctx=tc.ctx, db=db)
    keep = ("id", "to", "name", "bot_name", "direction", "state", "note", "created_at", "recap", "next_step")
    return {"total": found["total"], "offers": found["suggest"], "drafts": [{k: d[k] for k in keep} for d in found["items"]]}


DRAFT_KEYS = ("to", "subject", "recap", "answers", "next_step", "file_ids")


async def _read_draft(ctx, db, entity: str, keys: list) -> dict:
    from mail.api import get_draft
    d = await get_draft(entity, ctx=ctx, db=db)
    return {k: d[k] for k in keys}


async def _write_draft(ctx, db, entity: str, values: dict) -> None:
    from mail.api import DraftIn, save_draft
    current = await _read_draft(ctx, db, entity, list(DRAFT_KEYS))
    await save_draft(entity, DraftIn(**{**current, **values}), ctx=ctx, db=db)


adapter("email_draft", _read_draft, _write_draft, lambda entity: {"kind": "email_draft", "id": entity})


@tool("edit_email_draft", "Change an after-call email waiting in Drafts: who it goes to, its subject (empty keeps the "
      "design's), the recap points, the answers [{q, a}], the next step, the files (ids from email_drafts with draft_id). "
      "Say only what changes. It stays a draft until someone sends it.", "Changing an email draft",
      {"type": "object", "required": ["draft_id"], "properties": {
          "draft_id": {"type": "string"}, "to": {"type": "string"}, "subject": {"type": "string"},
          "recap": {"type": "array", "items": {"type": "string"}},
          "answers": {"type": "array", "items": {"type": "object", "properties": {"q": {"type": "string"}, "a": {"type": "string"}}}},
          "next_step": {"type": "string"}, "file_ids": {"type": "array", "items": {"type": "string"}}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/drafts/{job_id}",))
async def edit_email_draft(tc, db, draft_id, to=None, subject=None, recap=None, answers=None, next_step=None, file_ids=None):
    from fastapi import HTTPException
    changes = {k: v for k, v in (("to", to), ("subject", subject), ("recap", recap), ("answers", answers),
                                 ("next_step", next_step), ("file_ids", file_ids)) if v is not None}
    if not changes:
        raise ToolError("Say what to change in the draft.")
    try:
        before = await _read_draft(tc.ctx, db, draft_id, list(changes))
        await _write_draft(tc.ctx, db, draft_id, changes)
        after = await _read_draft(tc.ctx, db, draft_id, list(changes))
    except HTTPException as e:
        raise ToolError(str(e.detail))
    return Change(f"Draft to {after.get('to') or before.get('to') or 'them'} changed: {', '.join(changes)}", "email_draft", draft_id,
                  before, after, {"kind": "email_draft", "id": draft_id})


async def _preview_send(tc, db, draft_id):
    from mail.api import get_draft
    d = await get_draft(draft_id, ctx=tc.ctx, db=db)
    if d["state"] == "writing":
        raise ToolError("The AI is still writing this email.")
    return {"title": f"Send this email to {d['to']}", "summary": f"Send \"{d['shown_subject']}\" to {d['to']}:\n\n{d['text'][:900]}"}


@tool("send_email_draft", "Send an after-call email waiting in Drafts to the customer. The person confirms in the panel "
      "first; once sent it can't be taken back.", "Preparing to send an email",
      {"type": "object", "required": ["draft_id"], "properties": {"draft_id": {"type": "string"}}},
      level="confirm", roles=MANAGERS, preview=_preview_send, screens=AREAS["email"], routes=("POST /api/email/drafts/{job_id}/send",))
async def send_email_draft(tc, db, draft_id):
    from mail.api import get_draft, send_draft
    to = (await get_draft(draft_id, ctx=tc.ctx, db=db))["to"]
    await send_draft(draft_id, ctx=tc.ctx, db=db)
    return {"message": f"The email to {to} is on its way.", "refresh": {"kind": "email_draft", "id": draft_id}}


async def _preview_discard(tc, db, draft_id):
    from mail.api import get_draft
    d = await get_draft(draft_id, ctx=tc.ctx, db=db)
    return {"title": f"Discard the email to {d['to']}", "summary": f"Discard the after-call email to {d['to']}. It won't be sent."}


@tool("discard_email_draft", "Discard an after-call email waiting in Drafts: it isn't sent. The person confirms in the panel first.",
      "Preparing to discard an email", {"type": "object", "required": ["draft_id"], "properties": {"draft_id": {"type": "string"}}},
      level="confirm", roles=MANAGERS, preview=_preview_discard, screens=AREAS["email"], routes=("POST /api/email/drafts/{job_id}/discard",))
async def discard_email_draft(tc, db, draft_id):
    from mail.api import discard_draft, get_draft
    to = (await get_draft(draft_id, ctx=tc.ctx, db=db))["to"]
    await discard_draft(draft_id, ctx=tc.ctx, db=db)
    return {"message": f"Discarded the email to {to}.", "refresh": {"kind": "email_draft", "id": draft_id}}
