"""
A run's events, as the AG-UI protocol names them (RUN_STARTED, TEXT_MESSAGE_START / CONTENT / END, TOOL_CALL_START /
ARGS / END / RESULT, CUSTOM, RUN_FINISHED, RUN_ERROR; camelCase fields), plus our own "seq".

The server runs four processes, and a browser can reload or lose its connection. So every event is numbered and
saved before it is sent: whoever follows the run in the same process gets it at once, and a follower in another
process (a reload that reached a different one) reads the saved events, looking for new ones twice a second. Text
pieces that arrive within FLUSH_SEC of each other are merged, so a long answer is a few dozen rows, not thousands.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

import database
from backend.models import AgentEvent, AgentRun

logger = logging.getLogger(__name__)

FLUSH_SEC = 0.15
POLL_SEC = 0.5
PING_SEC = 15.0
STALE_SEC = 60.0  # a run whose process sent no heartbeat for this long has died (a deploy, a crash)
ENDING_SEC = 5.0  # a run that ended this recently still sends its own last event
DONE = ("RUN_FINISHED", "RUN_ERROR")
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite gives times back without their zone; they are all UTC."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def stale(run: AgentRun) -> bool:
    return run.state == "running" and (aware(run.heartbeat_at) or now()) < now() - timedelta(seconds=STALE_SEC)


class Stream:
    """The events of one run while it runs in this process."""
    live: dict[str, "Stream"] = {}

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.seq = 0
        self.pending: list[dict] = []
        self.listeners: set[asyncio.Queue] = set()
        self.last_flush = 0.0
        self.timer: Optional[asyncio.TimerHandle] = None
        self.flushing: set[asyncio.Task] = set()
        self.lock = asyncio.Lock()
        Stream.live[run_id] = self

    async def emit(self, type: str, **fields) -> None:
        last = self.pending[-1] if self.pending else None
        if type == "TEXT_MESSAGE_CONTENT" and last and last["type"] == type and last["messageId"] == fields.get("messageId"):
            last["delta"] += fields["delta"]
        else:
            self.pending.append({"type": type, **fields})
        wait = FLUSH_SEC - (time.monotonic() - self.last_flush)
        if type != "TEXT_MESSAGE_CONTENT" or wait <= 0:
            await self.flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(wait, self._flush_later)

    def _flush_later(self) -> None:
        self.timer = None
        task = asyncio.ensure_future(self.flush())
        self.flushing.add(task)
        task.add_done_callback(self.flushing.discard)

    async def flush(self) -> None:
        async with self.lock:
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            batch, self.pending = self.pending, []
            if not batch:
                return
            self.last_flush = time.monotonic()
            for event in batch:
                self.seq += 1
                event["seq"] = self.seq
            try:
                async with database.async_session() as db:
                    db.add_all([AgentEvent(run_id=self.run_id, seq=e["seq"], type=e["type"], data=e) for e in batch])
                    await db.execute(update(AgentRun).where(AgentRun.id == self.run_id)
                                     .values(last_seq=self.seq, heartbeat_at=now()))
                    await db.commit()
            except Exception as e:  # the panel in this process still gets them; only a replay would miss them
                logger.error(f"Agent run {self.run_id}: couldn't save events {batch[0]['seq']}-{self.seq}: {e}")
            for queue in list(self.listeners):
                for event in batch:
                    queue.put_nowait(event)

    async def close(self) -> None:
        await self.flush()
        Stream.live.pop(self.run_id, None)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def saved(run_id: str, after: int) -> list[dict]:
    async with database.async_session() as db:
        rows = (await db.execute(select(AgentEvent.data).where(AgentEvent.run_id == run_id, AgentEvent.seq > after)
                                 .order_by(AgentEvent.seq))).scalars().all()
    return list(rows)


async def _end_dead_run(run_id: str) -> Optional[dict]:
    """The run's process is gone (or it ended without saying so): mark it failed and give the panel the last word."""
    async with database.async_session() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:
            return {"type": "RUN_ERROR", "message": "This answer is no longer available.", "seq": 0}
        if run.state == "running" and not stale(run):
            return None
        if run.state != "running" and (aware(run.finished_at) or now()) > now() - timedelta(seconds=ENDING_SEC):
            return None  # it has just ended: its own last event is on its way (loop.py saves the run first)
        if run.state == "running":
            run.state, run.error, run.finished_at = "failed", "interrupted: the server restarted", now()
        event = ({"type": "RUN_ERROR", "message": "The answer was cut off because the server restarted. Please ask again."}
                 if run.state == "failed" else {"type": "RUN_FINISHED", "threadId": run.thread_id, "runId": run.id,
                                                "outcome": "stopped" if run.state == "stopped" else "success"})
        event["seq"] = (run.last_seq or 0) + 1
        run.last_seq = event["seq"]
        db.add(AgentEvent(run_id=run_id, seq=event["seq"], type=event["type"], data=event))
        try:
            await db.commit()
        except IntegrityError:  # another follower wrote it first
            await db.rollback()
            return None
        return event


async def follow(run_id: str, after: int = 0) -> AsyncIterator[str]:
    """The run's events after `after`, as server-sent events, until it ends."""
    stream = Stream.live.get(run_id)
    queue: asyncio.Queue = asyncio.Queue()
    if stream is not None:
        stream.listeners.add(queue)
    last, quiet_since = after, time.monotonic()
    try:
        for event in await saved(run_id, last):
            last = event["seq"]
            yield sse(event)
            if event["type"] in DONE:
                return
        while True:
            if stream is not None and Stream.live.get(run_id) is stream:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_SEC)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event["seq"] <= last:
                    continue
                last = event["seq"]
                yield sse(event)
                if event["type"] in DONE:
                    return
                continue
            # The run is in another process, or has just ended here: read what was saved.
            fresh = await saved(run_id, last)
            for event in fresh:
                last = event["seq"]
                yield sse(event)
                if event["type"] in DONE:
                    return
            if fresh:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since > 2 * POLL_SEC and (end := await _end_dead_run(run_id)) is not None:
                yield sse(end)
                return
            if time.monotonic() - quiet_since > PING_SEC:
                yield ": ping\n\n"
                quiet_since = time.monotonic() - 2 * POLL_SEC
            await asyncio.sleep(POLL_SEC)
    finally:
        if stream is not None:
            stream.listeners.discard(queue)
