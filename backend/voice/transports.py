"""Audio transports for CallSession: the browser test panel and Exotel phone calls."""
import base64
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class BrowserTransport:
    """
    Browser <-> server over one WebSocket.
    Client sends binary frames of 16 kHz PCM16 mono, or JSON {"type": "hangup"}.
    Server sends binary PCM16 for playback and JSON events (agent/caller text, clear, ended).
    """
    provider = "browser"  # whose call it is (a hand-off to a person says where it goes)
    sample_rate = 16000

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.closed = False

    async def receive(self) -> Optional[bytes]:
        while True:
            try:
                msg = await self.ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return None
            if msg.get("type") == "websocket.disconnect":
                self.closed = True
                return None
            if msg.get("bytes"):
                return msg["bytes"]
            if msg.get("text"):
                try:
                    if json.loads(msg["text"]).get("type") == "hangup":
                        return None
                except ValueError:
                    pass

    async def play(self, pcm: bytes) -> None:
        if not self.closed:
            await self.ws.send_bytes(pcm)

    async def clear(self) -> None:
        await self.event({"type": "clear"})

    async def event(self, data: dict) -> None:
        if not self.closed:
            try:
                await self.ws.send_text(json.dumps(data))
            except Exception:
                self.closed = True

    async def hangup(self, reason: str) -> None:
        await self.event({"type": "hangup", "reason": reason})


class ExotelTransport:
    """
    Exotel Voicebot applet over a bidirectional WebSocket: 8 kHz PCM16 mono,
    base64 in JSON events (connected, start, media, mark, dtmf, stop).
    """
    provider = "exotel"  # whose call it is (a hand-off to a person says where it goes)
    sample_rate = 8000
    CHUNK = 3200  # 200 ms; Exotel wants multiples of 320 bytes

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.from_number: Optional[str] = None
        self.to_number: Optional[str] = None
        self.custom: dict = {}
        self.closed = False
        self.end_reason = "done"
        self._carry = b""  # audio shorter than one 320-byte frame, sent with the next chunk

    async def wait_for_start(self) -> bool:
        """Read events until 'start' arrives. Returns False if the stream ends first."""
        while True:
            try:
                raw = await self.ws.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                return False
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "start":
                start = msg.get("start") or {}
                self.stream_sid = start.get("stream_sid") or msg.get("stream_sid")
                self.call_sid = start.get("call_sid")
                self.from_number = start.get("from")
                self.to_number = start.get("to")
                self.custom = start.get("custom_parameters") or {}
                return True
            if event == "stop":
                return False

    async def receive(self) -> Optional[bytes]:
        while True:
            try:
                raw = await self.ws.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return None
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "media":
                payload = (msg.get("media") or {}).get("payload")
                if payload:
                    return base64.b64decode(payload)
            elif event == "stop":
                self.closed = True
                return None

    async def play(self, pcm: bytes) -> None:
        """Send audio in 320-byte multiples; a partial tail waits for the next chunk (streamed TTS)."""
        if self.closed:
            return
        pcm = self._carry + pcm
        usable = len(pcm) - len(pcm) % 320
        self._carry = pcm[usable:]
        for i in range(0, usable, self.CHUNK):
            await self.ws.send_text(json.dumps({
                "event": "media", "stream_sid": self.stream_sid,
                "media": {"payload": base64.b64encode(pcm[i:min(i + self.CHUNK, usable)]).decode()},
            }))

    async def clear(self) -> None:
        self._carry = b""
        if not self.closed:
            await self.ws.send_text(json.dumps({"event": "clear", "stream_sid": self.stream_sid}))

    async def event(self, data: dict) -> None:
        return None  # nothing to show on a phone call

    async def hangup(self, reason: str) -> None:
        """Closing the stream hands the call back to the Exotel flow (transfer or hang up)."""
        self.end_reason = reason
        if not self.closed:
            self.closed = True
            try:
                await self.ws.close()
            except Exception:
                pass


class TwilioTransport:
    """
    Twilio Media Streams over a bidirectional WebSocket (<Connect><Stream>):
    8 kHz G.711 mu-law, base64 in JSON events (connected, start, media, mark, stop).
    """
    provider = "twilio"  # whose call it is (a hand-off to a person says where it goes)
    sample_rate = 8000

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.params: dict = {}
        self.closed = False

    async def wait_for_start(self) -> bool:
        while True:
            try:
                msg = json.loads(await self.ws.receive_text())
            except (WebSocketDisconnect, RuntimeError):
                return False
            if msg.get("event") == "start":
                start = msg.get("start") or {}
                self.stream_sid = start.get("streamSid") or msg.get("streamSid")
                self.call_sid = start.get("callSid")
                self.params = start.get("customParameters") or {}
                return True
            if msg.get("event") == "stop":
                return False

    async def receive(self) -> Optional[bytes]:
        from voice.twilio import ulaw_to_pcm
        while True:
            try:
                msg = json.loads(await self.ws.receive_text())
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return None
            event = msg.get("event")
            if event == "media":
                payload = (msg.get("media") or {}).get("payload")
                if payload:
                    return ulaw_to_pcm(base64.b64decode(payload))
            elif event == "stop":
                self.closed = True
                return None

    async def play(self, pcm: bytes) -> None:
        from voice.twilio import pcm_to_ulaw
        if self.closed or not pcm:
            return
        await self.ws.send_text(json.dumps({
            "event": "media", "streamSid": self.stream_sid,
            "media": {"payload": base64.b64encode(pcm_to_ulaw(pcm)).decode()},
        }))

    async def clear(self) -> None:
        if not self.closed:
            await self.ws.send_text(json.dumps({"event": "clear", "streamSid": self.stream_sid}))

    async def event(self, data: dict) -> None:
        return None

    async def hangup(self, reason: str) -> None:
        """Closing the stream continues the TwiML: the <Connect> action decides transfer or hang up."""
        if not self.closed:
            self.closed = True
            try:
                await self.ws.close()
            except Exception:
                pass
