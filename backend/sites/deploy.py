"""
Publishing a deploy, and housekeeping.

A deploy stores its new files, then switches the site to it in one update, so visitors see the
old version or the new one, never a half-published mix. A failed deploy leaves the site as it was.
Older deploys beyond the plan's limit are removed with the files nothing else uses.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

from sqlalchemy.future import select

import plans
from database import async_session
from backend.models import Site, SiteDeploy
from sites import domains, serve, storage
from sites.bundle import Bundle, BundleError

logger = logging.getLogger(__name__)

_slots = asyncio.Semaphore(3)  # deploys processed at once per server (each can hold up to 100 MB)
STALE_AFTER = timedelta(minutes=20)
KEEP_DELETED_DAYS = 30


async def _fail(deploy_id: str, message: str) -> None:
    async with async_session() as db:
        deploy = (await db.execute(select(SiteDeploy).where(SiteDeploy.id == deploy_id))).scalars().first()
        if deploy and deploy.status == "building":
            deploy.status, deploy.error, deploy.finished_at = "failed", message[:500], datetime.utcnow()
            await db.commit()


async def publish(deploy_id: str, site_id: str, load: Callable[[], Awaitable[Bundle]]) -> None:
    """Run in the background: get the files, store the new ones, make the deploy live."""
    async with _slots:
        try:
            bundle = await load()
            manifest = bundle.manifest()
            async with async_session() as db:
                site = (await db.execute(select(Site).where(Site.id == site_id))).scalars().first()
                if not site or site.deleted_at:
                    raise BundleError("The site was deleted while publishing")
                stored = set()
                for files in (await db.execute(select(SiteDeploy.files).where(
                        SiteDeploy.site_id == site_id, SiteDeploy.status == "ready"))).scalars().all():
                    stored.update(entry[0] for entry in (files or {}).values())
            fresh: dict[str, bytes] = {}
            for path, (sha, _) in manifest.items():
                if sha not in stored:
                    fresh[sha] = bundle.files[path]
            await storage.put_many(site_id, fresh)

            async with async_session() as db:
                site = (await db.execute(select(Site).where(Site.id == site_id))).scalars().first()
                deploy = (await db.execute(select(SiteDeploy).where(SiteDeploy.id == deploy_id))).scalars().first()
                if not site or not deploy or deploy.status != "building":
                    return
                deploy.files, deploy.file_count, deploy.total_bytes = manifest, len(manifest), bundle.total_bytes
                deploy.spa, deploy.note = bundle.spa, bundle.note()
                deploy.commit_sha, deploy.commit_message = bundle.commit_sha, bundle.commit_message
                deploy.status, deploy.finished_at = "ready", datetime.utcnow()
                site.current_deploy_id = deploy.id
                slug, owner = site.slug, site.user_id
                await db.commit()
            serve.forget(slug)
            async with async_session() as db:
                keep = (await plans.limits(db, owner)).deploys_kept
            await prune(site_id, keep)
        except BundleError as e:
            await _fail(deploy_id, str(e))
        except Exception as e:
            logger.exception(f"Deploy {deploy_id} failed: {e}")
            await _fail(deploy_id, "Something went wrong while publishing. Try again; if it keeps happening, contact support.")


async def prune(site_id: str, keep: int) -> None:
    """Keep the newest `keep` ready deploys (and the live one) plus recent failures; remove the rest and unused files."""
    async with async_session() as db:
        site = (await db.execute(select(Site).where(Site.id == site_id))).scalars().first()
        deploys = (await db.execute(select(SiteDeploy).where(SiteDeploy.site_id == site_id)
                                    .order_by(SiteDeploy.created_at.desc()))).scalars().all()
        ready = [d for d in deploys if d.status == "ready"]
        kept_ids = {d.id for d in ready[:keep]} | ({site.current_deploy_id} if site and site.current_deploy_id else set())
        kept_ids |= {d.id for d in [d for d in deploys if d.status != "ready"][:10]}  # recent failures stay visible
        drop = [d for d in deploys if d.id not in kept_ids]
        if not drop:
            return
        used = {entry[0] for d in deploys if d.id in kept_ids for entry in (d.files or {}).values()}
        unused = {entry[0] for d in drop for entry in (d.files or {}).values()} - used
        for d in drop:
            await db.delete(d)
        await db.commit()
    await storage.delete_many(site_id, unused)


async def remove_site_files(site: Site) -> None:
    async with async_session() as db:
        shas = set()
        for files in (await db.execute(select(SiteDeploy.files).where(SiteDeploy.site_id == site.id))).scalars().all():
            shas.update(entry[0] for entry in (files or {}).values())
    await storage.delete_many(site.id, shas)


async def check_domain(site: Site) -> None:
    """Move a custom domain along: DNS records found -> certificate requested -> live. Updates `site` (caller commits)."""
    if not site.custom_domain:
        return
    owned, pointed = await domains.dns_status(site.custom_domain, site.domain_token)
    site.domain_checked_at = datetime.utcnow()
    if not owned:
        site.domain_status, site.domain_error = "pending", "The TXT record isn't visible yet."
        return
    if not pointed:
        site.domain_status, site.domain_error = "pending", "The CNAME record doesn't point to Nimmi yet."
        return
    if not domains.cloudflare():  # local development: DNS is all there is to check
        site.domain_status, site.domain_error = "active", None
        return
    try:
        if not site.domain_provider_id:
            site.domain_provider_id = await domains.cf_create(site.custom_domain)
        ready, problem = await domains.cf_status(site.domain_provider_id)
    except Exception as e:
        logger.warning(f"Custom domain {site.custom_domain}: {e}")
        site.domain_status, site.domain_error = "issuing", "Setting up the secure certificate. This usually takes a few minutes."
        return
    site.domain_status = "active" if ready else "issuing"
    site.domain_error = None if ready else (problem or "Setting up the secure certificate. This usually takes a few minutes.")


async def maintenance() -> None:
    """From the scheduler: fail deploys cut off by a restart, check pending domains, remove sites deleted 30 days ago."""
    now = datetime.utcnow()
    async with async_session() as db:
        stale = (await db.execute(select(SiteDeploy).where(
            SiteDeploy.status == "building", SiteDeploy.created_at < now - STALE_AFTER))).scalars().all()
        for d in stale:
            d.status, d.error, d.finished_at = "failed", "Publishing was interrupted. Deploy again.", now
        waiting = (await db.execute(select(Site).where(
            Site.domain_status.in_(("pending", "issuing")), Site.deleted_at.is_(None)))).scalars().all()
        for site in waiting:
            checked = site.domain_checked_at.replace(tzinfo=None) if site.domain_checked_at else None
            if checked and now - checked < timedelta(minutes=10):
                continue
            added = site.domain_added_at.replace(tzinfo=None) if site.domain_added_at else now
            if site.domain_status == "pending" and now - added > timedelta(days=7):
                site.domain_status, site.domain_error = "failed", "We couldn't find the DNS records for a week. Check them and try again."
                continue
            try:
                await check_domain(site)
            except Exception as e:
                logger.warning(f"Domain check for {site.custom_domain} failed: {e}")
        await db.commit()
        expired = (await db.execute(select(Site).where(
            Site.deleted_at.is_not(None), Site.deleted_at < now - timedelta(days=KEEP_DELETED_DAYS)))).scalars().all()
        for site in expired:
            await remove_site_files(site)
            if site.domain_provider_id:
                await domains.cf_delete(site.domain_provider_id)
            await db.delete(site)
        await db.commit()
    if stale or expired:
        serve.forget()
