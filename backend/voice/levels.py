"""
How loud the caller's side of a call is, 20 ms at a time: to tell the caller's own voice from the quieter sound
around them. The speech recognizer takes any speech-like sound for speech, however faint. On real calls (Oct 2026)
sound in the caller's room came through as "caller" lines in random languages ("नमस्कार", "this friend.", "ஆ")
and the agent answered them; talk in the background (a TV) kept the recognizer from ever ending the caller's
turn. The caller's own voice, close to the phone, was 20-35 dB louder than all of it.
"""
import math
from array import array
from collections import deque
from statistics import median
from typing import Optional

FRAME_SEC = 0.02
# A turn is the room when its loud part (the 90th percentile of its 20 ms levels) is this far below the caller's
# usual level. Replaying two real calls: the caller's own lines were at most 7 dB below it, the room's lines 19 dB
# or more; a TV 20 dB quieter than the caller (simulated) 20 dB.
BACKGROUND_DB = 12.0
VOICE_RANGE_DB = 15.0  # 20 ms this close to the caller's usual level is their voice
# Before the caller's level is known, a voice close to the phone is at least this loud (theirs on the real calls:
# -9 to -17 dBFS at its loudest; that simulated TV never came above -28).
FIRST_VOICE_DB = -24.0
JUDGE_SEC = 0.3    # with less audio than this to go by, nothing is decided (it's taken for the caller, as before)
TURNS_KEPT = 6     # the caller's usual level comes from their latest turns
KEEP_SEC = 30.0


class CallerLevels:
    def __init__(self, rate: int):
        self.frame_bytes = int(rate * FRAME_SEC) * 2
        self._carry = b""
        self.frames: deque = deque(maxlen=int(KEEP_SEC / FRAME_SEC))  # (arrival time, dBFS), 20 ms each
        self.turns: deque = deque(maxlen=TURNS_KEPT)                   # how loud each of the caller's turns was

    def add(self, pcm: bytes, now: float) -> list[float]:
        """Measure audio that just arrived: the level of each whole 20 ms of it."""
        data = self._carry + pcm
        count = len(data) // self.frame_bytes
        self._carry = data[count * self.frame_bytes:]
        levels = []
        for i in range(count):
            samples = array("h")
            samples.frombytes(data[i * self.frame_bytes:(i + 1) * self.frame_bytes])
            level = 20 * math.log10(max(math.sqrt(sum(s * s for s in samples) / len(samples)), 0.5) / 32768)
            self.frames.append((now - (count - 1 - i) * FRAME_SEC, level))
            levels.append(level)
        return levels

    @property
    def voice(self) -> Optional[float]:
        """The caller's usual level when they talk; unknown until they've said something. Quieter turns (the room,
        taken for the caller before their level was known) don't count once they've been heard."""
        if not self.turns:
            return None
        loudest = max(self.turns)
        return median(t for t in self.turns if t >= loudest - BACKGROUND_DB)

    def is_voice(self, level: float) -> bool:
        """This 20 ms sounds like the caller's own voice."""
        voice = self.voice
        return level >= (FIRST_VOICE_DB if voice is None else voice - VOICE_RANGE_DB)

    def _between(self, since: float, until: float) -> list[float]:
        return [level for t, level in self.frames if since <= t <= until]

    def loud_level(self, since: float, until: float) -> Optional[float]:
        """How loud the sound between two times was in its loud part: the 90th percentile of its 20 ms levels."""
        levels = sorted(self._between(since, until))
        return levels[int(0.9 * (len(levels) - 1))] if levels else None

    def little_voice(self, since: float, until: float, seconds: float) -> bool:
        """Less than `seconds` of the caller's own voice between two times. Never decided before their level is
        known, nor without enough audio to go by."""
        levels = self._between(since, until)
        if self.voice is None or len(levels) * FRAME_SEC < JUDGE_SEC:
            return False
        return FRAME_SEC * sum(1 for level in levels if self.is_voice(level)) < seconds

    def background(self, since: float, until: float) -> bool:
        """The sound between two times was the room: its loud part far below the caller's usual level. Never decided
        before their level is known, nor without enough audio to go by."""
        levels = self._between(since, until)
        if self.voice is None or len(levels) * FRAME_SEC < JUDGE_SEC:
            return False
        return self.loud_level(since, until) < self.voice - BACKGROUND_DB

    def heard_turn(self, since: float, until: float) -> None:
        """The caller said something between these times: their usual level learns from it."""
        level = self.loud_level(since, until)
        if level is not None:
            self.turns.append(level)
