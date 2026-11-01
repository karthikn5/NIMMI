"""Tools about email (the Email section, mail_plan.md): how sending is going, the business's own domains, who each
assistant's emails come from (undoable), addresses that aren't emailed, history and bulk email, each assistant's emails
and their designs (undoable), the AI's after-call emails waiting for the team, and conversations with people who replied (changes
undoable; sending and discarding need the person's Confirm)."""
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


@tool("email_bulk_sends", "One assistant's bulk emails: subject, status, who they went to, and how each did: sent, delivered, clicked, replied, unsubscribed, "
      "spam reports, bounces. How many people have agreed to offers and news, and who the emails come from.", "Checking bulk emails",
      {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}}}, roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/bulk/{bot_id}",))
async def email_bulk_sends(tc, db, assistant_id):
    from mail.broadcasts_api import bulk_page
    found = await bulk_page((await get_owned_bot(assistant_id, tc.ctx, db)).bot_id, ctx=tc.ctx, db=db)
    keep = ("id", "status", "subject", "recipients", "send_at", "finished_at", "paused_why", "winner", "counts", "rsvp")
    return {"agreed": found["agreed"], "people_with_an_email": found["with_email"], "sender": found["sender"], "can_send_today": found["room_today"], "groups": found["segments"],
            "bulk_emails": [{k: b.get(k) for k in keep} for b in found["broadcasts"]]}


@tool("email_audience", "How many people a bulk email would reach, and who it leaves out and why (no consent, stopped, throwaway). Only people who agreed to offers and news are ever "
      "included. Narrow it by statuses, stages, sources, tags, active_days, engaged_days. Sends nothing.", "Counting who a bulk email would reach",
      {"type": "object", "required": ["assistant_id"], "properties": {
          "assistant_id": {"type": "string"}, "statuses": {"type": "array", "items": {"type": "string"}}, "stages": {"type": "array", "items": {"type": "string"}},
          "sources": {"type": "array", "items": {"type": "string"}}, "tags": {"type": "array", "items": {"type": "string"}}, "active_days": {"type": "integer"}, "engaged_days": {"type": "integer"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("POST /api/email/bulk/count",))
async def email_audience(tc, db, assistant_id, **rules):
    from mail.broadcasts_api import CountIn, count_people
    found = await count_people(CountIn(bot_id=assistant_id, rules=rules), ctx=tc.ctx, db=db)
    return {"people": found["count"], "left_out": found["left_out"]}


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
      "or a setting: after_call {inbound, outbound: off/review/auto}, replies {mode: ai/draft/team}, welcome {ai_note, ai_files, max_files}, "
      "during_call/callback_booked/voicemail/chat_copy/lead_email {enabled}, missed_chat {enabled, minutes}, lead_call {enabled, minutes}, meeting {thanks, missed}.",
      "Changing an assistant's emails",
      {"type": "object", "required": ["assistant_id"], "properties": {
          "assistant_id": {"type": "string"},
          "automation": {"type": "string", "enum": ["chat_lead", "call_lead", "goal_met", "call_missed", "handoff_done"]},
          "enabled": {"type": "boolean"},
          "steps": {"type": "array", "items": {"type": "object", "properties": {
              "delay": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}},
          "setting": {"type": "string", "enum": ["after_call", "replies", "welcome", "during_call", "callback_booked", "voicemail", "missed_chat", "chat_copy", "meeting", "lead_email", "lead_call"]},
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
      "welcome, after_call, meeting, callback_booked, voicemail, missed_chat, chat_copy, during_call.", "Reading an email's design",
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


# ─── Conversations: people who replied (Email > Inbox) ──────────────

@tool("email_inbox", "Conversations with people who replied to the business's emails (Email > Inbox): who, their latest words, "
      "what the reply was (a question, wants a call...), whether the AI's draft is waiting; status open (waiting), answered or closed. "
      "With thread_id, one conversation in full. Sends nothing, and doesn't mark anything read.", "Reading the email inbox",
      {"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "answered", "closed"]}, "search": {"type": "string"},
                                        "thread_id": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/inbox", "GET /api/email/inbox/{thread_id}"))
async def email_inbox(tc, db, status="open", search="", thread_id=None):
    from mail.inbox import _own, list_threads, thread_detail
    if thread_id:
        return await thread_detail(await _own(thread_id, tc.ctx, db), tc.ctx, db)
    found = await list_threads(status=status or "open", q=search or "", ctx=tc.ctx, db=db)
    keep = ("id", "email", "name", "subject", "kind", "unread", "draft", "bot_name", "last", "last_at")
    return {"counts": found["counts"], "unread": found["unread"], "receiving": found["enabled"], "conversations": [{k: t[k] for k in keep} for t in found["items"]]}


async def _read_thread(ctx, db, entity: str, keys: list) -> dict:
    from mail.inbox import _own, thread_detail
    t = await thread_detail(await _own(entity, ctx, db), ctx, db)
    return {k: t[k] for k in keys}


async def _write_thread(ctx, db, entity: str, values: dict) -> None:
    from mail.inbox import ThreadIn, update_thread
    await update_thread(entity, ThreadIn(**values), ctx=ctx, db=db)


adapter("email_thread", _read_thread, _write_thread, lambda entity: {"kind": "email_thread", "id": entity})


@tool("update_email_conversation", "Change a conversation in Email > Inbox: its status (open, answered, closed), who looks after it "
      "(a team member's id), or the team's notes. The customer sees none of this.", "Changing a conversation",
      {"type": "object", "required": ["thread_id"], "properties": {
          "thread_id": {"type": "string"}, "status": {"type": "string", "enum": ["open", "answered", "closed"]},
          "assigned_to": {"type": "string"}, "notes": {"type": "string"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/inbox/{thread_id}",))
async def update_email_conversation(tc, db, thread_id, status=None, assigned_to=None, notes=None):
    from fastapi import HTTPException
    changes = {k: v for k, v in (("status", status), ("assigned_to", assigned_to), ("notes", notes)) if v is not None}
    if not changes:
        raise ToolError("Say what to change: the status, who looks after it, or the notes.")
    try:
        before = await _read_thread(tc.ctx, db, thread_id, list(changes))
        await _write_thread(tc.ctx, db, thread_id, changes)
        after = await _read_thread(tc.ctx, db, thread_id, list(changes))
    except HTTPException as e:
        raise ToolError(str(e.detail))
    return Change(f"Conversation changed: {', '.join(changes)}", "email_thread", thread_id, before, after, {"kind": "email_thread", "id": thread_id})


async def _preview_answer(tc, db, thread_id, text=None, draft_id=None):
    from mail.inbox import _own, thread_detail
    t = await thread_detail(await _own(thread_id, tc.ctx, db), tc.ctx, db)
    draft = next((m for m in t["messages"] if m["id"] == draft_id and m["status"] == "draft"), None)
    words = (text or (draft or {}).get("text") or "").strip()
    if not words:
        raise ToolError("Say what to send, or give the id of the AI's draft.")
    return {"title": f"Send this answer to {t['email']}", "summary": f"Send to {t['email']}:\n\n{words[:900]}"}


@tool("answer_email", "Send an answer to someone in a conversation in Email > Inbox: your text, or the AI's draft by draft_id (its "
      "booking, if it has one, is made first). The person confirms in the panel first; once sent it can't be taken back.",
      "Preparing to send an answer", {"type": "object", "required": ["thread_id"], "properties": {
          "thread_id": {"type": "string"}, "text": {"type": "string"}, "draft_id": {"type": "string"}}},
      level="confirm", roles=MANAGERS, preview=_preview_answer, screens=AREAS["email"],
      routes=("POST /api/email/inbox/{thread_id}/reply", "POST /api/email/inbox/{thread_id}/drafts/{message_id}/send"))
async def answer_email(tc, db, thread_id, text=None, draft_id=None):
    from mail.inbox import ReplyIn, _own, _own_message, send_draft, team_reply
    if draft_id:
        row = await _own_message(await _own(thread_id, tc.ctx, db), draft_id, db)
        await send_draft(thread_id, draft_id, ReplyIn(text=(text or row.text or "").strip()), ctx=tc.ctx, db=db)
    else:
        await team_reply(thread_id, ReplyIn(text=(text or "").strip()), ctx=tc.ctx, db=db)
    return {"message": "The answer has been sent.", "refresh": {"kind": "email_thread", "id": thread_id}}


async def _preview_drop(tc, db, thread_id, draft_id):
    return {"title": "Drop the AI's draft", "summary": "Drop the AI's draft in this conversation. It won't be sent."}


@tool("drop_email_draft", "Drop the AI's draft in a conversation in Email > Inbox: it isn't sent. The person confirms in the panel first.",
      "Preparing to drop a draft", {"type": "object", "required": ["thread_id", "draft_id"], "properties": {
          "thread_id": {"type": "string"}, "draft_id": {"type": "string"}}},
      level="confirm", roles=MANAGERS, preview=_preview_drop, screens=AREAS["email"], routes=("DELETE /api/email/inbox/{thread_id}/drafts/{message_id}",))
async def drop_email_draft(tc, db, thread_id, draft_id):
    from mail.inbox import drop_draft
    await drop_draft(thread_id, draft_id, ctx=tc.ctx, db=db)
    return {"message": "Dropped the draft.", "refresh": {"kind": "email_thread", "id": thread_id}}


# ─── Leads from other places (Email > Lead sources) ─────────────────

@tool("email_lead_sources", "Where one assistant's leads from other places come in: whether it's on, the address to forward IndiaMART, JustDial "
      "or property-portal emails to, Gmail's forwarding confirmation code if one came, the links for IndiaMART's Push API and website forms, "
      "and the latest leads with what became of each.", "Reading lead sources",
      {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/leads/{bot_id}",))
async def email_lead_sources(tc, db, assistant_id):
    from mail.leads_api import detail
    return await detail(db, await get_owned_bot(assistant_id, tc.ctx, db), tc.ctx, make=False)


async def _read_leads(ctx, db, entity: str, keys: list) -> dict:
    from mail.leads_api import _own_bot, detail
    return {"enabled": (await detail(db, await _own_bot(entity, ctx, db), ctx, make=False))["enabled"]}


async def _write_leads(ctx, db, entity: str, values: dict) -> None:
    from mail.leads_api import LeadsIn, set_leads
    await set_leads(entity, LeadsIn(enabled=bool(values["enabled"])), ctx=ctx, db=db)


adapter("email_leads", _read_leads, _write_leads, lambda entity: {"kind": "email_leads", "id": entity})


@tool("set_lead_sources", "Turn an assistant's lead sources on or off: leads forwarded to its address, or sent by IndiaMART or a form, become contacts and "
      "get the new-lead email.", "Changing lead sources",
      {"type": "object", "required": ["assistant_id", "on"], "properties": {"assistant_id": {"type": "string"}, "on": {"type": "boolean"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/leads/{bot_id}",))
async def set_lead_sources(tc, db, assistant_id, on):
    from fastapi import HTTPException
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    before = await _read_leads(tc.ctx, db, bot.bot_id, ["enabled"])
    try:
        await _write_leads(tc.ctx, db, bot.bot_id, {"enabled": bool(on)})
    except HTTPException as e:
        raise ToolError(str(e.detail))
    return Change(f"{bot.bot_name}'s lead sources turned {'on' if on else 'off'}", "email_leads", bot.bot_id, before, {"enabled": bool(on)},
                  {"kind": "email_leads", "id": bot.bot_id})


# ─── Journeys and lead stages ───────────────────────────────────────

@tool("email_journeys", "One assistant's journeys: what starts each, what ends it, its steps, whether it's on, how many people are on it; the ready-made ones "
      "it can start from; and, with journey_id, who's on that journey and where they are.", "Reading journeys",
      {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}, "journey_id": {"type": "string"}}},
      roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/journeys", "GET /api/email/journeys/{journey_id}/runs"))
async def email_journeys(tc, db, assistant_id, journey_id=None):
    from mail.journeys_api import journey_runs, list_journeys
    bot = await get_owned_bot(assistant_id, tc.ctx, db)
    if journey_id:
        return await journey_runs(journey_id, ctx=tc.ctx, db=db)
    return await list_journeys(bot.bot_id, ctx=tc.ctx, db=db)


async def _read_journey(ctx, db, entity: str, keys: list) -> dict:
    from mail.journeys_api import _own
    return {"enabled": bool((await _own(entity, ctx, db)).enabled)}


async def _write_journey(ctx, db, entity: str, values: dict) -> None:
    from mail.journeys_api import JourneyIn, _own, save_journey
    j = await _own(entity, ctx, db)
    await save_journey(entity, JourneyIn(name=j.name, trigger=j.trigger, trigger_value=j.trigger_value, goal=j.goal, options=j.options, steps=j.steps or [], enabled=bool(values["enabled"])), ctx=ctx, db=db)


adapter("email_journey", _read_journey, _write_journey, lambda entity: {"kind": "email_journey", "id": entity})


@tool("set_journey", "Turn one of an assistant's journeys on or off. On, it starts for each lead its trigger fires for.", "Changing a journey",
      {"type": "object", "required": ["journey_id", "on"], "properties": {"journey_id": {"type": "string"}, "on": {"type": "boolean"}}},
      level="change", roles=MANAGERS, screens=AREAS["email"])
async def set_journey(tc, db, journey_id, on):
    from fastapi import HTTPException
    try:
        before = await _read_journey(tc.ctx, db, journey_id, ["enabled"])
        await _write_journey(tc.ctx, db, journey_id, {"enabled": bool(on)})
    except HTTPException as e:
        raise ToolError(str(e.detail))
    return Change(f"Journey turned {'on' if on else 'off'}", "email_journey", journey_id, before, {"enabled": bool(on)}, {"kind": "email_journey", "id": journey_id})


@tool("lead_board", "One assistant's leads by stage (new, contacted, interested, meeting, customer, lost), with status, who looks after each, and tags.", "Reading the lead board",
      {"type": "object", "required": ["assistant_id"], "properties": {"assistant_id": {"type": "string"}}}, roles=MANAGERS, screens=AREAS["email"], routes=("GET /api/email/board/{bot_id}",))
async def lead_board(tc, db, assistant_id):
    from mail.journeys_api import board
    return await board((await get_owned_bot(assistant_id, tc.ctx, db)).bot_id, ctx=tc.ctx, db=db)


async def _read_lead(ctx, db, entity: str, keys: list) -> dict:
    from sqlalchemy.future import select
    from backend.models import Contact
    c = (await db.execute(select(Contact).where(Contact.id == entity, Contact.user_id == ctx.owner_id))).scalars().first()
    if c is None:
        raise ToolError("Lead not found.")
    found = {"stage": c.stage or "new", "assigned_to": c.assigned_to or "", "tags": c.tags or []}
    return {k: found[k] for k in keys}


async def _write_lead(ctx, db, entity: str, values: dict) -> None:
    from mail.journeys_api import LeadIn, update_lead
    await update_lead(entity, LeadIn(**values), ctx=ctx, db=db)


adapter("lead", _read_lead, _write_lead, lambda entity: {"kind": "lead", "id": entity})


@tool("update_lead", "Change a lead's stage (new, contacted, interested, meeting, customer, lost), who looks after them, or their tags.", "Changing a lead",
      {"type": "object", "required": ["lead_id"], "properties": {"lead_id": {"type": "string"}, "stage": {"type": "string"}, "assigned_to": {"type": "string"},
                                                                 "tags": {"type": "array", "items": {"type": "string"}}}},
      level="change", roles=MANAGERS, screens=AREAS["email"], routes=("PUT /api/email/board/leads/{contact_id}",))
async def update_lead_tool(tc, db, lead_id, stage=None, assigned_to=None, tags=None):
    from fastapi import HTTPException
    changes = {k: v for k, v in (("stage", stage), ("assigned_to", assigned_to), ("tags", tags)) if v is not None}
    if not changes:
        raise ToolError("Say what to change: the stage, who looks after them, or the tags.")
    try:
        before = await _read_lead(tc.ctx, db, lead_id, list(changes))
        await _write_lead(tc.ctx, db, lead_id, changes)
    except HTTPException as e:
        raise ToolError(str(e.detail))
    return Change(f"Lead changed: {', '.join(changes)}", "lead", lead_id, before, await _read_lead(tc.ctx, db, lead_id, list(changes)), {"kind": "lead", "id": lead_id})

