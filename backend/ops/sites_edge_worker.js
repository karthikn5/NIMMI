/**
 * Cloudflare Worker in front of websites published on Nimmi (free <slug>.<SITES_DOMAIN> addresses
 * and customers' own domains connected through Cloudflare for SaaS). See ops/SITES_SETUP.md.
 *
 * Railway only answers host names registered on the service, so every visit is sent to the API's
 * own address, with the visitor's host in X-Nimmi-Site-Host and the shared key that makes the
 * backend trust it (sites/serve.py).
 *
 * Worker variables: ORIGIN (e.g. https://api.nimmiai.in) and SITES_EDGE_KEY (secret, same value as
 * the backend's SITES_EDGE_KEY).
 */
export default {
    async fetch(request, env) {
        if (request.method !== "GET" && request.method !== "HEAD") {
            return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });
        }
        const url = new URL(request.url);
        const target = new URL(url.pathname + url.search, env.ORIGIN);
        const headers = new Headers(request.headers);
        headers.set("X-Nimmi-Site-Host", url.host);
        headers.set("X-Nimmi-Edge-Key", env.SITES_EDGE_KEY);
        headers.delete("cookie"); // sites are static files; visitors' cookies never leave the edge
        // no-store: every site shares the origin's address, so a cached /style.css must never be
        // served to another site. Browsers still cache by the Cache-Control the backend sends.
        return fetch(target, { method: request.method, headers, redirect: "manual", cache: "no-store" });
    },
};
