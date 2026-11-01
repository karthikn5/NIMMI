"""
A meeting's emails, from the assistant's "meeting" design (mail/designs.py): what's happening, when and where, and the buttons that
make sense for it: join, change, cancel, or book another time after a meeting they missed. The text comes from voice/meetings.py,
which also writes it for WhatsApp.
"""
from typing import Optional

from backend.models import Bot, Meeting
from mail import compose, links, render, setup, threads

ACTIVE_NOTES = ("confirmed", "day_before", "link")


async def made(db, meeting: Meeting, what: str, text: str, subject: str, settings: dict, sender) -> tuple[render.Rendered, Optional[str]]:
    """(the email, where replies go)."""
    from voice import meetings
    bot = await db.get(Bot, meeting.bot_id)
    design = await setup.design_for(db, meeting.user_id, meeting.bot_id, "meeting", "en")
    where = meetings.place(meeting, settings)
    actions: dict = {}
    if what in ACTIVE_NOTES:
        actions.update(change=links.meeting_url(meeting.id, "change"), cancel=links.meeting_url(meeting.id, "cancel"))
        if meeting.kind == "online" and where and what != "day_before":
            actions["join"] = where
    elif what in ("missed", "cancelled") and meeting.email and settings["meetings"]["enabled"]:
        actions["book"] = links.book_url(meeting.user_id, meeting.bot_id, meeting.email)
    values = {"meeting_text": text, "meeting_subject": subject, "name": meeting.name, "first_name": compose._first_name(meeting.name), "business": sender.name,
              "signature": sender.name, "actions": actions,
              "meeting": {"when": meetings._when_for_people(meeting, settings), "where": where} if what in ACTIVE_NOTES else {}}
    rendered = render.email(design, values, render.brand_of(bot.visual_config if bot else None, sender.name))
    reply_to = sender.reply_to
    if threads.enabled() and meeting.email:
        thread = await threads.thread_for(db, meeting.user_id, meeting.bot_id, meeting.email, meeting.name, subject)
        reply_to = threads.address(thread)
    return rendered, reply_to
