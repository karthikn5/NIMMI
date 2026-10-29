"""The chat AI's providers: Groq answers first for an assistant set to it, and Gemini when Groq can't."""
from types import SimpleNamespace

import pytest

import ai


class FakeGroq:
    def __init__(self, answer=None, error=None, chunks=None, break_after=None, refuse=()):
        self.answer, self.error, self.chunks, self.break_after, self.calls = answer, error, chunks, break_after, []
        self.refuse = set(refuse)  # models that say no (a rate limit)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if kwargs["model"] in self.refuse:
            raise RuntimeError(f"429 rate limit for {kwargs['model']}")
        if kwargs.get("stream"):
            def stream():
                for i, piece in enumerate(self.chunks):
                    if self.break_after is not None and i == self.break_after:
                        raise RuntimeError("connection lost")
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
            return stream()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))])


@pytest.fixture
def gemini(monkeypatch):
    used = []
    monkeypatch.setattr(ai, "_gemini", lambda *a, **k: used.append(k) or "From Gemini")
    def stream(*a, **k):
        used.append(k)
        yield "From "
        yield "Gemini"
    monkeypatch.setattr(ai, "_gemini_stream", stream)
    return used


def test_groq_answers_first(monkeypatch, gemini):
    fake = FakeGroq(answer="From Groq", chunks=["From ", "Groq"])
    monkeypatch.setattr(ai, "_groq", lambda key: fake)
    assert ai.chat("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq") == "From Groq"
    assert "".join(ai.chat_stream("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq")) == "From Groq"
    assert not gemini
    assert fake.calls[0]["model"] == ai.GROQ_CHAT_MODEL and fake.calls[0]["extra_body"] == {"reasoning_effort": "low"}
    assert fake.calls[0]["messages"][0] == {"role": "system", "content": "Be brief."}


def test_gemini_answers_when_groq_cant(monkeypatch, gemini):
    monkeypatch.setattr(ai, "_groq", lambda key: FakeGroq(error=RuntimeError("429 rate limit")))
    assert ai.chat("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq") == "From Gemini"
    assert "".join(ai.chat_stream("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq")) == "From Gemini"
    assert gemini[0]["api_key"] is None  # Nimmi's own Gemini key, not the assistant's Groq key


def test_a_groq_answer_cut_off_isnt_started_again(monkeypatch, gemini):
    monkeypatch.setattr(ai, "_groq", lambda key: FakeGroq(chunks=["Our plans ", "start at ", "Rs 999."], break_after=2))
    assert "".join(ai.chat_stream("Be brief.", [{"role": "user", "content": "Price?"}], provider="groq")) == "Our plans start at "
    assert not gemini


def test_a_refused_groq_model_hands_over_to_the_next(monkeypatch, gemini):
    first, second = ai.GROQ_CHAT_MODELS[:2]
    fake = FakeGroq(answer="From the second", chunks=["From ", "the second"], refuse={first})
    monkeypatch.setattr(ai, "_groq", lambda key: fake)
    assert ai.chat("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq") == "From the second"
    assert "".join(ai.chat_stream("Be brief.", [{"role": "user", "content": "Hi"}], provider="groq")) == "From the second"
    assert [c["model"] for c in fake.calls] == [first, second, first, second] and not gemini
