"""Knowledge sources as a list (add, refresh, remove), whole-site crawl and visitor answer ratings."""
import knowledge_sources
from routers import bots as bots_router
from routers import chat as chat_router


def test_sources_split_put_and_remove():
    text = "Open 9 to 7.\n\n--- Source: https://a.com ---\nOld A\n\n--- YouTube Source ---\nVideo words"
    assert [s["kind"] for s in knowledge_sources.listing(text)] == ["website", "youtube"]
    text = knowledge_sources.put(text, "https://a.com", "New A")  # re-adding refreshes, never duplicates
    written, blocks = knowledge_sources.split(text)
    assert written == "Open 9 to 7." and blocks.count(("https://a.com", "New A")) == 1 and len(blocks) == 2
    text, removed = knowledge_sources.remove(text, "YouTube video")
    assert removed and "Video words" not in text and text.startswith("Open 9 to 7.")


def test_crawl_whole_site_then_remove_a_page(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()

    async def safe(url):
        return url

    async def fake_site(url, max_pages):
        assert max_pages == 10
        return [(url, "Home page"), (url + "/pricing", "2BHK from 58 lakhs")]
    monkeypatch.setattr(bots_router, "assert_public_url", safe)
    monkeypatch.setattr(bots_router, "crawl_site", fake_site)

    r = client.post("/api/knowledge/crawl", json={"bot_id": bot, "url": "https://homes.example", "pages": 10}, headers=u.h())
    assert r.status_code == 200 and r.json()["pages"] == 2, r.text
    names = [s["name"] for s in client.get(f"/api/bots/{bot}/knowledge/sources", headers=u.h()).json()["sources"]]
    assert names == ["https://homes.example", "https://homes.example/pricing"]

    # Crawling again refreshes the same pages instead of adding copies.
    client.post("/api/knowledge/crawl", json={"bot_id": bot, "url": "https://homes.example", "pages": 10}, headers=u.h())
    assert len(client.get(f"/api/bots/{bot}/knowledge/sources", headers=u.h()).json()["sources"]) == 2

    r = client.delete(f"/api/bots/{bot}/knowledge/sources", params={"name": "https://homes.example/pricing"}, headers=u.h())
    assert r.status_code == 200 and "58 lakhs" not in r.json()["knowledge_base"]
    assert client.delete(f"/api/bots/{bot}/knowledge/sources", params={"name": "nope"}, headers=u.h()).status_code == 404


def test_unhelpful_rating_goes_to_questions(client, make_user, monkeypatch):
    u = make_user()
    bot = u.bot()
    monkeypatch.setattr(chat_router, "generate_ai_response", lambda *a, **k: "We have parking.")
    r = client.post("/api/chat/message", json={"bot_id": bot, "message": "Is there visitor parking?", "visitor_session_id": "s-rate",
                                               "history": [], "is_demo": True}, headers=u.h())
    assert r.status_code == 200, r.text

    body = {"bot_id": bot, "visitor_session_id": "s-rate", "question": "Is there visitor parking?", "helpful": False}
    assert client.post("/api/chat/feedback", json=body).status_code == 200
    assert client.post("/api/chat/feedback", json={**body, "visitor_session_id": "never-chatted"}).status_code == 404
    items = client.get("/api/questions", headers=u.h()).json()["items"]
    assert [q["question"] for q in items] == ["Is there visitor parking?"]
