"""
Outbound URL safety. Used wherever the server fetches a URL that a customer
or visitor supplied (HTTP request node, website crawler, CRM webhooks), so
those features can't be used to reach internal services.

Two layers:
  assert_public_url()  a quick check with a friendly error before doing anything.
  safe_client()        an httpx client whose every connection, including each redirect,
                       is checked at connect time against the address it actually dials.
                       This closes DNS rebinding (a name that resolves to a public address
                       for the check and a private one for the request) and redirects into
                       the private network.
"""
import asyncio
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

import httpcore
import httpx


class UnsafeUrl(ValueError):
    pass


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped or addr.sixtofour or (addr.teredo[1] if addr.teredo else None)
        if mapped is not None:
            return _is_public(str(mapped))
    # is_global excludes private, loopback, link-local (cloud metadata), shared (100.64/10),
    # reserved, benchmarking and documentation ranges.
    return addr.is_global and not addr.is_multicast


def _parse(url: str):
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrl("Only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrl("URLs with a username or password aren't allowed")
    return parsed


async def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeUrl("That address could not be found")
    return list(dict.fromkeys(info[4][0] for info in infos))


async def assert_public_url(url: str) -> str:
    """Raise UnsafeUrl unless `url` is http(s) and every resolved address is public."""
    parsed = _parse(url)
    for ip in await _resolve(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)):
        if not _is_public(ip):
            raise UnsafeUrl("That address points to a private network")
    return url.strip()


class _PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Resolves the host itself and connects only to a checked public address."""

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host: str, port: int, timeout: Optional[float] = None,
                          local_address: Optional[str] = None, socket_options=None):
        ips = await _resolve(host, port)
        if not ips or not all(_is_public(ip) for ip in ips):
            raise httpcore.ConnectError(f"Blocked: {host} points to a private network")
        # TLS still verifies the certificate for `host` (httpx passes the hostname for SNI).
        return await self._inner.connect_tcp(ips[0], port, timeout=timeout, local_address=local_address,
                                             socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.ConnectError("Blocked: unix sockets")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _SafeTransport(httpx.AsyncHTTPTransport):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        pool = self._pool
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=pool._ssl_context, max_connections=pool._max_connections,
            max_keepalive_connections=pool._max_keepalive_connections, keepalive_expiry=pool._keepalive_expiry,
            http1=pool._http1, http2=pool._http2, retries=pool._retries, network_backend=_PublicOnlyBackend(),
        )


def safe_client(timeout: float = 10.0, follow_redirects: bool = False, max_redirects: int = 5) -> httpx.AsyncClient:
    """An httpx client for user-supplied URLs: public internet only, also after redirects. No proxies from the environment."""
    return httpx.AsyncClient(transport=_SafeTransport(), timeout=timeout, follow_redirects=follow_redirects,
                             max_redirects=max_redirects, trust_env=False)
