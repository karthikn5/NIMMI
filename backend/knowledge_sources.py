"""Sources inside a bot's written knowledge.

Websites, videos and files are stored in Bot.knowledge_base as blocks that start with a
"--- Source: <name> ---" line, after the business's own written text. These helpers list,
replace and remove those blocks, so the builder can show sources as a list.
"""
import re

_MARK = re.compile(r"^--- (?:Source: (?P<name>.+?)|(?P<yt>YouTube Source)) ---$", re.MULTILINE)


def split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(written text before any source, [(source name, its text), ...])."""
    text = text or ""
    marks = list(_MARK.finditer(text))
    if not marks:
        return text.strip(), []
    written = text[: marks[0].start()].strip()
    blocks = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        name = m.group("name") or "YouTube video"
        blocks.append((name.strip(), text[m.end():end].strip()))
    return written, blocks


def join(written: str, blocks: list[tuple[str, str]]) -> str:
    parts = [written.strip()] if written.strip() else []
    parts += [f"--- Source: {name} ---\n{body}" for name, body in blocks]
    return "\n\n".join(parts)


def put(text: str, name: str, body: str) -> str:
    """Add a source, replacing an earlier copy with the same name (so re-adding refreshes it)."""
    written, blocks = split(text)
    blocks = [(n, b) for n, b in blocks if n != name] + [(name, body.strip())]
    return join(written, blocks)


def remove(text: str, name: str) -> tuple[str, bool]:
    written, blocks = split(text)
    kept = [(n, b) for n, b in blocks if n != name]
    return join(written, kept), len(kept) != len(blocks)


def listing(text: str) -> list[dict]:
    """Sources for the builder: name, kind and size."""
    _, blocks = split(text)
    def kind(name: str) -> str:
        if name.startswith("file: "):
            return "file"
        if "youtube.com" in name or "youtu.be" in name or name == "YouTube video":
            return "youtube"
        return "website"
    return [{"name": n, "kind": kind(n), "chars": len(b)} for n, b in blocks]
