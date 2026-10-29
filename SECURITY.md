# Security and data safety

How Nimmi protects customer data, and what to do when something goes wrong.

## How data is protected

| Layer | Protection |
|---|---|
| Database | Only the backend reads it (connects as the table owner). Row level security is on for every table, so Supabase's public REST API returns nothing; the backend re-checks this on every start (`database._close_public_api`). |
| Secrets at rest | Customers' AI keys, WhatsApp, LeadSquared and webhook secrets, and Twilio/Exotel keys are encrypted with `ENCRYPTION_KEY` (`secretbox.EncryptedText`). Password reset links are stored hashed; passwords use bcrypt. |
| Accounts | Sessions are signed with `JWT_SECRET` (required in production). Changing or resetting a password signs out every other device; Profile has "Sign out everywhere". Changing the email needs the current password. Google sign-in only accepts addresses Google has verified. Team invites are accepted through the invite link only. |
| Workspaces | Every signed-in endpoint checks the workspace. `tests/test_tenant_isolation.py` calls all of them as another workspace and fails if any data is shown or changed. |
| Live chat | Agents can only open their own workspace's conversations and only they speak as "agent"; WhatsApp rooms are kept apart per assistant. |
| Public endpoints | Size limits on every request, rate limits per visitor address, and the flow's HTTP and AI steps only run what the business put in its flow. Outbound requests to customer-supplied URLs can't reach private networks, also after redirects (`netsafe.safe_client`). |
| Uploads | Images are recognised by their content. An SVG is never stored as sent: `svgsafe` rebuilds it from a list of drawing elements, without scripts, event handlers, animation, links, embedded pages or anything loaded from outside the file. PDFs must be real PDFs, and `/static` files are served sandboxed. |
| Calls | Only to supported countries (`CALL_COUNTRY_CODES`), never to premium-rate ranges. Twilio webhooks need Twilio's signature. |
| Browsers | Security headers on the API and dashboard; the dashboard can't be framed by other sites (the widget can). |
| Data loss | A daily encrypted backup (private `backups` bucket, 30 days). Deleted assistants can be restored for 30 days, and payment records are never deleted with them. Uploads and recordings never silently fall back to the server's disk in production. |

## Production settings (Railway, backend service)

Required: `DATABASE_URL`, `JWT_SECRET` (32+ random characters), `ENCRYPTION_KEY`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`. Also set `ADMIN_API_KEY` (24+ characters) if you use the admin endpoint.
The server refuses to start without `DATABASE_URL` or `JWT_SECRET`. See `backend/.env.example`.

Keep a copy of `ENCRYPTION_KEY` in a password manager. Without it, stored secrets and backups can't be read.

## Backups

- Automatic: once a day, when `SUPABASE_SERVICE_ROLE_KEY` is set. Check Supabase, Storage, `backups`.
- Manual, from `backend/`: `python -m ops.backup --out nimmi.backup`
- Restore into a new, empty database: set `DATABASE_URL` to it, then `python -m ops.restore nimmi.backup`.
  Check the data, then point Railway's `DATABASE_URL` at it.
- Also turn on Supabase's own backups (Pro plan, ideally point-in-time recovery).

## If a secret leaks

| What leaked | Do this |
|---|---|
| Database password | Supabase, Project Settings, Database, Reset database password. Update `DATABASE_URL` in Railway and redeploy. |
| `JWT_SECRET` | Set a new one in Railway. Everyone is signed out. |
| `ENCRYPTION_KEY` | Set the new key as `ENCRYPTION_KEY` and the old one as `JWT_SECRET` for one deploy (both can decrypt; new values use the new key), then ask customers to re-enter their keys. |
| Supabase service key, Twilio, Resend, Razorpay | Rotate it in that provider's dashboard and update Railway. |
| A customer's API key | Tell the customer to revoke it at their provider and save a new one in the builder. |

Never commit `.env` files. Secrets only live in Railway and in your local `backend/.env`.

## Before each release

```
cd backend && venv/Scripts/python -m pytest -q tests     # includes the isolation and hardening tests
cd dashboard && npm audit --omit=dev
```
and `pip-audit -r backend/requirements.txt` from time to time; raise the version floors in
`requirements.txt` when advisories land.
