"""
Deployments: publish a static website (upload a folder or .zip, or import from GitHub/GitLab),
get a public address, roll back to any kept version, add the assistant to every page, and
connect a custom domain on paid plans. Serving is in sites/serve.py.
"""
import asyncio
import hashlib
import hmac
import io
import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import plans
from auth import AuthContext, client_ip, get_ctx, rate_limit, require_manager
from database import get_db
from backend.models import Bot, Site, SiteDeploy
from notify.events import fire_and_forget
from security import is_production
from sites import bundle as bundles
from sites import deploy as deploys
from sites import domains, git, serve, storage
from sites.bundle import BundleError

router = APIRouter(prefix="/api/sites", tags=["sites"])

HISTORY = 20  # deploys listed on a site's page


# ─── shapes ───────────────────────────────────────────────────────
def _deploy_json(d: SiteDeploy, site: Site) -> dict:
    return {
        "id": d.id, "status": d.status, "source": d.source, "file_count": d.file_count or 0, "total_bytes": d.total_bytes or 0,
        "commit_sha": d.commit_sha, "commit_message": d.commit_message, "note": d.note, "error": d.error,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "finished_at": d.finished_at.isoformat() if d.finished_at else None,
        "live": d.id == site.current_deploy_id,
        "preview_url": domains.preview_url(site.slug, d.id) if d.status == "ready" else None,
    }


def _site_json(site: Site, latest: Optional[SiteDeploy] = None, live: Optional[SiteDeploy] = None) -> dict:
    domain = None
    if site.custom_domain:
        domain = {"name": site.custom_domain, "status": site.domain_status, "error": site.domain_error,
                  "records": domains.records(site.custom_domain, site.domain_token or ""),
                  "apex": domains.apex(site.custom_domain),
                  "checked_at": site.domain_checked_at.isoformat() if site.domain_checked_at else None,
                  "url": f"https://{site.custom_domain}" if site.domain_status == "active" else None}
    return {
        "id": site.id, "name": site.name, "slug": site.slug, "status": site.status,
        "url": domains.site_url(site.slug), "bot_id": site.bot_id, "spa": site.spa or "auto",
        "git": {"url": site.git_url, "branch": site.git_branch, "folder": site.git_folder,
                "has_token": bool(site.git_token), "hook": bool(site.hook_secret)} if site.git_url else None,
        "domain": domain,
        "latest": _deploy_json(latest, site) if latest else None,
        "live": _deploy_json(live, site) if live else None,
        "created_at": site.created_at.isoformat() if site.created_at else None,
        "deleted_at": site.deleted_at.isoformat() if site.deleted_at else None,
    }


async def _owned(site_id: str, ctx: AuthContext, db: AsyncSession, deleted: bool = False) -> Site:
    site = (await db.execute(select(Site).where(Site.id == site_id, Site.user_id == ctx.owner_id))).scalars().first()
    if not site or bool(site.deleted_at) != deleted:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


async def _deploy_rows(db: AsyncSession, site: Site, limit: int = HISTORY) -> list[SiteDeploy]:
    return (await db.execute(select(SiteDeploy).where(SiteDeploy.site_id == site.id)
                             .order_by(SiteDeploy.created_at.desc()).limit(limit))).scalars().all()


def _ready() -> None:
    """Publishing needs an address to publish at and somewhere to keep the files."""
    if not domains.sites_domain():
        raise HTTPException(status_code=503, detail="Publishing isn't set up on this server yet (SITES_DOMAIN).")
    if not storage.configured():
        raise HTTPException(status_code=503, detail="Publishing isn't set up on this server yet (file storage).")


async def _slug_taken(db: AsyncSession, slug: str, except_id: Optional[str] = None) -> bool:
    q = select(Site.id).where(Site.slug == slug)
    if except_id:
        q = q.where(Site.id != except_id)
    return (await db.execute(q)).first() is not None


# ─── sites ────────────────────────────────────────────────────────
@router.get("")
async def list_sites(ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Site).where(Site.user_id == ctx.owner_id).order_by(Site.created_at.desc()))).scalars().all()
    out, deleted = [], []
    for site in rows:
        if site.deleted_at:
            deleted.append(_site_json(site))
            continue
        latest = (await _deploy_rows(db, site, 1) or [None])[0]
        live = latest if latest and latest.id == site.current_deploy_id else (
            (await db.execute(select(SiteDeploy).where(SiteDeploy.id == site.current_deploy_id))).scalars().first()
            if site.current_deploy_id else None)
        out.append(_site_json(site, latest, live))
    lim = await plans.limits(db, ctx.owner_id)
    return {"sites": out, "deleted": deleted, "domain": domains.sites_domain(), "ready": bool(domains.sites_domain()) and storage.configured(),
            "custom_domains": lim.custom_domains, "custom_domains_available": domains.custom_domains_available(),
            "limits": {"sites": lim.sites, "deploy_bytes": lim.deploy_bytes, "deploy_files": lim.deploy_files,
                       "file_bytes": lim.file_bytes, "paid": lim.paid}}


@router.get("/check")
async def check_slug(slug: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    slug = slug.strip().lower()
    problem = domains.slug_problem(slug) or ("That address is taken" if await _slug_taken(db, slug) else None)
    return {"slug": slug, "available": problem is None, "problem": problem, "url": domains.site_url(slug)}


class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    slug: Optional[str] = Field(None, max_length=40)


@router.post("")
async def create_site(data: SiteCreate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    _ready()
    await plans.require_room_for_site(db, ctx.owner_id)
    rate_limit(f"site-create:{ctx.owner_id}", 20, 3600)
    name = data.name.strip()
    slug = (data.slug or "").strip().lower() or domains.slugify(name)
    if data.slug:
        problem = domains.slug_problem(slug)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        if await _slug_taken(db, slug):
            raise HTTPException(status_code=409, detail="That address is taken. Try another.")
    else:  # from the name: make it valid and free
        base = slug if not domains.slug_problem(slug) else (slug + "-site")[:40].strip("-")
        if domains.slug_problem(base):
            base = "site"
        slug = base
        while domains.slug_problem(slug) or await _slug_taken(db, slug):
            slug = f"{base[:33]}-{secrets.token_hex(3)}"
    site = Site(user_id=ctx.owner_id, name=name, slug=slug)
    db.add(site)
    await db.commit()
    serve.forget(slug)
    return _site_json(site)


@router.get("/{site_id}")
async def get_site(site_id: str, ctx: AuthContext = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    rows = await _deploy_rows(db, site)
    live = next((d for d in rows if d.id == site.current_deploy_id), None)
    if site.current_deploy_id and not live:
        live = (await db.execute(select(SiteDeploy).where(SiteDeploy.id == site.current_deploy_id))).scalars().first()
    return {**_site_json(site, rows[0] if rows else None, live), "deploys": [_deploy_json(d, site) for d in rows]}


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    slug: Optional[str] = Field(None, max_length=40)
    bot_id: Optional[str] = None  # "" removes the assistant
    spa: Optional[str] = None


@router.patch("/{site_id}")
async def update_site(site_id: str, data: SiteUpdate, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    old_slug = site.slug
    if data.name is not None:
        site.name = data.name.strip()
    if data.slug is not None and data.slug.strip().lower() != site.slug:
        slug = data.slug.strip().lower()
        problem = domains.slug_problem(slug)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        if await _slug_taken(db, slug, site.id):
            raise HTTPException(status_code=409, detail="That address is taken. Try another.")
        site.slug = slug
    if data.bot_id is not None:
        if data.bot_id:
            bot = (await db.execute(select(Bot.bot_id).where(Bot.bot_id == data.bot_id, Bot.user_id == ctx.owner_id))).first()
            if not bot:
                raise HTTPException(status_code=400, detail="Choose one of your assistants")
        site.bot_id = data.bot_id or None
    if data.spa is not None:
        if data.spa not in ("auto", "on", "off"):
            raise HTTPException(status_code=400, detail="Unknown setting")
        site.spa = data.spa
    await db.commit()
    serve.forget(old_slug)
    serve.forget(site.slug)
    return await get_site(site.id, ctx, db)


@router.delete("/{site_id}")
async def delete_site(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Takes the site offline now; it can be restored for 30 days, then its files are removed."""
    site = await _owned(site_id, ctx, db)
    site.deleted_at = datetime.utcnow()
    if site.domain_provider_id:
        await domains.cf_delete(site.domain_provider_id)
    site.custom_domain = site.domain_status = site.domain_provider_id = site.domain_error = None
    await db.commit()
    serve.forget(site.slug)
    return {"message": "Site deleted", "restorable_days": deploys.KEEP_DELETED_DAYS}


@router.post("/{site_id}/restore")
async def restore_site(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db, deleted=True)
    await plans.require_room_for_site(db, ctx.owner_id)
    site.deleted_at = None
    await db.commit()
    serve.forget(site.slug)
    return _site_json(site)


# ─── deploying ────────────────────────────────────────────────────
async def _start(db: AsyncSession, site: Site, source: str, ctx_user: Optional[str]) -> SiteDeploy:
    busy = (await db.execute(select(SiteDeploy.id).where(SiteDeploy.site_id == site.id, SiteDeploy.status == "building"))).first()
    if busy:
        raise HTTPException(status_code=409, detail="A deploy is already in progress for this site. Wait for it to finish.")
    deploy = SiteDeploy(site_id=site.id, source=source, status="building", created_by=ctx_user)
    db.add(deploy)
    await db.commit()
    return deploy


@router.post("/{site_id}/deploys")
async def upload_deploy(site_id: str, request: Request, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A .zip (field "archive"), or a folder's files (fields "files" with matching "paths")."""
    _ready()
    site = await _owned(site_id, ctx, db)
    rate_limit(f"site-deploy:{ctx.owner_id}", 60, 3600)
    lim = await plans.limits(db, ctx.owner_id)
    declared = int(request.headers.get("content-length") or 0)
    if declared > lim.deploy_bytes + 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"That upload is over your plan's {bundles.mb(lim.deploy_bytes)} per deployment")
    async with request.form(max_files=lim.deploy_files + 1, max_fields=lim.deploy_files + 10) as form:
        archive = form.get("archive")
        try:
            if archive is not None and hasattr(archive, "read"):
                raw = await archive.read()
                bundle = await asyncio.to_thread(bundles.from_zip, io.BytesIO(raw), lim)
            else:
                uploads = [f for f in form.getlist("files") if hasattr(f, "read")]
                paths = [str(p) for p in form.getlist("paths")]
                if not uploads:
                    raise BundleError("Choose a folder or a .zip file to publish")
                if len(paths) != len(uploads):
                    raise BundleError("The upload was incomplete. Try again.")
                items = [(path, await f.read()) for path, f in zip(paths, uploads)]
                bundle = await asyncio.to_thread(bundles.from_files, items, lim)
        except BundleError as e:
            raise HTTPException(status_code=400, detail=str(e))
    deploy = await _start(db, site, "upload", ctx.user_id)

    async def load():
        return bundle
    fire_and_forget(deploys.publish(deploy.id, site.id, load))
    return _deploy_json(deploy, site)


class GitDeploy(BaseModel):
    repo_url: Optional[str] = Field(None, max_length=300)  # empty: the saved repository
    branch: Optional[str] = Field(None, max_length=100)
    folder: Optional[str] = Field(None, max_length=200)
    token: Optional[str] = Field(None, max_length=300)  # empty: keep the saved token
    clear_token: bool = False


def _publish_git(deploy: SiteDeploy, site: Site, lim: plans.Limits) -> None:
    """Download the repository and publish it, in the background."""
    repo = git.parse(site.git_url, site.git_branch)
    token, folder = site.git_token, site.git_folder

    async def load():
        archive = await git.download(repo, token, max_bytes=min(lim.deploy_bytes * 4, 250 * 1024 * 1024))
        try:  # an archive also holds source files that aren't published, so it may be bigger than the site
            bundle = await asyncio.to_thread(bundles.from_zip, archive.file, lim, folder or None,
                                             min(lim.deploy_bytes * 6, 300 * 1024 * 1024))
        finally:
            archive.file.close()
        bundle.commit_sha, bundle.commit_message = archive.commit_sha, archive.commit_message
        return bundle
    fire_and_forget(deploys.publish(deploy.id, site.id, load))


@router.post("/{site_id}/deploys/git")
async def git_deploy(site_id: str, data: GitDeploy, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    _ready()
    site = await _owned(site_id, ctx, db)
    rate_limit(f"site-deploy:{ctx.owner_id}", 60, 3600)
    try:
        repo = git.parse(data.repo_url or site.git_url or "", data.branch if data.repo_url else (data.branch or site.git_branch))
        folder = bundles.clean_path(data.folder) if (data.folder or "").strip() else None
    except BundleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    site.git_url, site.git_branch, site.git_folder = repo.url, repo.branch, folder
    if data.clear_token:
        site.git_token = None
    elif (data.token or "").strip():
        site.git_token = data.token.strip()
    await db.commit()
    lim = await plans.limits(db, ctx.owner_id)
    deploy = await _start(db, site, "git", ctx.user_id)
    _publish_git(deploy, site, lim)
    return _deploy_json(deploy, site)


@router.post("/{site_id}/deploys/{deploy_id}/promote")
async def promote(site_id: str, deploy_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """Make an earlier (or later) version the live one: an instant rollback."""
    site = await _owned(site_id, ctx, db)
    deploy = (await db.execute(select(SiteDeploy).where(SiteDeploy.id == deploy_id, SiteDeploy.site_id == site.id))).scalars().first()
    if not deploy or deploy.status != "ready":
        raise HTTPException(status_code=400, detail="Only a successful deploy can go live")
    site.current_deploy_id = deploy.id
    await db.commit()
    serve.forget(site.slug)
    return await get_site(site.id, ctx, db)


# ─── deploy hook (publish on every push) ──────────────────────────
def _hook_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _hook_url(secret: str) -> str:
    base = os.getenv("PUBLIC_BACKEND_URL", "").rstrip("/") or "https://api.nimmiai.in"
    return f"{base}/api/sites/hooks/{secret}"


@router.post("/{site_id}/hook")
async def create_hook(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    """A secret link that publishes the repository again; add it to GitHub/GitLab as a push webhook.
    Shown once: making a new one replaces the old."""
    site = await _owned(site_id, ctx, db)
    if not site.git_url:
        raise HTTPException(status_code=400, detail="Publish from a repository first")
    secret = secrets.token_urlsafe(32)
    site.hook_secret = _hook_hash(secret)
    await db.commit()
    return {"url": _hook_url(secret)}


@router.delete("/{site_id}/hook")
async def delete_hook(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    site.hook_secret = None
    await db.commit()
    return {"message": "Deploy hook removed"}


@router.post("/hooks/{secret}")
async def run_hook(secret: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Public: called by GitHub/GitLab on push. Pushes to other branches are ignored."""
    rate_limit(f"site-hook:{client_ip(request)}", 30, 600)
    if len(secret) < 20:
        raise HTTPException(status_code=404, detail="Unknown hook")
    site = (await db.execute(select(Site).where(Site.hook_secret == _hook_hash(secret), Site.deleted_at.is_(None)))).scalars().first()
    if not site or not site.git_url:
        raise HTTPException(status_code=404, detail="Unknown hook")
    event = request.headers.get("x-github-event") or request.headers.get("x-gitlab-event") or ""
    if event == "ping":
        return {"message": "Hook is connected"}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    ref = payload.get("ref") if isinstance(payload, dict) else None
    if ref and site.git_branch and ref != f"refs/heads/{site.git_branch}":
        return {"message": f"Ignored: a push to {ref}, this site publishes {site.git_branch}"}
    rate_limit(f"site-hook-site:{site.id}", 6, 600)
    lim = await plans.limits(db, site.user_id)
    try:
        deploy = await _start(db, site, "hook", None)
    except HTTPException:
        return {"message": "A deploy is already in progress"}
    _publish_git(deploy, site, lim)
    return {"message": "Deploy started", "deploy_id": deploy.id}


# ─── custom domain ────────────────────────────────────────────────
class DomainIn(BaseModel):
    domain: str = Field(..., max_length=253)


@router.put("/{site_id}/domain")
async def set_domain(site_id: str, data: DomainIn, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    await plans.require(db, ctx.owner_id, "custom_domains")
    if not domains.custom_domains_available():
        raise HTTPException(status_code=503, detail="Custom domains aren't available on this server yet.")
    try:
        host = domains.normalize(data.domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if domains.is_apex(host):
        raise HTTPException(status_code=400, detail=f"Use www.{host} (or another subdomain). Most registrars, GoDaddy included, "
                                                    f"can't point a bare domain with a CNAME; we'll show you how to forward {host} to it.")
    taken = (await db.execute(select(Site.id).where(Site.custom_domain == host, Site.id != site.id))).first()
    if taken:
        raise HTTPException(status_code=409, detail="That domain is already connected to another site")
    if site.domain_provider_id:
        await domains.cf_delete(site.domain_provider_id)
    site.custom_domain, site.domain_status, site.domain_error = host, "pending", None
    site.domain_token, site.domain_provider_id = secrets.token_hex(16), None
    site.domain_added_at, site.domain_checked_at = datetime.utcnow(), None
    await db.commit()
    serve.forget(site.slug)
    return await get_site(site.id, ctx, db)


@router.post("/{site_id}/domain/check")
async def check_domain(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    if not site.custom_domain:
        raise HTTPException(status_code=400, detail="Add a domain first")
    rate_limit(f"domain-check:{site.id}", 20, 600)
    await deploys.check_domain(site)
    await db.commit()
    serve.forget(site.slug)
    return await get_site(site.id, ctx, db)


@router.delete("/{site_id}/domain")
async def remove_domain(site_id: str, ctx: AuthContext = Depends(require_manager), db: AsyncSession = Depends(get_db)):
    site = await _owned(site_id, ctx, db)
    if site.domain_provider_id:
        await domains.cf_delete(site.domain_provider_id)
    site.custom_domain = site.domain_status = site.domain_provider_id = site.domain_error = site.domain_token = None
    site.domain_added_at = site.domain_checked_at = None
    await db.commit()
    serve.forget(site.slug)
    return await get_site(site.id, ctx, db)


# ─── abuse (operations) ───────────────────────────────────────────
@router.post("/admin/{slug}/{action}")
async def admin_block(slug: str, action: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Ops: take a site down for abuse (phishing, malware) or put it back. Needs X-Admin-Key."""
    key = os.getenv("ADMIN_API_KEY")
    if key and len(key) < 24 and is_production():
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is too short. Use at least 24 random characters.")
    if not key or not hmac.compare_digest(request.headers.get("x-admin-key", ""), key):
        raise HTTPException(status_code=403, detail="Forbidden")
    if action not in ("block", "unblock"):
        raise HTTPException(status_code=400, detail="Use block or unblock")
    site = (await db.execute(select(Site).where(Site.slug == slug))).scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.status = "blocked" if action == "block" else "active"
    await db.commit()
    serve.forget(site.slug)
    return {"slug": site.slug, "status": site.status}
