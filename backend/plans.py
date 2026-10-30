"""
What a workspace may use on its plan.

Free (no assistant on an active plan): one assistant and one website, a nimmi subdomain, smaller
uploads, and phone calls paid with voice credits (10 free to start, then packs: voice/catalog.py).
Custom domains need a paid plan. A workspace is paid while any of its assistants has an active plan
(plans are bought per assistant, see subscriptions.py).

What each plan includes (BILLING_PLAN.md, the website's lists made real): `Includes` per assistant,
by its plan (Starter, Growth, Pro; the earlier 1/6/12 Month plans get everything until they end), and
the most any of a workspace's assistants has for what's shared (team seats, integrations, business
hours). Phone calls work on every plan with call credits.

Limits apply to new things only: a workspace that made more assistants before these limits keeps
them, it just can't add another until it upgrades.
"""
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx
from database import async_session, get_db
from backend.models import AiReplyUsage, Bot, Site, Subscription, TeamMember

logger = logging.getLogger(__name__)

MB = 1024 * 1024


def enforced() -> bool:
    """Off only in the test suite (ENFORCE_PLAN_LIMITS=false), where most tests aren't about plans."""
    return os.getenv("ENFORCE_PLAN_LIMITS", "true").lower() != "false"


@dataclass(frozen=True)
class Limits:
    paid: bool
    assistants: Optional[int]   # None: no limit
    sites: int
    custom_domains: bool
    voice: bool
    integrations: bool
    deploy_bytes: int           # one deployment, all files together
    deploy_files: int
    file_bytes: int             # one file
    deploys_kept: int           # older deployments are removed (their files too)


FREE = Limits(paid=False, assistants=1, sites=1, custom_domains=False, voice=True, integrations=False,
              deploy_bytes=25 * MB, deploy_files=1000, file_bytes=10 * MB, deploys_kept=5)
PAID = Limits(paid=True, assistants=None, sites=10, custom_domains=True, voice=True, integrations=True,
              deploy_bytes=100 * MB, deploy_files=5000, file_bytes=25 * MB, deploys_kept=20)

FEATURE_NAMES = {"voice": "Voice calls", "integrations": "Integrations", "custom_domains": "Custom domains"}


async def is_paid(db: AsyncSession, owner_id: str) -> bool:
    """Paid while an active plan covers one of the workspace's assistants, or one it paid for itself (one set to
    start later doesn't count yet)."""
    from subscriptions import naive
    now = datetime.utcnow()
    spans = (await db.execute(select(Subscription.start_date, Subscription.end_date).outerjoin(Bot, Bot.bot_id == Subscription.bot_id).where(
        or_(Bot.user_id == owner_id, Subscription.user_id == owner_id), Subscription.status == "active"))).all()
    return any(end and naive(end) > now and (start is None or naive(start) <= now) for start, end in spans)


async def limits(db: AsyncSession, owner_id: str) -> Limits:
    return PAID if (await is_paid(db, owner_id) or not enforced()) else FREE


def upgrade_error(what: str) -> HTTPException:
    """402 with a message the dashboard shows as is, next to a "Choose a plan" button."""
    return HTTPException(status_code=402, detail=what)


async def require(db: AsyncSession, owner_id: str, feature: str) -> None:
    """Refuse a paid feature (voice, integrations, custom_domains) on the free plan."""
    if not getattr(await limits(db, owner_id), feature):
        raise upgrade_error(f"{FEATURE_NAMES[feature]} come with a paid plan. Choose a plan for one of your assistants to turn them on.")


async def assistants_used(db: AsyncSession, owner_id: str) -> int:
    return (await db.execute(select(func.count()).select_from(Bot).where(Bot.user_id == owner_id))).scalar_one()


async def sites_used(db: AsyncSession, owner_id: str) -> int:
    return (await db.execute(select(func.count()).select_from(Site).where(
        Site.user_id == owner_id, Site.deleted_at.is_(None)))).scalar_one()


async def require_room_for_assistant(db: AsyncSession, owner_id: str) -> None:
    lim = await limits(db, owner_id)
    if lim.assistants is not None and await assistants_used(db, owner_id) >= lim.assistants:
        raise upgrade_error("The free plan includes one assistant. Choose a plan for your assistant to add more.")


async def require_room_for_site(db: AsyncSession, owner_id: str) -> None:
    lim = await limits(db, owner_id)
    if await sites_used(db, owner_id) >= lim.sites:
        raise upgrade_error("The free plan includes one website. Choose a plan for one of your assistants to publish more."
                            if not lim.paid else f"You can publish up to {lim.sites} websites. Delete one to add another.")


# ─── what each plan includes ──────────────────────────────────────
@dataclass(frozen=True)
class Includes:
    tier: Optional[str]            # starter, growth, pro; "earlier": a 1/6/12 Month plan (everything); None: no plan
    replies: Optional[int]         # AI replies a month (website chat and WhatsApp); None: no limit
    seats: int                     # people in the workspace, the owner included
    call_credits: int = 0          # call credits included each month
    whatsapp: bool = False
    live_chat: bool = False        # "Talk to a person", and chats handed to the team
    email_alerts: bool = False     # lead and call alerts to the team, follow-up emails to customers
    schedule: bool = False         # call-backs, follow-ups and meeting calls; the widget's call-back offer
    campaigns: bool = False
    integrations: bool = False     # webhooks, LeadSquared, Google Sheets
    business_hours: bool = False
    transfers: bool = False        # warm transfers, and picking up calls in the dashboard


_ALL = dict(whatsapp=True, live_chat=True, email_alerts=True, schedule=True, campaigns=True, integrations=True,
            business_hours=True, transfers=True)
NO_PLAN = Includes(None, None, 1)  # build and test: the assistant answers customers only on a plan
STARTER = Includes("starter", 2000, 1)
GROWTH = Includes("growth", 10000, 3, whatsapp=True, live_chat=True, email_alerts=True)
PRO = Includes("pro", 25000, 5, 300, **_ALL)
EARLIER = Includes("earlier", None, 5, **_ALL)
BY_TIER = {"starter": STARTER, "growth": GROWTH, "pro": PRO}
_RANK = {None: 0, "starter": 1, "growth": 2, "pro": 3, "earlier": 3}
# What each feature is called, and the plan it starts on.
NEEDS = {"whatsapp": ("WhatsApp comes", "Growth"), "live_chat": ("Live chat comes", "Growth"),
         "email_alerts": ("Email alerts and follow-ups come", "Growth"), "schedule": ("Call-backs and follow-up calls come", "Pro"),
         "campaigns": ("Campaigns come", "Pro"), "integrations": ("Webhooks, LeadSquared and Google Sheets come", "Pro"),
         "business_hours": ("Business hours come", "Pro"), "transfers": ("Transfers to your team come", "Pro")}


def includes_of(sub: Optional[Subscription]) -> Includes:
    if sub is None:
        return NO_PLAN
    return BY_TIER.get(sub.tier, EARLIER)


async def includes(db: AsyncSession, bot_id: Optional[str]) -> Includes:
    """What an assistant's plan includes now (everything when limits are off, as in most tests)."""
    if not enforced():
        return EARLIER
    if not bot_id:
        return NO_PLAN
    from subscriptions import active_subscription
    return includes_of(await active_subscription(bot_id, db))


async def workspace_includes(db: AsyncSession, owner_id: str) -> Includes:
    """The most any of the workspace's assistants has: for what they share (seats, integrations, business hours).
    One query: calls look this up while the caller waits."""
    if not enforced():
        return EARLIER
    from subscriptions import naive
    now = datetime.utcnow()
    spans = (await db.execute(select(Subscription.tier, Subscription.start_date, Subscription.end_date)
                              .join(Bot, Bot.bot_id == Subscription.bot_id)
                              .where(Bot.user_id == owner_id, Subscription.status == "active"))).all()
    best = NO_PLAN
    for tier, start, end in spans:
        if naive(end) > now and (start is None or naive(start) <= now):
            got = BY_TIER.get(tier, EARLIER)
            if _RANK[got.tier] > _RANK[best.tier]:
                best = got
    return best


def plan_needed(feature: str, assistant: Optional[str] = None) -> HTTPException:
    what, tier = NEEDS[feature]
    return upgrade_error(f"{what} with the {tier} plan. Choose it for {assistant or 'one of your assistants'} on the Billing page.")


async def require_feature(db: AsyncSession, bot_id: str, feature: str) -> None:
    """Refuse something an assistant's plan doesn't include (402, worded for the dashboard)."""
    if not getattr(await includes(db, bot_id), feature):
        bot = await db.get(Bot, bot_id)
        raise plan_needed(feature, bot.bot_name if bot else None)


async def require_workspace_feature(db: AsyncSession, owner_id: str, feature: str) -> None:
    if not getattr(await workspace_includes(db, owner_id), feature):
        raise plan_needed(feature)


# ─── team seats ───────────────────────────────────────────────────
async def seats_used(db: AsyncSession, owner_id: str) -> int:
    """The owner and everyone invited (joined or not yet)."""
    return 1 + (await db.execute(select(func.count()).select_from(TeamMember).where(TeamMember.owner_id == owner_id))).scalar_one()


async def require_seat(db: AsyncSession, owner_id: str) -> None:
    seats = (await workspace_includes(db, owner_id)).seats
    if await seats_used(db, owner_id) >= seats:
        more = ("Growth includes 3 and Pro 5: choose one for an assistant on the Billing page." if seats < 3 else
                "Pro includes 5: choose it for an assistant on the Billing page." if seats < 5 else
                "For more, write to support.nimmi@gmail.com.")
        raise upgrade_error(f"Your plan includes {seats} team seat{'s' if seats != 1 else ''}, yours included. {more}")


# ─── AI replies a month ───────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))
REPLIES_USED_UP = "Thanks for your message. Our team will get back to you soon."


def this_month() -> str:
    return datetime.now(IST).strftime("%Y-%m")


async def replies_used(db: AsyncSession, bot_id: str, month: Optional[str] = None) -> int:
    return (await db.execute(select(AiReplyUsage.replies).where(
        AiReplyUsage.bot_id == bot_id, AiReplyUsage.month == (month or this_month())))).scalar() or 0


async def can_reply(db: AsyncSession, bot_id: str) -> bool:
    """Whether the assistant has AI replies left this month (its plan's allowance; the month is India time)."""
    allowed = (await includes(db, bot_id)).replies
    return allowed is None or await replies_used(db, bot_id) < allowed


async def count_reply(bot_id: str) -> None:
    """One AI reply (website chat or WhatsApp), and the owner told at 80% and when they're used up. Never raises."""
    try:
        month = this_month()
        async with async_session() as db:
            done = await db.execute(update(AiReplyUsage).where(AiReplyUsage.bot_id == bot_id, AiReplyUsage.month == month)
                                    .values(replies=AiReplyUsage.replies + 1).execution_options(synchronize_session=False))
            if not done.rowcount:
                db.add(AiReplyUsage(bot_id=bot_id, month=month, replies=1))
            try:
                await db.commit()
            except IntegrityError:  # its first reply of the month, twice at once
                await db.rollback()
                await db.execute(update(AiReplyUsage).where(AiReplyUsage.bot_id == bot_id, AiReplyUsage.month == month)
                                 .values(replies=AiReplyUsage.replies + 1).execution_options(synchronize_session=False))
                await db.commit()
            used, allowed = await replies_used(db, bot_id, month), (await includes(db, bot_id)).replies
        if allowed:
            for share, kind in ((0.8, "replies_80"), (1.0, "replies_used_up")):
                mark = int(allowed * share)
                if mark <= used < mark + 20:  # near the mark (each email goes once)
                    await _tell_replies(bot_id, month, kind, used, allowed)
    except Exception as e:
        logger.warning(f"Counting an AI reply for {bot_id} failed: {e}")


async def _tell_replies(bot_id: str, month: str, kind: str, used: int, allowed: int) -> None:
    from backend.models import User
    from notify import email
    from notify.events import _once
    async with async_session() as db:
        bot = await db.get(Bot, bot_id)
        owner = await db.get(User, bot.user_id) if bot else None
    if bot is None or owner is None or not owner.email:
        return
    link = f"{email.dashboard_url()}/dashboard/billing?bot={bot_id}"
    first = (datetime.strptime(month, "%Y-%m").replace(day=28) + timedelta(days=4)).replace(day=1)
    if kind == "replies_80":
        subject = f"{bot.bot_name} has used 80% of its AI replies this month"
        text = (f"{bot.bot_name} has written {used:,} of the {allowed:,} AI replies its plan includes this month. When they're "
                f"used up, it stops answering with AI until {first:%-d %B}. A bigger plan raises the limit at once:\n{link}")
    else:
        subject = f"{bot.bot_name} has used all its AI replies this month"
        text = (f"{bot.bot_name} has written all {allowed:,} AI replies its plan includes this month, so it tells customers your "
                f"team will get back to them. It answers again on {first:%-d %B}, or at once with a bigger plan:\n{link}")

    async def send():
        return None if await email.send_email(owner.email, subject, text) else "email not configured"
    await _once(bot.user_id, kind, f"{bot_id}@{month}", send)


router = APIRouter(prefix="/api/account", tags=["plans"])


@router.get("/limits")
async def get_limits(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The workspace's plan limits and what it uses now (the dashboard shows locks and upgrade prompts from this):
    what the workspace's best plan includes, and each assistant's plan and AI replies this month."""
    lim = await limits(db, ctx.owner_id)
    bots = (await db.execute(select(Bot.bot_id, Bot.bot_name).where(Bot.user_id == ctx.owner_id))).all()
    assistants = {}
    for bot_id, name in bots:
        got = await includes(db, bot_id)
        assistants[bot_id] = {"name": name, **asdict(got), "replies_used": await replies_used(db, bot_id)}
    return {**asdict(lim), "used": {"assistants": await assistants_used(db, ctx.owner_id),
                                    "sites": await sites_used(db, ctx.owner_id), "seats": await seats_used(db, ctx.owner_id)},
            "includes": asdict(await workspace_includes(db, ctx.owner_id)), "assistant_plans": assistants}
