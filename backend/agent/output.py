"""
What Nimmi writes, cleaned before anyone sees it. The owner's rule for everything Nimmi shows is no emojis, and
models add them anyway (GPT-OSS numbers its lists with keycaps: "1️⃣ Our Programs"). Pieces of a streamed answer
are cleaned one by one, which is safe because every character is judged on its own: an emoji split between two
pieces still goes.
"""
import re

_KEYCAP = re.compile("([0-9#*])️?⃣")  # 1️⃣ -> "1."
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF"
    "⌚⌛⏩-⏺‼⁉︎️⃣‍]")


def clean(text: str) -> str:
    return _EMOJI.sub("", _KEYCAP.sub(r"\1.", text or ""))
