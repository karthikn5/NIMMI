"""
The agent answering one message, in layers (NIMMI_AGENT_PLAN.md, section 14):

  intake    a first look (intake.py): a question or a task, and the groups of tools it needs (groups.py)
  plan      a task with several parts is a checklist in the panel, the model's own (update_plan), kept current
  tools     the model, the tools it asks for, their results, the model again, until it answers in words. Only the
            groups it needs come, whatever page is open (more with load_tools). A call already made in this
            answer isn't made again: a change isn't done twice, a lookup answers from before, a call that failed
            isn't repeated blindly
  guard     an answer while plan steps are still open sends the model back to them (NUDGES times at most)
  check     what the tools really did is in front of the model every round (<done>); a task's answer is reviewed
            against it before the person sees it (check.py), then shown as corrected, or the work carries on
  failures  a tool's error comes back as words and its kind, so the model fixes its inputs or tries another way; a
            busy or failing model gives way to the next (providers.py); a task waits up to TASK_PATIENCE_SEC for one
            to be free (the panel says so); a task cut short says exactly what it had done and what's left

A task's words are held until they're checked, so the person reads only checked answers; a question streams as it
comes. After MAX_ROUNDS (a task: TASK_ROUNDS) rounds of tools, or TOKEN_BUDGET tokens, the model must answer.

A run is its own task, so it carries on when the browser reloads or the connection drops; the panel picks it up
again from the saved events (events.py). A heartbeat every few seconds shows the run is alive, and reads
stop_requested, so the stop button works whichever server process the request reached.
"""
import asyncio
import json
import logging
import time
import uuid
from contextlib import aclosing
from typing import Optional

from sqlalchemy import func, select, update

import database
from agent import check, groups, intake, output, plan, prompt, providers, registry, screens
from agent.events import Stream, now
from auth import AuthContext
from backend.models import AgentAction, AgentMessage, AgentRun, AgentThread, User

logger = logging.getLogger(__name__)

MAX_ROUNDS = 6
TASK_ROUNDS = 14
RUN_SEC = 300.0  # one run; each model call has its own limit too (providers.CALL_SEC)
HISTORY = 40  # earlier messages the model gets back (tool results count); this answer's own all come
OLD_RESULT_CHARS = 1500  # a tool result from an earlier answer, shortened (the model can look again)
TOKEN_BUDGET = 150_000  # tokens in, across a run's rounds
NUDGES = 2
REVIEWS = 2
TASK_PATIENCE_SEC = 60.0  # a task half done is worth a minute's wait for a model at its rate limit
HEARTBEAT_SEC = 5.0
RESULT_PREVIEW = 300  # what the panel gets of a tool's result
ASSISTANTS_SHOWN = 25

_tasks: dict[str, asyncio.Task] = {}

GUARD = ("(A note from Nimmi's own checks, not from the person.) Your plan still has open steps: {steps}. Carry on with "
         "them now with your tools. If one can't be done, mark it failed or skipped with the reason (update_plan); if "
         "you need something from the person first, mark it waiting and ask them.")
TASK = ("<task>They asked you to do something. If it takes three or more steps, or steps that depend on each other, "
        "start with update_plan (the steps, in the same step as your first lookups), then work through them.</task>")
CARRY_ON = ("(A note from Nimmi's own checks, not from the person.) Part of the request isn't done yet: {todo}. Do it "
            "now with your tools if you can. If you can't, say plainly what wasn't done and why.")


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
    content = m.content or ""
    if m.role == "tool" and len(content) > OLD_RESULT_CHARS:
        content = content[:OLD_RESULT_CHARS] + " ...(shortened: look it up again if you need it)"
    return {"role": m.role, "content": content, "tool_calls": m.tool_calls, "tool_call_id": m.tool_call_id,
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
        self.note: Optional[str] = None  # a run that ended well but not whole (cut short): why, for the record

    def add(self, *usage) -> None:
        for u in usage:
            self.usage.append(u)
            self.models.append(u.model)
            self.tokens_in += u.tokens_in
            self.tokens_out += u.tokens_out


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
        message = (f"The AI service is busy right now (too many requests for its current plan). Please try again {providers.when_free(e)}."
                   if e.busy and e.wait <= 120 else
                   f"The AI service has used up its allowance for now (the limits of its current plan). Please try again {providers.when_free(e)}."
                   if e.busy else "I couldn't get an answer from the AI service just now. Please try again in a minute.")
    except Exception as e:
        logger.exception(f"Agent run {run_id} failed")
        state, error, message = "failed", f"{type(e).__name__}: {e}", "Something went wrong on our side. Please try again."
    finally:
        beat.cancel()
    try:
        # The run's record first, then its last event: whoever sees the end can read the run as it ended.
        async with database.async_session() as db:
            await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(
                state=state, error=(error or totals.note or "")[:2000] or None, finished_at=now(), rounds=totals.rounds,
                models=",".join(dict.fromkeys(totals.models)) or None, tokens_in=totals.tokens_in,
                tokens_out=totals.tokens_out, first_output_ms=totals.first_output_ms,
                cost_inr=providers.cost_inr(totals.usage) if totals.usage else None))
            await db.commit()
            thread_id = (await db.execute(select(AgentRun.thread_id).where(AgentRun.id == run_id))).scalar()
        if state == "failed":
            await stream.emit("RUN_ERROR", message=message, code="failed")
        else:
            await stream.emit("RUN_FINISHED", threadId=thread_id, runId=run_id,
                              outcome="stopped" if state == "stopped" else "success")
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


# ─── What the run knows besides the conversation ────────────────────

class RunState:
    """One answer's own state: what kind of message it is, its plan, the groups of tools it has, what its tools really
    did (the ledger), and the calls already made (so none is made twice)."""

    def __init__(self, run_id: str, first: intake.Intake):
        self.run_id = run_id
        self.kind = first.kind
        self.groups = set(first.groups)
        self.looked = first.ok  # False: the first look couldn't run, so the open page's tools come, as before
        self.plan: list[dict] = []
        self.ledger = check.Ledger()
        self.calls: dict[str, registry.Outcome] = {}
        self.used: set[str] = set()  # dashboard tools that worked in this answer (`after` waits for them; so does "done")

    @property
    def patience(self) -> float:
        """How long a model at its rate limit is waited for: a task half done is worth a minute."""
        return TASK_PATIENCE_SEC if self.kind == "do" or self.ledger.acted() else providers.WAIT_FOR_BUSY_SEC

    def tools(self, role: str, screen_id: Optional[str]) -> list[registry.Tool]:
        names = set(groups.CORE) | groups.tools_of(self.groups)
        chosen = [t for t in registry.TOOLS.values() if t.name in names and role in t.roles]
        if not self.looked:
            chosen += [t for t in registry.available(role, screen_id) if t not in chosen]
        return [t for t in chosen if not t.after or self.used.intersection(t.after)]

    def checked(self) -> bool:
        """Its words are held and reviewed before the person sees them: a task, or an answer that tried a change."""
        return self.kind == "do" or bool(self.plan) or self.ledger.acted()

    async def save_plan(self) -> None:
        async with database.async_session() as db:
            await db.execute(update(AgentRun).where(AgentRun.id == self.run_id).values(plan=self.plan or None))
            await db.commit()


async def _use(tc: registry.ToolContext, state: RunState, name: str, arguments: dict) -> registry.Outcome:
    """Run a tool, unless this exact call was made already in this answer."""
    t = registry.TOOLS.get(name)
    if t is None or t.internal:
        return await registry.run(tc, name, arguments)
    key = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
    earlier = state.calls.get(key)
    if earlier is not None and earlier.ok and t.level == "read":
        return earlier
    if earlier is not None and earlier.ok:
        return registry.Outcome(registry.dump({"already_done": "You made exactly this call earlier in this answer, so it "
                                                               "wasn't made twice. Its result is above."}), True, kind="repeat")
    if earlier is not None:
        problem = check._problem(earlier.text)
        return registry.Outcome(registry.dump({"error": f"{problem} (This exact call failed a moment ago, so it wasn't "
                                                        "tried again: fix the inputs, try another way, or tell the person.)",
                                               "kind": earlier.kind}), False, kind="repeat")
    outcome = await registry.run(tc, name, arguments)
    if outcome.ok:
        state.used.add(name)
    if outcome.action_id and t.level == "change":  # what was read before may be different now
        state.calls = {k: v for k, v in state.calls.items() if registry.TOOLS[k.split(":", 1)[0]].level != "read"}
    state.calls[key] = outcome
    return outcome


async def _assistants(ctx: AuthContext) -> list[dict]:
    from routers.bots import list_bots
    try:
        async with database.async_session() as db:
            return [{"id": b["id"], "name": b["name"] or "Assistant"} for b in await list_bots(ctx=ctx, db=db)]
    except Exception as e:  # noqa: BLE001 (the model can still list them with a tool)
        logger.warning(f"Agent: couldn't list the assistants for the note: {e}")
        return []


def _assistants_note(assistants: list[dict], screen: dict, message: str) -> str:
    """Their assistants by name and id, so a name in the message ("make GBOT like GTBOT") needs no lookup."""
    if not assistants:
        return "<assistants>They have no assistants yet.</assistants>"
    open_id = (screen.get("entity") or {}).get("id")
    said = (message or "").lower()
    named = [a for a in assistants if a["id"] == open_id or (a["name"].strip() and a["name"].strip().lower() in said)]
    shown = named + [a for a in assistants if a not in named][:max(0, ASSISTANTS_SHOWN - len(named))]
    lines = [f"- {a['name']} (id {a['id']}){': open on the screen' if a['id'] == open_id else ''}" for a in shown]
    if len(assistants) > len(shown):
        lines.append(f"- ...and {len(assistants) - len(shown)} more (list_assistants)")
    return ("<assistants>\nTheir assistants (use these ids with tools; never show ids to the person):\n"
            + "\n".join(lines) + "\n</assistants>")


async def _earlier(thread_id: str, run_id: str) -> str:
    """What Nimmi changed earlier in this chat, so "undo that" or "now make it shorter" knows what "that" is."""
    async with database.async_session() as db:
        rows = (await db.execute(select(AgentAction).where(AgentAction.thread_id == thread_id, AgentAction.run_id != run_id)
                                 .order_by(AgentAction.created_at.desc()).limit(8))).scalars().all()
    if not rows:
        return ""
    after = {"done": "", "undone": " (undone since)", "proposed": " (waited for their Confirm)", "cancelled": " (they cancelled it)",
             "expired": " (expired before they confirmed)", "failed": " (it didn't work)", "confirming": ""}
    lines = [f"- {a.summary}{after.get(a.state, '')}" for a in rows]
    return "<earlier>\nWhat you changed earlier in this chat (newest first):\n" + "\n".join(lines) + "\n</earlier>"


def _before(rows: list[AgentMessage]) -> list[tuple[str, str]]:
    """The exchange before the new message: their last message and Nimmi's last words."""
    out = []
    for m in rows[:-1]:
        if m.role == "user" and m.name != "note" and m.content:
            out.append(("Them", m.content))
        elif m.role == "assistant" and m.name != "card" and m.content:
            out.append(("Nimmi", m.content))
    return out[-2:]


def _cut_short(state: RunState, error: providers.ModelError) -> str:
    """When the AI stops answering part way through a task: what was done (from the ledger, not from a model), what
    wasn't, and how to carry on."""
    why = "the AI service is at its limit right now" if error.busy else "the AI service stopped answering"
    lines = [f"I couldn't finish: {why}. What I did before that:"]
    lines += [f"- {c}" for c in state.ledger.changed] or ["- Nothing was changed."]
    lines += [f"- Waiting for your Confirm: {p}" for p in state.ledger.proposed]
    if left := plan.unfinished(state.plan):
        lines.append("Not done yet: " + "; ".join(s["title"] for s in left) + ".")
    lines.append(f"Ask me to carry on {providers.when_free(error) if error.busy else 'in a minute'} and I'll pick up from there.")
    return "\n".join(lines)


async def _say(stream: Stream, message_id: str, text: str) -> None:
    """Words held until they were checked, shown at once."""
    await stream.emit("TEXT_MESSAGE_START", messageId=message_id, role="assistant")
    await stream.emit("TEXT_MESSAGE_CONTENT", messageId=message_id, delta=text)
    await stream.emit("TEXT_MESSAGE_END", messageId=message_id)


# ─── One answer ─────────────────────────────────────────────────────

async def _answer(run_id: str, stream: Stream, totals: _Totals, started: float) -> None:
    async with database.async_session() as db:
        run = await db.get(AgentRun, run_id)
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.thread_id == run.thread_id)
                                 .order_by(AgentMessage.seq.desc()).limit(HISTORY * 2))).scalars().all()[::-1]
    ctx = AuthContext(user_id=run.user_id, owner_id=run.owner_id, role=run.role)
    history = [_entry(m) for m in rows]
    screen = next((m.screen for m in reversed(rows) if m.role == "user"), None) or {}
    message = next((m.content or "" for m in reversed(rows) if m.role == "user" and m.name != "note"), "")
    person = await _person(ctx)
    await stream.emit("RUN_STARTED", threadId=run.thread_id, runId=run_id)

    def first_output() -> None:
        if totals.first_output_ms is None:
            totals.first_output_ms = int((time.monotonic() - started) * 1000)

    async def notes() -> tuple[list[dict], str]:  # one after the other: a run holds one database connection at a time
        return await _assistants(ctx), await _earlier(run.thread_id, run_id)

    used: list = []
    first, (assistants, earlier) = await asyncio.gather(intake.understand(message, screen, _before(rows), used), notes())
    totals.add(*used)
    state = RunState(run_id, first)
    async with database.async_session() as db:
        await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(kind=state.kind))
        await db.commit()
    tc = registry.ToolContext(ctx=ctx, run_id=run_id, thread_id=run.thread_id, screen=screen, run=state)
    rounds = TASK_ROUNDS if state.kind == "do" else MAX_ROUNDS
    try:
        await _rounds(run, stream, totals, state, tc, history, person, screen, message, assistants, earlier, rounds,
                      first_output)
    except providers.ModelError as e:
        if not state.ledger.acted():  # nothing done yet: the usual message
            raise
        text = _cut_short(state, e)
        await _say(stream, str(uuid.uuid4()), text)
        await _save(run.thread_id, run.id, [{"role": "assistant", "content": text}])
        totals.note = f"cut short: {e}"
        logger.warning(f"Agent run {run.id} cut short after its changes: {e}")


async def _rounds(run, stream, totals, state, tc, history, person, screen, message, assistants, earlier, rounds,
                  first_output) -> None:
    """The model and its tools, round after round, until the checked answer is out."""
    run_id = run.id
    ctx = tc.ctx
    own = 0  # this answer's own entries in `history`: all of them go to the model
    nudges = reviews = 0
    carried_on = False

    async def waiting(seconds: float) -> None:
        await stream.emit("CUSTOM", name="status", value={"text": f"Waiting for the AI service ({seconds:.0f} s)"})

    for round_no in range(rounds + 1):
        totals.rounds = round_no + 1
        message_id = str(uuid.uuid4())
        tools = registry.specs(state.tools(ctx.role, screen.get("id")), screen.get("id"))
        context = prompt.context(person, screen, now(), [_assistants_note(assistants, screen, message), earlier,
                                                         TASK if state.kind == "do" and not state.plan else "",
                                                         plan.text(state.plan), state.ledger.text()])
        force = round_no == rounds or totals.tokens_in > TOKEN_BUDGET
        held = state.checked()
        pieces: list[str] = []
        calls: list[providers.ToolCall] = []
        opened = False
        try:
            window = providers.trim(history, HISTORY + own)
            async with aclosing(providers.stream(prompt.SYSTEM, context, window, tools, force_answer=force,
                                                 patience=state.patience, on_wait=waiting)) as answer:
                async for item in answer:
                    if isinstance(item, providers.Text):
                        text = output.clean(item.text)
                        pieces.append(text)
                        if held or not text:
                            continue
                        if not opened:
                            first_output()
                            await stream.emit("TEXT_MESSAGE_START", messageId=message_id, role="assistant")
                            opened = True
                        await stream.emit("TEXT_MESSAGE_CONTENT", messageId=message_id, delta=text)
                    elif isinstance(item, providers.ToolCall):
                        first_output()
                        calls.append(item)
                    elif isinstance(item, providers.Usage):
                        totals.add(item)
        except asyncio.CancelledError:
            if pieces and not held:  # stopped part way: keep what they already saw
                await _save(run.thread_id, run_id, [{"role": "assistant", "content": "".join(pieces).strip()}])
            raise
        finally:
            if opened:
                await stream.emit("TEXT_MESSAGE_END", messageId=message_id)
        content = "".join(pieces).strip()

        if calls:
            if held and content:
                first_output()
                await _say(stream, message_id, content)
            entry = {"role": "assistant", "content": content,
                     "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
                     "raw": next((c.raw for c in calls if c.raw), None)}
            results, cards = {}, []
            # Nimmi's own tools (the plan) after the dashboard's in each round, so the plan reflects the round's work.
            for call in sorted(calls, key=lambda c: bool((t := registry.TOOLS.get(c.name)) and t.internal)):
                t = registry.TOOLS.get(call.name)
                shown = not (t is not None and t.internal)
                if shown:
                    await stream.emit("TOOL_CALL_START", toolCallId=call.id, toolCallName=call.name,
                                      parentMessageId=message_id, label=registry.label(call.name))
                    await stream.emit("TOOL_CALL_END", toolCallId=call.id)
                tc.tool_call_id = call.id
                outcome = await _use(tc, state, call.name, call.arguments)
                totals.add(*tc.usage)
                tc.usage.clear()
                state.ledger.add(t, registry.label(call.name), outcome)
                results[call.id] = {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": outcome.text}
                if shown:
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
                tc.actions.clear()
            results = [results[c.id] for c in calls]  # in the order the model asked for them
            await _save(run.thread_id, run_id, [entry, *results])
            if cards:  # after the round that showed them, so the chat reads in order
                from agent.builder import card_message
                await _save(run.thread_id, run_id, [card_message(c) for c in cards])
            history += [entry, *results]
            own += 1 + len(results)
            continue

        # Words without tools: the answer, unless the work isn't finished or the words don't match what was done.
        # The guard holds the model to a plan it's following (it has marked a step); a plan it never touched is
        # the review's to check against what was done, which costs far less than another round.
        draft = {"role": "assistant", "content": content}
        following = any(s["status"] != "pending" for s in state.plan)
        if not force and following and nudges < NUDGES and (open_steps := plan.unfinished(state.plan)):
            nudges += 1
            note = GUARD.format(steps="; ".join(s["title"] for s in open_steps))
            history += [draft, {"role": "user", "content": note}]
            own += 2
            continue
        if state.checked() and reviews < REVIEWS:
            reviews += 1
            used = []
            verdict = await check.review(message, state.plan, state.ledger, content, used,
                                         may_continue=not carried_on and not force and round_no < rounds - 1)
            totals.add(*used)
            if verdict.plan and [s["status"] for s in state.plan] != verdict.plan:
                state.plan = [{**s, "status": status} for s, status in zip(state.plan, verdict.plan)]
                await state.save_plan()
                await stream.emit("CUSTOM", name="plan", value={"steps": state.plan})
            if verdict.kind == "continue":
                carried_on = True
                history += [draft, {"role": "user", "content": CARRY_ON.format(todo="; ".join(verdict.todo))}]
                own += 2
                continue
            if verdict.kind == "fix":
                content = verdict.answer
        if held and content:
            first_output()
            await _say(stream, message_id, content)
        if content:
            await _save(run.thread_id, run_id, [{"role": "assistant", "content": content}])
        return
