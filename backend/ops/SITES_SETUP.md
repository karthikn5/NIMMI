# Turning on Deployments (website hosting)

Deployments needs three things in production: a domain to publish sites under, file storage, and
(for paid plans' custom domains) Cloudflare for SaaS. The code is in `sites/` and `routers/sites.py`.

## 1. A domain for published sites

Use a **separate domain** for customers' sites, for example `nimmi.site` (about ₹1,000 a year).
Sites are other people's HTML and JavaScript; if one is ever used for phishing, browsers and
blocklists flag the whole domain. Keeping them off `nimmiai.in` protects the product, the API and
your email reputation (GitHub uses github.io, Vercel uses vercel.app for the same reason).

Set on Railway: `SITES_DOMAIN=nimmi.site` and `SITES_EDGE_KEY=<40+ random characters>`.

## 2. File storage

Sites' files go to a private Supabase Storage bucket named `sites` (created automatically). This
needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, which daily backups already use.

## 3. Routing visits to Nimmi

**Option A: free addresses only (quickest).** In Railway, open the backend service, Settings,
Networking, Custom Domain, and add `*.nimmi.site`. Add the two DNS records Railway shows (a
wildcard CNAME and an `_acme-challenge` CNAME, which must not be proxied). Railway issues one
wildcard certificate. Custom domains won't be available in this setup.

**Option B: free addresses and custom domains (recommended).** Railway serves at most 20 custom
domains per service, so customers' domains go through Cloudflare for SaaS instead (100 domains
free, then US$0.10 per domain per month).

1. Add `nimmi.site` to Cloudflare (Free plan is fine) and point its nameservers there.
2. DNS: `origin` as an `AAAA` record to `100::`, proxied (the worker answers; nothing runs there).
   `*` as a CNAME to `origin.nimmi.site`, proxied. `cname` as a CNAME to `origin.nimmi.site`, proxied.
3. SSL/TLS, Custom Hostnames: enable Cloudflare for SaaS and set the fallback origin to `origin.nimmi.site`.
4. Workers: create a worker from `ops/sites_edge_worker.js`. Variables: `ORIGIN=https://api.nimmiai.in`,
   secret `SITES_EDGE_KEY` (same value as on Railway). Routes: `*.nimmi.site/*` and `*/*` (the second
   one is what serves customers' own domains).
5. API token (My Profile, API Tokens): permission Zone, SSL and Certificates, Edit, for `nimmi.site`.
6. On Railway: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` (Overview page of the zone),
   `CUSTOM_DOMAIN_TARGET=cname.nimmi.site`.

Customers then add, at GoDaddy or any registrar: a CNAME `www` to `cname.nimmi.site` and a TXT
record `_nimmi-verify.www` proving the domain is theirs. Nimmi checks both, registers the domain
with Cloudflare, and Cloudflare issues and renews its HTTPS certificate. The site's page in the
dashboard shows customers these steps.

## Plans

Limits are in `plans.py`: free is 1 assistant, 1 website, 25 MB per deployment, no custom domain,
no voice or integrations; paid is 10 websites, 100 MB per deployment, custom domains, voice and
integrations. A workspace is paid while any of its assistants has an active plan.

## Abuse

Take a site down (it shows "This site is unavailable" right away), or bring it back:

    curl -X POST https://api.nimmiai.in/api/sites/admin/<slug>/block   -H "X-Admin-Key: $ADMIN_API_KEY"
    curl -X POST https://api.nimmiai.in/api/sites/admin/<slug>/unblock -H "X-Admin-Key: $ADMIN_API_KEY"

Uploads never include `.env` files, private keys, `.git`, `node_modules` or program files
(`.exe`, `.apk`, ...), and paths that try to leave the site are refused.
