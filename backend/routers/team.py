"""
Team workspaces for agencies: an owner invites people as admins (manage
assistants, voice and integrations) or agents (live chat and calls only).
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, get_ctx, require_owner
from database import get_db
from backend.models import TeamMember, User
from notify.email import send_invite_email

router = APIRouter(prefix="/api/team", tags=["team"])


def _member_json(m: TeamMember, name: str = "") -> dict:
    return {"id": m.id, "email": m.email, "name": name, "role": m.role, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None}


@router.get("/workspaces")
async def workspaces(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Workspaces the signed-in person can switch between: their own plus any they joined."""
    me = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    rows = (await db.execute(
        select(TeamMember, User).join(User, User.id == TeamMember.owner_id)
        .where(TeamMember.member_id == ctx.user_id, TeamMember.status == "active")
    )).all()
    own = {"owner_id": ctx.user_id, "name": "My workspace", "owner_name": me.name if me else "", "role": "owner"}
    return [own] + [{"owner_id": owner.id, "name": f"{owner.name or owner.email}'s workspace", "owner_name": owner.name or "",
                     "role": m.role} for m, owner in rows]


@router.get("/members")
async def list_members(ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(TeamMember, User.name).outerjoin(User, User.id == TeamMember.member_id)
        .where(TeamMember.owner_id == ctx.owner_id).order_by(TeamMember.created_at)
    )).all()
    return [_member_json(m, name or "") for m, name in rows]


class InviteRequest(BaseModel):
    email: str
    role: str = "agent"


@router.post("/invite")
async def invite(req: InviteRequest, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    if "@" not in email or req.role not in ("admin", "agent"):
        raise HTTPException(status_code=400, detail="Enter an email and choose Admin or Agent")
    owner = (await db.execute(select(User).where(User.id == ctx.owner_id))).scalars().first()
    if owner and owner.email.lower() == email:
        raise HTTPException(status_code=400, detail="That's your own email")
    existing = (await db.execute(select(TeamMember).where(TeamMember.owner_id == ctx.owner_id,
                                                          func.lower(TeamMember.email) == email))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="This person is already on your team")
    count = (await db.execute(select(func.count()).select_from(TeamMember).where(TeamMember.owner_id == ctx.owner_id))).scalar_one()
    if count >= 25:
        raise HTTPException(status_code=400, detail="Teams can have up to 25 people")
    await plans.require_seat(db, ctx.owner_id)  # Starter 1 seat, Growth 3, Pro 5 (the owner's included)

    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    token = secrets.token_urlsafe(24)
    member = TeamMember(owner_id=ctx.owner_id, email=email, role=req.role, invite_token=token,
                        member_id=None, status="invited")
    db.add(member)
    await db.commit()
    sent = await send_invite_email(email, (owner.name or owner.email) if owner else "A teammate",
                                   f"{owner.name or 'their'} workspace" if owner else "a workspace", token)
    data = _member_json(member, user.name if user else "")
    data["email_sent"] = sent
    data["invite_link_path"] = f"/auth/invite?token={token}"
    return data


class AcceptRequest(BaseModel):
    token: str


@router.post("/accept")
async def accept(req: AcceptRequest, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    member = (await db.execute(select(TeamMember).where(TeamMember.invite_token == req.token))).scalars().first()
    if not member:
        raise HTTPException(status_code=404, detail="This invite has expired or was already used")
    me = (await db.execute(select(User).where(User.id == ctx.user_id))).scalars().first()
    if not me or me.email.lower() != member.email.lower():
        raise HTTPException(status_code=403, detail=f"This invite is for {member.email}. Sign in with that email to accept.")
    member.member_id, member.status, member.invite_token = me.id, "active", None
    await db.commit()
    return {"owner_id": member.owner_id, "role": member.role}


class RoleUpdate(BaseModel):
    role: str


@router.patch("/members/{member_id}")
async def change_role(member_id: str, req: RoleUpdate, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    if req.role not in ("admin", "agent"):
        raise HTTPException(status_code=400, detail="Role must be Admin or Agent")
    member = (await db.execute(select(TeamMember).where(TeamMember.id == member_id, TeamMember.owner_id == ctx.owner_id))).scalars().first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = req.role
    await db.commit()
    return _member_json(member)


@router.delete("/members/{member_id}")
async def remove_member(member_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Owners remove anyone; members can remove themselves (leave a workspace)."""
    member = (await db.execute(select(TeamMember).where(TeamMember.id == member_id))).scalars().first()
    if not member or (member.owner_id != ctx.user_id and member.member_id != ctx.user_id):
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(member)
    await db.commit()
    return {"status": "removed"}
