"""
The chat AI: the one place that talks to language models for website chat, WhatsApp and flows.

Gemini is called through its REST API (the google-generativeai SDK is no longer supported), with
a real system instruction and real conversation turns instead of one pasted prompt. Each request
tries a short list of fast models in order with time limits, so one slow or failing model doesn't
leave a visitor waiting: CHAT_MODELS sets the list. A business's own API key is tried first and
Nimmi's key is the fallback. Errors are logged, never shown to visitors.
"""
import json
import logging
import os
from typing import Iterator, Optional

import httpx

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
CHAT_MODELS = [m.strip() for m in os.getenv(
    "CHAT_MODELS", "gemini-2.5-flash,gemini-3.5-flash-lite,gemini-flash-lite-latest").split(",") if m.strip()]
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-flash-lite-latest")  # small jobs: extracting details, summaries
# Gemini models a business can pick in the builder; anything else (old saved values) means automatic.
PICKABLE = {"gemini-2.5-flash", "gemini-flash-lite-latest"}
TIMEOUT = httpx.Timeout(connect=6.0, read=30.0, write=15.0, pool=6.0)
SAFETY = [{"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]
SORRY = "Sorry, I'm having trouble answering right now. Please try again in a moment."


class AIError(Exception):
    pass


def _system_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def _contents(messages: list[dict]) -> list[dict]:
    """Chat turns for Gemini: roles user/model, alternating, starting with the user."""
    out: list[dict] = []
    for m in messages:
        text = str(m.get("content") or "").strip()
        if not text:
            continue
        role = "user" if m.get("role") == "user" else "model"
        if out and out[-1]["role"] == role:
            out[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            out.append({"role": role, "parts": [{"text": text}]})
    if out and out[0]["role"] == "model":
        out.insert(0, {"role": "user", "parts": [{"text": "(The visitor opened the chat.)"}]})
    return out or [{"role": "user", "parts": [{"text": "Hello"}]}]


def _body(model: str, system: str, messages: list[dict], temperature: float, max_tokens: int, json_mode: bool,
          extra: Optional[dict] = None) -> dict:
    config: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if model.startswith("gemini-2.5-flash"):
        config["thinkingConfig"] = {"thinkingBudget": 0}  # answers in ~2s instead of ~30s
    if json_mode:
        config["responseMimeType"] = "application/json"
    config.update(extra or {})
    body = {"contents": _contents(messages), "generationConfig": config, "safetySettings": SAFETY}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


def _text(data: dict) -> str:
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _keys(api_key: Optional[str]) -> list[str]:
    keys = [k for k in (api_key, _system_key()) if k]
    return list(dict.fromkeys(keys))


def _gemini(system: str, messages: list[dict], *, api_key: Optional[str], models: list[str], temperature: float,
            max_tokens: int, json_mode: bool) -> str:
    last = "no Gemini key configured"
    with httpx.Client(timeout=TIMEOUT) as client:
        for key in _keys(api_key):
            for model in models:
                try:
                    r = client.post(f"{GEMINI_URL}/{model}:generateContent", headers={"x-goog-api-key": key},
                                    json=_body(model, system, messages, temperature, max_tokens, json_mode))
                    if r.status_code == 200:
                        text = _text(r.json())
                        if text.strip():
                            return text
                        last = f"{model}: empty answer"
                        continue
                    last = f"{model}: HTTP {r.status_code} {r.text[:160]}"
                    if r.status_code in (400, 401, 403) and "API key" in r.text:
                        break  # this key doesn't work: try the next key
                except httpx.HTTPError as e:
                    last = f"{model}: {type(e).__name__}"
                logger.warning(f"AI model failed, trying the next one: {last}")
    raise AIError(last)


def _gemini_stream(system: str, messages: list[dict], *, api_key: Optional[str], models: list[str],
                   temperature: float, max_tokens: int, timeout: Optional[httpx.Timeout] = None,
                   extra: Optional[dict] = None) -> Iterator[str]:
    last = "no Gemini key configured"
    with httpx.Client(timeout=timeout or TIMEOUT) as client:
        for key in _keys(api_key):
            for model in models:
                sent = False
                try:
                    with client.stream("POST", f"{GEMINI_URL}/{model}:streamGenerateContent", params={"alt": "sse"},
                                       headers={"x-goog-api-key": key},
                                       json=_body(model, system, messages, temperature, max_tokens, False, extra)) as r:
                        if r.status_code != 200:
                            error = r.read()
                            last = f"{model}: HTTP {r.status_code} {error[:160]!r}"
                            if r.status_code in (400, 401, 403) and b"API key" in error:
                                break
                            logger.warning(f"AI model failed, trying the next one: {last}")
                            continue
                        for line in r.iter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                chunk = _text(json.loads(line[5:].strip()))
                            except ValueError:
                                continue
                            if chunk:
                                sent = True
                                yield chunk
                    if sent:
                        return
                    last = f"{model}: empty answer"
                except httpx.HTTPError as e:
                    last = f"{model}: {type(e).__name__}"
                    if sent:  # part of the answer already went out: stop cleanly rather than start over
                        logger.warning(f"AI stream interrupted: {last}")
                        return
                logger.warning(f"AI model failed, trying the next one: {last}")
    raise AIError(last)


def _openai_messages(system: str, messages: list[dict]) -> list[dict]:
    return [{"role": "system", "content": system}] + [
        {"role": "user" if m.get("role") == "user" else "assistant", "content": str(m.get("content") or "")}
        for m in messages if m.get("content")]


def _order(first: Optional[str]) -> list[str]:
    """Models to try: the chosen one first (when it's one we support), then the usual list."""
    if first not in PICKABLE and first != FAST_MODEL:
        return CHAT_MODELS
    return [first] + [m for m in CHAT_MODELS if m != first]


def chat(system: str, messages: list[dict], *, provider: str = "google", model: Optional[str] = None,
         api_key: Optional[str] = None, temperature: float = 0.3, max_tokens: int = 1024, json_mode: bool = False,
         fast: bool = False) -> str:
    """One complete answer. Raises AIError when no model could answer."""
    if provider == "openai":
        import openai
        try:
            client = openai.OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
            r = client.chat.completions.create(model=model or "gpt-4o-mini", messages=_openai_messages(system, messages),
                                               temperature=temperature, max_tokens=max_tokens,
                                               **({"response_format": {"type": "json_object"}} if json_mode else {}))
            return r.choices[0].message.content or ""
        except Exception as e:
            raise AIError(f"openai: {e}") from e
    return _gemini(system, messages, api_key=api_key, models=_order(FAST_MODEL if fast else model), temperature=temperature,
                   max_tokens=max_tokens, json_mode=json_mode)


def chat_stream(system: str, messages: list[dict], *, provider: str = "google", model: Optional[str] = None,
                api_key: Optional[str] = None, temperature: float = 0.3, max_tokens: int = 1024,
                timeout: Optional[httpx.Timeout] = None, only: bool = False, config: Optional[dict] = None) -> Iterator[str]:
    """The answer in pieces as it's written. Raises AIError before the first piece if no model could answer.
    `timeout` (Gemini) replaces the default limits, e.g. tighter ones for a live phone call. `only`: that Gemini
    model and no other (a voice agent's own choice; the call has its own backups). `config`: added to Gemini's
    generationConfig (e.g. a thinking setting)."""
    if provider == "openai":
        import openai
        try:
            client = openai.OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
            stream = client.chat.completions.create(model=model or "gpt-4o-mini", messages=_openai_messages(system, messages),
                                                    temperature=temperature, max_tokens=max_tokens, stream=True)
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
            return
        except Exception as e:
            raise AIError(f"openai: {e}") from e
    yield from _gemini_stream(system, messages, api_key=api_key, models=[model] if only and model else _order(model),
                              temperature=temperature, max_tokens=max_tokens, timeout=timeout, extra=config)


def look(instruction: str, data: bytes, mime: str, max_tokens: int = 400) -> str:
    """What a photo, PDF or recording shows or says (e.g. something a customer sent on WhatsApp), read by Gemini.
    Raises AIError when no model could read it."""
    import base64
    parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}, {"text": instruction}]
    last = "no Gemini key configured"
    with httpx.Client(timeout=httpx.Timeout(connect=6.0, read=90.0, write=60.0, pool=6.0)) as client:
        for key in _keys(None):
            for model in CHAT_MODELS:
                config: dict = {"temperature": 0, "maxOutputTokens": max_tokens}
                if model.startswith("gemini-2.5-flash"):
                    config["thinkingConfig"] = {"thinkingBudget": 0}
                try:
                    r = client.post(f"{GEMINI_URL}/{model}:generateContent", headers={"x-goog-api-key": key}, json={
                        "contents": [{"role": "user", "parts": parts}], "generationConfig": config, "safetySettings": SAFETY})
                    if r.status_code == 200 and _text(r.json()).strip():
                        return _text(r.json()).strip()
                    last = f"{model}: HTTP {r.status_code} {r.text[:160]}"
                    if r.status_code in (400, 401, 403) and "API key" in r.text:
                        break
                except httpx.HTTPError as e:
                    last = f"{model}: {type(e).__name__}"
                logger.warning(f"AI model couldn't read the file, trying the next one: {last}")
    raise AIError(last)


def extract_json(system: str, text: str, max_tokens: int = 400) -> dict:
    """A small structured answer (e.g. details a visitor gave). {} if it can't be had."""
    try:
        raw = chat(system, [{"role": "user", "content": text}], json_mode=True, max_tokens=max_tokens, temperature=0, fast=True)
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
    except (AIError, ValueError) as e:
        logger.info(f"Detail extraction skipped: {e}")
        return {}
