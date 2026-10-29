"""
The agent's AI models: one streaming call that may ask for tools, on Gemini or an OpenAI-style API (OpenAI, Groq).

Models are tried in order (AGENT_MODELS: ids from voice/ai_models.py; only those whose service key is set). The quick
checks around an answer (intake.py's first look, check.py's review) use AGENT_FAST_MODELS, small and fast ones, so
they cost little and don't spend the main model's per-minute allowance. Nimmi can
have keys of its own (AGENT_GROQ_API_KEY, AGENT_GEMINI_API_KEY, AGENT_OPENAI_API_KEY), so its use never eats the quota
that phone calls and website chat need; without them it uses the backend's keys. The next
one answers when one fails before saying anything; one that was rate-limited or failed rests a while, as on calls.
A call yields Text pieces, then a ToolCall for each tool the model wants run, then one Usage.

Messages use the shape voice/llm.py uses: {"role": "user" | "assistant" | "tool", "content", "tool_calls": [{"id",
"name", "arguments"}], "tool_call_id", "name", "raw"}. This client is separate from the voice one on purpose: that
one is tuned for the first spoken word (short answers, 16 messages, blocking clients in threads).
Claude comes in phase 5, when there is a key to test it with.
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import httpx

import ai
from voice import ai_models

logger = logging.getLogger(__name__)

AGENT_MODELS = [m.strip() for m in os.getenv("AGENT_MODELS", "gemini-3.6-flash,gpt-oss-120b,gpt-oss-20b").split(",") if m.strip()]
FAST_MODELS = [m.strip() for m in os.getenv("AGENT_FAST_MODELS", "gpt-oss-20b,gpt-oss-120b,gemini-3.6-flash").split(",") if m.strip()]
RUNS_ON = ("gemini", "openai", "groq")  # the services this client talks to
GAP_SEC = float(os.getenv("AGENT_MODEL_GAP_SEC", "30"))  # the longest silence: thinking before the first words, or a stall
CALL_SEC = float(os.getenv("AGENT_MODEL_CALL_SEC", "90"))  # one whole model call
MAX_OUT = 4096  # thinking included (Gemini counts it in the same allowance)
GEMINI_THINKING = os.getenv("AGENT_GEMINI_THINKING", "low")
OPENAI_URL = "https://api.openai.com/v1"
REST_SEC = 15.0  # a model that failed is skipped this long; a rate limit: as long as the service says (up to an hour)
MAX_REST_SEC = 3600.0  # a free tier's daily quota (Gemini: 20 a day, Oct 2026) is tried again hourly, not every minute
WAIT_FOR_BUSY_SEC = 12.0  # every model resting, one free again this soon: wait for it rather than fail
# Gemini checks that the function calls in a conversation are its own (thought signatures). One another model made
# is marked as such, as Gemini's docs say.
FOREIGN_CALL = "skip_thought_signature_validator"

_resting: dict[str, float] = {}
_client: Optional[httpx.AsyncClient] = None


@dataclass
class Text:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw: Optional[dict] = None  # Gemini: the turn's own parts (with its thought signatures), on the first call


@dataclass
class Usage:
    model: str  # catalog id (voice/ai_models.py)
    tokens_in: int = 0
    tokens_out: int = 0


class ModelError(Exception):
    """No model could answer, or the one answering stopped part way. `busy`: they were all at their rate limits;
    `wait`: seconds until the first is free again, as the services said (a daily allowance: up to an hour)."""

    def __init__(self, message: str, busy: bool = False, wait: float = 0.0):
        super().__init__(message)
        self.busy = busy
        self.wait = wait


def when_free(error: "ModelError") -> str:
    """When to try again, in words: a per-minute limit is a minute; a used-up allowance is longer, and said so."""
    if error.wait <= 120:
        return "in a minute"
    minutes = round(error.wait / 60)
    return "in about an hour or later" if minutes >= 55 else f"in about {minutes} minutes"


def http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(GAP_SEC, connect=5.0))
    return _client


def key(runs_on: str) -> str:
    """The agent's own key for a service (AGENT_GROQ_API_KEY...), or else the one the rest of the backend uses."""
    name = ai_models._KEYS[runs_on]
    return os.getenv(f"AGENT_{name}") or os.getenv(name, "")


def models(role: str = "main") -> list[ai_models.AiModel]:
    """The models the agent may use on this server, in the order it tries them; role "fast": the quick checks'."""
    out = []
    for model_id in FAST_MODELS if role == "fast" else AGENT_MODELS:
        m = ai_models.AI_MODELS_BY_ID.get(model_id)
        if m and m.runs_on in RUNS_ON and m.functions and key(m.runs_on):
            out.append(m)
    return out


def trim(history: list[dict], limit: int) -> list[dict]:
    """The last `limit` messages, starting with the person's own, and only whole tool rounds: a call without its
    result (a run stopped part way) and a result without its call are left out, since every service refuses them."""
    answered = {h.get("tool_call_id") for h in history if h.get("role") == "tool"}
    asked: set = set()
    out = []
    for h in history:
        if h.get("role") == "assistant" and h.get("tool_calls"):
            calls = [c for c in h["tool_calls"] if c.get("id") in answered]
            asked |= {c["id"] for c in calls}
            if not calls and not (h.get("content") or "").strip():
                continue
            h = {**h, "tool_calls": calls or None, "raw": h.get("raw") if len(calls) == len(h["tool_calls"]) else None}
        elif h.get("role") == "tool" and h.get("tool_call_id") not in asked:
            continue
        out.append(h)
    out = out[-limit:]
    while out and out[0].get("role") != "user":
        out = out[1:]
    return out


def _arguments(text: str) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def openai_messages(system: str, context: str, history: list[dict]) -> list[dict]:
    out = [{"role": "system", "content": system}]
    if context:
        out.append({"role": "system", "content": context})
    for h in history:
        if h.get("role") == "tool":
            out.append({"role": "tool", "tool_call_id": h["tool_call_id"], "content": h.get("content") or ""})
        elif h.get("role") == "assistant" and h.get("tool_calls"):
            out.append({"role": "assistant", "content": h.get("content") or None, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False)}}
                for c in h["tool_calls"]]})
        elif (h.get("content") or "").strip():
            out.append({"role": "user" if h.get("role") == "user" else "assistant", "content": h["content"]})
    return out


def gemini_contents(history: list[dict]) -> list[dict]:
    contents: list[dict] = []

    def add(role: str, parts: list[dict]) -> None:
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})

    for h in history:
        if h.get("role") == "tool":
            add("user", [{"functionResponse": {"name": h.get("name") or "", "response": {"result": h.get("content") or ""}}}])
        elif h.get("role") == "assistant" and h.get("tool_calls"):
            own = (h.get("raw") or {}).get("gemini_parts")
            if own:
                add("model", list(own))
            else:
                text = [{"text": h["content"]}] if h.get("content") else []
                add("model", text + [{"functionCall": {"name": c["name"], "args": c.get("arguments") or {}},
                                      "thoughtSignature": FOREIGN_CALL} for c in h["tool_calls"]])
        elif (h.get("content") or "").strip():
            add("user" if h.get("role") == "user" else "model", [{"text": h["content"]}])
    if not contents or contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": "(The conversation continues.)"}]})
    return contents


def _groq_reasoning(model: str) -> dict:
    # As on calls (voice/llm.py): these models reason first; keep it short and out of the answer.
    params = {"reasoning_format": "hidden"}
    if "gpt-oss" in model:
        params["reasoning_effort"] = "low"
    elif "qwen" in model:
        params["reasoning_effort"] = "none"
    return params


class _StatusError(Exception):
    def __init__(self, status: int, body: bytes, retry_after: Optional[str]):
        super().__init__(f"HTTP {status} {body[:200]!r}")
        self.status, self.retry_after, self.body = status, retry_after, body[:4000]

    def wait(self) -> Optional[float]:
        """How long the service says to wait: Retry-After, or Gemini's retryDelay in the error ("46419s")."""
        try:
            if self.retry_after:
                return float(self.retry_after)
        except ValueError:
            pass
        m = re.search(rb'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', self.body)
        return float(m.group(1)) if m else None


def _too_long(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ModelError(f"no complete answer within {CALL_SEC:.0f}s")


async def _gemini(m: ai_models.AiModel, system: str, context: str, history: list[dict], tools: list[dict],
                  force_answer: bool) -> AsyncIterator["Text | ToolCall | Usage"]:
    body = {
        "contents": gemini_contents(history),
        "systemInstruction": {"parts": [{"text": system}] + ([{"text": context}] if context else [])},
        "generationConfig": {"maxOutputTokens": MAX_OUT, "thinkingConfig": {"thinkingLevel": GEMINI_THINKING}},
        "safetySettings": ai.SAFETY,
    }
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
        if force_answer:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    deadline = time.monotonic() + CALL_SEC
    parts: list[dict] = []
    usage = Usage(m.id)
    async with http().stream("POST", f"{ai.GEMINI_URL}/{m.model}:streamGenerateContent", params={"alt": "sse"},
                             headers={"x-goog-api-key": key("gemini")}, json=body) as r:
        if r.status_code != 200:
            raise _StatusError(r.status_code, await r.aread(), r.headers.get("retry-after"))
        async for line in r.aiter_lines():
            _too_long(deadline)
            if not line.startswith("data:"):
                continue
            try:
                chunk = json.loads(line[5:])
            except ValueError:
                continue
            if meta := chunk.get("usageMetadata"):
                usage.tokens_in = meta.get("promptTokenCount") or 0
                usage.tokens_out = (meta.get("candidatesTokenCount") or 0) + (meta.get("thoughtsTokenCount") or 0)
            candidate = (chunk.get("candidates") or [{}])[0]
            for part in (candidate.get("content") or {}).get("parts") or []:
                parts.append(part)
                if part.get("text") and not part.get("thought"):
                    yield Text(part["text"])
            reason = candidate.get("finishReason")
            if reason in ("MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "SAFETY", "PROHIBITED_CONTENT"):
                raise ModelError(f"Gemini stopped: {reason}")
    calls = [p["functionCall"] for p in parts if p.get("functionCall")]
    for i, call in enumerate(calls):
        yield ToolCall(f"call_{uuid.uuid4().hex[:12]}", call.get("name") or "", call.get("args") or {},
                       {"gemini_parts": parts} if i == 0 else None)
    yield usage


async def _openai_style(m: ai_models.AiModel, system: str, context: str, history: list[dict], tools: list[dict],
                        force_answer: bool) -> AsyncIterator["Text | ToolCall | Usage"]:
    if m.runs_on == "groq":
        url, token = f"{ai.GROQ_URL}/chat/completions", key("groq")
        extra = {"temperature": 0.3, **_groq_reasoning(m.model)}  # Groq sends the counts with the last piece itself
    else:
        url, token = f"{OPENAI_URL}/chat/completions", key("openai")
        extra = {**m.extra, "stream_options": {"include_usage": True}}
    body = {"model": m.model, "stream": True, "max_completion_tokens": MAX_OUT,
            "messages": openai_messages(system, context, history), **extra}
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
        body["tool_choice"] = "none" if force_answer else "auto"
    deadline = time.monotonic() + CALL_SEC
    calls: dict[int, dict] = {}
    usage = Usage(m.id)
    async with http().stream("POST", url, headers={"Authorization": f"Bearer {token}"}, json=body) as r:
        if r.status_code != 200:
            raise _StatusError(r.status_code, await r.aread(), r.headers.get("retry-after"))
        async for line in r.aiter_lines():
            _too_long(deadline)
            data = line[5:].strip() if line.startswith("data:") else ""
            if not data:
                continue
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if counts := chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage"):
                usage.tokens_in = counts.get("prompt_tokens") or 0
                usage.tokens_out = counts.get("completion_tokens") or 0
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if text := delta.get("content"):
                    yield Text(text)
                for piece in delta.get("tool_calls") or []:  # a call comes in pieces: id and name, then its arguments
                    slot = calls.setdefault(piece.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    slot["id"] = slot["id"] or piece.get("id")
                    fn = piece.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["arguments"] += fn.get("arguments") or ""
    for i, c in sorted(calls.items()):
        if c["name"]:
            yield ToolCall(c["id"] or f"call_{i}_{uuid.uuid4().hex[:8]}", c["name"], _arguments(c["arguments"]))
    yield usage


def _rest(m: ai_models.AiModel, error: Exception) -> bool:
    """Rest a model that failed. True if it was a rate limit or quota."""
    wait, limited = REST_SEC, False
    if isinstance(error, _StatusError):
        if error.status in (400, 404):
            return False  # our request or the model's name: resting won't fix it (and the log says why)
        if error.status in (413, 429):
            wait, limited = error.wait() or 20.0, True
    _resting[m.id] = time.monotonic() + min(max(wait, 5.0), MAX_REST_SEC)
    return limited


async def stream(system: str, context: str, history: list[dict], tools: list[dict],
                 force_answer: bool = False, role: str = "main", patience: float = WAIT_FOR_BUSY_SEC,
                 on_wait=None) -> AsyncIterator["Text | ToolCall | Usage"]:
    """One answer from the first model that gives one. `force_answer`: the tools are still described (the
    conversation has used them) but the model must answer in words. When every model is at its rate limit and one is
    free again within `patience` seconds, it waits for it (`on_wait(seconds)` is told first) rather than fail: a task
    half done is better finished a minute later."""
    last: Optional[Exception] = None
    available = models(role)
    waited = 0.0
    while True:
        soonest = min((_resting.get(m.id, 0) for m in available), default=0) - time.monotonic()
        if available and 0 < soonest <= patience - waited:
            if on_wait is not None:
                await on_wait(soonest)
            await asyncio.sleep(soonest)  # all busy for a little longer (a per-minute limit): worth the wait
            waited += soonest
        busy = 0
        for m in available:
            if _resting.get(m.id, 0) > time.monotonic():
                busy += 1
                continue
            call = _gemini if m.runs_on == "gemini" else _openai_style
            started, said = time.monotonic(), False
            try:
                async with aclosing(call(m, system, context, history, tools, force_answer)) as items:
                    async for item in items:
                        if not said and not isinstance(item, Usage):
                            said = True
                            logger.info(f"Agent answer from {m.id}: first output after {time.monotonic() - started:.2f}s")
                        yield item
                if said:
                    return
                raise ModelError("an empty answer")
            except (ModelError, _StatusError, httpx.HTTPError) as e:
                last = e
                if said:
                    logger.warning(f"Agent model {m.id} stopped part way: {str(e)[:200]}")
                    raise ModelError(f"{m.name} stopped part way") from e
                logger.warning(f"Agent model {m.id} failed: {str(e)[:300]}")
                busy += _rest(m, e)
        if available and busy == len(available):
            soonest = min(_resting.get(m.id, 0) for m in available) - time.monotonic()
            if 0 < soonest <= patience - waited:
                continue  # each was at its limit, and one is free again soon enough: wait for it and try again
            raise ModelError("Every AI model is at its rate limit or quota", busy=True, wait=max(soonest, 0.0))
        raise ModelError("No AI model could answer" + (f" ({str(last)[:120]})" if last else ": none is set up"))


async def ask_json(system: str, text: str, role: str = "main", patience: float = WAIT_FOR_BUSY_SEC) -> tuple[dict, list[Usage]]:
    """One answer as a JSON object (no tools), from the first model that gives a valid one; asked again once if the
    first answer isn't JSON. Returns (the object, the token counts)."""
    usage: list[Usage] = []
    for _attempt in range(2):
        pieces = []
        async with aclosing(stream(system, "", [{"role": "user", "content": text}], [], role=role, patience=patience)) as items:
            async for item in items:
                if isinstance(item, Text):
                    pieces.append(item.text)
                elif isinstance(item, Usage):
                    usage.append(item)
        raw = "".join(pieces).strip()
        found = re.search(r"\{.*\}", raw, re.S)
        if found:
            try:
                value = json.loads(found.group(0))
                if isinstance(value, dict):
                    return value, usage
            except ValueError:
                pass
        text += "\n\nReply with only the JSON object, nothing before or after it."
    raise ModelError("The AI's answer wasn't usable")


def cost_inr(usage: list[Usage]) -> float:
    """What these answers cost at the models' list prices (voice/ai_models.py), in rupees."""
    from voice.catalog import USD_INR_RATE
    total = 0.0
    for u in usage:
        m = ai_models.AI_MODELS_BY_ID.get(u.model)
        if m is not None:
            total += (u.tokens_in * m.price_in + u.tokens_out * m.price_out) / 1e6 * (1 if m.rupees else USD_INR_RATE)
    return round(total, 4)
