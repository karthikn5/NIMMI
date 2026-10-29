"""
The API the agent panel uses (/api/agent). Every request acts for the signed-in person in the workspace they picked;
a thread belongs to the person who wrote it, and only they can read it, follow its runs or stop them.

Sending a message starts a run in the background and answers with its events as they happen (server-sent events).
If the connection drops, GET /runs/{id}/events?after=<last seq seen> picks up where it stopped, from any process.
"""
import os
import re
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import agent.tools  # noqa: F401  (registers the tools)
from agent import events, loop, providers, registry
from agent.prompt import clean_screen
from auth import AuthContext, get_ctx, rate_limit
from backend.models import AgentAction, AgentEvent, AgentJob, AgentMessage, AgentRun, AgentThread
from database import get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Messages (and builder steps) a workspace can send in 24 hours, by its plan. Set from the measured cost (NIMMI_AGENT_PLAN.md).
DAILY_FREE = int(os.getenv("AGENT_DAILY_FREE", "20"))
DAILY_PAID = int(os.getenv("AGENT_DAILY_PAID", "200"))
MAX_TEXT = 4000


class MessageIn(BaseModel):
    text: str = Field(..., max_length=20000)
    thread_id: Optional[str] = Field(None, max_length=36)
    screen: Optional[dict] = None


def _stream(run_id: str, after: int = 0) -> StreamingResponse:
    return StreamingResponse(events.follow(run_id, after), media_type="text/event-stream", headers=events.SSE_HEADERS)


async def _own_thread(thread_id: str, ctx: AuthContext, db: AsyncSession) -> AgentThread:
    thread = await db.get(AgentThread, (thread_id or "")[:36])
    if thread is None or thread.user_id != ctx.user_id or thread.owner_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return thread


async def _own_run(run_id: str, ctx: AuthContext, db: AsyncSession) -> AgentRun:
    run = await db.get(AgentRun, (run_id or "")[:36])
    if run is None or run.user_id != ctx.user_id or run.owner_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Not found")
    return run


async def _running(thread_id: str, db: AsyncSession) -> Optional[AgentRun]:
    """The thread's run that is still answering. One whose process died is closed here."""
    run = (await db.execute(select(AgentRun).where(AgentRun.thread_id == thread_id, AgentRun.state == "running")
                            .order_by(AgentRun.started_at.desc()))).scalars().first()
    if run is not None and events.stale(run):
        run.state, run.error, run.finished_at = "failed", "interrupted: the server restarted", events.now()
        await db.commit()
        return None
    return run


async def _today(ctx: AuthContext, db: AsyncSession) -> tuple[int, int]:
    """(used in the last 24 hours, the limit) for the workspace."""
    import plans
    limit = DAILY_PAID if (await plans.limits(db, ctx.owner_id)).paid else DAILY_FREE
    since = events.now() - timedelta(hours=24)
    used = (await db.execute(select(func.count(AgentRun.id)).where(AgentRun.owner_id == ctx.owner_id,
                                                                     AgentRun.started_at > since))).scalar() or 0
    return used, limit


async def _check_today(ctx: AuthContext, db: AsyncSession) -> None:
    used, limit = await _today(ctx, db)
    if used >= limit:
        raise HTTPException(status_code=429, detail=f"Your workspace has used today's {limit} messages to Nimmi. They reset "
                                                    "within 24 hours" + (", or a paid plan has more." if limit == DAILY_FREE else "."))


@router.get("/status")
async def status(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    used, limit = await _today(ctx, db)
    return {"ready": bool(providers.models()), "daily_limit": limit, "used_today": used}


@router.post("/messages")
async def send_message(body: MessageIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write a message first")
    if len(text) > MAX_TEXT:
        raise HTTPException(status_code=400, detail=f"That message is too long (up to {MAX_TEXT} characters)")
    if not providers.models():
        raise HTTPException(status_code=503, detail="Nimmi isn't set up on this server yet (no AI service key)")
    await _check_today(ctx, db)
    if body.thread_id:
        thread = await _own_thread(body.thread_id, ctx, db)
        if await _running(thread.id, db) is not None:
            raise HTTPException(status_code=409, detail="Nimmi is still answering your last message")
    else:
        thread = AgentThread(owner_id=ctx.owner_id, user_id=ctx.user_id, title=" ".join(text.split())[:80])
        db.add(thread)
        await db.flush()
    seq = (await db.execute(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == thread.id))).scalar() or 0
    run = AgentRun(thread_id=thread.id, user_id=ctx.user_id, owner_id=ctx.owner_id, role=ctx.role)
    db.add(run)
    await db.flush()
    db.add(AgentMessage(thread_id=thread.id, run_id=run.id, seq=seq + 1, role="user", content=text,
                        screen=clean_screen(body.screen) or None))
    thread.updated_at = events.now()
    await db.commit()
    loop.start(run.id)
    return _stream(run.id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, after: int = 0, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    await _own_run(run_id, ctx, db)
    await db.close()  # the stream can last minutes; it opens its own short sessions
    return _stream(run_id, max(after, 0))


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    run = await _own_run(run_id, ctx, db)
    if run.state != "running":
        return {"stopped": False, "state": run.state}
    run.stop_requested = True
    await db.commit()
    loop.stop_here(run_id)  # at once if it runs in this process; otherwise its heartbeat sees the flag within seconds
    return {"stopped": True}


@router.get("/threads")
async def list_threads(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentThread).where(AgentThread.user_id == ctx.user_id,
                                                       AgentThread.owner_id == ctx.owner_id)
                             .order_by(AgentThread.updated_at.desc()).limit(30))).scalars().all()
    return [{"id": t.id, "title": t.title or "Chat", "updated_at": events.aware(t.updated_at).isoformat()} for t in rows]


def _action_fields(a: AgentAction) -> dict:
    return {"actionId": a.id, "undoable": a.state == "done" and bool(a.adapter), "undone": a.state == "undone"}


def _items(messages: list[AgentMessage], skip_run: Optional[str], errors: Optional[dict] = None,
           actions: Optional[dict] = None, jobs: Optional[dict] = None, plans: Optional[dict] = None) -> list[dict]:
    """The thread as the panel shows it: the person's messages, the plan of a task (`plans`: run id -> its steps), the
    agent's words and the steps it took (with Undo for changes, and the Confirm card for what waited for them; Nimmi's
    own tools, like keeping the plan, aren't steps), notes of what they did in the panel, and what went wrong on a run
    that failed (`errors`: run id -> RUN_ERROR event). The run still answering is left out (the panel replays its
    events), except for the message that started it."""
    results = {m.tool_call_id: m for m in messages if m.role == "tool"}
    errors, actions, jobs, plans = errors or {}, actions or {}, jobs or {}, plans or {}
    items: list[dict] = []
    current = None

    def close_run(run_id):
        if run_id in errors:
            items.append({"type": "error", "id": f"error-{run_id}", "text": errors[run_id].get("message") or "That didn't work."})

    for m in messages:
        if m.run_id != current:
            close_run(current)
            current = m.run_id
        if m.role == "assistant" and m.name == "card":
            card = (m.raw or {}).get("card") or {}
            job = jobs.get(card.get("jobId"))  # a card can be used while its job waits at its step
            items.append({"type": "card", "id": m.id, "card": card,
                          "active": bool(job and job.status == "waiting" and job.step == card.get("kind"))})
        elif m.role == "user" and m.name == "note":
            items.append({"type": "note", "id": m.id, "text": m.content or ""})
        elif m.role == "user":
            items.append({"type": "user", "id": m.id, "text": m.content or ""})
            if m.run_id in plans and m.run_id != skip_run:
                items.append({"type": "plan", "id": f"plan-{m.run_id}", "runId": m.run_id, "steps": plans[m.run_id]})
        elif m.role == "assistant" and m.run_id != skip_run:
            if m.content:
                items.append({"type": "text", "id": m.id, "text": m.content, "runId": m.run_id})
            for call in m.tool_calls or []:
                if (t := registry.TOOLS.get(call.get("name") or "")) is not None and t.internal:
                    continue
                result = results.get(call.get("id"))
                ok = result is not None and not (result.content or "").startswith('{"error"')
                step = {"type": "step", "id": call.get("id"), "name": call.get("name"),
                        "label": registry.label(call.get("name") or ""), "ok": ok, "runId": m.run_id}
                action = actions.get(call.get("id"))
                if action is not None and action.inputs is None:  # a change: Undo
                    step.update(_action_fields(action))
                items.append(step)
                if action is not None and action.inputs is not None:  # a confirm card
                    items.append({"type": "confirm", "id": f"confirm-{action.id}", "actionId": action.id,
                                  "title": action.title or action.tool, "summary": action.summary,
                                  "state": "proposed" if action.state == "proposed" and not _expired(action) else action.state})
    close_run(current)
    return items


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    thread = await _own_thread(thread_id, ctx, db)
    running = await _running(thread.id, db)
    messages = (await db.execute(select(AgentMessage).where(AgentMessage.thread_id == thread.id)
                                 .order_by(AgentMessage.seq))).scalars().all()
    errors = dict((await db.execute(select(AgentEvent.run_id, AgentEvent.data).join(AgentRun, AgentRun.id == AgentEvent.run_id)
                                    .where(AgentRun.thread_id == thread.id, AgentEvent.type == "RUN_ERROR"))).all())
    actions = {a.tool_call_id: a for a in (await db.execute(select(AgentAction).where(
        AgentAction.thread_id == thread.id, AgentAction.user_id == ctx.user_id))).scalars().all() if a.tool_call_id}
    jobs = {j.id: j for j in (await db.execute(select(AgentJob).where(AgentJob.thread_id == thread.id))).scalars().all()}
    plans = {run_id: steps for run_id, steps in (await db.execute(
        select(AgentRun.id, AgentRun.plan).where(AgentRun.thread_id == thread.id))).all() if steps}
    return {"id": thread.id, "title": thread.title or "Chat",
            "items": _items(list(messages), running.id if running else None, errors, actions, jobs, plans),
            "running": {"id": running.id} if running else None}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    thread = await _own_thread(thread_id, ctx, db)
    if await _running(thread.id, db) is not None:
        raise HTTPException(status_code=409, detail="Nimmi is still answering in this chat. Stop it first.")
    run_ids = select(AgentRun.id).where(AgentRun.thread_id == thread.id)
    await db.execute(delete(AgentEvent).where(AgentEvent.run_id.in_(run_ids)))
    await db.execute(delete(AgentMessage).where(AgentMessage.thread_id == thread.id))
    await db.execute(delete(AgentRun).where(AgentRun.thread_id == thread.id))
    await db.delete(thread)
    await db.commit()
    return {"deleted": True}


# ─── The panel's buttons: Confirm, Cancel, Undo; and what Nimmi changed ───

def _expired(a: AgentAction) -> bool:
    return events.aware(a.created_at) < events.now() - timedelta(minutes=registry.CONFIRM_MINUTES)


async def _note(action_id: str, text: str) -> None:
    """Tell the chat what they did in the panel, so the agent knows on their next message."""
    from database import async_session
    async with async_session() as db:
        action = await db.get(AgentAction, action_id)
        if action is None or not action.thread_id or await db.get(AgentThread, action.thread_id) is None:
            return
        seq = (await db.execute(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == action.thread_id))).scalar() or 0
        db.add(AgentMessage(thread_id=action.thread_id, seq=seq + 1, role="user", name="note", content=text))
        await db.commit()


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, ctx: AuthContext = Depends(get_ctx)):
    result = await registry.confirm_action(ctx, action_id)
    outcome = f"Done: {result['message']}" if result["state"] == "done" else f"It didn't work: {result['message']}"
    await _note(action_id, f"(In the panel they confirmed: {result['summary']} {outcome})")
    return result


@router.post("/actions/{action_id}/cancel")
async def cancel_action(action_id: str, ctx: AuthContext = Depends(get_ctx)):
    result = await registry.cancel_action(ctx, action_id)
    await _note(action_id, f"(In the panel they cancelled: {result['summary']} Nothing was done.)")
    return result


@router.post("/actions/{action_id}/undo")
async def undo_action(action_id: str, ctx: AuthContext = Depends(get_ctx)):
    result = await registry.undo_action(ctx, action_id)
    await _note(action_id, f"(In the panel they undid: {result['summary']})")
    return result


@router.post("/runs/{run_id}/undo")
async def undo_run(run_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Undo everything one answer changed (the panel's "Undo all")."""
    run = await _own_run(run_id, ctx, db)
    thread_id = run.thread_id
    await db.close()
    result = await registry.undo_run(ctx, run_id)
    if result["undone"] or result["kept"]:
        text = "; ".join(u["summary"] for u in result["undone"]) or "nothing"
        kept = "".join(f" Kept: {k['summary']} ({k['reason']})" for k in result["kept"])
        await _note_thread(thread_id, f"(In the panel they undid everything from one answer: {text}.{kept})")
    return result


@router.get("/actions")
async def list_actions(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What Nimmi changed in this workspace (owners and admins see everyone's; others their own), newest first."""
    from backend.models import User
    from sqlalchemy import and_, or_
    query = select(AgentAction, User.name, User.email).join(User, User.id == AgentAction.user_id, isouter=True).where(
        AgentAction.owner_id == ctx.owner_id,
        or_(AgentAction.state.in_(("done", "undone", "failed")),
            and_(AgentAction.state == "proposed", AgentAction.user_id == ctx.user_id,
                 AgentAction.created_at > events.now() - timedelta(minutes=registry.CONFIRM_MINUTES))))
    if ctx.role not in registry.MANAGERS:
        query = query.where(AgentAction.user_id == ctx.user_id)
    rows = (await db.execute(query.order_by(AgentAction.created_at.desc()).limit(100))).all()
    return [{"id": a.id, "summary": a.summary, "title": a.title, "tool": a.tool, "state": a.state, "by": name or email or "",
             "mine": a.user_id == ctx.user_id, "undoable": a.state == "done" and bool(a.adapter) and a.user_id == ctx.user_id,
             "at": events.aware(a.created_at).isoformat()} for a, name, email in rows]


# ─── "Create an agent for me": the cards' steps (agent/builder.py) ───

@router.post("/jobs/{job_id}/{step}")
async def job_step(job_id: str, step: str, body: dict, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    from agent import builder
    job = await db.get(AgentJob, (job_id or "")[:36])
    if job is None or job.user_id != ctx.user_id or job.owner_id != ctx.owner_id:
        raise HTTPException(status_code=404, detail="Not found")
    if step == "cancel":
        if job.status in ("done", "cancelled"):
            return {"state": job.status}
        job.status = "cancelled"
        await db.commit()
        made = (job.state or {}).get("bot_id")
        await _note_thread(job.thread_id, "(In the panel they stopped the assistant builder." +
                           (" The draft assistant it made is still on the Assistants page.)" if made else ")"))
        return {"state": "cancelled", "bot_id": made}
    if step not in builder.STEPS:
        raise HTTPException(status_code=404, detail="Not found")
    if job.status != "waiting" or job.step != step:
        raise HTTPException(status_code=409, detail="That step is already done." if job.status != "working" else "Nimmi is still working on it.")
    if job.thread_id is None or await _running(job.thread_id, db) is not None:
        raise HTTPException(status_code=409, detail="Nimmi is still answering in this chat")
    await _check_today(ctx, db)
    run = AgentRun(thread_id=job.thread_id, user_id=ctx.user_id, owner_id=ctx.owner_id, role=ctx.role)
    db.add(run)
    job.status = "working"
    await db.commit()
    loop.start(run.id, builder.work(job.id, step, {k: v for k, v in (body or {}).items() if isinstance(k, str)}), limit=builder.JOB_SEC)
    return _stream(run.id)


async def _note_thread(thread_id: Optional[str], text: str) -> None:
    from database import async_session
    if not thread_id:
        return
    async with async_session() as db:
        seq = (await db.execute(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == thread_id))).scalar() or 0
        db.add(AgentMessage(thread_id=thread_id, seq=seq + 1, role="user", name="note", content=text))
        await db.commit()


@router.get("/usage")
async def usage(days: int = 30, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """What Nimmi did and cost in this workspace (owners and admins), per day and per person."""
    from backend.models import User
    if ctx.role not in registry.MANAGERS:
        raise HTTPException(status_code=403, detail="Your role doesn't allow this")
    since = events.now() - timedelta(days=max(1, min(days, 90)))
    rows = (await db.execute(select(AgentRun, User.name, User.email).join(User, User.id == AgentRun.user_id, isouter=True)
                             .where(AgentRun.owner_id == ctx.owner_id, AgentRun.started_at > since))).all()
    by_day: dict = {}
    by_person: dict = {}
    for run, name, email in rows:
        day = events.aware(run.started_at).date().isoformat()
        for key, table in ((day, by_day), (name or email or "", by_person)):
            t = table.setdefault(key, {"messages": 0, "tokens_in": 0, "tokens_out": 0, "cost_inr": 0.0, "failed": 0})
            t["messages"] += 1
            t["tokens_in"] += run.tokens_in or 0
            t["tokens_out"] += run.tokens_out or 0
            t["cost_inr"] = round(t["cost_inr"] + (run.cost_inr or 0), 4)
            t["failed"] += run.state == "failed"
    used, limit = await _today(ctx, db)
    total = {k: sum(d[k] for d in by_day.values()) for k in ("messages", "tokens_in", "tokens_out", "failed")}
    total["cost_inr"] = round(sum(d["cost_inr"] for d in by_day.values()), 2)
    return {"days": days, "total": total, "by_day": by_day, "by_person": by_person, "today": {"used": used, "limit": limit}}


# ─── Speaking to Nimmi, hearing its answers, and rating them ────────

MAX_VOICE_BYTES = 1_000_000  # about a minute of compressed speech
SPEAK_CHARS = 1500


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), ctx: AuthContext = Depends(get_ctx)):
    """The panel's mic: a short recording to text (Sarvam, which hears Indian languages and mixes like Tanglish, and
    finds the language itself)."""
    rate_limit(f"agent-mic:{ctx.user_id}", 30, 60)
    if not (file.content_type or "").startswith("audio/"):
        raise HTTPException(status_code=400, detail="Send an audio recording")
    audio = await file.read(MAX_VOICE_BYTES + 1)
    if not audio or len(audio) > MAX_VOICE_BYTES:
        raise HTTPException(status_code=400, detail="Keep it under a minute")
    from voice import sarvam
    if not sarvam.configured():
        raise HTTPException(status_code=503, detail="Voice input isn't available right now")
    try:
        text = await sarvam.transcribe(audio, file.filename or "speech.webm", file.content_type, "unknown")
    except sarvam.SarvamError:
        raise HTTPException(status_code=502, detail="Couldn't make that out. Please try again, or type it.")
    return {"text": (text or "").strip()}


def spoken(text: str) -> str:
    """An answer as it should be read aloud: no Markdown marks, links read by their words."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()


class SpeakIn(BaseModel):
    text: str = Field(..., max_length=8000)


@router.post("/speak")
async def speak(body: SpeakIn, ctx: AuthContext = Depends(get_ctx)):
    """Read an answer aloud in Priya's voice, in the language it's written in (Sarvam)."""
    rate_limit(f"agent-speak:{ctx.user_id}", 30, 60)
    text = spoken(body.text)[:SPEAK_CHARS]
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to read")
    from voice import sarvam
    from voice.pipeline import written_language
    if not sarvam.configured():
        raise HTTPException(status_code=503, detail="Reading aloud isn't available right now")
    try:
        pcm = await sarvam.synthesize(text, written_language(text, None) or "en-IN", "priya", 1.0, 22050)
    except sarvam.SarvamError:
        raise HTTPException(status_code=502, detail="Couldn't read that aloud just now. Please try again.")
    return Response(sarvam.pcm_to_wav(pcm, 22050), media_type="audio/wav", headers={"Cache-Control": "no-store"})


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    note: str = Field("", max_length=1000)


@router.post("/runs/{run_id}/feedback")
async def feedback(run_id: str, body: FeedbackIn, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """A thumbs up or down on an answer (and why), so the answers' quality can be followed."""
    run = await _own_run(run_id, ctx, db)
    run.feedback, run.feedback_note = body.rating, body.note.strip() or None
    await db.commit()
    return {"saved": True}
