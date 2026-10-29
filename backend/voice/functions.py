"""
Functions a voice agent can use during a call, like Retell's custom functions and calendar tools: the model asks for
one by name with arguments, Nimmi runs it, and the model answers the caller with the result.

Kinds:
  custom       an HTTP request to the business's own API (public internet only: netsafe), with the arguments as the
               JSON body (POST, PUT, PATCH) or the query (GET, DELETE). {{variables}} work in the URL, query and headers
               (caller_number, call_id, name, and a campaign's own columns).
  check_slots  Cal.com: free times for one event type over the coming days.
  book         Cal.com: books a time for the caller, with their number.
Secrets (header values, Cal.com keys) are stored sealed (secretbox) and shown masked; a masked value sent back unchanged
keeps the stored secret.
"""
import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

import netsafe
import secretbox

logger = logging.getLogger(__name__)

KINDS = ("custom", "check_slots", "book")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PARAM_TYPES = ("string", "number", "boolean", "enum")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
MAX_FUNCTIONS, MAX_PARAMS, MAX_HEADERS = 15, 12, 10
RESULT_CHARS = 3000  # what the model reads back from a function
MASK = "••••"
CAL_API = os.getenv("CAL_API_URL", "https://api.cal.com/v2")
CAL_SLOTS_VERSION, CAL_BOOKINGS_VERSION = "2024-09-04", "2026-02-25"
DEFAULT_TZ = "Asia/Kolkata"
_PLACEHOLDER = re.compile(r"\{\{\s*([\w .-]+?)\s*\}\}")


class FunctionError(ValueError):
    """A function the dashboard sent that can't be saved; the message is shown as is."""


def _seal(value: str) -> str:
    return secretbox.PREFIX + secretbox.seal(value) if value else ""


def _open(value: str) -> str:
    return secretbox.unseal(value[len(secretbox.PREFIX):]) if (value or "").startswith(secretbox.PREFIX) else (value or "")


def _masked(sealed: str) -> str:
    plain = _open(sealed)
    return MASK + plain[-4:] if plain else ""


def _keep_secret(new: str, old: str) -> str:
    """The dashboard shows secrets masked: an unchanged mask keeps the stored one."""
    new = (new or "").strip()
    if new.startswith(MASK):
        return old or ""
    return _seal(new)


def _fill(text: str, variables: dict) -> str:
    lookup = {str(k).strip().lower(): str(v) for k, v in variables.items() if v not in (None, "")}
    return _PLACEHOLDER.sub(lambda m: lookup.get(m.group(1).strip().lower(), ""), text or "")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def clean(new: list[dict], old: Optional[list[dict]] = None) -> list[dict]:
    """Check and tidy the agent's functions from the dashboard. Raises FunctionError with a message for the owner."""
    old_by_id = {f.get("id"): f for f in (old or [])}
    if len(new) > MAX_FUNCTIONS:
        raise FunctionError(f"An agent can have up to {MAX_FUNCTIONS} functions")
    out, names = [], set()
    for raw in new:
        kind = raw.get("kind")
        if kind not in KINDS:
            raise FunctionError("Unknown kind of function")
        name = str(raw.get("name") or "").strip().lower()
        if not NAME_RE.match(name):
            raise FunctionError(f'"{name or "(no name)"}": use lowercase letters, numbers and underscores, starting with a letter')
        if name in names or name in ("end_call", "transfer_call"):
            raise FunctionError(f'Two functions are called "{name}"' if name in names else f'"{name}" is taken')
        names.add(name)
        description = str(raw.get("description") or "").strip()[:500]
        if not description:
            raise FunctionError(f'"{name}": say when the agent should use it')
        prior = old_by_id.get(raw.get("id")) or {}
        fn = {"id": raw.get("id") or f"fn_{uuid.uuid4().hex[:10]}", "kind": kind, "name": name, "description": description,
              "enabled": raw.get("enabled", True) is not False,
              "speak_during": str(raw.get("speak_during") or "").strip()[:200]}
        if kind == "custom":
            fn.update(_clean_custom(raw, prior, name))
        else:
            key = _keep_secret(raw.get("cal_api_key", ""), prior.get("cal_api_key", ""))
            if not key:
                raise FunctionError(f'"{name}": add your Cal.com API key')
            try:
                event_type = int(raw.get("event_type_id"))
            except (TypeError, ValueError):
                raise FunctionError(f'"{name}": add the Cal.com event type ID (a number)')
            fn.update({"cal_api_key": key, "event_type_id": event_type, "timezone": str(_zone(raw.get("timezone") or DEFAULT_TZ))})
        out.append(fn)
    return out


def _clean_custom(raw: dict, prior: dict, name: str) -> dict:
    url = str(raw.get("url") or "").strip()
    if not re.match(r"^https?://[^\s/]+", url):
        raise FunctionError(f'"{name}": add the address it calls, starting with https://')
    method = str(raw.get("method") or "POST").upper()
    if method not in METHODS:
        raise FunctionError(f'"{name}": unknown method {method}')
    params, seen = [], set()
    for p in (raw.get("parameters") or [])[:MAX_PARAMS]:
        pname = str(p.get("name") or "").strip()
        if not pname:
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$", pname) or pname in seen:
            raise FunctionError(f'"{name}": parameter "{pname}" needs a unique name of letters, numbers and underscores')
        seen.add(pname)
        ptype = p.get("type") if p.get("type") in PARAM_TYPES else "string"
        choices = [str(c).strip()[:60] for c in (p.get("choices") or []) if str(c).strip()][:20]
        if ptype == "enum" and not choices:
            raise FunctionError(f'"{name}": parameter "{pname}" needs its choices')
        params.append({"name": pname, "type": ptype, "description": str(p.get("description") or "").strip()[:200],
                       "required": bool(p.get("required")), "choices": choices if ptype == "enum" else []})
    old_headers = {h.get("name"): h.get("value", "") for h in prior.get("headers") or []}
    headers = []
    for h in (raw.get("headers") or [])[:MAX_HEADERS]:
        hname = str(h.get("name") or "").strip()
        if not hname:
            continue
        if not re.match(r"^[A-Za-z0-9-]{1,60}$", hname):
            raise FunctionError(f'"{name}": header "{hname}" isn\'t a valid header name')
        headers.append({"name": hname, "value": _keep_secret(str(h.get("value") or ""), old_headers.get(hname, ""))})
    try:
        timeout = min(max(int(raw.get("timeout_sec") or 10), 2), 30)
    except (TypeError, ValueError):
        timeout = 10
    return {"url": url[:500], "method": method, "parameters": params, "headers": headers, "timeout_sec": timeout}


def public(functions: Optional[list[dict]]) -> list[dict]:
    """The functions as the dashboard shows them: secrets masked."""
    out = []
    for f in functions or []:
        f = dict(f)
        if f.get("headers"):
            f["headers"] = [{"name": h["name"], "value": _masked(h.get("value", ""))} for h in f["headers"]]
        if "cal_api_key" in f:
            f["cal_api_key"] = _masked(f["cal_api_key"])
        out.append(f)
    return out


def _schema(params: list[dict]) -> dict:
    props = {}
    for p in params:
        prop: dict = {"type": "string" if p["type"] == "enum" else p["type"]}
        if p.get("description"):
            prop["description"] = p["description"]
        if p["type"] == "enum":
            prop["enum"] = p["choices"]
        props[p["name"]] = prop
    return {"type": "object", "properties": props, "required": [p["name"] for p in params if p.get("required")]}


def tool_specs(functions: Optional[list[dict]]) -> list[dict]:
    """What the model is told about each function it may use: its name, when to use it, and its arguments. Calendar
    functions also get today's date in the calendar's time zone, so "tomorrow at 10" can become a date."""
    specs = []
    for f in functions or []:
        if not f.get("enabled", True):
            continue
        if f["kind"] == "custom":
            needs = [p["name"] for p in f.get("parameters") or [] if p.get("required")]
            ask_first = f" Use it only once the caller has given: {', '.join(needs)}." if needs else ""
            specs.append({"name": f["name"], "description": f["description"] + ask_first,
                          "parameters": _schema(f.get("parameters") or [])})
            continue
        now = datetime.now(_zone(f.get("timezone")))
        if f["kind"] == "check_slots":
            specs.append({"name": f["name"], "description": f"{f['description']} Today is {now:%A %d %B %Y}.",
                          "parameters": {"type": "object", "properties": {
                              "start_date": {"type": "string", "description": "First day to look at, YYYY-MM-DD"},
                              "end_date": {"type": "string", "description": "Last day to look at, YYYY-MM-DD (at most 14 days on)"}},
                              "required": ["start_date"]}})
        else:
            specs.append({"name": f["name"], "description": f"{f['description']} Today is {now:%A %d %B %Y}, {now:%H:%M}.",
                          "parameters": {"type": "object", "properties": {
                              "start": {"type": "string", "description": "The time they chose, YYYY-MM-DDTHH:MM, local time"},
                              "name": {"type": "string", "description": "The caller's full name"},
                              "email": {"type": "string", "description": "Their email address, if they gave one"}},
                              "required": ["start", "name"]}})
    return specs


def by_name(functions: Optional[list[dict]], name: str) -> Optional[dict]:
    return next((f for f in functions or [] if f.get("name") == name and f.get("enabled", True)), None)


def _short(text: str) -> str:
    text = text.strip()
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + " …(cut short)"


async def run(fn: dict, args: dict, variables: dict) -> str:
    """Run one function; what comes back is for the model to read, and never raises: a failure is described so the
    agent can tell the caller."""
    try:
        if fn["kind"] == "custom":
            return await _run_custom(fn, args, variables)
        if fn["kind"] == "check_slots":
            return await _check_slots(fn, args)
        return await _book(fn, args, variables)
    except netsafe.UnsafeUrl:
        return "This function isn't set up to reach a public address, so it can't be used."
    except httpx.TimeoutException:
        return "The service didn't answer in time. Tell the caller you couldn't check just now."
    except Exception as e:
        logger.warning(f"Function {fn.get('name')} failed: {e}")
        return "The service couldn't be reached. Tell the caller you couldn't check just now."


async def _run_custom(fn: dict, args: dict, variables: dict) -> str:
    url = httpx.URL(await netsafe.assert_public_url(_fill(fn["url"], variables)))
    headers = {h["name"]: _fill(_open(h.get("value", "")), variables) for h in fn.get("headers") or []}
    body = None
    if fn["method"] in ("GET", "DELETE"):  # the arguments join any query the address already has
        url = url.copy_merge_params({k: v if isinstance(v, str) else json.dumps(v) for k, v in (args or {}).items()})
    else:
        body = args or {}
    async with netsafe.safe_client(timeout=fn.get("timeout_sec", 10)) as client:
        r = await client.request(fn["method"], url, json=body, headers=headers)
    try:
        text = json.dumps(r.json(), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        text = r.text
    if r.status_code >= 400:
        return _short(f"The request failed (HTTP {r.status_code}): {text}")
    return _short(text or "Done.")


def _cal_headers(fn: dict, version: str) -> dict:
    return {"Authorization": f"Bearer {_open(fn['cal_api_key'])}", "cal-api-version": version}


def _day(value, default: date) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return default


async def _check_slots(fn: dict, args: dict) -> str:
    zone = _zone(fn.get("timezone"))
    today = datetime.now(zone).date()
    start = max(_day(args.get("start_date"), today), today)
    end = min(max(_day(args.get("end_date"), start + timedelta(days=6)), start), start + timedelta(days=14))
    async with netsafe.safe_client(timeout=10) as client:
        r = await client.get(f"{CAL_API}/slots", headers=_cal_headers(fn, CAL_SLOTS_VERSION), params={
            "eventTypeId": fn["event_type_id"], "start": start.isoformat(), "end": end.isoformat(), "timeZone": str(zone)})
    if r.status_code >= 400:
        return _short(f"The calendar couldn't be checked (HTTP {r.status_code}): {r.text}")
    days = (r.json().get("data") or {}) if r.headers.get("content-type", "").startswith("application/json") else {}
    lines, total = [], 0
    for day, slots in sorted(days.items()):
        times = []
        for s in slots:
            when = s.get("start") if isinstance(s, dict) else s
            try:
                times.append(datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone(zone).strftime("%H:%M"))
            except ValueError:
                continue
        if times and total < 30:
            lines.append(f"{date.fromisoformat(day):%A %d %B}: {', '.join(times[:30 - total])}")
            total += len(times)
    if not lines:
        return f"No free times between {start:%d %B} and {end:%d %B}."
    return _short(f"Free times ({zone}):\n" + "\n".join(lines))


async def _book(fn: dict, args: dict, variables: dict) -> str:
    zone = _zone(fn.get("timezone"))
    try:
        local = datetime.fromisoformat(str(args.get("start") or "").strip())
    except ValueError:
        return "Ask the caller for the day and time they want, then try again."
    local = local.replace(tzinfo=zone) if local.tzinfo is None else local
    name = str(args.get("name") or variables.get("name") or "").strip()
    if not name:
        return "Ask the caller for their name first."
    attendee = {"name": name[:100], "timeZone": str(zone), "language": "en"}
    if args.get("email"):
        attendee["email"] = str(args["email"]).strip()[:200]
    if variables.get("caller_number"):
        attendee["phoneNumber"] = variables["caller_number"]
    body = {"start": local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"), "eventTypeId": fn["event_type_id"],
            "attendee": attendee, "metadata": {"source": "nimmi-voice", "call_id": str(variables.get("call_id") or "")[:40]}}
    async with netsafe.safe_client(timeout=15) as client:
        r = await client.post(f"{CAL_API}/bookings", headers=_cal_headers(fn, CAL_BOOKINGS_VERSION), json=body)
    if r.status_code >= 400:
        detail = r.text
        try:
            detail = (r.json().get("error") or {}).get("message") or detail
        except (ValueError, AttributeError):
            pass
        return _short(f"The booking didn't go through (HTTP {r.status_code}): {detail}. Offer the caller another time.")
    data = r.json().get("data") or {}
    when = local.strftime("%A %d %B at %H:%M")
    return f"Booked: {when} ({zone}) for {name}. Status: {data.get('status', 'accepted')}."


def test_variables(caller_number: str = "+919876543210") -> dict:
    """Sample values for a test run from the dashboard."""
    return {"caller_number": caller_number, "call_id": "test-call", "name": "Test Caller", "direction": "outbound"}
