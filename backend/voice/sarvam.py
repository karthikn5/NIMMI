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
import wave
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from urllib.parse import urlencode

import httpx
import websockets

from voice.catalog import STT_MODEL, TTS_MODEL

logger = logging.getLogger(__name__)

STT_WS_URL = "wss://api.sarvam.ai/speech-to-text/ws"
TTS_URL = "https://api.sarvam.ai/text-to-speech"


class SarvamError(Exception):
    pass


async def _connect_ws(url: str, attempts: int = 3):
    """Open a Sarvam WebSocket, retrying a slow or failed handshake (seen occasionally in testing)."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return await websockets.connect(url, additional_headers={"Api-Subscription-Key": api_key()},
                                            max_size=2**22, open_timeout=8)
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
                    yield SttEvent("transcript", text, data.get("language_code"))
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
        self.config = {
            "language_code": language, "speaker": speaker, "model": TTS_MODEL,
            "pace": max(0.5, min(2.0, pace)), "speech_sample_rate": str(sample_rate), "output_audio_codec": "linear16",
            "enable_preprocessing": True,
        }
        self._ws = None

    async def _connect(self):
        self._ws = await _connect_ws(f"{TTS_WS_URL}?model={TTS_MODEL}&send_completion_event=true")
        await self._ws.send(json.dumps({"type": "config", "data": self.config}))

    async def close(self):
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        if self._ws is None:
            await self._connect()
        finished = False
        try:
            await self._ws.send(json.dumps({"type": "text", "data": {"text": text[:2500]}}))
            await self._ws.send(json.dumps({"type": "flush"}))
            async for raw in self._ws:
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "audio":
                    chunk = base64.b64decode(msg["data"]["audio"])
                    yield _wav_to_pcm(chunk) if chunk[:4] == b"RIFF" else chunk
                elif kind == "event" and (msg.get("data") or {}).get("event_type") == "final":
                    finished = True
                    return
                elif kind == "error":
                    raise SarvamError(str((msg.get("data") or {}).get("message")))
        finally:
            if not finished:
                await self.close()  # interrupted or failed: start clean next time


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
    async with httpx.AsyncClient(timeout=20) as client:
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
