"""Voice credits: what a call costs on each AI model, the free credits, packs, and the model an agent answers with."""
import importlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import update
from sqlalchemy.future import select

from database import async_session
from backend.models import CallbackJob, CallbackSettings, VoiceAgent, VoiceWallet
from tests.test_pipeline import Ev, FakeTransport, _call, _setup, replier_saying
from voice import ai_models, catalog, llm, metering, pipeline, scheduler, twilio


def _set_wallet(run, user_id, **values):
    async def go():
        async with async_session() as db:
            await metering.get_wallet(db, user_id)
            await db.execute(update(VoiceWallet).where(VoiceWallet.user_id == user_id).values(**values))
            await db.commit()
    run(go)


def _wallet(run, user_id) -> VoiceWallet:
    async def go():
        async with async_session() as db:
            return await metering.get_wallet(db, user_id)
    return run(go)


def test_half_minute_steps_at_the_calls_rate():
    assert metering.call_credits(0, 1) == 0
    assert metering.call_credits(1, 1) == 0.5 and metering.call_credits(30, 1) == 0.5
    assert metering.call_credits(31, 1) == 1 and metering.call_credits(61, 1) == 1.5
    assert metering.call_credits(61, 1.5) == 2.25 and metering.call_credits(600, 1.5) == 15
    assert metering.call_credits(20, 1.27) == 0.64  # rounded up, never down
    assert metering.enough_for_a_call(0.5, 1) and not metering.enough_for_a_call(0.25, 1)
    assert not metering.enough_for_a_call(0.5, 1.08) and metering.enough_for_a_call(0.54, 1.08)
    assert metering.seconds_for(1.5, 1.5) == 60 and metering.seconds_for(-2, 1) == 0


def test_model_rates_follow_our_cost_and_stay_below_retell():
    by_id = ai_models.AI_MODELS_BY_ID
    assert ai_models.BASE_CREDITS == 1 and ai_models.CREDIT_INR == 4.499  # the 1,000-credit pack
    assert by_id["gpt-oss-120b"].credits == 0.08 and ai_models.per_minute(by_id["gpt-oss-120b"]) == 1.08
    assert by_id["gpt-5.4-mini"].credits == 0.40 and by_id["claude-haiku-5-5"].credits == 0.06
    assert by_id["claude-haiku-4-5"].credits == 0.45  # cost plus half would be above Retell's price
    for m in ai_models.AI_MODELS:
        price = m.credits * ai_models.CREDIT_INR
        assert price >= m.cost_inr * ai_models.MIN_MARKUP - 0.01, m.id  # always at least 15% over our cost
        if m.retell:
            ceiling = max(m.retell * catalog.USD_INR_RATE * ai_models.BELOW_RETELL, m.cost_inr * ai_models.MIN_MARKUP)
            assert price <= ceiling + 0.01 * ai_models.CREDIT_INR, m.id
    assert {m.group for m in ai_models.AI_MODELS} == {ai_models.FAST, ai_models.SMART}
    assert ai_models.ai_model(None).id == ai_models.ai_model("auto").id == ai_models.DEFAULT == "gpt-oss-120b"


def test_a_new_workspace_gets_the_free_credits(run, make_user):
    wallet = _wallet(run, make_user().id)
    assert wallet.credits == catalog.FREE_CREDITS == 10 and metering.credits_left(wallet) == 10


def test_minutes_from_before_credits_move_over_once(run, make_user):
    u = make_user()
    _set_wallet(run, u.id, credits=None, plan_credits=None, plan_credits_used=None, topup_minutes=42, plan_minutes=100,
                plan_minutes_used=20)
    wallet = _wallet(run, u.id)
    assert (wallet.credits, wallet.plan_credits, wallet.plan_credits_used) == (42, 100, 20)
    assert metering.credits_left(wallet) == 122
    _set_wallet(run, u.id, credits=7)  # spent since; the old minutes are never copied again
    assert _wallet(run, u.id).credits == 7


def test_charging_uses_plan_credits_first_and_never_goes_below_zero(run, make_user):
    u = make_user()
    _set_wallet(run, u.id, plan_credits=2, plan_credits_used=0, credits=5)

    async def charge(seconds, rate):
        async with async_session() as db:
            return await metering.charge(db, u.id, seconds, rate)
    assert run(charge, 90, 1.5) == 2.25  # three half-minutes at 1.5 a minute
    wallet = _wallet(run, u.id)
    assert (wallet.plan_credits_used, wallet.credits) == (2, 4.75)
    assert run(charge, 600, 1) == 10
    assert metering.credits_left(_wallet(run, u.id)) == 0


def test_a_call_costs_its_models_rate_and_is_logged(run, make_user, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    u = make_user()
    bot = u.bot()

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, ai_model="gemini-3-flash")
        return await _call(setup, t, [Ev("speech_start"), Ev("transcript", "Fees?"), Ev("transcript", "ok bye")],
                           replier_saying("One lakh a year."))
    _, log = run(scenario)
    rate = ai_models.per_minute(ai_models.ai_model("gemini-3-flash"))
    assert rate == 1.27 and log.ai_model == "gemini-3-flash" and log.credits_used == 0.64 and log.billed_minutes == 1
    assert log.reply_ms is not None
    assert _wallet(run, u.id).credits == 9.36


def test_turns_a_backup_answered_cost_the_backups_rate(run, make_user):
    u = make_user()
    bot = u.bot()

    async def busy_own_model(bot, agent, history, text, direction, consent, answered=None, **_):
        answered.append("gpt-5.4-mini")  # what llm.stream_reply records when a backup answers
        yield "Sure.", None

    async def scenario():
        setup = await _setup(u.id, bot)  # the default model, GPT-OSS 120B
        return await _call(setup, FakeTransport(), [Ev("speech_start"), Ev("transcript", "Fees?"), Ev("transcript", "ok bye")],
                           busy_own_model)
    _, log = run(scenario)
    assert log.credits_used == metering.call_credits(1, 1 + ai_models.ai_model("gpt-5.4-mini").credits) == 0.7


def test_a_model_that_isnt_set_up_is_billed_as_the_default(run, make_user):
    u = make_user()
    bot = u.bot()

    async def scenario():
        setup = await _setup(u.id, bot, ai_model="gpt-5.4-mini")  # no OpenAI key here
        return await _call(setup, FakeTransport(), [Ev("speech_start"), Ev("transcript", "ok bye")], replier_saying("Sure."))
    _, log = run(scenario)
    assert log.ai_model == "gpt-oss-120b" and log.credits_used == 0.54


def test_the_call_ends_when_the_credits_run_out(run, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    _set_wallet(run, u.id, credits=0.6)  # a half-minute at 1.08 a minute
    rate = ai_models.per_minute(ai_models.ai_model(None))
    monkeypatch.setattr(pipeline, "GOODBYE_SEC", metering.seconds_for(0.6, rate) - 0.5)  # so it ends after half a second

    async def scenario():
        t = FakeTransport()
        setup = await _setup(u.id, bot, silence_timeout_sec=60)
        return t, await _call(setup, t, [Ev("speech_start")], replier_saying("unused"))
    t, (_, log) = run(scenario)
    assert pipeline.TIMEOUT_REPLIES["en-IN"] in t.said() and log.outcome != "failed"
    assert log.credits_used == 0.54 and abs(_wallet(run, u.id).credits - 0.06) < 1e-9


def test_the_dialler_skips_calls_the_credits_cant_pay_for(run, make_user, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    dialled = []

    async def fake_place(to, frm, job_id, **_):
        dialled.append(job_id)
        return "CA-credits"
    monkeypatch.setattr(twilio, "place_call", fake_place)
    u = make_user()
    bot = u.bot()
    _set_wallet(run, u.id, credits=0.6)  # half a minute at the default rate, but its agent uses Gemini 3 Flash (1.27)

    async def queue():
        async with async_session() as db:
            db.add(VoiceAgent(bot_id=bot, user_id=u.id, enabled=True, voice_id="priya", ai_model="gemini-3-flash"))
            db.add(CallbackSettings(user_id=u.id, enabled=True, window_start="00:00", window_end="23:59"))
            job = CallbackJob(user_id=u.id, bot_id=bot, e164="+919876543210", consent_source="test", status="queued",
                              next_attempt_at=datetime.utcnow() - timedelta(minutes=1))
            db.add(job)
            await db.commit()
            return job.id
    job_id = run(queue)
    run(scheduler.dispatch_due_callbacks)

    async def job():
        async with async_session() as db:
            return (await db.execute(select(CallbackJob).where(CallbackJob.id == job_id))).scalars().first()
    done = run(job)
    assert done.status == "failed" and done.last_error == "No voice credits left" and job_id not in dialled


def test_the_agents_model_answers_first_then_the_backups(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm, "_rate_limited", {})
    calls = []

    def sarvam(url, headers, body, limit):
        calls.append((body["model"], limit))
        yield "From Sarvam."
    monkeypatch.setattr(llm, "_stream_openai_style", sarvam)
    monkeypatch.setattr(llm, "_stream_groq", lambda model, *a: iter([f"From {model}."]))
    bot, answered = llm.Bot(bot_name="Desk"), []
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "sarvam-105b", answered)) == "From Sarvam."
    assert calls == [("sarvam-105b-conversations", llm.GROQ_FIRST_WORDS_SEC)] and answered == ["sarvam-105b"]
    assert "".join(llm.stream_reply(bot, "p", [], "hi", None, answered)) == "From openai/gpt-oss-120b."  # the default

    class Busy(Exception):
        status_code = 429

    def busy(url, headers, body, limit):
        raise Busy("rate_limit_exceeded")
        yield  # pragma: no cover
    monkeypatch.setattr(llm, "_stream_openai_style", busy)
    answered.clear()
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "sarvam-105b", answered)) == "From qwen/qwen3.8-27b."
    assert "sarvam-105b" in llm._rate_limited and answered == ["qwen-3.8-27b"]  # billed as the backup that answered

    def cut(url, headers, body, limit):
        yield "Half an"
        raise ConnectionError("dropped")
    monkeypatch.setattr(llm, "_rate_limited", {})
    monkeypatch.setattr(llm, "_stream_openai_style", cut)
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "sarvam-105b")) == "Half an"  # no second answer after it


def test_a_chosen_gemini_model_is_asked_alone_without_thinking(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    seen = []

    def google(request):
        seen.append(request)
        return httpx.Response(200, text='data: {"candidates": [{"content": {"parts": [{"text": "From Gemini."}]}}]}\n\n')
    monkeypatch.setattr(llm, "_http", httpx.Client(transport=httpx.MockTransport(google)))
    out = "".join(llm.stream_reply(llm.Bot(bot_name="Desk"), "p", [{"role": "assistant", "content": "Hello"}], "hi",
                                   "gemini-3-flash"))
    body = json.loads(seen[0].content)
    assert out == "From Gemini." and seen[0].url.path.endswith("/gemini-3-flash-preview:streamGenerateContent")
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"} and "tools" not in body
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]  # Gemini needs the caller first


def _chunks(*pieces):
    return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))]) for p in pieces]


class _Stream(list):
    closed = False

    def close(self):
        self.closed = True


def test_chatgpt_models_answer_without_reasoning_first(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    sent = []

    class Completions:
        def create(self, **kw):
            sent.append(kw)
            return _Stream(_chunks(None, "Hello", " there."))
    monkeypatch.setattr(llm, "_openai_client", SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    bot = llm.Bot(bot_name="Desk")
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "gpt-5.4-mini")) == "Hello there."
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "gpt-5-mini")) == "Hello there."
    assert "".join(llm.stream_reply(bot, "p", [], "hi", "gpt-4.1-mini")) == "Hello there."
    assert [k.get("reasoning_effort") for k in sent] == ["none", "minimal", None]
    assert all(k["max_completion_tokens"] == 300 and "temperature" not in k for k in sent)


class _ClaudeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, *exc):
        return False


def test_claude_models_answer_without_thinking_and_cache_the_instructions(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "")
    sent = []
    events = [SimpleNamespace(type="message_start"),
              SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Vanakkam."))]

    class Messages:
        def stream(self, **kw):
            sent.append(kw)
            return _ClaudeStream(events)
    monkeypatch.setattr(llm, "_anthropic_client", SimpleNamespace(messages=Messages()))
    history = [{"role": "assistant", "content": "Hello, how can I help?"}]
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Desk"), "p", history, "hi", "claude-haiku-5-5")) == "Vanakkam."
    kw = sent[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["thinking"] == {"type": "disabled"} and kw["max_tokens"] == 300
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and "temperature" not in kw
    assert [m["role"] for m in kw["messages"]] == ["user", "assistant", "user"]  # Claude needs the caller first
    llm.stream_reply(llm.Bot(bot_name="Desk"), "p", [], "hi", "claude-sonnet-5-5").__next__()
    assert sent[-1]["thinking"] == {"type": "between_tools"}

    # Still thinking when its time is up: a backup answers that turn instead (Gemini, as Groq is off here).
    monkeypatch.setattr(llm, "CHOSEN_FIRST_WORDS_SEC", {ai_models.FAST: 0.0, ai_models.SMART: 0.0})
    monkeypatch.setattr(llm, "_rate_limited", {})
    events[:] = [SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="thinking_delta", thinking=""))]
    monkeypatch.setattr(llm, "_stream_gemini", lambda *a: iter(["From the backup."]))
    answered = []
    assert "".join(llm.stream_reply(llm.Bot(bot_name="Desk"), "p", [], "hi", "claude-opus-5-5", answered)) == "From the backup."
    assert sent[-1]["output_config"] == {"effort": "low"} and "thinking" not in sent[-1]
    assert answered == [ai_models.DEFAULT] and "claude-opus-5-5" in llm._rate_limited


def test_agents_pick_a_model_per_direction(client, make_user, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    u = make_user()
    bot = u.bot()
    base = client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()
    assert base["ai_model"] == "gpt-oss-120b"
    body = {**base, "voice_id": "priya", "ai_model": "gemini-3-flash"}
    saved = client.put(f"/api/voice/agents/{bot}?direction=inbound", json=body, headers=u.h())
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai_model"] == "gemini-3-flash"
    assert client.get(f"/api/voice/agents/{bot}", headers=u.h()).json()["ai_model"] == "gpt-oss-120b"  # the outgoing one's own
    assert client.put(f"/api/voice/agents/{bot}", json={**body, "ai_model": "gpt-9"}, headers=u.h()).status_code == 400
    no_key = client.put(f"/api/voice/agents/{bot}", json={**body, "ai_model": "gpt-5.4-mini"}, headers=u.h())
    assert no_key.status_code == 400 and "isn't available" in no_key.json()["detail"]
    # Without the model in the request (an older dashboard), the saved choice stays.
    older = {k: v for k, v in body.items() if k != "ai_model"}
    assert client.put(f"/api/voice/agents/{bot}?direction=inbound", json=older, headers=u.h()).json()["ai_model"] == "gemini-3-flash"

    models = client.get("/api/voice/models", headers=u.h()).json()
    by_id = {m["id"]: m for m in models["models"]}
    assert models["credits_left"] == 10 and models["billing_step_sec"] == 30 and models["base_credits"] == 1
    assert by_id["gemini-3-flash"]["credits_per_minute"] == 1.27 and by_id["gemini-3-flash"]["minutes_left"] == 7.9
    assert by_id["gemini-3-flash"]["available"] and not by_id["gpt-5.4-mini"]["available"]
    assert set(models["groups"]) == {"fast", "smart"} and models["default"] == "gpt-oss-120b"

    details = client.get(f"/api/voice/agents/{bot}/details?direction=inbound", headers=u.h()).json()
    assert details["credits_per_minute"] == 1.27 and details["model"]["id"] == "gemini-3-flash"
    assert details["prompt_tokens"] > 500 and details["reply_sec_expected"] == 1.55 and details["reply_sec_measured"] is None


def test_the_public_rate_card_lists_only_models_that_are_set_up(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    card = client.get("/api/voice/rates").json()  # no sign-in: the website shows it
    ids = {m["id"] for m in card["models"]}
    assert {"gpt-oss-120b", "qwen-3.8-27b"} <= ids and "gpt-5.4-mini" not in ids and "sarvam-105b" not in ids
    assert card["base_credits"] == 1 and card["free_credits"] == 10 and card["packs"][0]["credits"] == 100
    assert "minutes_left" not in card["models"][0]


def test_rates_and_packs_can_change_without_a_deploy(monkeypatch):
    monkeypatch.setenv("VOICE_MODEL_CREDITS_JSON", '{"gemini-3-flash": 2}')
    monkeypatch.setenv("VOICE_HIDDEN_MODELS", "gpt-6-astra")
    monkeypatch.setenv("VOICE_PACKS_JSON", '[{"id": "old", "minutes": 50, "price": 299}]')
    try:
        importlib.reload(catalog)
        fresh = importlib.reload(ai_models)
        assert fresh.ai_model("gemini-3-flash").credits == 2 and fresh.per_minute(fresh.ai_model("gemini-3-flash")) == 3
        assert "gpt-6-astra" not in fresh.AI_MODELS_BY_ID and fresh.ai_model("gpt-6-astra").id == fresh.DEFAULT
        assert catalog.PACKS == [{"id": "old", "minutes": 50, "price": 299, "credits": 50}]  # minutes from before credits
        assert fresh.CREDIT_INR == 5.98
    finally:
        for name in ("VOICE_MODEL_CREDITS_JSON", "VOICE_HIDDEN_MODELS", "VOICE_PACKS_JSON"):
            monkeypatch.delenv(name)
        importlib.reload(catalog)
        importlib.reload(ai_models)
