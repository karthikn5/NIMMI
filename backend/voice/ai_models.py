"""
The AI models a voice agent can answer with, and what a call minute costs on each.

A call minute costs BASE_CREDITS (hearing the caller, the voice and the phone line) plus the model's own credits.
A model's credits are what it costs us on a busy call minute at its list price, plus half, counted at the lowest price
a credit sells for (the biggest pack). They're never more than 95% of what Retell charges for the same model, unless
that would leave less than 15% over our cost. A busy minute, measured on 40 test calls (Oct 2026): 5.6 answers, each
about 3,000 tokens in (the agent's instructions and knowledge go with every answer) and 60 out. Rates can change
without a deploy: VOICE_MODEL_CREDITS_JSON, e.g. {"gpt-5.4-mini": 0.5}; VOICE_HIDDEN_MODELS takes models off the list.

Speeds: the median time to the first words with an agent's real prompt and a Tanglish question (29 Oct 2026,
dev-scripts/voice/model_latency.py and gemini_thinking_probe.py); None until measured. Each model is asked to answer
without thinking first (`extra`; Groq's models get theirs in llm._reasoning_params), the biggest difference to how
soon a caller hears it.
"""
import json
import math
import os
from dataclasses import dataclass, field, replace
from typing import Optional

from voice.catalog import PACKS, USD_INR_RATE

BASE_CREDITS = float(os.getenv("VOICE_BASE_CREDITS", "1"))
BUSY_TOKENS_IN, BUSY_TOKENS_OUT = 16_800, 336
MARKUP, MIN_MARKUP, BELOW_RETELL = 1.5, 1.15, 0.95
CREDIT_INR = min(p["price"] / p["credits"] for p in PACKS)
FAST, SMART = "fast", "smart"
GROUPS = {FAST: "Quick and low cost", SMART: "Smarter, for detailed questions"}
# The model an agent uses until one is chosen ("auto": agents saved before models could be chosen).
DEFAULT = os.getenv("VOICE_DEFAULT_MODEL", "gpt-oss-120b")


@dataclass(frozen=True)
class AiModel:
    id: str                    # what an agent saves
    name: str
    maker: str
    group: str
    runs_on: str               # who serves it: groq, sarvam, gemini, openai, anthropic
    model: str                 # that service's name for it
    price_in: float            # list price per million tokens in, USD (rupees when `rupees`)
    price_out: float           # and out, thinking included
    retell: Optional[float] = None       # Retell's price a minute for the same model, USD (Oct 2026)
    first_words: Optional[float] = None  # seconds
    about: str = ""
    extra: dict = field(default_factory=dict)  # sent with each request so it answers without thinking first
    rupees: bool = False
    thinks: bool = False       # always thinks before answering (about 4x the words out)
    preview: bool = False      # its service calls it a preview, not for production
    suggested: bool = False
    functions: bool = True     # can call the agent's functions (voice/functions.py)
    credits: float = 0         # a minute, on top of BASE_CREDITS (worked out below)

    @property
    def cost_inr(self) -> float:
        """What a busy call minute costs us at list price."""
        out = BUSY_TOKENS_OUT * (4 if self.thinks else 1)
        return (BUSY_TOKENS_IN * self.price_in + out * self.price_out) / 1e6 * (1 if self.rupees else USD_INR_RATE)


def _gpt(id_, name, group, price_in, price_out, retell, about, effort="none", **kw):
    extra = {"reasoning_effort": effort} if effort else {}
    return AiModel(id_, name, "OpenAI", group, "openai", id_, price_in, price_out, retell, about=about, extra=extra, **kw)


def _claude(id_, name, group, price_in, price_out, retell, about, thinking, **kw):
    return AiModel(id_, name, "Anthropic", group, "anthropic", id_, price_in, price_out, retell, about=about, extra=thinking, **kw)


def _gemini(id_, name, group, model, price_in, price_out, retell, about, level="minimal", **kw):
    # The 3.8 Flash and 4 Argon don't take "minimal": "low" is their quickest, and they think a little first.
    return AiModel(id_, name, "Google", group, "gemini", model, price_in, price_out, retell, about=about,
                   extra={"thinkingConfig": {"thinkingLevel": level}}, thinks=level != "minimal", **kw)


OFF = {"thinking": {"type": "disabled"}}
# Gemini prices are the ones Google has announced for 2027 where they rise (3.6 and 3.8 Flash, Gemini 4 Argon).
AI_MODELS = [
    AiModel("gpt-oss-120b", "GPT-OSS 120B", "OpenAI", FAST, "groq", "openai/gpt-oss-120b", 0.15, 0.60, first_words=0.71,
            suggested=True, about="OpenAI's open model on Groq's fast servers. Quick, low cost, and good at following instructions."),
    AiModel("gpt-oss-20b", "GPT-OSS 20B", "OpenAI", FAST, "groq", "openai/gpt-oss-20b", 0.075, 0.30, first_words=0.72,
            about="The smaller open model: the lowest cost, for simple calls."),
    AiModel("qwen-3.8-27b", "Qwen 3.8 27B", "Alibaba", FAST, "groq", "qwen/qwen3.8-27b", 0.80, 4.00, first_words=0.39,
            preview=True, about="Among the quickest to answer. Groq offers it as a preview, so it can change or go away."),
    AiModel("sarvam-105b", "Sarvam 105B", "Sarvam AI", FAST, "sarvam", "sarvam-105b-conversations", 15, 60, first_words=0.28,
            rupees=True, functions=False,
            about="Made in India for Indian languages, and the quickest to answer. Best when callers keep to one language."),
    _gpt("gpt-6-luna", "GPT-6 Luna", FAST, 0.10, 0.50, 0.0032, "ChatGPT's newest small model: low cost and quick."),
    _gpt("gpt-5.6-luna", "GPT-5.6 Luna", FAST, 0.20, 1.20, 0.0064, "A small ChatGPT model for everyday calls."),
    _gpt("gpt-5.4-mini", "GPT-5.4 mini", FAST, 0.75, 4.50, 0.024, "ChatGPT's capable small model, for longer conversations."),
    _gpt("gpt-5.4-nano", "GPT-5.4 nano", FAST, 0.20, 1.25, 0.0064, "ChatGPT's smallest 5.4 model, for simple calls."),
    _gpt("gpt-5-mini", "GPT-5 mini", FAST, 0.25, 2.00, 0.008, "An earlier small ChatGPT model.", effort="minimal"),
    _gpt("gpt-5-nano", "GPT-5 nano", FAST, 0.05, 0.40, 0.0016, "An earlier, very low-cost ChatGPT model.", effort="minimal"),
    _gpt("gpt-4.1-mini", "GPT-4.1 mini", FAST, 0.40, 1.60, 0.0128, "A dependable older ChatGPT model that doesn't reason first.",
         effort=None),
    _claude("claude-haiku-5-5", "Claude Haiku 5.5", FAST, 0.10, 0.50, 0.0032, "Claude's quickest model, at a very low cost.", OFF),
    _claude("claude-haiku-4-5", "Claude Haiku 4.5", FAST, 1.00, 5.00, 0.025, "The earlier Claude Haiku.", {}),
    _gemini("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", FAST, "gemini-3.5-flash-lite", 0.30, 2.50, 0.0096,
            "Google's quick, low-cost model.", first_words=1.1),
    _gemini("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", FAST, "gemini-3.1-flash-lite", 0.25, 1.50, 0.008,
            "The earlier Flash-Lite.", first_words=1.5),
    _gpt("gpt-6.1-terra", "GPT-6.1 Terra", SMART, 1.00, 5.00, 0.032, "ChatGPT's newest all-round model.", suggested=True),
    _gpt("gpt-6.1-sol", "GPT-6.1 Sol", SMART, 2.00, 10.00, 0.064, "A highly capable ChatGPT model."),
    _gpt("gpt-6-sol", "GPT-6 Sol", SMART, 2.00, 10.00, 0.064, "The earlier Sol model."),
    _gpt("gpt-6-astra", "GPT-6 Astra", SMART, 10.00, 50.00, 0.32, "ChatGPT's most capable model, at a high cost."),
    _gpt("gpt-5.6-terra", "GPT-5.6 Terra", SMART, 2.00, 12.00, 0.064, "A capable all-round ChatGPT model."),
    _gpt("gpt-5.5", "GPT-5.5", SMART, 5.00, 30.00, 0.16, "A large, highly capable ChatGPT model."),
    _gpt("gpt-5.4", "GPT-5.4", SMART, 2.50, 15.00, 0.08, "A capable ChatGPT model."),
    _gpt("gpt-5.2", "GPT-5.2", SMART, 1.75, 14.00, 0.056, "An earlier ChatGPT model."),
    _gpt("gpt-5.1", "GPT-5.1", SMART, 1.25, 10.00, 0.04, "An earlier ChatGPT model."),
    _gpt("gpt-5", "GPT-5", SMART, 1.25, 10.00, 0.04, "An earlier ChatGPT model.", effort="minimal"),
    _gpt("gpt-4.1", "GPT-4.1", SMART, 2.00, 8.00, 0.045, "A dependable older ChatGPT model.", effort=None),
    _claude("claude-sonnet-5-5", "Claude Sonnet 5.5", SMART, 2.00, 10.00, 0.064, "Claude's capable everyday model.",
            {"thinking": {"type": "between_tools"}}, suggested=True),
    _claude("claude-sonnet-5", "Claude Sonnet 5", SMART, 2.00, 10.00, 0.064, "The earlier Claude Sonnet.", OFF),
    _claude("claude-sonnet-4-6", "Claude Sonnet 4.6", SMART, 3.00, 15.00, 0.08, "An older Claude Sonnet.", {}),
    _claude("claude-opus-5-5", "Claude Opus 5.5", SMART, 4.00, 20.00, 0.128,
            "Claude's most capable model. It thinks before answering, so it's slower to start.",
            {"output_config": {"effort": "low"}}, thinks=True),
    _claude("claude-opus-5", "Claude Opus 5", SMART, 5.00, 25.00, 0.16, "The earlier Claude Opus.", OFF),
    _gemini("gemini-4-argon", "Gemini 4 Argon", SMART, "gemini-4-argon", 4.00, 20.00, 0.128, "Google's most capable model.",
            level="low"),
    _gemini("gemini-3.8-flash", "Gemini 3.8 Flash", SMART, "gemini-3.8-flash", 1.50, 7.50, 0.048, "Google's newest Flash model.",
            level="low"),
    _gemini("gemini-3.7-flash", "Gemini 3.7 Flash", SMART, "gemini-3.7-flash", 1.50, 7.50, 0.048, "A recent Flash model.",
            level="low"),
    _gemini("gemini-3.6-flash", "Gemini 3.6 Flash", SMART, "gemini-3.6-flash", 1.50, 7.50, 0.024, "A recent Flash model."),
    _gemini("gemini-3.5-flash", "Gemini 3.5 Flash", SMART, "gemini-3.5-flash", 1.50, 9.00, 0.048, "A capable Flash model.",
            first_words=1.2),
    _gemini("gemini-3-flash", "Gemini 3 Flash", SMART, "gemini-3-flash-preview", 0.50, 3.00, 0.016,
            "An earlier Flash model, at a lower cost.", first_words=1.2),
]
_KEYS = {"groq": "GROQ_API_KEY", "sarvam": "SARVAM_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
         "anthropic": "ANTHROPIC_API_KEY"}


def _credits(m: AiModel) -> float:
    price = m.cost_inr * MARKUP
    if m.retell:
        price = max(m.cost_inr * MIN_MARKUP, min(price, m.retell * USD_INR_RATE * BELOW_RETELL))
    return max(0.01, math.ceil(round(price / CREDIT_INR * 100, 6)) / 100)


def _priced(models: list[AiModel]) -> list[AiModel]:
    try:
        rates = json.loads(os.getenv("VOICE_MODEL_CREDITS_JSON") or "{}")
    except ValueError:
        rates = {}
    hidden = {m.strip() for m in os.getenv("VOICE_HIDDEN_MODELS", "").split(",") if m.strip()}
    return [replace(m, credits=float(rates.get(m.id, _credits(m)))) for m in models if m.id not in hidden or m.id == DEFAULT]


AI_MODELS = _priced(AI_MODELS)
AI_MODELS_BY_ID = {m.id: m for m in AI_MODELS}


def ai_model(model_id: Optional[str]) -> AiModel:
    """The agent's model; the default when none is chosen, or one that's no longer offered."""
    return AI_MODELS_BY_ID.get(model_id or DEFAULT) or AI_MODELS_BY_ID[DEFAULT]


def available(m: AiModel) -> bool:
    """Its service is set up on this server (ChatGPT's models need an OpenAI key, Claude's an Anthropic key)."""
    return bool(os.getenv(_KEYS[m.runs_on]))


def call_model(model_id: Optional[str]) -> AiModel:
    """The model a call asks first: the agent's, or the default while that one isn't set up."""
    m = ai_model(model_id)
    return m if available(m) else ai_model(DEFAULT)


def per_minute(m: AiModel) -> float:
    return round(BASE_CREDITS + m.credits, 2)


def by_service_name(name: str) -> AiModel:
    """The catalog model behind a service's model name (the backups in llm.stream_reply), or the default."""
    return next((m for m in AI_MODELS if m.model == name), ai_model(DEFAULT))


def public(m: AiModel, credits_left: Optional[float] = None) -> dict:
    data = {"id": m.id, "name": m.name, "maker": m.maker, "group": m.group, "about": m.about,
            "credits_per_minute": per_minute(m), "model_credits": m.credits, "first_words_sec": m.first_words,
            "available": available(m), "suggested": m.suggested, "preview": m.preview, "functions": m.functions}
    if credits_left is not None:
        data["minutes_left"] = round(max(credits_left, 0) / per_minute(m), 1)
    return data
