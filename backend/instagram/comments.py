"""
Comments on the account's posts and reels (instagram_plan.md, phase 6). A comment that matches a rule gets one private reply (Instagram's DM to someone
who commented: one per comment, within 7 days of it) and, if the rule has them, a public reply from a few variations. The comment starts a conversation:
when they answer the private reply, the assistant has their comment (quoted, as their words: data, never instructions), and they're a lead like any DM.

- Each comment is kept once (Meta's comment id is unique) before Meta hears "received"; then one process claims it and replies.
- The account's own comments, Nimmi's public replies coming back among them, are never answered: no reply to a reply of ours, no loop.
- Instagram allows 750 private replies an hour per account (Meta's messaging rate limits, read 3 November 2026). Each private reply takes its slot in a
  single statement under a lock on the account's row, so the four server processes never pass it; a comment over the limit waits for a slot.
- Nothing goes to anyone who didn't act first: a private reply is addressed to the comment itself, never to a person.
Meta's comment webhook has no time of its own: the time Meta sent it stands for when it was written.
"""
import hashlib
import logging
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select as sa_select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

import plans
from backend.models import InstagramAccount, InstagramChat, InstagramComment, InstagramMessage, InstagramRule, LeadDeal, Message
from database import async_session
from instagram import accounts, chats, graph, live

logger = logging.getLogger(__name__)

HOURLY = int(os.getenv("INSTAGRAM_PRIVATE_REPLIES_HOURLY", "750"))
TOO_OLD = timedelta(days=7)
STUCK = timedelta(minutes=5)
PASS_EVERY = timedelta(seconds=30)
WAIT_FOR_SLOT = timedelta(minutes=5)
_last_pass: Optional[datetime] = None


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(at: Optional[datetime]) -> Optional[datetime]:
    return at.replace(tzinfo=timezone.utc) if at is not None and at.tzinfo is None else at


def norm(value: Optional[str]) -> str:
    """For matching words in any language or script: the same letters typed different ways compare equal, and case doesn't matter."""
    return unicodedata.normalize("NFKC", value or "").casefold().strip()


def matches(rule: InstagramRule, media_id: Optional[str], said: Optional[str]) -> bool:
    if rule.media_ids and (media_id or "") not in rule.media_ids:
        return False
    words = [w for w in (norm(k) for k in rule.keywords or []) if w]
    if not words:
        return True
    found = norm(said)
    return any(w in found for w in words)  # inside the text: works for Tamil, Hindi and emoji alike, which have no word breaks Python knows


def _when(sent) -> datetime:
    try:
        value = float(sent)
    except (TypeError, ValueError):
        return now()
    return datetime.fromtimestamp(value / 1000 if value > 10 ** 11 else value, tz=timezone.utc)


def _value(entry: dict) -> list[dict]:
    """The comments in a webhook entry: Business Login for Instagram puts field and value on the entry itself; Meta's other logins use "changes"."""
    found = []
    if entry.get("field") == "comments" and isinstance(entry.get("value"), dict):
        found.append(entry["value"])
    for change in entry.get("changes") or []:
        if isinstance(change, dict) and change.get("field") == "comments" and isinstance(change.get("value"), dict):
            found.append(change["value"])
    return found


async def keep(account: InstagramAccount, value: dict, sent=None) -> Optional[str]:
    """Keep a comment once. Returns its row's id when it's new and someone else's, else None."""
    comment_id = str(value.get("id") or value.get("comment_id") or "")[:64]
    if not comment_id:
        return None
    who = value.get("from") if isinstance(value.get("from"), dict) else {}
    from_id, username = str(who.get("id") or "")[:64], str(who.get("username") or "")[:120]
    if from_id == account.ig_id or (username and account.username and username.lower() == account.username.lower()):
        return None  # the account's own comment: its replies, Nimmi's among them, are never answered
    media = value.get("media") if isinstance(value.get("media"), dict) else {}
    async with async_session() as db:
        if (await db.execute(select(InstagramComment.id).where(InstagramComment.public_reply_id == comment_id))).first():
            return None  # Nimmi's own public reply, back as a comment
        row = InstagramComment(user_id=account.user_id, account_id=account.id, comment_id=comment_id, parent_id=str(value.get("parent_id") or "")[:64] or None,
                               media_id=str(media.get("id") or "")[:64] or None, media_type=str(media.get("media_product_type") or "")[:20] or None,
                               ad_id=str(media.get("ad_id") or "")[:64] or None, ad_title=str(media.get("ad_title") or "")[:300] or None,
                               from_id=from_id or None, from_username=username or None, text=str(value.get("text") or "")[:4000], commented_at=_when(sent),
                               status="new", attempts=0)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:  # Meta sent it again, or another process kept it a moment ago
            await db.rollback()
            return None
        return row.id


async def _slot(comment_row_id: str, account_id: str, at: datetime) -> bool:
    """This comment's private reply takes one of the hour's slots, or there are none left. One statement under a lock on the account's row: on Postgres
    the lock makes processes take turns; SQLite writes one at a time anyway."""
    async with async_session() as db:
        await db.execute(sa_select(InstagramAccount.id).where(InstagramAccount.id == account_id).with_for_update())
        used = sa_select(func.count()).select_from(InstagramComment).where(
            InstagramComment.account_id == account_id, InstagramComment.private_at.isnot(None), InstagramComment.private_at >= at - timedelta(hours=1)).scalar_subquery()
        taken = await db.execute(update(InstagramComment).where(InstagramComment.id == comment_row_id, InstagramComment.private_at.is_(None), used < HOURLY)
                                 .values(private_at=at).execution_options(synchronize_session=False))
        await db.commit()
    return taken.rowcount == 1


async def _done(comment_row_id: str, **values) -> None:
    async with async_session() as db:
        await db.execute(update(InstagramComment).where(InstagramComment.id == comment_row_id).values(claimed_at=None, **values)
                         .execution_options(synchronize_session=False))
        await db.commit()


async def _rule_trouble(rule_id: str, why: str) -> None:
    async with async_session() as db:
        rule = await db.get(InstagramRule, rule_id)
        if rule is not None:
            rule.last_error, rule.last_error_at = why[:500], now()
            await db.commit()


def _variation(row: InstagramComment, variations: list[str]) -> Optional[str]:
    usable = [v.strip() for v in variations or [] if v and v.strip()]
    if not usable:
        return None
    return usable[int(hashlib.sha256(row.comment_id.encode()).hexdigest(), 16) % len(usable)]  # each comment its own, so the public replies vary


def _fill(template: str, row: InstagramComment) -> str:
    return template.replace("{{username}}", f"@{row.from_username}" if row.from_username else "").replace("  ", " ").strip()


async def process(comment_row_id: str, at: Optional[datetime] = None) -> None:
    """One kept comment: claimed by one process, matched to a rule, replied to once. Never raises."""
    at = at or now()
    try:
        await _process(comment_row_id, at)
    except Exception as e:  # noqa: BLE001  one comment's trouble never stops the others
        logger.exception(f"Instagram comment {comment_row_id} failed: {e}")
        await _done(comment_row_id, status="failed", why="Something went wrong handling this comment")


async def _process(comment_row_id: str, at: datetime) -> None:
    async with async_session() as db:
        claimed = await db.execute(update(InstagramComment).where(
            InstagramComment.id == comment_row_id, InstagramComment.status.in_(("new", "working")),
            or_(InstagramComment.claimed_at.is_(None), InstagramComment.claimed_at < at - STUCK),
            or_(InstagramComment.retry_at.is_(None), InstagramComment.retry_at <= at))
            .values(status="working", claimed_at=at, attempts=InstagramComment.attempts + 1).execution_options(synchronize_session=False))
        await db.commit()
        if claimed.rowcount != 1:
            return
        row = await db.get(InstagramComment, comment_row_id)
        account = await db.get(InstagramAccount, row.account_id)
        rules = (await db.execute(select(InstagramRule).where(InstagramRule.account_id == row.account_id, InstagramRule.enabled.is_(True))
                                  .order_by(InstagramRule.created_at))).scalars().all()
        rule = next((r for r in rules if matches(r, row.media_id, row.text)), None)
        bot = await accounts.assistant(db, account) if account is not None else None
        allowed = bool(bot) and (await plans.includes(db, bot.bot_id)).instagram
    if account is None or account.status == "disconnected" or not account.access_token:
        return await _done(comment_row_id, status="skipped", why="The account isn't connected any more")
    if rule is None:
        return await _done(comment_row_id, status="skipped", why="No rule matches it")
    if at - (_aware(row.commented_at) or at) > TOO_OLD:
        return await _done(comment_row_id, status="skipped", rule_id=rule.id, why="More than 7 days old: Instagram allows a private reply only within 7 days")
    if not allowed:
        return await _done(comment_row_id, status="skipped", rule_id=rule.id, why="Instagram replies come with the Growth plan")
    if account.status != "connected":  # the sign-in ended or was refused: it waits for "Connect again", while the 7 days last
        return await _done(comment_row_id, status="new", rule_id=rule.id, retry_at=at + timedelta(hours=1), why=account.status_detail or "Connect the account again")
    if not row.private_at and not await _slot(row.id, account.id, at):
        return await _done(comment_row_id, status="new", rule_id=rule.id, retry_at=at + WAIT_FOR_SLOT,
                           why=f"Waiting: Instagram allows {HOURLY} private replies an hour")
    said = _fill(rule.private_reply, row)
    async with async_session() as db:
        await db.execute(update(InstagramComment).where(InstagramComment.id == row.id).values(rule_id=rule.id, private_text=said)
                         .execution_options(synchronize_session=False))
        await db.commit()
    try:
        mid, igsid = await graph.private_reply(account.ig_id, account.access_token, row.comment_id, said)
    except graph.IGError as e:
        await accounts.trouble(account.id, e)
        if e.kind in ("token", "permission"):
            return await _done(row.id, status="new", retry_at=at + timedelta(hours=1), why=str(e))
        if e.kind == "busy":
            return await _done(row.id, status="new", retry_at=at + WAIT_FOR_SLOT, why=str(e))
        await _rule_trouble(rule.id, f"A private reply wasn't sent: {e}")
        return await _done(row.id, status="failed", why=str(e)[:300])
    public_id, why = None, None
    public = _variation(row, rule.public_replies or [])
    if public:
        try:
            public_id = await graph.public_reply(row.comment_id, account.access_token, _fill(public, row))
        except graph.IGError as e:
            why = f"The public reply wasn't posted: {e}"[:300]
            await _rule_trouble(rule.id, why)
    await _done(row.id, status="replied", private_mid=mid[:255] or None, igsid=igsid[:64] or None, public_reply_id=public_id or None, why=why, retry_at=None)
    if igsid:
        await _into_chat(account, row.id, igsid)


async def _into_chat(account: InstagramAccount, comment_row_id: str, igsid: str) -> None:
    """The comment and the private reply go into the person's chat, so when they answer, the assistant and the team see how it started. Their comment
    doesn't open Instagram's window: only their message does."""
    chat = await chats.find_or_create(account, igsid)
    async with async_session() as db:
        row = await db.get(InstagramComment, comment_row_id)
        chat = await db.get(InstagramChat, chat.id)
        account = await db.get(InstagramAccount, account.id)
        bot = await accounts.assistant(db, account)
        if bot is None:
            return
        conv, new = await chats.conversation(db, chat, bot)
        if not chat.username and row.from_username:
            chat.username = row.from_username
        if not conv.origin:  # what the lead page shows as where they came from: the ad, or the rule (a post's id would mean nothing to the team)
            from leads import origin as lead_origin
            rule = await db.get(InstagramRule, row.rule_id) if row.rule_id else None
            conv.origin = lead_origin.clean({"channel": "instagram_ad", "ad_id": row.ad_id, "headline": row.ad_title} if row.ad_id
                                            else {"channel": "instagram_comment", "rule": rule.name if rule else None})
        at = chats.now()
        said = Message(conversation_id=conv.conversation_id, role="user", content=f'(commented on your post: "{(row.text or "").strip()[:1000]}")', timestamp=at)
        db.add(said)
        await db.flush()
        db.add(InstagramMessage(chat_id=chat.id, message_id=said.id, mid=f"comment:{row.comment_id}"[:255], direction="in", kind="comment", sent_by="customer",
                                status="received", handled=True, created_at=at))
        answer = Message(conversation_id=conv.conversation_id, role="assistant", content=row.private_text or "", timestamp=at + timedelta(milliseconds=1))
        db.add(answer)
        await db.flush()
        if row.private_mid and not (await db.execute(select(InstagramMessage.id).where(InstagramMessage.mid == row.private_mid))).first():
            db.add(InstagramMessage(chat_id=chat.id, message_id=answer.id, mid=row.private_mid, direction="out", kind="text", sent_by="ai", status="sent",
                                    handled=True, created_at=at))
        chat.last_message_at = at
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return
    if new:
        from instagram import contacts
        await contacts.first_dm(chat.id)  # someone who commented with a rule's words is a lead, with their name
    await live.chat_changed(account.user_id, chat)


async def recent_own_send(account: InstagramAccount, mid: str, said: str) -> bool:
    """An echo of a private reply this account is sending now (its answer from Meta may come after the echo): not a reply typed in the Instagram app."""
    async with async_session() as db:
        return (await db.execute(select(InstagramComment.id).where(InstagramComment.account_id == account.id, or_(
            InstagramComment.private_mid == mid,
            and_(InstagramComment.status == "working", InstagramComment.private_text == said, InstagramComment.private_at >= now() - timedelta(minutes=2)))))).first() is not None


async def tick(at: Optional[datetime] = None) -> None:
    """Scheduler: comments waiting for a slot, a reconnection or a process that stopped."""
    global _last_pass
    at = at or now()
    if _last_pass and at - _last_pass < PASS_EVERY:
        return
    _last_pass = at
    async with async_session() as db:
        due = (await db.execute(select(InstagramComment.id).where(
            InstagramComment.status.in_(("new", "working")), or_(InstagramComment.retry_at.is_(None), InstagramComment.retry_at <= at),
            or_(InstagramComment.claimed_at.is_(None), InstagramComment.claimed_at < at - STUCK)).order_by(InstagramComment.created_at).limit(100))).scalars().all()
    for row_id in due:
        await process(row_id, at)


async def report(db, owner_id: str, account_id: Optional[str] = None) -> dict:
    """Per rule: comments it matched, private and public replies, the conversations they started, the leads and the sales from them."""
    q = select(InstagramComment).where(InstagramComment.user_id == owner_id, InstagramComment.rule_id.isnot(None))
    if account_id:
        q = q.where(InstagramComment.account_id == account_id)
    rows = (await db.execute(q)).scalars().all()
    out: dict = {}
    replied = [r for r in rows if r.status == "replied" and r.igsid]
    started: dict = {}
    if replied:
        chats_ = (await db.execute(select(InstagramChat).where(InstagramChat.user_id == owner_id, InstagramChat.igsid.in_({r.igsid for r in replied})))).scalars().all()
        by = {(c.account_id, c.igsid): c for c in chats_}
        for r in replied:
            c = by.get((r.account_id, r.igsid))
            if c is not None and c.last_inbound_at and _aware(c.last_inbound_at) > (_aware(r.private_at) or _aware(r.created_at) or now()):
                started[r.id] = c
    contacts = {c.contact_id for c in started.values() if c.contact_id}
    won = {}
    if contacts:
        for contact_id, amount in (await db.execute(select(LeadDeal.contact_id, LeadDeal.amount).where(
                LeadDeal.contact_id.in_(contacts), LeadDeal.outcome == "won", LeadDeal.reopened_at.is_(None)))).all():
            won.setdefault(contact_id, []).append(amount or 0)
    for r in rows:
        x = out.setdefault(r.rule_id, {"comments": 0, "private_replies": 0, "public_replies": 0, "conversations": 0, "leads": 0, "sales": 0, "value": 0.0})
        x["comments"] += 1
        x["private_replies"] += r.status == "replied"
        x["public_replies"] += bool(r.public_reply_id)
        c = started.get(r.id)
        if c is not None:
            x["conversations"] += 1
            if c.contact_id:
                x["leads"] += 1
                x["sales"] += len(won.get(c.contact_id, []))
                x["value"] += sum(won.get(c.contact_id, []))
    return out
