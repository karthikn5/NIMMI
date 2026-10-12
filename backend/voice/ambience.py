"""
Background sound for calls, engineered for professional realism without disturbance or fatigue.

Each ambience is synthesised once per sample rate as a seamless ~12 s loop,
using psychoacoustically tuned low-pass filters and soft comfort-noise profiles,
then mixed under the call with speech-aware ducking.
"""
import io
import math
import random
import wave
from array import array
from functools import lru_cache

KINDS = {
    "none": "Crystal Clean (Silent / Studio clean)",
    "subtle_room": "Subtle Room Tone (Warm & Soft acoustic floor)",
    "quiet_office": "Quiet Professional Office (Gentle air & distant presence)",
    "call_center": "Call Center Floor (Soft low-pass murmur, no harsh clicks)",
    "executive_suite": "Executive Suite (Warm acoustic room presence)",
    "cafe": "Café Ambience (Warm distant murmur)",
    "comfort_noise": "Telecom Line Warmth (Soft analog comfort tone)",
    # Backward compatibility for existing records:
    "office": "Quiet Professional Office",
    "street": "Soft Street Ambience (Distant low rumble)",
    "static": "Telecom Line Warmth",
}

# Broadcast-calibrated RMS levels (speech is ~3000-6000 RMS).
# Subtle/Low/Medium/High are designed to be comforting room tone rather than irritating noise.
VOLUMES = {
    "subtle": 40,   # -38 dB: barely perceptible acoustic warmth, prevents dead line
    "low": 85,      # -31 dB: gentle room presence
    "medium": 150,  # -26 dB: natural office/room level
    "high": 240,    # -22 dB: noticeable ambience without masking speech
}

LOOP_SECONDS = 12
FADE_SECONDS = 0.6


def _lowpass(samples: list[float], rate: int, cutoff_hz: float) -> list[float]:
    """Single-pole IIR lowpass filter to remove harsh high-frequency hiss/clicks."""
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / rate
    alpha = dt / (rc + dt)
    out = [0.0] * len(samples)
    y = 0.0
    for i, x in enumerate(samples):
        y += alpha * (x - y)
        out[i] = y
    return out


def _bandpass(samples: list[float], rate: int, low_hz: float, high_hz: float) -> list[float]:
    """Soft bandpass keeping audio in the telephony / natural comfort band."""
    lp = _lowpass(samples, rate, high_hz)
    hp_sub = _lowpass(samples, rate, low_hz)
    return [l - h for l, h in zip(lp, hp_sub)]


def _pink(n: int, rnd: random.Random) -> list[float]:
    """Pink noise (Kellet filter) for natural, warm acoustic air tone."""
    b0 = b1 = b2 = 0.0
    out = [0.0] * n
    for i in range(n):
        w = rnd.uniform(-1, 1)
        b0 = 0.99765 * b0 + w * 0.0990460
        b1 = 0.96300 * b1 + w * 0.2965164
        b2 = 0.57000 * b2 + w * 1.0526913
        out[i] = b0 + b1 + b2 + w * 0.1848
    return out


def _brown(n: int, rnd: random.Random) -> list[float]:
    """Brown noise (integrated white noise): deep, soothing room rumble."""
    v, out = 0.0, [0.0] * n
    for i in range(n):
        v = 0.995 * v + rnd.uniform(-1, 1) * 0.05
        out[i] = v
    return out


def _distant_murmur(n: int, rate: int, rnd: random.Random, layers_count: int = 3) -> list[float]:
    """
    Very soft, heavily low-pass filtered distant conversational presence (< 700 Hz).
    Uses smooth sinusoidal envelope modulations rather than abrupt steps,
    so it sounds like distant human warmth through a wall without any intelligible or jarring sounds.
    """
    out = [0.0] * n
    base_noise = _pink(n, rnd)
    # Filter strictly below 650 Hz so syllables NEVER clash with the speaker
    filtered = _lowpass(base_noise, rate, 650)
    for _ in range(layers_count):
        freq = rnd.uniform(0.15, 0.45)  # slow natural breath/cadence wave
        phase = rnd.uniform(0, 2 * math.pi)
        depth = rnd.uniform(0.3, 0.7)
        for i in range(n):
            t = i / rate
            env = 1.0 + depth * math.sin(2 * math.pi * freq * t + phase)
            out[i] += filtered[i] * env
    return out


def _ac_hum(n: int, rate: int, rnd: random.Random) -> list[float]:
    """Gentle HVAC air ventilation hum (120 Hz + 240 Hz subtle resonance + brown air)."""
    brown = _brown(n, rnd)
    out = [0.0] * n
    for i in range(n):
        t = i / rate
        hum = 0.15 * math.sin(2 * math.pi * 120 * t) + 0.08 * math.sin(2 * math.pi * 240 * t)
        out[i] = brown[i] * 0.8 + hum
    return _lowpass(out, rate, 500)


def _mix(layers: list[tuple[list[float], float]], n: int) -> list[float]:
    out = [0.0] * n
    for samples, weight in layers:
        rms = math.sqrt(sum(x * x for x in samples) / max(1, n)) or 1.0
        scale = weight / rms
        for i in range(n):
            out[i] += samples[i] * scale
    return out


@lru_cache(maxsize=32)
def loop(kind: str, rate: int) -> bytes:
    """PCM16 mono loop at `rate`, normalised to RMS 1000 (scaled down per volume when mixed)."""
    if kind not in KINDS or kind == "none":
        return b""
    fade = int(rate * FADE_SECONDS)
    n = rate * LOOP_SECONDS + fade
    rnd = random.Random(f"{kind}-{rate}")  # deterministic and repeatable

    if kind in ("subtle_room", "executive_suite"):
        # Warm, gentle acoustic room tone. No chatter, no clicks.
        layers = [(_lowpass(_pink(n, rnd), rate, 450), 0.8), (_brown(n, rnd), 0.4)]
    elif kind in ("quiet_office", "office"):
        # Executive office: subtle air circulation & deep quiet warmth
        layers = [(_ac_hum(n, rate, rnd), 0.6), (_lowpass(_pink(n, rnd), rate, 500), 0.7)]
    elif kind == "call_center":
        # Call center: softened, heavily filtered distant murmur, gentle room tone. NO harsh clicks.
        layers = [
            (_distant_murmur(n, rate, rnd, 3), 0.7),
            (_lowpass(_pink(n, rnd), rate, 600), 0.5),
            (_brown(n, rnd), 0.2),
        ]
    elif kind == "cafe":
        # Café: warm acoustic room presence, soft distant presence
        layers = [
            (_distant_murmur(n, rate, rnd, 2), 0.6),
            (_lowpass(_pink(n, rnd), rate, 550), 0.6),
            (_brown(n, rnd), 0.3),
        ]
    elif kind in ("comfort_noise", "static"):
        # Telephony comfort tone: smooth analog warmth (bandpass 200 - 2200 Hz)
        layers = [(_bandpass(_pink(n, rnd), rate, 220, 2200), 0.9)]
    elif kind == "street":
        # Soft low street rumble (deep brown noise + smooth lowpass)
        layers = [(_lowpass(_brown(n, rnd), rate, 350), 0.9), (_lowpass(_pink(n, rnd), rate, 400), 0.3)]
    else:
        layers = [(_lowpass(_pink(n, rnd), rate, 500), 1.0)]

    mixed = _mix(layers, n)

    # Seamless loop blending
    body = rate * LOOP_SECONDS
    for i in range(fade):
        w = i / fade
        mixed[i] = mixed[i] * w + mixed[body + i] * (1 - w)
    mixed = mixed[:body]
    rms = math.sqrt(sum(x * x for x in mixed) / body) or 1.0
    pcm = array("h", (max(-32767, min(32767, int(x / rms * 1000))) for x in mixed))
    return pcm.tobytes()


class AmbiencePlayer:
    """Hands out consecutive slices of the loop at the chosen volume with smooth ducking support."""

    def __init__(self, kind: str, volume: str, rate: int):
        self.pcm = loop(kind, rate)
        target = VOLUMES.get(volume or "medium", VOLUMES["medium"])
        self.factor = target / 1000.0
        self.ducked_factor = (target * 0.45) / 1000.0  # duck by ~7 dB during assistant speech
        self.is_ducked = False
        self.pos = 0

    def __bool__(self) -> bool:
        return bool(self.pcm)

    def set_ducked(self, ducked: bool) -> None:
        self.is_ducked = ducked

    def next(self, nbytes: int) -> bytes:
        if not self.pcm:
            return b"\x00" * nbytes
        out = b""
        while len(out) < nbytes:
            take = min(nbytes - len(out), len(self.pcm) - self.pos)
            out += self.pcm[self.pos:self.pos + take]
            self.pos = (self.pos + take) % len(self.pcm)
        samples = array("h")
        samples.frombytes(out)
        f = self.ducked_factor if self.is_ducked else self.factor
        return array("h", (int(x * f) for x in samples)).tobytes()


def mix(speech: bytes, ambience: bytes) -> bytes:
    """Speech over ambience (same length, PCM16); clipping-safe."""
    a, b = array("h"), array("h")
    a.frombytes(speech)
    b.frombytes(ambience)
    return array("h", (max(-32768, min(32767, x + y)) for x, y in zip(a, b))).tobytes()


def preview_wav(kind: str, volume: str = "medium", seconds: int = 6, rate: int = 16000) -> bytes:
    player = AmbiencePlayer(kind, volume, rate)
    pcm = player.next(rate * 2 * seconds) if player else b"\x00\x00" * rate * seconds
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
