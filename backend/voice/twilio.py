"""
Twilio telephony: incoming calls (number webhook -> TwiML -> Media Stream) and
outgoing calls (REST). Call audio is 8 kHz G.711 mu-law over a WebSocket, which
we convert to/from 16-bit PCM for the voice engine.

Note for India: Twilio can't provide Indian numbers for domestic calls, so a
Twilio number is for testing and for customers outside India. Use Exotel for
Indian numbers.
"""
import base64
import hashlib
import hmac
import logging
import os
from array import array
from xml.sax.saxutils import escape, quoteattr

import httpx

logger = logging.getLogger(__name__)

API = "https://api.twilio.com/2010-04-01"


class TwilioError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and ws_secret() and public_base())


def ws_secret() -> str:
    return os.getenv("TWILIO_WS_SECRET", "")


def public_base() -> str:
    """The backend's public https address (a tunnel while testing, api.nimmiai.in in production)."""
    return (os.getenv("PUBLIC_BACKEND_URL") or os.getenv("BACKEND_URL") or "").rstrip("/")


Creds = tuple[str, str]  # (account SID, auth token); None means Nimmi's own account from the environment


def _auth(creds: Creds | None = None) -> tuple[str, str]:
    return creds or (os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", ""))


def incoming_url(hook: str | None = None) -> str:
    """Where a number's incoming calls go. `hook` is a connected account's own webhook token."""
    return f"{public_base()}/api/voice/twilio/incoming/{hook or ws_secret()}"


def valid_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Twilio's X-Twilio-Signature: HMAC-SHA1 of the URL plus the sorted form fields, keyed by the auth token."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = base64.b64encode(hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return bool(signature) and hmac.compare_digest(digest, signature)


# ─── G.711 mu-law <-> PCM16 ───────────────────────────────────────
_BIAS = 0x84


def _ulaw_to_linear(u: int) -> int:
    u = ~u & 0xFF
    exponent, mantissa = (u >> 4) & 0x07, u & 0x0F
    sample = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return -sample if u & 0x80 else sample


_SEG_END = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


def _linear_to_ulaw(sample: int) -> int:
    """ITU G.711 mu-law, the 14-bit variant used by Python's audioop (bit-exact with it)."""
    sample >>= 2
    if sample < 0:
        sample, mask = -sample, 0x7F
    else:
        mask = 0xFF
    sample = min(sample, 8159) + (_BIAS >> 2)
    seg = next((i for i, end in enumerate(_SEG_END) if sample <= end), 8)
    if seg >= 8:
        return 0x7F ^ mask
    return ((seg << 4) | ((sample >> (seg + 1)) & 0x0F)) ^ mask


_DECODE = [array("h", [_ulaw_to_linear(u)]).tobytes() for u in range(256)]
_ENCODE = bytes(_linear_to_ulaw(s - 65536 if s >= 32768 else s) for s in range(65536))


def ulaw_to_pcm(data: bytes) -> bytes:
    return b"".join(_DECODE[b] for b in data)


def pcm_to_ulaw(pcm: bytes) -> bytes:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    return bytes(_ENCODE[s & 0xFFFF] for s in samples)


# ─── TwiML ────────────────────────────────────────────────────────
def connect_twiml(params: dict, hook: str | None = None) -> str:
    """Stream the call to our voice engine; when the stream ends, ask /after whether to transfer."""
    base = public_base()
    token = hook or ws_secret()
    ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/voice/ws/twilio/{token}"
    action = f"{base}/api/voice/twilio/after/{token}"
    parameters = "".join(f"<Parameter name={quoteattr(k)} value={quoteattr(str(v))}/>" for k, v in params.items() if v)
    return (f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect action={quoteattr(action)}>'
            f"<Stream url={quoteattr(ws_url)}>{parameters}</Stream></Connect></Response>")


def say_and_hangup(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>{escape(text)}</Say><Hangup/></Response>'


def dial_twiml(e164: str, whisper_call: str = "", hook: str | None = None) -> str:
    """Transfer the caller. With `whisper_call`, the person answering first hears a brief (warm transfer)."""
    if not whisper_call:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial>{escape(e164)}</Dial></Response>'
    url = f"{public_base()}/api/voice/twilio/whisper/{hook or ws_secret()}?call={whisper_call}"
    return (f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial>'
            f'<Number url={quoteattr(url)}>{escape(e164)}</Number></Dial></Response>')


def whisper_twiml(text: str) -> str:
    """Played only to the person taking the transfer, before the caller is connected."""
    return (f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>Incoming transfer from your AI assistant. '
            f'{escape(text)}</Say></Response>')


def hangup_twiml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


# ─── REST ─────────────────────────────────────────────────────────
async def place_call(to_e164: str, from_e164: str, job_id: str, detect_voicemail: bool = False,
                     creds: Creds | None = None, hook: str | None = None) -> str:
    """
    Ring `to_e164` from a Twilio number and connect them to the voice engine. Returns the call SID.
    With `detect_voicemail`, Twilio listens first (a few seconds) and tells /outbound who answered.
    `creds` and `hook` are set for numbers on a customer's own Twilio account.
    """
    if not (creds and public_base()) and not configured():
        raise TwilioError("Twilio isn't configured on the server")
    sid, _ = _auth(creds)
    token = hook or ws_secret()
    # A dict (not a list of pairs): httpx treats a list as a raw byte stream and fails on AsyncClient.
    data = {
        "To": to_e164, "From": from_e164,
        "StatusCallback": f"{public_base()}/api/voice/twilio/status/{token}",
        "StatusCallbackEvent": "completed",
    }
    if detect_voicemail:
        data["Url"] = f"{public_base()}/api/voice/twilio/outbound/{token}?job={job_id}"
        data["MachineDetection"] = "DetectMessageEnd"  # wait for the beep, so a message lands in full
    else:
        data["Twiml"] = connect_twiml({"job": job_id, "direction": "outbound"}, hook)
    async with httpx.AsyncClient(timeout=20, auth=_auth(creds)) as client:
        resp = await client.post(f"{API}/Accounts/{sid}/Calls.json", data=data)
    if resp.status_code >= 300:
        try:
            message = resp.json().get("message")
        except ValueError:
            message = resp.text[:300]
        raise TwilioError(f"Twilio {resp.status_code}: {message}")
    return resp.json()["sid"]


async def point_number_here(e164: str) -> None:
    """Set the Twilio number's 'A call comes in' webhook to our incoming-call endpoint."""
    sid, _ = _auth()
    async with httpx.AsyncClient(timeout=20, auth=_auth()) as client:
        found = await client.get(f"{API}/Accounts/{sid}/IncomingPhoneNumbers.json", params={"PhoneNumber": e164})
        numbers = found.json().get("incoming_phone_numbers") or []
        if not numbers:
            raise TwilioError(f"{e164} isn't a number on this Twilio account")
        resp = await client.post(f"{API}/Accounts/{sid}/IncomingPhoneNumbers/{numbers[0]['sid']}.json", data={
            "VoiceUrl": f"{public_base()}/api/voice/twilio/incoming/{ws_secret()}", "VoiceMethod": "POST",
        })
    if resp.status_code >= 300:
        raise TwilioError(f"Couldn't update the number: {resp.text[:300]}")


# ─── Customers' own Twilio accounts ───────────────────────────────
async def verify_account(creds: Creds) -> str:
    """Check the SID and auth token work; returns the account's name."""
    sid, _ = creds
    async with httpx.AsyncClient(timeout=20, auth=creds) as client:
        resp = await client.get(f"{API}/Accounts/{sid}.json")
    if resp.status_code in (401, 403, 404):
        raise TwilioError("Twilio didn't accept that Account SID and auth token")
    if resp.status_code >= 300:
        raise TwilioError(_error(resp))
    body = resp.json()
    if body.get("status") not in (None, "active"):
        raise TwilioError(f"This Twilio account is {body.get('status')}")
    return body.get("friendly_name") or sid


async def list_numbers(creds: Creds) -> list[dict]:
    """Voice-capable numbers on the account, with where their calls go now."""
    sid, _ = creds
    data = await _get(f"/Accounts/{sid}/IncomingPhoneNumbers.json", {"PageSize": 200}, creds=creds)
    return [
        {"sid": n["sid"], "phone_number": n["phone_number"], "friendly_name": n.get("friendly_name") or "",
         "voice_url": n.get("voice_url") or "", "country": n.get("iso_country") or ""}
        for n in data.get("incoming_phone_numbers") or [] if (n.get("capabilities") or {}).get("voice", True)
    ]


async def set_voice_url(number_sid: str, url: str, creds: Creds | None = None) -> None:
    """Point a number's 'A call comes in' webhook at `url`."""
    sid, _ = _auth(creds)
    async with httpx.AsyncClient(timeout=20, auth=_auth(creds)) as client:
        resp = await client.post(f"{API}/Accounts/{sid}/IncomingPhoneNumbers/{number_sid}.json",
                                 data={"VoiceUrl": url, "VoiceMethod": "POST"})
    if resp.status_code >= 300:
        raise TwilioError(f"Couldn't update the number: {_error(resp)}")


async def account_numbers() -> list[str]:
    sid, _ = _auth()
    async with httpx.AsyncClient(timeout=20, auth=_auth()) as client:
        resp = await client.get(f"{API}/Accounts/{sid}/IncomingPhoneNumbers.json")
    if resp.status_code >= 300:
        raise TwilioError(f"Twilio {resp.status_code}: {resp.text[:200]}")
    return [n["phone_number"] for n in resp.json().get("incoming_phone_numbers") or []]



# ─── Self-serve numbers for customers ─────────────────────────────
NUMBER_TYPES = {"local": "Local", "toll_free": "TollFree", "mobile": "Mobile"}


async def _get(path: str, params: dict | None = None, base: str = API, creds: Creds | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20, auth=_auth(creds)) as client:
        resp = await client.get(f"{base}{path}", params=params)
    if resp.status_code >= 300:
        raise TwilioError(_error(resp))
    return resp.json()


def _error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return body.get("message") or body.get("detail") or resp.text[:300]
    except ValueError:
        return resp.text[:300]


async def search_numbers(country: str, number_type: str, area_code: str = "", contains: str = "") -> list[dict]:
    """Numbers available to buy right now, voice-capable."""
    sid, _ = _auth()
    params = {"VoiceEnabled": "true", "PageSize": 20}
    if area_code:
        params["AreaCode"] = area_code
    if contains:
        params["Contains"] = contains
    data = await _get(f"/Accounts/{sid}/AvailablePhoneNumbers/{country}/{NUMBER_TYPES[number_type]}.json", params)
    return [
        {"phone_number": n["phone_number"], "friendly_name": n.get("friendly_name") or n["phone_number"],
         "locality": n.get("locality") or "", "region": n.get("region") or "",
         "address_required": (n.get("address_requirements") or "none") != "none"}
        for n in data.get("available_phone_numbers") or []
    ]


async def monthly_price_usd(country: str, number_type: str) -> float | None:
    """Twilio's monthly price for this number type in this country."""
    data = await _get(f"/PhoneNumbers/Countries/{country}", base="https://pricing.twilio.com/v1")
    wanted = {"local": "local", "toll_free": "toll free", "mobile": "mobile"}[number_type]
    for p in data.get("phone_number_prices") or []:
        if (p.get("number_type") or "").lower() == wanted:
            return float(p.get("current_price") or p.get("base_price") or 0)
    return None


async def create_address(customer_name: str, street: str, city: str, region: str, postal_code: str, country: str) -> str:
    sid, _ = _auth()
    async with httpx.AsyncClient(timeout=20, auth=_auth()) as client:
        resp = await client.post(f"{API}/Accounts/{sid}/Addresses.json", data={
            "CustomerName": customer_name, "Street": street, "City": city, "Region": region,
            "PostalCode": postal_code, "IsoCountry": country, "FriendlyName": f"Nimmi: {customer_name}"[:64],
        })
    if resp.status_code >= 300:
        raise TwilioError(f"Address rejected: {_error(resp)}")
    return resp.json()["sid"]


async def buy_number(phone_number: str, friendly_name: str, address_sid: str | None = None) -> str:
    """Purchase a number on our Twilio account, already pointed at our incoming-call webhook. Returns its SID."""
    sid, _ = _auth()
    data = {"PhoneNumber": phone_number, "FriendlyName": friendly_name[:64],
            "VoiceUrl": f"{public_base()}/api/voice/twilio/incoming/{ws_secret()}", "VoiceMethod": "POST"}
    if address_sid:
        data["AddressSid"] = address_sid
    async with httpx.AsyncClient(timeout=30, auth=_auth()) as client:
        resp = await client.post(f"{API}/Accounts/{sid}/IncomingPhoneNumbers.json", data=data)
    if resp.status_code >= 300:
        raise TwilioError(_error(resp))
    return resp.json()["sid"]


async def release_number(number_sid: str) -> None:
    sid, _ = _auth()
    async with httpx.AsyncClient(timeout=20, auth=_auth()) as client:
        resp = await client.delete(f"{API}/Accounts/{sid}/IncomingPhoneNumbers/{number_sid}.json")
    if resp.status_code not in (204, 404):
        raise TwilioError(_error(resp))
