"""Adding an assistant to a website or app: only with a plan, and the WordPress plugin is ready to upload."""
import io
import zipfile
from datetime import datetime, timedelta

import wordpress
from backend.models import Subscription
from database import async_session


def _subscribe(run, user_id, bot_id):
    async def go():
        async with async_session() as db:
            db.add(Subscription(user_id=user_id, bot_id=bot_id, plan_name="6 Month Plan", price_paid=499,
                                end_date=datetime.utcnow() + timedelta(days=30), status="active"))
            await db.commit()
    run(go)


def test_install_code_needs_a_plan(client, make_user, run):
    u = make_user()
    bot = u.bot("Front desk")
    for path in (f"/api/bots/{bot}/install", f"/api/bots/{bot}/wordpress-plugin"):
        r = client.get(path, headers=u.h())
        assert r.status_code == 402 and "Choose a plan" in r.json()["detail"]
    # Not someone else's assistant, plan or not.
    assert client.get(f"/api/bots/{bot}/install", headers=make_user().h()).status_code in (403, 404)

    _subscribe(run, u.id, bot)
    info = client.get(f"/api/bots/{bot}/install", headers=u.h()).json()
    assert info["bot_name"] == "Front desk" and info["plan"] == "6 Month Plan"


def test_wordpress_plugin_is_filled_in(client, make_user, run):
    u = make_user()
    bot = u.bot("Green Park Homes")
    _subscribe(run, u.id, bot)
    r = client.get(f"/api/bots/{bot}/wordpress-plugin", headers=u.h(),
                   params={"api": "https://api.example.in/", "dashboard": "https://app.example.in"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="nimmi-ai-chat.zip"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["nimmi-ai-chat/nimmi-ai-chat.php", "nimmi-ai-chat/readme.txt", "nimmi-ai-chat/uninstall.php"]
    php = z.read("nimmi-ai-chat/nimmi-ai-chat.php").decode()
    assert php.startswith("<?php") and "Plugin Name:       Nimmi AI Chat" in php
    assert f"'bot_id'        => '{bot}'" in php and "'api_url'       => 'https://api.example.in'" in php
    assert "{{" not in php and "{{" not in z.read("nimmi-ai-chat/readme.txt").decode()


def test_server_addresses_in_the_plugin_are_never_raw_input():
    fallback = "https://api.nimmiai.in"
    assert wordpress.clean_base("https://api.nimmiai.in/", fallback) == "https://api.nimmiai.in"
    assert wordpress.clean_base("http://localhost:8001", fallback) == "http://localhost:8001"
    for bad in ("javascript:alert(1)", "https://x.in/'; phpinfo(); '", "https://x.in/path", "ftp://x.in", ""):
        assert wordpress.clean_base(bad, fallback) == fallback
