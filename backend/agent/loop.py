"""
The agent answering one message: the model, the tools it asks for, their results, the model again, until it answers
without asking for more. After MAX_ROUNDS rounds of tools it must answer in words.

A run is its own task, so it carries on when the browser reloads or the connection drops; the panel picks it up
again from the saved events (events.py). A heartbeat every few seconds shows the run is alive, and reads
stop_requested, so the stop button works whichever server process the request reached.
"""
import asyncio
import logging
import time
import uuid
from contextlib import aclosing
from typing import Optional

from sqlalchemy import func, select, update

import database
from agent import prompt, providers, registry, screens
from agent.events import Stream, now
from auth import AuthContext
from backend.models import AgentMessage, AgentRun, AgentThread, User

logger = logging.getLogger(__name__)

MAX_ROUNDS = 6
RUN_SEC = 150.0
HISTORY = 40  # messages the model gets back (tool results count)
HEARTBEAT_SEC = 5.0
RESULT_PREVIEW = 300  # what the panel gets of a tool's result

_tasks: dict[str, asyncio.Task] = {}


class ShownError(Exception):
    """Something the person should read as it is (the builder couldn't read a website, a plan has no room...)."""


def start(run_id: str, work=None, limit: float = RUN_SEC) -> Stream:
    """Answer in the background (or do `work`: a builder step); returns the run's event stream (in this process)."""
    stream = Stream(run_id)
    task = asyncio.create_task(_run(run_id, stream, work or _answer, limit))
    _tasks[run_id] = task
    task.add_done_callback(lambda _: _tasks.pop(run_id, None))
    return stream


def stop_here(run_id: str) -> bool:
    """Stop a run if this process is running it."""
    task = _tasks.get(run_id)
    if task is None:
        return False
    task.cancel()
    return True


async def _heartbeat(run_id: str, task: asyncio.Task) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SEC)
        try:
            async with database.async_session() as db:
                await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(heartbeat_at=now()))
                stop = (await db.execute(select(AgentRun.stop_requested).where(AgentRun.id == run_id))).scalar()
                await db.commit()
        except Exception as e:
            logger.warning(f"Agent run {run_id}: heartbeat failed: {e}")
            continue
        if stop:
            task.cancel()
            return


def _entry(m: AgentMessage) -> dict:
    return {"role": m.role, "content": m.content or "", "tool_calls": m.tool_calls, "tool_call_id": m.tool_call_id,
            "name": m.name, "raw": m.raw}


async def _person(ctx: AuthContext) -> dict:
    async with database.async_session() as db:
        me = await db.get(User, ctx.user_id)
        owner = me if ctx.owner_id == ctx.user_id else await db.get(User, ctx.owner_id)
    workspace = "their own workspace" if ctx.owner_id == ctx.user_id else \
        f"{(owner.name or owner.email) if owner else 'a team'}'s workspace, as a team member"
    return {"name": (me.name or "").strip() if me else "", "role": ctx.role, "workspace": workspace}


class _Totals:
    def __init__(self):
        self.models: list[str] = []
        self.usage: list = []
        self.tokens_in = self.tokens_out = self.rounds = 0
        self.first_output_ms: Optional[int] = None


async def _run(run_id: str, stream: Stream, work, limit: float) -> None:
    started = time.monotonic()
    me = asyncio.current_task()
    beat = asyncio.create_task(_heartbeat(run_id, me))
    totals = _Totals()
    state, error, message = "done", None, None
    try:
        await asyncio.wait_for(work(run_id, stream, totals, started), limit)
    except asyncio.CancelledError:
        state = "stopped"
        me.uncancel()  # stopped on purpose: the steps below (saving the end) must still run
    except TimeoutError:
        state, error, message = "failed", "took too long", "That took too long, so I stopped. Please try again."
    except ShownError as e:
        state, error, message = "failed", str(e), str(e)
    except providers.ModelError as e:
        state, error = "failed", str(e)
        message = ("The AI service is busy right now (too many requests for its current plan). Please try again in a minute."
                   if e.busy else "I couldn't get an answer from the AI service just now. Please try again in a minute.")
    except Exception as e:
        logger.exception(f"Agent run {run_id} failed")
        state, error, message = "failed", f"{type(e).__name__}: {e}", "Something went wrong on our side. Please try again."
    finally:
        beat.cancel()
    try:
        if state == "failed":
            await stream.emit("RUN_ERROR", message=message, code="failed")
        else:
            async with database.async_session() as db:
                thread_id = (await db.execute(select(AgentRun.thread_id).where(AgentRun.id == run_id))).scalar()
            await stream.emit("RUN_FINISHED", threadId=thread_id, runId=run_id,
                              outcome="stopped" if state == "stopped" else "success")
        async with database.async_session() as db:
            await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(
                state=state, error=(error or "")[:2000] or None, finished_at=now(), rounds=totals.rounds,
                models=",".join(dict.fromkeys(totals.models)) or None, tokens_in=totals.tokens_in,
                tokens_out=totals.tokens_out, first_output_ms=totals.first_output_ms,
                cost_inr=providers.cost_inr(totals.usage) if totals.usage else None))
            await db.commit()
    except Exception as e:
        logger.error(f"Agent run {run_id}: couldn't record the end ({state}): {e}")
    finally:
        await stream.close()
    logger.info(f"Agent run {run_id} {state} in {time.monotonic() - started:.1f}s: {totals.rounds} round(s), "
                f"models {','.join(dict.fromkeys(totals.models)) or '-'}, tokens {totals.tokens_in}/{totals.tokens_out}, "
                f"first output {totals.first_output_ms} ms")


async def _save(thread_id: str, run_id: str, entries: list[dict]) -> None:
    async with database.async_session() as db:
        seq = (await db.execute(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == thread_id))).scalar() or 0
        for entry in entries:
            seq += 1
            db.add(AgentMessage(thread_id=thread_id, run_id=run_id, seq=seq, role=entry["role"],
                                content=entry.get("content") or None, tool_calls=entry.get("tool_calls") or None,
                                tool_call_id=entry.get("tool_call_id"), name=entry.get("name"), raw=entry.get("raw")))
        await db.execute(update(AgentThread).where(AgentThread.id == thread_id).values(updated_at=now()))
        await db.commit()


async def _answer(run_id: str, stream: Stream, totals: _Totals, started: float) -> None:
    async with database.async_session() as db:
        run = await db.get(AgentRun, run_id)
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.thread_id == run.thread_id)
                                 .order_by(AgentMessage.seq.desc()).limit(HISTORY * 2))).scalars().all()[::-1]
    ctx = AuthContext(user_id=run.user_id, owner_id=run.owner_id, role=run.role)
    history = [_entry(m) for m in rows]
    screen = next((m.screen for m in reversed(rows) if m.role == "user"), None) or {}
    tc = registry.ToolContext(ctx=ctx, run_id=run_id, thread_id=run.thread_id, screen=screen)
    person = await _person(ctx)
    tools = registry.specs(registry.available(ctx.role, screen.get("id")), screen.get("id"))
    context = prompt.context(person, screen, now())
    await stream.emit("RUN_STARTED", threadId=run.thread_id, runId=run_id)

    def first_output() -> None:
        if totals.first_output_ms is None:
            totals.first_output_ms = int((time.monotonic() - started) * 1000)

    for round_no in range(MAX_ROUNDS + 1):
        totals.rounds = round_no + 1
        message_id = str(uuid.uuid4())
        pieces: list[str] = []
        calls: list[providers.ToolCall] = []
        opened = False
        try:
            async with aclosing(providers.stream(prompt.SYSTEM, context, providers.trim(history, HISTORY), tools,
                                                 force_answer=round_no == MAX_ROUNDS)) as answer:
                async for item in answer:
                    if isinstance(item, providers.Text):
                        if not opened:
                            first_output()
                            await stream.emit("TEXT_MESSAGE_START", messageId=message_id, role="assistant")
                            opened = True
                        pieces.append(item.text)
                        await stream.emit("TEXT_MESSAGE_CONTENT", messageId=message_id, delta=item.text)
                    elif isinstance(item, providers.ToolCall):
                        first_output()
                        calls.append(item)
                    elif isinstance(item, providers.Usage):
                        totals.usage.append(item)
                        totals.models.append(item.model)
                        totals.tokens_in += item.tokens_in
                        totals.tokens_out += item.tokens_out
        except asyncio.CancelledError:
            if pieces:  # stopped part way: keep what they already saw
                await _save(run.thread_id, run_id, [{"role": "assistant", "content": "".join(pieces).strip()}])
            raise
        finally:
            if opened:
                await stream.emit("TEXT_MESSAGE_END", messageId=message_id)
        content = "".join(pieces).strip()
        entry = {"role": "assistant", "content": content,
                 "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls] or None,
                 "raw": next((c.raw for c in calls if c.raw), None)}
        results, cards = [], []
        for call in calls:
            await stream.emit("TOOL_CALL_START", toolCallId=call.id, toolCallName=call.name, parentMessageId=message_id,
                              label=registry.label(call.name))
            await stream.emit("TOOL_CALL_END", toolCallId=call.id)
            tc.tool_call_id = call.id
            outcome = await registry.run(tc, call.name, call.arguments)
            results.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": outcome.text})
            await stream.emit("TOOL_CALL_RESULT", messageId=str(uuid.uuid4()), toolCallId=call.id, role="tool",
                              content=outcome.text[:RESULT_PREVIEW], ok=outcome.ok,
                              **({"actionId": outcome.action_id, "undoable": outcome.undoable} if outcome.action_id else {}))
            if outcome.proposed:
                await stream.emit("CUSTOM", name="confirm", value={**outcome.proposed, "toolCallId": call.id})
            for action in tc.actions:
                await stream.emit("CUSTOM", name=action["name"], value=action["value"])
                if action["name"] == "card":
                    cards.append(action["value"])
                if action["name"] == "navigate":  # the page it opened is the screen now: its notes and tools come next
                    screen = tc.screen = screens.screen_for_path(action["value"]["path"])
                    tools = registry.specs(registry.available(ctx.role, screen.get("id")), screen.get("id"))
                    context = prompt.context(person, screen, now())
            tc.actions.clear()
        if content or calls:
            await _save(run.thread_id, run_id, [entry, *results])
        if cards:  # after the round that showed them, so the chat reads in order
            from agent.builder import card_message
            await _save(run.thread_id, run_id, [card_message(c) for c in cards])
        history += [entry, *results]
        if not calls:
            return
