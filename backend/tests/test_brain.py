"""The assistant's brain: instructions, knowledge, and learning the visitor's details from the chat."""
import json

from sqlalchemy.future import select

import brain
from database import async_session
from backend.models import Bot, Conversation
from notify import events
from routers import chat as chat_router


def _bot(**kw) -> Bot:
    return Bot(bot_id="b-1", user_id="u-1", bot_name="Kdbot", system_prompt="You are a helpful assistant.", **kw)


def test_prompt_asks_for_what_is_missing_and_never_again_for_what_is_known():
    bot = _bot(behaviour={"collect": {"fields": ["name", "phone", "email"], "custom": ["Budget"], "timing": "early"}})
    p = brain.system_prompt(bot, captured={"phone": "+919876543210", "Name": "Ravi"}, first_message=False,
                            channel="chat", knowledge_text="2BHK from 65 lakh")
    assert "Already known, never ask again: Name: Ravi; Phone number: +919876543210." in p
    assert "Still needed: Email, Budget." in p and "right after your first answer" in p
    assert "2BHK from 65 lakh" in p and "Never invent prices" in p and "Don't introduce yourself again" in p

    done = brain.system_prompt(bot, captured={"name": "Ravi", "phone": "+919876543210", "email": "r@x.in", "Budget": "70L"},
                               first_message=True, channel="whatsapp", knowledge_text="")
    assert "You have everything" in done and "Format for WhatsApp" in done and "introduce yourself" in done

    off = brain.system_prompt(_bot(behaviour={"collect": {"enabled": False}}), captured={}, first_message=False,
                              channel="chat", knowledge_text="")
    assert "Details to collect" not in off


def test_turns_do_not_repeat_the_current_message():
    history = [{"role": "assistant", "content": "Hi!"}, {"role": "user", "content": "Price?"}]
    assert brain.turns(history, "Price?") == [{"role": "assistant", "content": "Hi!"}, {"role": "user", "content": "Price?"}]


def test_small_knowledge_is_read_in_full(run, monkeypatch):
    async def no_confirmed(bot_id):
        return ""
    monkeypatch.setattr(brain.assist, "verified_answers", no_confirmed)
    small = "--- Source: https://acme.in ---\nWe open 9 to 6. Parking is free."
    assert run(brain.knowledge, _bot(knowledge_base=small), "parking?") == small

    async def search(bot_id, query, top_k):
        return [{"text": "Parking is free for 40 cars.", "source": "https://acme.in/visit"}]
    import vector_store
    monkeypatch.setattr(vector_store, "query_knowledge", search)
    big = "--- Source: Business summary ---\nAcme Realty builds homes in Chennai.\n\n--- Source: x ---\n" + "filler. " * 20000
    text = run(brain.knowledge, _bot(knowledge_base=big), "parking?")
    assert "Acme Realty builds homes" in text and "Parking is free for 40 cars." in text and len(text) < 5000


def test_details_mentioned_in_chat_are_saved(client, make_user, run, monkeypatch):
    u = make_user()
    bot_id = u.bot()
    leads = []

    async def fake_lead(conversation_id):
        leads.append(conversation_id)
    monkeypatch.setattr(events, "lead_captured", fake_lead)
    monkeypatch.setattr(brain, "_extract_with_ai", lambda fields, asked, said: {"name": "Ravi Kumar", "email": None})

    async def scenario():
        async with async_session() as db:
            conv = Conversation(bot_id=bot_id, visitor_session_id="s-learn", captured_data={})
            db.add(conv)
            await db.commit()
            bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
        learned = await brain.learn_details(conv.conversation_id, bot, "I'm Ravi, call me on 98765 43210",
                                            "Could I have your name and number?")
        async with async_session() as db:
            saved = (await db.execute(select(Conversation.captured_data).where(
                Conversation.conversation_id == conv.conversation_id))).scalar()
        return learned, saved, conv.conversation_id
    learned, saved, cid = run(scenario)
    assert learned == {"phone": "+919876543210", "name": "Ravi Kumar"}
    assert saved == {"phone": "+919876543210", "name": "Ravi Kumar"} and leads == [cid]


def test_streamed_answers_keep_their_line_breaks(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()

    def fake_stream(system, context, question, history=None, **kw):
        yield "We offer:\n\n"
        yield "- 2BHK\n- 3BHK"
    monkeypatch.setattr(chat_router, "generate_ai_response_stream", fake_stream)
    monkeypatch.setattr(brain, "learn_details", lambda *a, **k: _noop())
    r = client.post("/api/chat/message/stream", headers=u.h(),
                    json={"bot_id": bot, "message": "What do you offer?", "visitor_session_id": "s-stream", "history": [], "is_demo": True})
    pieces = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    assert "".join(pieces) == "We offer:\n\n- 2BHK\n- 3BHK"


async def _noop():
    return {}


def test_an_editor_save_keeps_the_summary_written_in_the_background(client, make_user, run):
    u = make_user()
    bot_id = u.bot()
    loaded = "Open 9 to 7.\n\n--- Source: https://homes.example ---\n2BHK from 58 lakhs"

    async def summary_arrives():
        async with async_session() as db:
            bot = (await db.execute(select(Bot).where(Bot.bot_id == bot_id))).scalars().first()
            bot.knowledge_base = loaded + "\n\n--- Source: Business summary ---\nHomes in Chennai."
            await db.commit()
    run(summary_arrives)

    # The builder still has the text it loaded before the summary, and saves an edit to it.
    assert client.patch(f"/api/bots/{bot_id}", headers=u.h(),
                        json={"knowledge_base": loaded.replace("9 to 7", "9 to 8")}).status_code == 200
    sources = client.get(f"/api/bots/{bot_id}/knowledge/sources", headers=u.h()).json()["sources"]
    assert [s["kind"] for s in sources] == ["website", "summary"]
    kb = client.get(f"/api/bots/{bot_id}/config", headers=u.h()).json()["knowledge_base"]
    assert "Open 9 to 8." in kb and "Homes in Chennai." in kb

    # Removing it from the sources list does remove it.
    client.delete(f"/api/bots/{bot_id}/knowledge/sources", params={"name": "Business summary"}, headers=u.h())
    assert "Homes in Chennai." not in client.get(f"/api/bots/{bot_id}/config", headers=u.h()).json()["knowledge_base"]


def test_search_passages_say_which_page_they_came_from():
    import vector_store
    kb = ("Open 9 to 7\n\n--- Source: https://homes.example ---\n## https://homes.example/\nWelcome\n\n"
          "## https://homes.example/pricing\n2BHK from 58 lakhs\n\n--- Source: Business summary ---\nHomes in Chennai\n\n"
          "--- Source: file: brochure.pdf ---\nAmenities")
    assert [(source, body.strip()) for source, body in vector_store._sections(kb)] == [
        ("Written knowledge", "Open 9 to 7"), ("https://homes.example/", "Welcome"),
        ("https://homes.example/pricing", "2BHK from 58 lakhs"), ("file: brochure.pdf", "Amenities")]
