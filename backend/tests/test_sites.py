"""Deployments: publishing static sites, serving them by host name, custom domains and plan limits."""
import io
import time
import uuid
import zipfile
from datetime import datetime, timedelta

import pytest

import plans
from backend.models import Subscription
from database import async_session
from sites import domains, git
from sites import serve as site_serve


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _slug() -> str:
    return f"shop-{uuid.uuid4().hex[:8]}"


def _site(client, u, slug=None, name="My Shop"):
    r = client.post("/api/sites", json={"name": name, "slug": slug or _slug()}, headers=u.h())
    assert r.status_code == 200, r.text
    return r.json()


def _wait(client, u, site_id):
    for _ in range(100):
        site = client.get(f"/api/sites/{site_id}", headers=u.h()).json()
        if site["deploys"] and all(d["status"] != "building" for d in site["deploys"]):
            return site
        time.sleep(0.05)
    raise AssertionError("deploy didn't finish")


def _deploy_zip(client, u, site_id, files: dict):
    r = client.post(f"/api/sites/{site_id}/deploys", headers=u.h(),
                    files={"archive": ("site.zip", _zip(files), "application/zip")})
    return r


def _visit(client, slug, path="/", **headers):
    return client.get(path, headers={"host": f"{slug}.sites.test", **headers}, follow_redirects=False)


SITE = {
    "my-site/index.html": "<html><body><h1>Welcome</h1><a href='about'>About</a></body></html>",
    "my-site/about.html": "<html><body>About us</body></html>",
    "my-site/blog/index.html": "<html><body>Blog</body></html>",
    "my-site/assets/app.3f9a8b7c1d.js": "console.log('hi');" * 200,
    "my-site/.env": "SECRET=1",
    "my-site/node_modules/lib/index.js": "x",
}


def test_upload_zip_publishes_and_serves_the_site(client, make_user):
    u = make_user()
    site = _site(client, u)
    r = _deploy_zip(client, u, site["id"], SITE)
    assert r.status_code == 200, r.text
    done = _wait(client, u, site["id"])
    assert done["latest"]["status"] == "ready" and done["live"]["id"] == done["latest"]["id"]
    assert done["latest"]["file_count"] == 4 and "Left out 2 files" in done["latest"]["note"]
    slug = site["slug"]

    home = _visit(client, slug)
    assert home.status_code == 200 and "Welcome" in home.text and home.headers["content-type"].startswith("text/html")
    assert home.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert _visit(client, slug, "/about").text == "<html><body>About us</body></html>"  # clean URLs
    moved = _visit(client, slug, "/blog")
    assert moved.status_code == 308 and moved.headers["location"] == "/blog/"
    assert _visit(client, slug, "/blog/").text == "<html><body>Blog</body></html>"
    js = _visit(client, slug, "/assets/app.3f9a8b7c1d.js", **{"accept-encoding": "gzip"})
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    assert js.headers["cache-control"] == "public, max-age=31536000, immutable" and js.headers["content-encoding"] == "gzip"
    assert _visit(client, slug, "/.env").status_code == 404  # secrets are never published
    missing = _visit(client, slug, "/nope")
    assert missing.status_code == 404 and "Page not found" in missing.text
    # Unchanged pages are revalidated, not downloaded again.
    assert _visit(client, slug, "/", **{"if-none-match": home.headers["etag"]}).status_code == 304
    assert client.post("/", headers={"host": f"{slug}.sites.test"}).status_code == 405
    # The API is untouched on its own host.
    assert client.get("/api/sites", headers=u.h()).status_code == 200


def test_folder_upload_finds_the_build_folder_and_single_page_apps(client, make_user):
    u = make_user()
    site = _site(client, u)
    files = {"package.json": b"{}", "src/main.jsx": b"app", "dist/index.html": b"<div id=root></div>",
             "dist/assets/index-abcdef12.js": b"render()"}
    r = client.post(f"/api/sites/{site['id']}/deploys", headers=u.h(),
                    files=[("files", (p.split("/")[-1], d, "application/octet-stream")) for p, d in files.items()],
                    data={"paths": list(files)})
    assert r.status_code == 200, r.text
    assert _wait(client, u, site["id"])["latest"]["status"] == "ready"
    # One page that routes itself: any page address shows it.
    deep = _visit(client, site["slug"], "/dashboard/settings")
    assert deep.status_code == 200 and "root" in deep.text
    assert _visit(client, site["slug"], "/missing.png").status_code == 404


@pytest.mark.parametrize("files,message", [
    ({"../evil.html": "x", "index.html": "x"}, "outside the site"),
    ({"readme.txt": "hello"}, "couldn't find an index.html"),
    ({"package.json": "{}", "src/App.jsx": "x"}, "looks like source code"),
    ({"index.html": "x", "big.jpg": b"\0" * (26 * 1024 * 1024)}, "files can be up to"),
])
def test_unsafe_or_unusable_uploads_are_refused(client, make_user, files, message):
    u = make_user()
    site = _site(client, u)
    r = _deploy_zip(client, u, site["id"], files)
    assert r.status_code == 400 and message in r.json()["detail"], r.text
    assert client.get(f"/api/sites/{site['id']}", headers=u.h()).json()["latest"] is None  # nothing started


def test_every_version_has_an_address_and_any_can_go_back_live(client, make_user):
    u = make_user()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "version one"})
    first = _wait(client, u, site["id"])["latest"]["id"]
    _deploy_zip(client, u, site["id"], {"index.html": "version two"})
    second = _wait(client, u, site["id"])["latest"]["id"]
    assert _visit(client, site["slug"]).text == "version two"

    older = client.get(f"/", headers={"host": f"{site['slug']}--{first[:8]}.sites.test"})
    assert older.text == "version one" and older.headers["x-robots-tag"] == "noindex"
    r = client.post(f"/api/sites/{site['id']}/deploys/{first}/promote", headers=u.h())
    assert r.status_code == 200 and r.json()["live"]["id"] == first
    assert _visit(client, site["slug"]).text == "version one"
    assert {d["id"] for d in r.json()["deploys"]} == {first, second}


def test_the_assistant_can_be_added_to_every_page(client, make_user):
    u = make_user()
    bot = u.bot()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "<html><body><p>Hi</p></body></html>"})
    _wait(client, u, site["id"])
    other = make_user().bot()
    assert client.patch(f"/api/sites/{site['id']}", json={"bot_id": other}, headers=u.h()).status_code == 400
    assert client.patch(f"/api/sites/{site['id']}", json={"bot_id": bot}, headers=u.h()).status_code == 200
    page = _visit(client, site["slug"]).text
    assert f'data-bot-id="{bot}"' in page and page.index("nimmi-widget.js") < page.index("</body>")


def test_custom_domain_needs_both_dns_records(client, make_user, monkeypatch):
    u = make_user()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "on my own domain"})
    _wait(client, u, site["id"])
    domain = f"www.{uuid.uuid4().hex[:8]}.in"

    bare = client.put(f"/api/sites/{site['id']}/domain", json={"domain": domain[4:]}, headers=u.h())
    assert bare.status_code == 400 and f"Use www.{domain[4:]}" in bare.json()["detail"]
    r = client.put(f"/api/sites/{site['id']}/domain", json={"domain": f"https://{domain.upper()}/"}, headers=u.h())
    assert r.status_code == 200, r.text
    d = r.json()["domain"]
    assert d["name"] == domain and d["status"] == "pending"
    cname, txt = d["records"]
    assert (cname["type"], cname["host"], cname["value"]) == ("CNAME", "www", "cname.sites.test")
    assert txt["type"] == "TXT" and txt["host"] == "_nimmi-verify.www" and txt["value"].startswith("nimmi-verify=")

    answers = {}

    async def fake_lookup(name, rtype):
        return answers.get((name, rtype), [])
    monkeypatch.setattr(domains, "lookup", fake_lookup)
    r = client.post(f"/api/sites/{site['id']}/domain/check", headers=u.h())
    assert r.json()["domain"]["status"] == "pending" and "TXT" in r.json()["domain"]["error"]
    answers[(f"_nimmi-verify.{domain}", "TXT")] = [txt["value"]]
    r = client.post(f"/api/sites/{site['id']}/domain/check", headers=u.h())
    assert r.json()["domain"]["status"] == "pending" and "CNAME" in r.json()["domain"]["error"]
    answers[(domain, "CNAME")] = ["cname.sites.test"]
    r = client.post(f"/api/sites/{site['id']}/domain/check", headers=u.h())
    assert r.json()["domain"]["status"] == "active" and r.json()["domain"]["url"] == f"https://{domain}"
    assert client.get("/", headers={"host": domain}).text == "on my own domain"

    # One domain, one site.
    other = _site(client, u)
    assert client.put(f"/api/sites/{other['id']}/domain", json={"domain": domain}, headers=u.h()).status_code == 409
    assert client.delete(f"/api/sites/{site['id']}/domain", headers=u.h()).json()["domain"] is None
    assert "on my own domain" not in client.get("/", headers={"host": domain}).text


def test_the_edge_can_forward_a_visitors_host_only_with_its_key(client, make_user):
    u = make_user()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "via the edge"})
    _wait(client, u, site["id"])
    forwarded = {"x-nimmi-site-host": f"{site['slug']}.sites.test"}
    assert client.get("/", headers={**forwarded, "x-nimmi-edge-key": "edge-key"}).text == "via the edge"
    assert client.get("/", headers={**forwarded, "x-nimmi-edge-key": "wrong"}).text != "via the edge"


def test_publishing_from_a_repository_and_its_deploy_hook(client, make_user, monkeypatch):
    u = make_user()
    site = _site(client, u)
    pushes = []

    async def fake_download(repo, token, max_bytes):
        pushes.append((repo.url, repo.branch, token))
        archive = io.BytesIO(_zip({"site-main/README.md": "x", "site-main/docs/index.html": f"docs {len(pushes)}"}))
        return git.Archive(archive, "abc123", "Update pricing")
    monkeypatch.setattr(git, "download", fake_download)

    r = client.post(f"/api/sites/{site['id']}/deploys/git", headers=u.h(),
                    json={"repo_url": "https://github.com/acme/site/tree/main", "folder": "docs", "token": "ghp_secret"})
    assert r.status_code == 200, r.text
    done = _wait(client, u, site["id"])
    assert done["latest"]["status"] == "ready" and done["latest"]["commit_message"] == "Update pricing"
    assert done["git"] == {"url": "https://github.com/acme/site", "branch": "main", "folder": "docs", "has_token": True, "hook": False}
    assert pushes == [("https://github.com/acme/site", "main", "ghp_secret")]
    assert _visit(client, site["slug"]).text == "docs 1"

    hook = client.post(f"/api/sites/{site['id']}/hook", headers=u.h()).json()["url"]
    path = hook.split("example.test", 1)[1]
    assert client.post(path, headers={"x-github-event": "ping"}).json()["message"] == "Hook is connected"
    ignored = client.post(path, json={"ref": "refs/heads/dev"}, headers={"x-github-event": "push"}).json()
    assert ignored["message"].startswith("Ignored")
    started = client.post(path, json={"ref": "refs/heads/main"}, headers={"x-github-event": "push"})
    assert started.status_code == 200 and "deploy_id" in started.json()
    _wait(client, u, site["id"])
    assert _visit(client, site["slug"]).text == "docs 2"
    assert client.post("/api/sites/hooks/not-a-real-hook-secret-value", json={}).status_code == 404


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/acme/site", ("github", "acme/site", None)),
    ("git@github.com:acme/site.git", ("github", "acme/site", None)),
    ("github.com/acme/site/tree/gh-pages", ("github", "acme/site", "gh-pages")),
    ("https://gitlab.com/group/sub/site", ("gitlab", "group/sub/site", None)),
])
def test_repository_links(url, expected):
    repo = git.parse(url)
    assert (repo.host, repo.path, repo.branch) == expected


def test_deleting_takes_the_site_offline_and_it_can_be_restored(client, make_user):
    u = make_user()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "still here"})
    _wait(client, u, site["id"])
    assert client.delete(f"/api/sites/{site['id']}", headers=u.h()).json()["restorable_days"] == 30
    gone = _visit(client, site["slug"])
    assert gone.status_code == 404 and "There's no site here" in gone.text
    listing = client.get("/api/sites", headers=u.h()).json()
    assert [s["id"] for s in listing["deleted"]] == [site["id"]] and listing["sites"] == []
    assert client.post(f"/api/sites/{site['id']}/restore", headers=u.h()).status_code == 200
    assert _visit(client, site["slug"]).text == "still here"


def test_operations_can_take_down_an_abusive_site(client, make_user):
    u = make_user()
    site = _site(client, u)
    _deploy_zip(client, u, site["id"], {"index.html": "phish"})
    _wait(client, u, site["id"])
    assert client.post(f"/api/sites/admin/{site['slug']}/block").status_code == 403
    assert client.post(f"/api/sites/admin/{site['slug']}/block", headers={"x-admin-key": "admin-key"}).status_code == 200
    assert _visit(client, site["slug"]).status_code == 451


def test_site_addresses(client, make_user):
    u = make_user()
    taken = _site(client, u)["slug"]
    check = lambda s: client.get("/api/sites/check", params={"slug": s}, headers=u.h()).json()  # noqa: E731
    assert check("ab")["available"] is False and check("www")["problem"] == "That address is reserved"
    assert check(taken)["problem"] == "That address is taken"
    free = check(_slug())
    assert free["available"] and free["url"].endswith(".sites.test")
    named = client.post("/api/sites", json={"name": "Sri Ganesh Sweets!"}, headers=u.h()).json()
    assert named["slug"].startswith("sri-ganesh-sweets") and named["url"] == f"https://{named['slug']}.sites.test"


# ─── plans ────────────────────────────────────────────────────────
def test_free_plan_one_assistant_one_site_no_voice_or_integrations(client, make_user, run, monkeypatch):
    monkeypatch.setenv("ENFORCE_PLAN_LIMITS", "true")
    u = make_user()
    limits = client.get("/api/account/limits", headers=u.h()).json()
    assert limits["paid"] is False and limits["assistants"] == 1 and limits["sites"] == 1 and limits["used"]["assistants"] == 0

    bot = u.bot()
    second = client.post("/api/bots/create", json={"name": "Two"}, headers=u.h())
    assert second.status_code == 402 and "one assistant" in second.json()["detail"]
    site = _site(client, u)
    assert client.post("/api/sites", json={"name": "Second"}, headers=u.h()).status_code == 402
    domain = client.put(f"/api/sites/{site['id']}/domain", json={"domain": "www.example.in"}, headers=u.h())
    assert domain.status_code == 402 and "Custom domains" in domain.json()["detail"]
    assert client.post("/api/voice/session", json={"bot_id": bot}, headers=u.h()).status_code == 402
    assert client.put("/api/integrations", json={}, headers=u.h()).status_code == 402
    # Free uploads are smaller.
    big = _deploy_zip(client, u, site["id"], {"index.html": "x", "photo.jpg": b"\1" * (11 * 1024 * 1024)})
    assert big.status_code == 400 and "10 MB" in big.json()["detail"]

    async def subscribe():
        async with async_session() as db:
            db.add(Subscription(user_id=u.id, bot_id=bot, plan_name="6 Month Plan", price_paid=499,
                                end_date=datetime.utcnow() + timedelta(days=30), status="active"))
            await db.commit()
    run(subscribe)
    assert client.get("/api/account/limits", headers=u.h()).json()["paid"] is True
    assert client.post("/api/bots/create", json={"name": "Two"}, headers=u.h()).status_code == 200
    assert client.post("/api/sites", json={"name": "Second"}, headers=u.h()).status_code == 200
    assert client.put(f"/api/sites/{site['id']}/domain", json={"domain": f"www.{uuid.uuid4().hex[:8]}.in"},
                      headers=u.h()).status_code == 200


def test_limits_follow_the_plan_module():
    assert plans.FREE.sites == 1 and plans.FREE.assistants == 1 and not plans.FREE.voice and not plans.FREE.integrations
    assert plans.PAID.custom_domains and plans.PAID.deploy_bytes > plans.FREE.deploy_bytes
    assert site_serve.with_assistant(b"<body>x</body>", "b1").count(b"nimmi-widget.js") == 1
    assert site_serve.with_assistant(b'<script src="/static/nimmi-widget.js"></script>', "b1").count(b"nimmi-widget.js") == 1
