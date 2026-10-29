"""
Sarvam AI speech: streaming speech-to-text (Saaras) and text-to-speech (Bulbul).

Docs: https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe/ws
      https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
"""
import asyncio
import base64
import io
import json
import logging
import os
import time
import wave
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from urllib.parse import urlencode

import httpx
import websockets
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from voice.catalog import STT_MODEL, TTS_MODEL

logger = logging.getLogger(__name__)

STT_WS_URL = "wss://api.sarvam.ai/speech-to-text/ws"
TTS_URL = "https://api.sarvam.ai/text-to-speech"

# A sentence's audio normally starts well within a second. Nothing for this long (connecting included), or a
# gap this long mid-sentence, means the connection is stuck: the sentence is given up on (REST takes over)
# instead of leaving the caller in silence with every later sentence queued behind it.
TTS_FIRST_AUDIO_SEC = float(os.getenv("VOICE_TTS_FIRST_AUDIO_SEC", "4"))
TTS_CHUNK_GAP_SEC = float(os.getenv("VOICE_TTS_CHUNK_GAP_SEC", "3"))
# Sarvam closes a speech connection after a minute without traffic; a ping well before that keeps it open.
TTS_KEEPALIVE_SEC = 25.0


class SarvamError(Exception):
    pass


async def _connect_ws(url: str, attempts: int = 3, open_timeout: float = 8):
    """Open a Sarvam WebSocket, retrying a slow or failed handshake (seen occasionally in testing)."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return await websockets.connect(url, additional_headers={"Api-Subscription-Key": api_key()},
                                            max_size=2**22, open_timeout=open_timeout, close_timeout=2)
        except (asyncio.TimeoutError, OSError, websockets.exceptions.InvalidHandshake) as e:
            last = e
            logger.warning(f"Sarvam connect attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(0.3 * (attempt + 1))
    raise SarvamError(f"Couldn't connect to Sarvam: {last}")


def api_key() -> str:
    key = os.getenv("SARVAM_API_KEY", "")
    if not key:
        raise SarvamError("SARVAM_API_KEY is not set")
    return key


def configured() -> bool:
    return bool(os.getenv("SARVAM_API_KEY"))


@dataclass
class SttEvent:
    kind: str  # "speech_start", "speech_end", "transcript", "error"
    text: str = ""
    language: Optional[str] = None
    probability: Optional[float] = None  # how sure the recognizer is of `language` (only when detecting it)


class SttStream:
    """
    One streaming recognition session. Feed 16-bit mono PCM with `send()`;
    iterate `events()` for speech start/end signals and transcripts.
    """

    def __init__(self, language: str, sample_rate: int, code_mixed: bool):
        self.language = language
        self.sample_rate = sample_rate
        self.code_mixed = code_mixed
        self._ws = None

    async def __aenter__(self):
        params = {
            "language-code": self.language,
            "model": STT_MODEL,
            "mode": "codemix" if self.code_mixed and STT_MODEL.startswith("saaras:v3") else "transcribe",
            "sample_rate": str(self.sample_rate),
            "input_audio_codec": "pcm_s16le",
            "vad_signals": "true",
            # Normal sensitivity keeps a whole sentence as one turn; high splits at comma pauses.
            "high_vad_sensitivity": os.getenv("SARVAM_HIGH_VAD_SENSITIVITY", "false"),
            # flush() finishes the turn it's hearing at once: talk in the caller's room can keep it from ending.
            "flush_signal": "true",
        }
        self._ws = await _connect_ws(f"{STT_WS_URL}?{urlencode(params)}")
        return self

    async def __aexit__(self, *exc):
        if self._ws is not None:
            await self._ws.close()

    async def send(self, pcm: bytes) -> None:
        await self._ws.send(json.dumps({
            "audio": {"data": base64.b64encode(pcm).decode(), "encoding": "audio/wav", "sample_rate": str(self.sample_rate)}
        }))

    async def flush(self) -> None:
        await self._ws.send(json.dumps({"type": "flush"}))

    async def events(self) -> AsyncIterator[SttEvent]:
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind, data = msg.get("type"), msg.get("data") or {}
            if kind == "events":
                signal = data.get("signal_type")
                if signal == "START_SPEECH":
                    yield SttEvent("speech_start")
                elif signal == "END_SPEECH":
                    yield SttEvent("speech_end")
            elif kind == "data":
                text = (data.get("transcript") or "").strip()
                if text:
                    probability = data.get("language_probability")
                    yield SttEvent("transcript", text, data.get("language_code"),
                                   float(probability) if isinstance(probability, (int, float)) else None)
            elif kind == "error":
                yield SttEvent("error", str(data.get("error") or data))


TTS_WS_URL = "wss://api.sarvam.ai/text-to-speech/ws"


class TtsStream:
    """
    One streaming TTS connection per call. `speak(text)` yields raw PCM16 chunks
    as Sarvam produces them (first audio in roughly 0.4 s, versus 2-4 s for REST).
    If a sentence is abandoned mid-stream (barge-in), the connection is dropped
    so leftover audio can't leak into the next sentence; the next call reconnects.
    """

    def __init__(self, language: str, speaker: str, pace: float, sample_rate: int):
        self.language = language  # fixed for the connection; another language needs another stream
        self.config = {
            "language_code": language, "speaker": speaker, "model": TTS_MODEL,
            "pace": max(0.5, min(2.0, pace)), "speech_sample_rate": str(sample_rate), "output_audio_codec": "linear16",
            "enable_preprocessing": True,
        }
        self._ws = None
        self.used_at = time.monotonic()  # last traffic on the connection (for the keep-alive)

    async def _connect(self):
        # Two quick tries: a sentence is usually waiting (TTS_FIRST_AUDIO_SEC bounds the whole wait anyway).
        ws = await _connect_ws(f"{TTS_WS_URL}?model={TTS_MODEL}&send_completion_event=true", attempts=2, open_timeout=4)
        try:
            await ws.send(json.dumps({"type": "config", "data": self.config}))
        except BaseException:
            await _close_quietly(ws)
            raise
        self._ws = ws
        self.used_at = time.monotonic()

    async def open(self) -> None:
        """Connect ahead of the first sentence (otherwise the first sentence connects)."""
        if self._ws is None:
            await self._connect()

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def idle_for(self) -> float:
        return time.monotonic() - self.used_at

    async def ping(self) -> None:
        """Keep an idle connection open. One found closed is dropped, and the next sentence opens a new one."""
        ws = self._ws
        if ws is None:
            return
        try:
            if ws.state is not State.OPEN:
                raise ConnectionError("closed by Sarvam")
            await ws.send(json.dumps({"type": "ping"}))
            self.used_at = time.monotonic()
        except Exception as e:
            logger.info(f"Sarvam speech connection lost while idle ({e}); the next sentence reconnects")
            if self._ws is ws:
                self._ws = None
            await _close_quietly(ws)

    async def close(self):
        ws, self._ws = self._ws, None  # detached first: a sentence started meanwhile opens a fresh connection
        if ws is not None:
            await _close_quietly(ws)

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def speak(self, text: str, first_audio_sec: float = TTS_FIRST_AUDIO_SEC) -> AsyncIterator[bytes]:
        """Audio for `text`, in pieces as Sarvam makes it. Raises SarvamError when it hasn't started
        `first_audio_sec` after the call (connecting included) or stops for TTS_CHUNK_GAP_SEC part way: a stuck
        connection must not hold up the call. A connection kept from earlier that turns out to be closed
        (Sarvam closes idle ones) gets one fresh try within the same time, rather than going to REST (~2 s)."""
        deadline = time.monotonic() + first_audio_sec
        for attempt in (1, 2):
            if self._ws is not None and self._ws.state is not State.OPEN:
                self._ws = None  # Sarvam closed it while the caller talked: reconnect (~0.4 s)
            reused = self._ws is not None
            if self._ws is None:
                try:
                    await asyncio.wait_for(self._connect(), max(0.1, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    raise SarvamError(f"no speech connection within {first_audio_sec:.1f}s") from None
            ws, finished, started = self._ws, False, False
            try:
                try:
                    await ws.send(json.dumps({"type": "text", "data": {"text": text[:2500]}}))
                    await ws.send(json.dumps({"type": "flush"}))
                    self.used_at = time.monotonic()
                    while True:
                        wait = max(0.1, TTS_CHUNK_GAP_SEC if started else deadline - time.monotonic())
                        try:
                            raw = await asyncio.wait_for(ws.recv(), wait)
                        except asyncio.TimeoutError:
                            raise SarvamError(f"no audio for {wait:.1f}s {'mid-sentence' if started else 'after asking'}") from None
                        msg = json.loads(raw)
                        kind = msg.get("type")
                        if kind == "audio":
                            started = True
                            self.used_at = time.monotonic()
                            chunk = base64.b64decode(msg["data"]["audio"])
                            yield _wav_to_pcm(chunk) if chunk[:4] == b"RIFF" else chunk
                        elif kind == "event" and (msg.get("data") or {}).get("event_type") == "final":
                            finished = True
                            return
                        elif kind == "error":
                            raise SarvamError(str((msg.get("data") or {}).get("message")))
                except ConnectionClosed:
                    if started or not reused or attempt == 2:
                        raise
                    logger.info("Sarvam speech connection had closed while idle; trying a fresh one")
                    continue
            finally:
                if not finished:  # interrupted or failed: start clean next time
                    if self._ws is ws:
                        self._ws = None
                    await _close_quietly(ws)


async def _close_quietly(ws) -> None:
    try:
        await ws.close()
    except Exception:
        pass


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.readframes(w.getnframes())


async def synthesize(text: str, language: str, speaker: str, pace: float, sample_rate: int) -> bytes:
    """Speak `text`; returns 16-bit mono PCM at `sample_rate`."""
    payload = {
        "text": text[:2500],
        "target_language_code": language,
        "language_code": language,
        "speaker": speaker,
        "model": TTS_MODEL,
        "pace": max(0.5, min(2.0, pace)),
        "speech_sample_rate": sample_rate,
        "enable_preprocessing": True,
    }
    # The fallback for a sentence on a live call: a few seconds normally; never long enough to leave a caller waiting.
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
        resp = await client.post(TTS_URL, headers={"api-subscription-key": api_key()}, json=payload)
    if resp.status_code >= 300:
        raise SarvamError(f"TTS {resp.status_code}: {resp.text[:300]}")
    audios = resp.json().get("audios") or []
    return b"".join(_wav_to_pcm(base64.b64decode(a)) for a in audios)


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "voice_samples")
SAMPLE_LINES = {
    "en-IN": "Hi, thanks for calling. How can I help you today?",
    "hi-IN": "नमस्ते, कॉल करने के लिए धन्यवाद। मैं आपकी कैसे मदद कर सकती हूँ?",
    "ta-IN": "வணக்கம், அழைத்ததற்கு நன்றி. நான் உங்களுக்கு எப்படி உதவலாம்?",
    "te-IN": "నమస్కారం, కాల్ చేసినందుకు ధన్యవాదాలు. నేను మీకు ఎలా సహాయం చేయగలను?",
    "kn-IN": "ನಮಸ್ಕಾರ, ಕರೆ ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "ml-IN": "നമസ്കാരം, വിളിച്ചതിന് നന്ദി. ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "mr-IN": "नमस्कार, कॉल केल्याबद्दल धन्यवाद. मी तुम्हाला कशी मदत करू शकते?",
    "bn-IN": "নমস্কার, কল করার জন্য ধন্যবাদ। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    "gu-IN": "નમસ્તે, કૉલ કરવા બદલ આભાર. હું તમને કેવી રીતે મદદ કરી શકું?",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ, ਕਾਲ ਕਰਨ ਲਈ ਧੰਨਵਾਦ। ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦੀ ਹਾਂ?",
    "od-IN": "ନମସ୍କାର, କଲ୍ କରିଥିବାରୁ ଧନ୍ୟବାଦ। ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
}
_sample_lock = asyncio.Lock()


async def voice_sample(voice_id: str, language: str) -> bytes:
    """A short WAV preview of a voice, generated once and cached on disk."""
    language = language if language in SAMPLE_LINES else "en-IN"
    path = os.path.join(SAMPLE_DIR, f"{voice_id}_{language}.wav")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    async with _sample_lock:
        pcm = await synthesize(SAMPLE_LINES[language], language, voice_id, 1.0, 22050)
        wav = pcm_to_wav(pcm, 22050)
        os.makedirs(SAMPLE_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(wav)
        return wav


STT_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe(audio: bytes, filename: str, content_type: str, language: str = "unknown") -> str:
    """Text of a short recording (the chat widget's mic, and the dashboard agent's). Browsers label recordings with
    their codecs ("audio/webm;codecs=opus"), which Sarvam refuses (Oct 2026): the label goes without them, and a type
    Sarvam doesn't list (Safari's audio/mp4) is sent again as application/octet-stream, which it does."""
    kind = (content_type or "").split(";")[0].strip().lower() or "application/octet-stream"
    data = {"model": STT_MODEL, "language_code": language or "unknown"}
    async with httpx.AsyncClient(timeout=30) as client:
        for label in dict.fromkeys((kind, "application/octet-stream")):
            files = {"file": (filename or "speech.webm", audio, label)}
            resp = await client.post(STT_URL, headers={"api-subscription-key": api_key()}, files=files, data=data)
            if not (resp.status_code == 400 and "invalid file type" in resp.text.lower()):
                break
    if resp.status_code >= 300:
        raise SarvamError(f"STT {resp.status_code}: {resp.text[:300]}")
    return (resp.json().get("transcript") or "").strip()
