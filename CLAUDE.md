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
  agent page; "the call is cut" = the call drops; "credits" (before Oct 2026: "min left" / "minutes") = the voice wallet;
  "model" / "AI model" = the agent's AI model (Voice > Agents).
- "schedule" = Voice > Schedule: call-backs callers ask for, follow-ups by lead status, meetings the owner approves.
- "deployment(s)" = the Vercel-like static website hosting feature; "live chat" = human handoff chat
  (dashboard Live chat page + the widget's "Talk to a person"); "watermark" = the "Powered by Nimmi" line.
- "free tier rules" = free plan: 1 assistant + 1 website + 10 voice credits (calls are pay as you go with credit packs);
  integrations and custom domains need a paid plan.
- "builder" = assistant builder (Design / Knowledge / Behaviour / Flow / Leads); "Add to website" = export modal.
- Test assistant: bot `d55deb11-a8d0-45cb-945a-f61c9c11291f` ("Kdbot" locally, "GBot" on live).

## Repository layout

- `backend/` FastAPI app (Python 3.12). Entry `main.py`.
  - `routers/`: auth_routes, bots (builder, knowledge, install, WordPress plugin), chat (public widget
    API), handoffs (live chat, agent side), workspace, team, analytics, integrations, email_center, sites.
  - `voice/`: phone assistant (see Voice). `whatsapp/`: WhatsApp (see WhatsApp). `sites/`: static site hosting.
    `notify/`: email + events.
    `plugins/wordpress/`: WordPress plugin source. `ops/`: runbooks (SITES_SETUP.md, backups).
  - Core modules: `models.py` (SQLAlchemy models), `database.py` (engine, pool), `auth.py` (JWT, workspaces,
    roles owner/admin/agent, rate limits), `plans.py` (free/paid limits), `secretbox.py` (encrypted
    columns), `ai.py` (Gemini REST, model order), `utils.py` (chat answers), `vector_store.py` (Pinecone),
    `knowledge_sources.py`, `brain.py` (summaries, learned details), `assist.py` (business hours, lead score,
    unanswered questions), `realtime.py` (Socket.IO), `payments.py` / `subscriptions.py` (Razorpay), `phone.py`.
  - Many old one-off scripts at `backend/*.py` (check_*, fix_*, test_bot_*): not part of the app.
  - `tests/`: pytest suite (~242 tests, ~115 s).
  - `static/nimmi-widget.js`: the embed script customers paste; it opens an iframe of the dashboard's `/widget/[botId]`.
- `dashboard/` Next.js 15 (React 19, Tailwind), App Router in `src/app`: `/dashboard/*` (builder, voice, whatsapp,
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
- Regions: Railway and Supabase both in Singapore since 28 Oct 2026 (before: US West and Sydney, ~0.2-0.75 s per
  DB round trip; the widget config now answers in ~0.13-0.15 s). Users in India. Deploys happen on push to `main`.
- DNS at GoDaddy: `api` CNAME to Railway; Google Workspace mail on nimmiai.in (MX smtp.google.com, one SPF record).
- Transactional email via Resend (`notify/email.py`), SMTP fallback.

## Product rules

- Plans (`plans.py`): free = 1 assistant + 1 website, no custom domain, voice calls paid with credits (10 free);
  integrations and custom domains need paid. A workspace is paid while any of its assistants has an active
  subscription (or one the owner paid for). `ENFORCE_PLAN_LIMITS` is off in tests.
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
- AI model per agent (`voice/ai_models.py`, Voice > Agents toolbar dropdown, per direction like the other
  `PER_DIRECTION` settings): 37 models like Retell's list (Groq GPT-OSS/Qwen, Sarvam 105B, OpenAI GPT-4.1..GPT-6.x,
  Claude Haiku/Sonnet/Opus, Gemini 3.x/4), grouped "fast" / "smart"; a model shows only when its service key is set
  (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). Default `VOICE_DEFAULT_MODEL` = GPT-OSS 120B (Qwen 3.8 27B is a Groq
  preview, 5x the price). The chosen model answers first, asked not to think (`extra`: reasoning_effort none/minimal,
  Claude thinking disabled/between_tools, Gemini thinkingLevel minimal); when it's busy, slow to start (3 s fast,
  6 s smart) or fails, the Groq rotation below answers, and `answered` records who did. Speeds:
  `dev-scripts/voice/model_latency.py`, `gemini_thinking_probe.py` (Oct 2026: Sarvam 0.28 s, Qwen 0.39 s, GPT-OSS 0.7 s,
  Gemini 3.x Flash 1.1-1.5 s with thinking "minimal"; Gemini 3.5 Flash-Lite rejects thinkingBudget 0; Gemini 2.5
  Flash-Lite is closed to new users). Sarvam 105B kept answering in Hindi after a caller moved to English and Tamil.
- Functions (`voice/functions.py`, agent page > Functions, per direction like the other `PER_DIRECTION` settings): custom
  HTTP functions (netsafe client: public internet only; GET/DELETE add the arguments to the address's own query, the
  others send them as JSON; `{{caller_number}}`, `{{name}}`, campaign columns in the address and headers) and Cal.com
  check_slots / book (API v2; cal-api-version 2024-09-04 for slots, 2026-02-25 for bookings). Header values and Cal.com
  keys are sealed (secretbox), shown masked, and kept when the mask comes back. Models call them natively: Groq/OpenAI
  `tools`, Claude `tool_use`, Gemini `functionDeclarations` with the reply's parts (thought signatures) kept in `raw` and
  sent back unchanged; another model's calls carry Gemini's documented `skip_thought_signature_validator`. Up to
  `MAX_FUNCTION_ROUNDS` (3) a turn, then the model must answer. `FUNCTION_RULES` go in the prompt: on test calls (Oct
  2026) Gemini ran a function with the placeholder "order_id" before asking, and models filled gaps in a result with
  guesses. The call history keeps each request and result (before the spoken answer); the transcript gets "Function
  <name>: <result>" lines. Sarvam can't run functions: its turns that need one go to the backups. Test button:
  `POST /api/voice/agents/{bot}/functions/test`; real-model probe: `dev-scripts/voice/function_probe.py`.
- Replies (`llm.py`): Groq first (rotation `qwen/qwen3.8-27b` -> `openai/gpt-oss-20b` -> `openai/gpt-oss-120b`,
  SDK retries OFF so a rate limit fails over instantly), Gemini REST last. The free Groq tier
  (8k tokens/min/model) is the main cause of slow or stuck turns; the paid tier fixes it. Kdbot's prompt is
  ~9,100 characters per answer (measured Oct 2026). A model with no words after 3 s rests 15 s (`SlowModel`);
  Gemini on a call gets an 8 s limit, not the chat's 30 s.
  `reply_sentences` splits sentences (also "?word" without a space or a glued-on "[END_CALL]", never at "..."),
  ends the turn at a question, and drops filler sounds/empty reactions ("Hmm,", "ஓ, அப்படியா!") in
  `_clean_for_speech`. The prompt must never give filler examples: models copy them into every reply (seen on real
  calls, Oct 2026). A question never ends or transfers the call: the gpt-oss fallbacks glue `[END_CALL]` onto
  questions ("என்ன?[END_CALL]"), which hung up live calls mid-conversation (Oct 2026). The prompt says exactly when
  to write the markers; "write [END_CALL] on its own" was read as "after every reply".
- Call behaviour (`pipeline.py`): speaks first the moment the call connects (opening audio cached in memory and
  in `VOICE_OPENINGS_DIR`, made ahead while the phone rings / when the agent is saved); the opening can't be
  interrupted and a "hello" over it is ignored; barge-in only after the caller keeps talking `BARGE_IN_SEC` (1 s;
  a cough or "mm" ends sooner), or at once for words that need an answer; "ok"/"சரி" and the agent's own echo
  over its speech are ignored; follows the caller's language (script detection `spoken_language`, per-agent
  `follow_caller_language`): one clear sentence (`switch_now`: 3+ words in an Indian script; English 5+ and
  Sarvam's `language_probability` not below 0.6) or two in a row switch, pre-connecting the new language's voice
  (Sarvam gave clear Tanglish only 0.58, so the probability never blocks Indian-script sentences). A language not
  heard yet on the call needs 5+ words (`FIRST_SWITCH_WORDS`) or two in a row: unclear first words came out as
  Punjabi and Malayalam on live calls. Each agent can limit the languages it may switch to (`switch_languages`;
  empty = any);
  number check for 10-digit Indian numbers; end phrases and opt-out (DNC); silence reminders; "one moment" once
  if an answer takes 3 s, the fallback apology at 15 s; one sentence at a time on the voice connection
  (`self.voice` lock, `aclosing`); every speech step has a time limit (`TTS_FIRST_AUDIO_SEC`, gaps
  `TTS_CHUNK_GAP_SEC`, then REST) and idle voices are pinged (Sarvam closes them after a minute); a recognizer
  connection that drops is replaced and the call goes on (`_listen`; more than 3 drops a minute, or none reachable,
  end it with an apology); if the voice fails, the call ends within ~2 s. Both are logged "failed" (reason in the
  transcript) and aren't billed. A bug handling one sentence is logged and the call goes on.
- Sound around the caller (`voice/levels.py`): Sarvam takes any speech-like sound for speech, however faint. On real
  calls the caller's own lines were -12 to -23 dBFS at their loudest, the room's (transcribed as "नमस्कार", "this
  friend.", "ஆ") -35 to -52. A turn whose loud part (90th percentile of 20 ms levels) is 12+ dB below the caller's
  usual level is the room: its transcript is ignored, and it can't stop the agent (that needs 0.3 s of their voice in
  the last 1.6 s). Talk in the room keeps Sarvam from ever ending a turn (no transcript at all under a TV), so the
  pump `flush`es it (`flush_signal=true`): 0.9 s after the caller's voice stops, and where they start after only the
  room (that part is ignored). Before their level is known, a voice is >= -24 dBFS. A lone filler ("so", "uh", "ஆ")
  isn't answered. Sarvam's VAD frame is 64 ms at 8 kHz; it ends a short sound ~0.6 s after it stops.
- Python's `\w` doesn't match Indic vowel signs: split words with `llm.plain_words`, not `[^\w]` regexes.
- Incoming and outgoing agents (`voice/scripts.py`): the `voice_agents` columns are the outgoing agent; `inbound` (JSON)
  holds the incoming agent's own phone settings (`PER_DIRECTION`) once it's edited, and until then it mirrors the
  outgoing one. Name, business name and pronunciations are shared. The agents API takes `?direction=`; none means
  outgoing (the old behaviour). What each says is a `VoiceScript` per assistant and direction (Voice > Knowledge):
  opening, opening for known callers (`{{name}}` = first name), personality preset, instructions, goal, fields.
  Unsaved, it falls back to the agent's old greeting, goal and fields. "Write with AI" is
  `POST /api/voice/scripts/{bot}/{direction}/draft` (questions are in the dashboard's `WriteWithAI.tsx`).
- Caller memory (`voice/memory.py`): a `Contact` per assistant and number (never shared between assistants, as
  one account can run several businesses). It's updated after every phone call (`remember_call`, fired from
  `_finish`); a shorter name never replaces a fuller one. At call start `context_for` gives the name, details,
  team notes and the last 5 call summaries, including calls from before contacts existed. A known caller gets the
  known-caller opening; on Twilio it's made while the phone rings (`_prepare_known_opening`). Email and number are
  never put in the prompt. "Forget" sets `remember_from`; Compliance > Erase deletes the contact. The assistant's
  "Remember callers" switch (`remember_callers`, None = on) stops both reading and saving; contacts already saved stay.
- Credits (`metering.py`, `ai_models.py`): a call minute = `VOICE_BASE_CREDITS` (1: voice, speech recognition,
  phone line) + the model's credits = its list cost on a busy minute (16,800 tokens in, 336 out) x 1.5 at the cheapest
  credit price, capped at 95% of Retell's price for the same model unless that leaves under 15% (GPT-OSS 120B 1.08,
  GPT-5.4 mini 1.40, Claude Sonnet 5.5 2.05). Billed in 30-second steps, rounded up to 0.01, at the base plus the average
  of the models that answered; a call needs one step's credits to start and ends with the time-limit goodbye when they
  run out. New workspaces get `VOICE_FREE_CREDITS` (10); packs 100/500/1000 for Rs 549/2,499/4,499 (`VOICE_PACKS_JSON`);
  plan credits per plan name in `VOICE_PLAN_CREDITS_JSON`; `VOICE_MODEL_CREDITS_JSON` overrides a model's rate.
  `voice_wallets` keeps the old minute columns; a wallet's minutes move to credits 1:1 the first time it's read.
  Public rate card: `GET /api/voice/rates` (the website's pricing); the agent header: `/api/voice/agents/{bot}/details`.
- Outbound: `scheduler.py` dials call-backs and campaigns; answering-machine detection only when the agent's
  voicemail action isn't "off" (it adds 2-4 s before the call connects).
- Logs to read: "opening started X s after the call connected", "reply timing: ...", "Voice reply from <model>",
  "the caller kept talking over the agent", "that sounded like <lang>", "the answer is slow; saying one moment",
  "Streaming TTS failed (...); using REST", "ignored a sound from around the caller", "finishing their turn now",
  "sound over the agent, far quieter than the caller's voice"; the call's "diagnostics" line counts both.
- Tests for these real-call problems: `tests/test_voice_reliability.py`; agents, scripts and memory: `tests/test_voice_inbound.py`.
- Simulated calls without a phone: `dev-scripts/voice/lang_call.py`, `noisy_call.py` (a TV in the caller's room);
  `replay_caller.py` replays a real recording's caller side through Sarvam; `memory_calls.py`: one number calls twice
  (the second call is greeted by name). Git-ignored local harnesses; see `dev-scripts/README.md`.

## Schedule (Voice > Schedule: call-backs, follow-ups, meetings)

- `voice/schedule.py` (settings per assistant in `schedule_settings`, all off by default; calling hours; the call's
  functions; planning after each call), `voice/meetings.py` (free times, booking, the team's decisions, reminders),
  `voice/schedule_api.py` (`/api/voice/schedule/*`). Dashboard: `/dashboard/voice/schedule` (Coming up, Meetings, Calls,
  Settings), lead rating in Contacts, a Schedule card on the agent page, a count on the Voice menu.
- Everything dialled is a `CallbackJob` with a `kind`: callback, follow_up, meeting (confirm / proposed time / declined,
  in `variables.about`), no_show; `person` is a to-do for the team (status `todo`, never dialled); follow-ups waiting for
  the team's OK are status `review`. `dial_check` runs before each dial (do-not-call first, the kind's hours and days, still
  makes sense), calls go out from the number they called (`CallLog.number_id`), 2 lines per assistant
  (`VOICE_SCHEDULE_LINES`), call-backs first. Call-backs and meeting calls already promised are made even if their switch
  is turned off later; turning follow-ups off cancels the waiting ones.
- During a call (`CallTools`, passed to `llm.reply_sentences` as `schedule_tools`): `schedule_callback` (one text field
  `when`, "in 10 minutes" / "YYYY-MM-DD HH:MM": a number field got whole turns rejected by Groq's argument check),
  `cancel_callback`, `check_meeting_times`, `book_meeting` (moves their upcoming one; agreeing to a time the team proposed
  confirms it), `cancel_meeting`. Names reserved in `functions.RESERVED`. A browser test books nothing.
- After every phone call (`schedule.after_call`, after `memory.remember_call`): the analysis (`llm.summarize`) gives
  `lead` (hot/warm/cold/new/not_interested), what the next call should do, a day they named, an agreed call-back or meeting
  time; saved on `CallLog.lead` / `next_step`. The contact is rated (never over a customer the team marked); a call-back or
  meeting the agent agreed to but didn't book is made now (Oct 2026: GPT-OSS 120B said "you're booked" without booking);
  "a person should call me" becomes a to-do; then one follow-up is planned by the rules (count, every N days, at about the
  hour they last picked up), replacing the last plan. None while a call-back, to-do or meeting waits, after a transfer,
  past `max_total`, with Remember callers off, or more than `stop_after_days` (7) after their last conversation (TRAI 2025:
  consent for an enquiry lasts 7 days). A test call's follow-up waits in `review`.
- Meetings: requested -> the team approves (link or default link, host) -> confirmation call + written confirmation
  (WhatsApp inside the 24-hour window, else the approved template `Hi {{1}}, about your meeting with {{2}}: {{3}}. {{4}}`;
  email with an .ics invite) -> day-before reminder and the joining details `link_minutes` before (`meetings.process_due`,
  each tick; each message once via NotificationLog, keyed by meeting and start time). The team can propose another time
  (the agent calls to agree it), decline (with a call to find another time, or in writing), move, mark attended / missed
  (missed: a call to rebook). Unanswered requests expire at their time; unmarked meetings close as attended after 3 days.
- Real-model checks (Oct 2026): call-backs booked right on GPT-OSS 120B and Gemini 3.6 Flash (Tamil too); meetings
  reliable on Gemini 3.6 Flash, about 1 in 3 on GPT-OSS 120B (the after-call recovery covers the rest).
- Tests: `tests/test_voice_schedule.py`. Real models: `dev-scripts/voice/schedule_probe.py` (books under a test number and
  removes it); sample data for the dashboard: `schedule_seed.py` (`--clean`); UI: `dev-scripts/ui-checks/schedule_ui.mjs`.

## WhatsApp

- Meta's WhatsApp Cloud API (Graph v26.0, `whatsapp/graph.py`); each workspace connects numbers in the dashboard's
  WhatsApp > Settings (`WhatsAppNumber`; the old Integrations fields are moved over at startup). Plan agreed Oct 2026:
  Nimmi becomes a Meta Tech Provider (one-click Embedded Signup v4, coexistence with the WhatsApp Business app);
  until then numbers are connected manually from the business's own Meta app (token + app secret).
- Webhook (`whatsapp/webhook.py`, same URL as before: `/api/integrations/whatsapp/webhook`): each number's part is
  trusted only if signed with that number's app secret (manual) or Nimmi's `WHATSAPP_APP_SECRET`; what Meta sends is
  kept before answering 200 (`inbound.py`), each Meta message id once (unique `wamid`), so Meta's retries are safe.
- Customers are keyed by Meta's user id (BSUID, in webhooks since Apr 2026; usernames hide the number) with the phone
  number when shared (`chats.py`); the text lives in the usual Conversation/Message (session `wa:<number or id>`), so
  Live chat, leads, questions and analytics work as for website chat.
- Replies (`replies.py`): due `wait_seconds` after the last message (a burst gets one answer), claimed in the database
  so one of the 4 processes answers (timer in the receiving process; the scheduler's sweep catches lost timers; claims
  allow 250 ms for a timer waking early). Read + "typing…", voice notes written out (Sarvam, Gemini fallback), photos
  and PDFs read (`understand.py`, `ai.look`), then 1-3 short messages with pauses, files from WhatsApp > Files
  (`[FILE n]`), buttons (`[BUTTONS: a | b]`), `[QUOTE n]`, `[HANDOFF]`. Rules learned on real runs: the reply follows
  the script of the customer's latest message (Tanglish stays in English letters); a sent file shows in the AI's
  history as `[FILE n]` (it copied '(sent the file "...")' as text); "Hi Priya," never goes out on its own; no handover
  just because the business doesn't offer something. A message arriving while it writes: it answers everything once.
- The team (Inbox, or the phone app via coexistence echoes) pauses the assistant on that chat (`pause_hours`);
  "Hand back" resumes. Team messages need the 24-hour window. Memory is shared with calls (`whatsapp/memory.py`:
  contact per assistant + number; quiet chats get a summary the voice agent hears).
- Meta facts (Oct 2026): replies inside 24 h are free for the first 1,000 per number per month, then about Rs 0.115
  each (India); marketing templates about Rs 0.86; general-purpose AI bots banned since Jan 2026 (business AI allowed).
- Tests: `tests/test_whatsapp.py` (FakeMeta). Local run without a number: `dev-scripts/whatsapp/fake_meta.py` +
  `sim_chat.py` (backend started with `WHATSAPP_GRAPH_URL=http://127.0.0.1:8790`); UI: `dev-scripts/ui-checks/whatsapp_ui.mjs`.

## Public site and SEO

- Pages: home `src/app/page.tsx` (sections in `components/site/`); product pages `/ai-voice-agent`, `/whatsapp-chatbot`,
  `/ai-chatbot-for-website`, `/lead-management`, `/pricing`, built from `components/site/PageParts.tsx` (SitePage,
  PageHero, PageFaq, RelatedPages); `/solutions/[industry]` (older design); blog posts in `src/lib/site/blog.ts`
  (`seoTitle` is the search title, `title` the H1).
- Each public page sets its own metadata with `pageMetadata()` (`src/lib/site/seo.ts`: title, a 140-160 character
  description, its own canonical, a 1200x630 share image from `public/og/`) and JSON-LD (`components/site/JsonLd.tsx`).
  No canonical in the root layout: inherited, it told Google every page was a copy of the home page (Oct 2026: on live,
  every page had one title and that canonical). The home page needs `title.absolute` (the root template skips it).
- Hidden from search: auth, dashboard and widget (noindex layouts + X-Robots-Tag in `next.config.ts`), and demo.
  robots.txt is the static `public/robots.txt` (an `app/robots.ts` would clash). New pages and posts go in
  `app/sitemap.ts` with real dates. `public/llms.txt` describes the product for AI assistants.
- Copy claims only what the product does (no HIPAA, no invented figures). One page per search topic, no keyword stuffing:
  the keyword map (`dev-scripts/seo/keywords.py`) gives each keyword its page; `dev-scripts/seo/crawl.py` checks every
  page's title, description, canonical, H1, JSON-LD and share image (dashboard on :3000).

## Testing conventions

- Fakes in `tests/test_pipeline.py` (FakeTransport, FakeStt, fake_tts, replier_saying); `run` fixture runs
  coroutines on the app loop; `make_user` makes a signed-up user with `.bot()`.
- For timing-sensitive tests, make ordering deterministic (Windows timers are coarse: ~16 ms).
- New behaviour gets a test that fails without the fix (check by reverting the fix once).
