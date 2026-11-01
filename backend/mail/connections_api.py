"""
Email > Settings > Mailboxes and calendars (/api/email/connections): someone connects their own Gmail or Outlook (mail/mailbox.py). The provider sends them back to the dashboard's
page, which finishes it here with their sign-in: so a link someone else started can't attach their mailbox to another workspace.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import AuthContext, rate_limit, require_manager
from backend.models import MailConnection, TeamMember, User
from database import get_db
from mail import mailbox
from notify.events import fire_and_forget
import plans

router = APIRouter(prefix="/api/email/connections", tags=["email"])


async def _people(db: AsyncSession, owner_id: str) -> dict:
    ids = {owner_id} | set((await db.execute(select(TeamMember.member_id).where(TeamMember.owner_id == owner_id, TeamMember.member_id.isnot(None)))).scalars().all())
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).all())


def _json(row: MailConnection, ctx: AuthContext, names: dict) -> dict:
    return {"id": row.id, "provider": row.provider, "address": row.address, "name": row.name, "person": names.get(row.person_id), "mine": row.person_id == ctx.user_id,
            "can_send": mailbox.can(row, "mail"), "has_calendar": mailbox.can(row, "calendar"), "status": row.status, "error": row.error,
            "sent_today": row.sent_today if row.sent_day == mailbox.date.today().isoformat() else 0}


@router.get("")
async def connections(ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(MailConnection).where(MailConnection.user_id == ctx.owner_id).order_by(MailConnection.created_at))).scalars().all()
    names = await _people(db, ctx.owner_id)
    return {"available": mailbox.available(), "daily_limit": mailbox.daily_limit(), "items": [_json(r, ctx, names) for r in rows]}


class StartIn(BaseModel):
    purpose: str = Field(..., max_length=10)


@router.post("/{provider}/start")
async def start(provider: str, data: StartIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    if provider not in mailbox.PROVIDERS or data.purpose not in mailbox.PURPOSES:
        raise HTTPException(status_code=400, detail="Choose Google or Microsoft, for email or a calendar")
    if not mailbox.available()[provider]:
        raise HTTPException(status_code=409, detail="This connection isn't set up on Nimmi yet")
    await plans.require_workspace_feature(db, ctx.owner_id, "email_alerts" if data.purpose == "mail" else "schedule")
    rate_limit(f"mailbox-start:{ctx.user_id}", 10, 3600)
    return {"url": mailbox.start_url(provider, data.purpose, ctx.owner_id, ctx.user_id)}


class FinishIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=4000)
    state: str = Field(..., min_length=1, max_length=2000)


@router.post("/finish")
async def finish(data: FinishIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    from voice import calendars
    state = mailbox.read_state(data.state)
    if state is None or state["owner"] != ctx.owner_id or state["person"] != ctx.user_id:
        raise HTTPException(status_code=403, detail="This connection was started from another account, or too long ago. Start it again from this page.")
    await db.commit()  # the provider answers next: no connection waits on it
    try:
        row = await mailbox.finish(state["provider"], state["purpose"], data.code, ctx.owner_id, ctx.user_id)
    except mailbox.MailboxError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if mailbox.can(row, "calendar"):
        fire_and_forget(calendars.refresh(row.id))
    return _json(row, ctx, await _people(db, ctx.owner_id))


@router.delete("/{connection_id}")
async def remove(connection_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(MailConnection).where(MailConnection.id == connection_id, MailConnection.user_id == ctx.owner_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.commit()
    await mailbox.disconnect(connection_id)
    return {"ok": True}
