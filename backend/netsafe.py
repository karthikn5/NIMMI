"""
Outbound URL safety. Used wherever the server fetches a URL that a customer
or visitor supplied (HTTP request node, website crawler, CRM webhooks), so
those features can't be used to reach internal services.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrl(ValueError):
    pass


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )


async def assert_public_url(url: str) -> str:
    """Raise UnsafeUrl unless `url` is http(s) and every resolved address is public."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrl("Only http and https URLs are allowed")
    host = parsed.hostname
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise UnsafeUrl("That address could not be found")
    for info in infos:
        if not _is_public(info[4][0]):
            raise UnsafeUrl("That address points to a private network")
    return url.strip()
