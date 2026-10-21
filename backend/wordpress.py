"""The WordPress plugin a business downloads to add its assistant: plugins/wordpress, filled in and zipped."""
import io
import os
import re
import zipfile
from typing import Optional

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins", "wordpress")
SLUG = "nimmi-ai-chat"
_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?$")


def clean_base(url: Optional[str], fallback: str) -> str:
    """An origin like https://api.nimmiai.in (no path, quotes or spaces), safe inside PHP and HTML."""
    url = (url or "").strip().rstrip("/")
    return url if _URL.match(url) else fallback


def plugin_zip(bot_id: str, bot_name: str, api_url: str, dashboard_url: str) -> bytes:
    """nimmi-ai-chat.zip: install it from Plugins, Add New, Upload Plugin."""
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", bot_id):
        raise ValueError("Unexpected assistant id")
    name = re.sub(r"[^\w .&'-]", "", bot_name or "your assistant")[:60] or "your assistant"
    values = {"{{BOT_ID}}": bot_id, "{{API_URL}}": api_url, "{{DASHBOARD_URL}}": dashboard_url, "{{BOT_NAME}}": name}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for filename in sorted(os.listdir(_DIR)):
            with open(os.path.join(_DIR, filename), encoding="utf-8") as f:
                text = f.read()
            for key, value in values.items():
                text = text.replace(key, value)
            z.writestr(f"{SLUG}/{filename}", text)
    return buf.getvalue()
