"""
Flows as Nimmi reads and writes them: steps in order instead of the canvas's blocks and links.

The Flow tab saves a canvas (React Flow): blocks with positions and the links between them, which the chat widget
runs (dashboard/src/app/widget/[botId]/flow.ts). A model writes and edits that far more reliably as a list:

  {"id": "topic", "type": "choices", "text": "What would you like to know?", "save_as": "topic",
   "choices": [{"label": "Courses", "next": "courses"}, {"label": "Talk to a person", "next": "person"}]}

A step goes on to the one after it in the list unless it says `next` (a step's id, or "stop": the flow ends there
and the AI chat takes over); each choice goes where it says (or to the step's `next`, or the step after); a condition
goes to `yes` or `no`; end and handover stop. outline() turns a saved flow into steps and build() turns steps back
into a flow, checked first: every link leads to a step, every step can be reached, and no loop goes round forever
without waiting for the visitor. What a block has that its step doesn't describe (a phone question's call-back
offer, its own label) is kept when a step with the same id comes back. Blocks keep their place on the canvas; new
ones go under the block before them.
"""
import copy
import re
from collections import defaultdict

KINDS = {  # step type -> (block type, the canvas's name for the block)
    "message": ("message", "Message"),
    "text_question": ("textInput", "Text question"),
    "email_question": ("emailInput", "Email question"),
    "phone_question": ("phoneInput", "Phone question"),
    "number_question": ("numberInput", "Number question"),
    "date_question": ("datePicker", "Date question"),
    "choices": ("multipleChoice", "Choices"),
    "rating": ("rating", "Rating"),
    "file_upload": ("fileUpload", "File upload"),
    "image": ("image", "Image"),
    "video": ("video", "Video"),
    "wait": ("delay", "Wait"),
    "set_value": ("variable", "Set value"),
    "condition": ("condition", "Condition"),
    "ai_step": ("aiPrompt", "AI step"),
    "http_request": ("httpRequest", "HTTP request"),
    "webhook": ("webhook", "Webhook"),
    "slack": ("slack", "Slack"),
    "google_sheets": ("googleSheets", "Google Sheets"),
    "handover": ("handover", "Hand to a person"),
    "end": ("end", "End"),
}
STEP_OF = {block: step for step, (block, _) in KINDS.items()}
QUESTIONS = {"text_question", "email_question", "phone_question", "number_question", "date_question"}
WAITS = QUESTIONS | {"choices", "rating", "file_upload"}  # the flow stops here until the visitor answers
STOPS = {"end", "handover"}
SAYS = WAITS | {"message", "handover", "end"}  # steps whose text the visitor reads
NEEDS_TEXT = WAITS | {"message"}
NEEDS_URL = {"image", "video", "http_request", "webhook", "slack"}
OPERATORS = ("equals", "contains", "greater_than", "less_than")
# Per step type, the fields it takes: step field -> block data key.
FIELDS = {
    **{q: {"save_as": "variableName", "required": "required"} for q in QUESTIONS},
    "phone_question": {"save_as": "variableName", "required": "required", "offer_callback": "offerCallback"},
    "choices": {"save_as": "variableName"},
    "rating": {"save_as": "variableName", "scale": "scale"},
    "file_upload": {"save_as": "variableName"},
    "wait": {"seconds": "delay"},
    "set_value": {"save_as": "variableName", "value": "variableValue"},
    "ai_step": {"prompt": "prompt", "save_as": "variableName"},
    "http_request": {"method": "method", "save_as": "variableName"},
    "slack": {"channel": "channel"},
    "google_sheets": {"spreadsheet_id": "spreadsheetId", "sheet_name": "sheetName"},
}
URL_KEY = {"image": "imageUrl", "video": "videoUrl", "http_request": "url", "webhook": "url", "slack": "url"}
STOP = "stop"
MAX_STEPS = 60
LIMITS = {"text": 1000, "prompt": 2000, "label": 40, "url": 500, "save_as": 40, "value": 300}
ID = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")
PLACEHOLDER = re.compile(r"\{\{?\s*[A-Za-z_][\w ]*\s*\}?\}")  # {name}, {{name}}: the widget shows these as they are
GAP_X, GAP_Y = 300, 150


class FlowProblem(Exception):
    """Steps that can't become a working flow; the message says what to fix, in plain words."""


# ─── Saved flow -> steps ────────────────────────────────────────────

def _live(flow: dict) -> tuple[dict, list]:
    nodes = {n["id"]: n for n in (flow or {}).get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    edges = [e for e in (flow or {}).get("edges") or []
             if isinstance(e, dict) and e.get("source") in nodes and e.get("target") in nodes]
    return nodes, edges


def _exits(node: dict, edges: list) -> list[tuple[str, dict]]:
    """Where a block leads, in reading order: choices in their order, then yes and no, then the plain link."""
    out = [e for e in edges if e["source"] == node["id"]]
    options = [str(o) for o in (node.get("data") or {}).get("options") or []]
    by_handle = {e.get("sourceHandle"): e for e in out if e.get("sourceHandle")}
    ordered = [by_handle[h] for h in (*options, "true", "false") if h in by_handle]
    return [(e.get("sourceHandle") or "", e) for e in ordered + [e for e in out if not e.get("sourceHandle")]]


def _step(node: dict, edges: list) -> dict:
    kind = STEP_OF.get(node.get("type"))
    d = node.get("data") or {}
    if kind is None:  # a block steps don't describe: kept as it is
        step = {"id": node["id"], "type": "keep", "block": node.get("type")}
        if d.get("message"):
            step["text"] = d["message"]
        step["next"] = next((e["target"] for handle, e in _exits(node, edges) if not handle), None) or STOP
        return step
    step = {"id": node["id"], "type": kind}
    if kind in SAYS and str(d.get("message") or "").strip():
        step["text"] = d["message"]
    if kind in URL_KEY and d.get(URL_KEY[kind]):
        step["url"] = d[URL_KEY[kind]]
    for field, key in FIELDS.get(kind, {}).items():
        if d.get(key) not in (None, "", []):
            step[field] = d[key]
    exits = _exits(node, edges)
    plain = next((e["target"] for handle, e in exits if not handle), None)
    if kind == "choices":
        targets = {handle: e["target"] for handle, e in exits if handle}
        step["choices"] = [{"label": str(o), **({"next": targets[str(o)]} if str(o) in targets else {})}
                           for o in d.get("options") or [] if str(o).strip()]
        if plain:
            step["next"] = plain
    elif kind == "condition":
        step["check"] = {"value_of": d.get("variable") or "", "is": d.get("operator") or "equals", "value": d.get("value") or ""}
        for handle, e in exits:
            if handle in ("true", "false"):
                step["yes" if handle == "true" else "no"] = e["target"]
    elif kind not in STOPS:
        step["next"] = plain or STOP
    return step


def outline(flow: dict) -> dict:
    """The saved flow as steps, in the order a visitor meets them (each branch in turn), the blocks nothing links
    to at the end. A `next` that is simply the step after it is left out."""
    nodes, edges = _live(flow)
    start = next((n for n in nodes.values() if n.get("type") == "start"), None)
    order: list[str] = []
    seen = {start["id"]} if start else set()
    stack = [e["target"] for _, e in reversed(_exits(start, edges))] if start else []
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        order.append(node_id)
        stack.extend(e["target"] for _, e in reversed(_exits(nodes[node_id], edges)))
    rest = sorted((n for n in nodes.values() if n["id"] not in seen and n.get("type") != "start"),
                  key=lambda n: ((n.get("position") or {}).get("y", 0), (n.get("position") or {}).get("x", 0)))
    order += [n["id"] for n in rest]
    steps = [_step(nodes[i], edges) for i in order]
    for i, step in enumerate(steps):
        after = steps[i + 1]["id"] if i + 1 < len(steps) else None
        if "next" in step and step["type"] not in ("choices", "condition") and step["next"] in (after, STOP if after is None else after):
            step.pop("next")
    return {"steps": steps, "unreachable": [n["id"] for n in rest]}


def brief(flow: dict, limit: int = 70) -> list[str]:
    """One line per step, for an answer: "3. Choices: What would you like to know? (Courses | Fees | Talk to us)"."""
    lines = []
    for i, step in enumerate(outline(flow)["steps"], 1):
        name = KINDS.get(step["type"], (None, step.get("block") or "Block"))[1]
        text = " ".join(str(step.get("text") or step.get("prompt") or step.get("url") or "").split())
        text = text[:limit] + "..." if len(text) > limit else text
        options = f" ({' | '.join(c['label'] for c in step.get('choices') or [])})" if step.get("choices") else ""
        lines.append(f"{i}. {name}{': ' + text if text else ''}{options}")
    return lines


# ─── Steps -> a flow to save ───────────────────────────────────────

def _text(value, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _link(source: str, target: str, handle=None) -> dict:
    return {"id": f"e-{source}-{target}" + (f"-{handle}" if handle else ""), "source": source, "target": target,
            "sourceHandle": handle, "type": "animated", "markerEnd": {"type": "arrowclosed", "color": "#550a64"}}


def build(steps, current: dict) -> dict:
    """The flow these steps describe, checked, keeping what the current flow's blocks had. Raises FlowProblem."""
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        raise FlowProblem("steps must be a list of steps (objects).")
    if len(steps) > MAX_STEPS:
        raise FlowProblem(f"A flow can have up to {MAX_STEPS} steps.")
    old, _ = _live(current)
    start = copy.deepcopy(next((n for n in old.values() if n.get("type") == "start"), None)) or \
        {"id": "start-1", "type": "start", "position": {"x": 250, "y": 0}, "data": {"label": "Start"}}
    problems: list[str] = []
    ids: list[str] = []
    for i, step in enumerate(steps):
        given = _text(step.get("id"), 80)
        step_id = given or f"s{i + 1}"
        while not given and step_id in ids:
            step_id += "x"
        if not ID.match(step_id) or step_id in (STOP, start["id"]):
            problems.append(f'Step {i + 1}: "{step_id}" can\'t be an id (letters, numbers, - and _ only).')
        elif step_id in ids:
            problems.append(f'Two steps have the id "{step_id}".')
        ids.append(step_id)
    known = set(ids)

    def target(value, where: str, fallback):
        if value is None or value == "":
            return fallback
        value = _text(value, 80)
        if value == STOP:
            return None
        if value not in known:
            problems.append(f'{where} goes to "{value}", but there is no step with that id.')
            return None
        return value

    nodes, edges = [], []
    for i, (step_id, step) in enumerate(zip(ids, steps)):
        kind = _text(step.get("type"), 40)
        after = ids[i + 1] if i + 1 < len(ids) else None
        where = f'Step "{step_id}"'
        if kind == "keep":
            before = old.get(step_id)
            if before is None:
                problems.append(f'{where} keeps a block that isn\'t in the flow.')
                continue
            node = copy.deepcopy(before)
            if "text" in step:
                node.setdefault("data", {})["message"] = _text(step["text"], LIMITS["text"])
            nodes.append(node)
            if (nxt := target(step.get("next"), where, after)) is not None:
                edges.append(_link(step_id, nxt))
            continue
        if kind not in KINDS:
            problems.append(f'{where} has the type "{kind}"; use one of: {", ".join(KINDS)}.')
            continue
        block, label = KINDS[kind]
        before = old.get(step_id)
        data = copy.deepcopy(before.get("data") or {}) if before and before.get("type") == block else {"label": label}
        data.setdefault("label", label)
        text = _text(step.get("text"), LIMITS["text"])
        if PLACEHOLDER.search(text):
            problems.append(f'{where} shows "{PLACEHOLDER.search(text).group(0)}": the widget can\'t fill that in, so '
                            f'visitors would see it as it is. Write the words without it.')
        if kind in SAYS:
            if text:
                data["message"] = text
            elif kind in NEEDS_TEXT:
                problems.append(f'{where} ({label}) needs text: what it says or asks.')
        if kind in URL_KEY:
            url = _text(step.get("url") or data.get(URL_KEY[kind]), LIMITS["url"])
            if not re.match(r"^https?://\S+$", url):
                problems.append(f'{where} ({label}) needs a web address (url) starting with https://.')
            data[URL_KEY[kind]] = url
        for field, key in FIELDS.get(kind, {}).items():
            if field not in step or step[field] in (None, ""):
                continue
            value = step[field]
            if field in ("required", "offer_callback"):
                data[key] = bool(value) if not isinstance(value, str) else value.strip().lower() in ("true", "yes", "1")
            elif field in ("seconds", "scale"):
                try:
                    number = int(float(value))
                except (TypeError, ValueError):
                    problems.append(f'{where}: {field} must be a number.')
                    continue
                data[key] = max(1, min(number, 60)) if field == "seconds" else max(3, min(number, 10))
            else:
                data[key] = _text(value, LIMITS.get(field, 200))
        if kind == "phone_question":
            data.setdefault("variableName", "phone")
        elif kind == "email_question":
            data.setdefault("variableName", "email")
        if kind in QUESTIONS:
            data.setdefault("required", True)
        if kind == "ai_step" and not str(data.get("prompt") or "").strip():
            problems.append(f'{where} (AI step) needs a prompt: what the AI should do there.')
        if kind == "set_value" and not str(data.get("variableName") or "").strip():
            problems.append(f'{where} (Set value) needs save_as: the name of the value it sets.')
        if kind == "google_sheets" and not str(data.get("spreadsheetId") or "").strip():
            problems.append(f'{where} (Google Sheets) needs the spreadsheet_id.')

        if kind == "choices":
            raw = step.get("choices") or []
            labels: list[str] = []
            otherwise = target(step.get("next"), where, after)  # for the choices that don't say where they go
            for c in raw if isinstance(raw, list) else []:
                choice = c if isinstance(c, dict) else {"label": c}
                name = _text(choice.get("label"), LIMITS["label"])
                if not name:
                    continue
                if name in labels:
                    problems.append(f'{where} has the choice "{name}" twice.')
                    continue
                labels.append(name)
                if (nxt := target(choice.get("next"), f'{where}, choice "{name}"', otherwise)) is not None:
                    edges.append(_link(step_id, nxt, name))
            if not 2 <= len(labels) <= 10:
                problems.append(f'{where} (Choices) needs 2 to 10 choices.')
            data["options"] = labels
        elif kind == "condition":
            check = step.get("check") if isinstance(step.get("check"), dict) else {}
            data["variable"] = _text(check.get("value_of"), LIMITS["save_as"])
            data["operator"] = _text(check.get("is"), 20) or "equals"
            data["value"] = _text(check.get("value"), LIMITS["value"])
            if not data["variable"]:
                problems.append(f'{where} (Condition) needs check.value_of: the saved answer it checks.')
            if data["operator"] not in OPERATORS:
                problems.append(f'{where} (Condition): check.is must be one of {", ".join(OPERATORS)}.')
            for side, handle in (("yes", "true"), ("no", "false")):
                nxt = target(step.get(side), where, None)
                if nxt is None:
                    problems.append(f'{where} (Condition) needs "{side}": the step it goes to.')
                else:
                    edges.append(_link(step_id, nxt, handle))
        elif kind not in STOPS:
            if (nxt := target(step.get("next"), where, after)) is not None:
                edges.append(_link(step_id, nxt))
        nodes.append({"id": step_id, "type": block, "position": copy.deepcopy((before or {}).get("position")), "data": data})

    if ids and not problems:
        edges.insert(0, _link(start["id"], ids[0]))
        problems += _unreachable(ids, edges, start["id"]) + _endless(nodes, edges)
    if problems:
        shown = problems[:8] + ([f"...and {len(problems) - 8} more."] if len(problems) > 8 else [])
        raise FlowProblem("The flow wasn't saved: " + " ".join(shown))
    _place(start, nodes, edges)
    return {"nodes": [start, *nodes], "edges": edges}


def _unreachable(ids: list[str], edges: list, start_id: str) -> list[str]:
    out = defaultdict(list)
    for e in edges:
        out[e["source"]].append(e["target"])
    seen, queue = set(), [start_id]
    while queue:
        node_id = queue.pop()
        if node_id not in seen:
            seen.add(node_id)
            queue.extend(out[node_id])
    return [f'Step "{i}" can\'t be reached: link to it from another step, or leave it out.' for i in ids if i not in seen]


def _endless(nodes: list, edges: list) -> list[str]:
    """Loops made only of steps that don't wait for the visitor would run forever in the widget."""
    passing = {n["id"] for n in nodes if STEP_OF.get(n["type"]) not in WAITS and STEP_OF.get(n["type"]) not in STOPS}
    out = defaultdict(list)
    for e in edges:
        if e["source"] in passing and e["target"] in passing:
            out[e["source"]].append(e["target"])
    state: dict[str, int] = {}

    def loops(node_id: str, path: list[str]):
        state[node_id] = 1
        for nxt in out[node_id]:
            if state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt] if nxt in path else [node_id, nxt]
            if nxt not in state and (found := loops(nxt, path + [nxt])):
                return found
        state[node_id] = 2
        return None

    for node_id in passing:
        if node_id not in state and (found := loops(node_id, [node_id])):
            return [f'Steps {" -> ".join(found)} go round forever without waiting for the visitor: put a question '
                    f'or choices in that loop, or end it.']
    return []


def _place(start: dict, nodes: list, edges: list) -> None:
    """Blocks that were on the canvas stay where they were; each new one goes under the block that leads to it."""
    by_id = {n["id"]: n for n in [start, *nodes]}
    if not start.get("position"):
        start["position"] = {"x": 250, "y": 0}
    parents = defaultdict(list)
    for e in edges:
        parents[e["target"]].append(e["source"])
    placed = [n["position"] for n in by_id.values() if n.get("position")]

    def free(x: float, y: float) -> tuple[float, float]:
        while any(abs(p["x"] - x) < GAP_X * 0.7 and abs(p["y"] - y) < GAP_Y * 0.7 for p in placed):
            x += GAP_X
        return x, y

    pending = [n for n in nodes if not n.get("position")]
    for _ in range(len(pending) + 1):
        if not pending:
            break
        later = []
        for n in pending:
            parent = next((by_id[p] for p in parents[n["id"]] if by_id[p].get("position")), None)
            if parent is None:
                later.append(n)
                continue
            x, y = free(parent["position"]["x"], parent["position"]["y"] + GAP_Y)
            n["position"] = {"x": x, "y": y}
            placed.append(n["position"])
        if len(later) == len(pending):  # nothing leads to these yet: under everything else
            bottom = max(p["y"] for p in placed) + GAP_Y
            for n in later:
                x, y = free(start["position"]["x"], bottom)
                n["position"] = {"x": x, "y": y}
                placed.append(n["position"])
            later = []
        pending = later
