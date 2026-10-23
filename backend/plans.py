"""
What a workspace may use on its plan.

Free (no assistant on an active plan): one assistant and one website, a nimmi subdomain, and
smaller uploads. Voice, integrations and custom domains need a paid plan. A workspace is paid
while any of its assistants has an active plan (plans are bought per assistant, see subscriptions.py).

Limits apply to new things only: a workspace that made more assistants before these limits keeps
them, it just can't add another until it upgrades.
"""
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, get_ctx
from database import get_db
from backend.models import Bot, Site, Subscription

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


FREE = Limits(paid=False, assistants=1, sites=1, custom_domains=False, voice=False, integrations=False,
              deploy_bytes=25 * MB, deploy_files=1000, file_bytes=10 * MB, deploys_kept=5)
PAID = Limits(paid=True, assistants=None, sites=10, custom_domains=True, voice=True, integrations=True,
              deploy_bytes=100 * MB, deploy_files=5000, file_bytes=25 * MB, deploys_kept=20)

FEATURE_NAMES = {"voice": "Voice calls", "integrations": "Integrations", "custom_domains": "Custom domains"}


async def is_paid(db: AsyncSession, owner_id: str) -> bool:
    """Paid while an active plan covers one of the workspace's assistants, or one it paid for itself."""
    now = datetime.utcnow()
    ends = (await db.execute(select(Subscription.end_date).outerjoin(Bot, Bot.bot_id == Subscription.bot_id).where(
        or_(Bot.user_id == owner_id, Subscription.user_id == owner_id), Subscription.status == "active"))).scalars().all()
    return any(end and end.replace(tzinfo=None) > now for end in ends)


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


router = APIRouter(prefix="/api/account", tags=["plans"])


@router.get("/limits")
async def get_limits(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """The workspace's plan limits and what it uses now (the dashboard shows locks and upgrade prompts from this)."""
    lim = await limits(db, ctx.owner_id)
    return {**asdict(lim), "used": {"assistants": await assistants_used(db, ctx.owner_id),
                                    "sites": await sites_used(db, ctx.owner_id)}}
