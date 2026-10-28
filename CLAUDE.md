# Nimmi AI

Indian SaaS for AI assistants on three channels: a website chat widget, WhatsApp, and phone calls
(voice AI). Live at https://nimmiai.in (dashboard) and https://api.nimmiai.in (backend).
Owner's GitHub: `karthikn5` (repo `karthikn5/NIMMI`, public). Private operational notes (git-ignored,
only on the owner's machines): @.claude/private-notes.md

## How to work with the owner

- Senior-level, production-quality work: "100% commercial, without any gap". Research and test end to end
  before saying something works; report real measurements, never invented numbers.
- No emojis anywhere (UI, copy, messages). Professional, consistent UI in the site's theme.
- Explain in plain, simple English (the owner writes informal English, sometimes Tamil); give exact click
  paths for third-party consoles (Railway, GoDaddy, Twilio, Google).
- Ask before: committing or pushing, any production change (database, Railway, DNS), anything paid or
  outward-facing. Read-only checks are fine. Never put secrets in git: the GitHub repo is public.
- Don't touch port 8000 locally (another project). This app uses 8001 (backend) and 3000 (dashboard).

### The owner's words
- "live" = production (nimmiai.in, api.nimmiai.in); "local" = this machine (localhost:3000 / :8001).
- "agent" / "voice agent" = an assistant's phone voice settings; "Call me" = the test call button on the
  agent page; "the call is cut" = the call drops; "min left" / "minutes" = the voice wallet.
- "deployment(s)" = the Vercel-like static website hosting feature; "live chat" = human handoff chat
  (dashboard Live chat page + the widget's "Talk to a person"); "watermark" = the "Powered by Nimmi" line.
- "free tier rules" = free plan: 1 assistant + 1 website; voice, integrations, custom domains need a paid plan.
- "builder" = assistant builder (Design / Knowledge / Behaviour / Flow / Leads); "Add to website" = export modal.
- Test assistant: bot `d55deb11-a8d0-45cb-945a-f61c9c11291f` ("Kdbot" locally, "GBot" on live).

## Repository layout

- `backend/` FastAPI app (Python 3.12). Entry `main.py`.
  - `routers/`: auth_routes, bots (builder, knowledge, install, WordPress plugin), chat (public widget
    API), handoffs (live chat, agent side), workspace, team, analytics, integrations, whatsapp, email_center, sites.
  - `voice/`: phone assistant (see Voice). `sites/`: static site hosting. `notify/`: email + events.
    `plugins/wordpress/`: WordPress plugin source. `ops/`: runbooks (SITES_SETUP.md, backups).
  - Core modules: `models.py` (SQLAlchemy models), `database.py` (engine, pool), `auth.py` (JWT, workspaces,
    roles owner/admin/agent, rate limits), `plans.py` (free/paid limits), `secretbox.py` (encrypted
    columns), `ai.py` (Gemini REST, model order), `utils.py` (chat answers), `vector_store.py` (Pinecone),
    `knowledge_sources.py`, `brain.py` (summaries, learned details), `assist.py` (business hours, lead score,
    unanswered questions), `realtime.py` (Socket.IO), `payments.py` / `subscriptions.py` (Razorpay), `phone.py`.
  - Many old one-off scripts at `backend/*.py` (check_*, fix_*, test_bot_*): not part of the app.
  - `tests/`: pytest suite (~177 tests, ~100 s).
  - `static/nimmi-widget.js`: the embed script customers paste; it opens an iframe of the dashboard's `/widget/[botId]`.
- `dashboard/` Next.js 15 (React 19, Tailwind), App Router in `src/app`: `/dashboard/*` (builder, voice,
  live-chat, deployments, integrations, analytics, questions, team, billing, profile), `/widget/[botId]`
  (the chat widget itself), `/demo/[id]`, `/auth/*`, `/blog`, `/solutions/[industry]`.
  Shared UI kit in `src/components/ui.tsx`; API helpers `src/lib/api.ts`, live chat socket `src/lib/liveChat.ts`.
- Root docs: `SECURITY.md` (security audit and hardening), research/requirement notes.

## Running locally (Windows)

- Backend: `cd backend` then `$env:PORT=8001; venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001`.
  `LOCAL_DEV=true` in `backend/.env` uses SQLite `backend/nimmi_local.db` (never production), relaxes some
  checks, and is ignored in production.
- Dashboard: `cd dashboard` then `npm run dev` (port 3000); `dashboard/.env.local` points it at `http://localhost:8001`.
- Tests: from `backend/`: `venv\Scripts\python -m pytest -q -p no:warnings tests` (always target `tests`;
  running from the repo root collects stray scripts). Dashboard check: `npx tsc --noEmit -p .` (ESLint isn't configured).
- Scripts that import backend modules: run from `backend/` with `PYTHONPATH=".;.."` and `PYTHONIOENCODING=utf-8`.
  Importing `database` prints a "[DB] Using SQLite" line to stdout: take the last line when capturing output.
- Local sign-in token for scripts: `venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv('.env'); from auth import issue_token; print(issue_token('<user id>'))"`.
- Phone calls to a local backend need a public tunnel (Twilio must reach it): `cloudflared tunnel --url http://localhost:8001`,
  put the https URL in `PUBLIC_BACKEND_URL` in `backend/.env`, restart the backend. "Call me" refuses to dial
  if that URL is unreachable. Through the tunnel, Twilio (US) to a laptop in India adds ~1-2 s per direction.
- Bash on Windows: heredocs mangle backslashes (write scripts with a file instead); MSYS rewrites args starting
  with "/" (`MSYS_NO_PATHCONV=1`); a plain `sleep` loop is slow, pace against the clock.

## Production

- Railway: two services from this repo. Backend runs `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`
  (`backend/nixpacks.toml`): FOUR processes, so anything kept in memory is per process (sockets, caches,
  pending transfers). The scheduler loop runs in every process and claims jobs atomically.
- Database: Supabase Postgres (also auth helpers and storage). The session pooler (port 5432) allows only 15
  clients in total: pool defaults are `DB_POOL_SIZE=2`, `DB_POOL_OVERFLOW=1`; the transaction pooler (6543) allows more.
  New nullable columns are added at startup (no migration tool); other schema changes need care.
- Regions: Railway US West, Supabase Sydney, users in India: every DB round trip is slow (~0.2-0.75 s);
  moving both to Singapore is recommended. Deploys happen on push to `main`.
- DNS at GoDaddy: `api` CNAME to Railway; Google Workspace mail on nimmiai.in (MX smtp.google.com, one SPF record).
- Transactional email via Resend (`notify/email.py`), SMTP fallback.

## Product rules

- Plans (`plans.py`): free = 1 assistant + 1 website, no custom domain; voice, integrations, custom domains
  need paid. A workspace is paid while any of its assistants has an active subscription (or one the owner
  paid for). `ENFORCE_PLAN_LIMITS` is off in tests.
- Workspaces: owner plus team members (admin/agent); requests act on `ctx.owner_id`; the `X-Workspace` header picks one.
- Encrypted secrets (customer AI keys, phone account tokens): `secretbox` MultiFernet over ENCRYPTION_KEY
  (+ JWT_SECRET, + `ENCRYPTION_OLD_KEYS` decrypt-only); columns store `enc:v1:...`.

## Chat widget and live chat

- Widget page `dashboard/src/app/widget/[botId]/page.tsx`: visual flow runner, AI chat, voice input,
  "Prefer a call?" call-back request, "Talk to a person" handoff, "Powered by Nimmi" (links to nimmiai.in).
  Sessions: `widget-session-ai-<visitorId>` and `widget-session-human-<visitorId>` (random id in localStorage
  is the visitor's proof).
- Live chat across processes: team replies go through `POST /api/handoffs/{id}/reply` (saved, then emitted);
  the widget also checks `GET /api/chat/live/{bot}/{session}` every 4 s and the dashboard re-reads the open chat,
  deduplicating by message id. `REALTIME_REDIS_URL` (optional) makes Socket.IO share messages between
  processes for instant delivery. Rooms and permissions: see the docstring in `backend/realtime.py`.

## Voice (phone assistant)

- Flow: dial or incoming call -> Twilio Media Stream (8 kHz mu-law WebSocket, `transports.py`) or Exotel ->
  `voice/router.py::_route_and_run` (lookups in parallel) -> `pipeline.py::CallSession.run`.
- Speech: Sarvam (`sarvam.py`): streaming STT `saaras:v3` (language `unknown` when following the caller,
  codemix mode), streaming TTS `bulbul:v3` with REST fallback. Tested Oct 2026: saaras:v4 no faster and
  spells Tamil phone numbers as words; bulbul:v4-flash no faster. Keep v3 unless re-measured.
- Replies (`llm.py`): Groq first (rotation `qwen/qwen3.8-27b` -> `openai/gpt-oss-20b` -> `openai/gpt-oss-120b`,
  SDK retries OFF so a rate limit fails over instantly), Gemini REST last. The free Groq tier
  (8k tokens/min/model) is the main cause of slow or stuck turns; the paid tier fixes it. Kdbot's prompt is
  ~9,100 characters per answer (measured Oct 2026). A model with no words after 3 s rests 15 s (`SlowModel`);
  Gemini on a call gets an 8 s limit, not the chat's 30 s.
  `reply_sentences` splits sentences (also "?word" without a space, never at "..."), ends the turn at a question,
  and drops filler sounds/empty reactions ("Hmm,", "ஓ, அப்படியா!") in `_clean_for_speech`. The prompt must never
  give filler examples: models copy them into every reply (seen on real calls, Oct 2026).
- Call behaviour (`pipeline.py`): speaks first the moment the call connects (opening audio cached in memory and
  in `VOICE_OPENINGS_DIR`, made ahead while the phone rings / when the agent is saved); the opening can't be
  interrupted and a "hello" over it is ignored; barge-in only after the caller keeps talking `BARGE_IN_SEC` (1 s;
  a cough or "mm" ends sooner), or at once for words that need an answer; "ok"/"சரி" and the agent's own echo
  over its speech are ignored; follows the caller's language (script detection `spoken_language`, per-agent
  `follow_caller_language`): one clear sentence (`switch_now`: 3+ words in an Indian script; English 5+ and
  Sarvam's `language_probability` not below 0.6) or two in a row switch, pre-connecting the new language's voice
  (Sarvam gave clear Tanglish only 0.58, so the probability never blocks Indian-script sentences);
  number check for 10-digit Indian numbers; end phrases and opt-out (DNC); silence reminders; "one moment" once
  if an answer takes 3 s, the fallback apology at 15 s; one sentence at a time on the voice connection
  (`self.voice` lock, `aclosing`); every speech step has a time limit (`TTS_FIRST_AUDIO_SEC`, gaps
  `TTS_CHUNK_GAP_SEC`, then REST) and idle voices are pinged (Sarvam closes them after a minute); if the speech
  service fails or drops, the call ends within ~2 s, is logged "failed" and isn't billed.
- Python's `\w` doesn't match Indic vowel signs: split words with `llm.plain_words`, not `[^\w]` regexes.
- Minutes: `voice_wallets` (plan minutes + top-up minutes, `metering.py`); every connected call bills at least a minute.
- Outbound: `scheduler.py` dials call-backs and campaigns; answering-machine detection only when the agent's
  voicemail action isn't "off" (it adds 2-4 s before the call connects).
- Logs to read: "opening started X s after the call connected", "reply timing: ...", "Voice reply from <model>",
  "the caller kept talking over the agent", "that sounded like <lang>", "the answer is slow; saying one moment",
  "Streaming TTS failed (...); using REST".
- Tests for these real-call problems: `tests/test_voice_reliability.py`.
- Simulated calls without a phone: `dev-scripts/voice/lang_call.py` (git-ignored local harnesses; see `dev-scripts/README.md`).

## Testing conventions

- Fakes in `tests/test_pipeline.py` (FakeTransport, FakeStt, fake_tts, replier_saying); `run` fixture runs
  coroutines on the app loop; `make_user` makes a signed-up user with `.bot()`.
- For timing-sensitive tests, make ordering deterministic (Windows timers are coarse: ~16 ms).
- New behaviour gets a test that fails without the fix (check by reverting the fix once).
