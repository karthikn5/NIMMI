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
- "leads" = the Leads section (Needs attention, All leads, Board, Sources, Reports; instagram_plan.md).
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
    `notify/`: email + events. `leads/`: the Leads section (see Leads).
    `plugins/wordpress/`: WordPress plugin source. `ops/`: runbooks (SITES_SETUP.md, backups).
  - Core modules: `models.py` (SQLAlchemy models), `database.py` (engine, pool), `auth.py` (JWT, workspaces,
    roles owner/admin/agent, rate limits), `plans.py` (free/paid limits), `secretbox.py` (encrypted
    columns), `svgsafe.py` (uploaded SVG logos rebuilt from safe parts), `ai.py` (Gemini REST, model order), `utils.py` (chat answers), `vector_store.py` (Pinecone),
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
- The dashboard and the backend deploy separately, so for a minute either can be newer: a page must survive a field the server doesn't send yet (a row waits for its setting;
  1 Nov 2026: a new dashboard on an older backend crashed Email > Automations), and `app/dashboard/error.tsx` catches what's left.
- DNS at GoDaddy: `api` CNAME to Railway; Google Workspace mail on nimmiai.in (MX smtp.google.com, one SPF record).
- Transactional email via Resend (`notify/email.py`), SMTP fallback.

## Product rules

- Plans (`plans.py`): free = 1 assistant + 1 website, no custom domain, voice calls paid with credits (10 free). A
  workspace is paid while any of its assistants has an active subscription (or one the owner paid for). What each plan
  includes (`Includes`, BILLING_PLAN.md phase 2): Starter = website chat, team alerts and a plain welcome email
  (`team_alerts`, `welcome_email`), 2,000 AI replies a month, 1 seat; Growth + WhatsApp, live chat, every other email to
  customers (`email_alerts`: the AI's note and files, after-call emails, follow-ups, bulk, their own domain), 10,000 replies, 3 seats; Pro + 300 call credits a month, Schedule,
  campaigns, webhooks/LeadSquared/Sheets, business hours, transfers and "Pick up the call", 25,000 replies, 5 seats;
  earlier 1/6/12 Month plans everything with no reply limit. Per assistant (`includes`); seats, integrations and business
  hours by the workspace's best plan (`workspace_includes`). Checked where things run (WhatsApp answering, the widget's
  Person switch and call-back offer, the dialler, call setup, alerts and webhooks, `assist.workspace`) and on save
  (402 "X comes with the Y plan"; `PlanNeeded` in the dashboard). AI replies (chat, the flow's AI step, WhatsApp) count
  per assistant per calendar month in `ai_reply_usage`; the business's own tries don't. `ENFORCE_PLAN_LIMITS` is off
  in tests (then everything is included); `tests/test_plan_features.py` turns it on.
- Billing (BILLING_PLAN.md, `subscriptions.py`, `payments.py`): Starter ₹999, Growth ₹2,499, Pro ₹6,999 a month per
  assistant, yearly at 10 months' price (the website's `dashboard/src/lib/plans.ts`; a test keeps the two equal). Monthly
  = a Razorpay subscription that renews itself (first month charged at checkout; `subscription.*` webhooks extend the plan
  or report a failed charge); yearly = one order a year, with reminders (RBI: automatic debits over ₹15,000 need an OTP).
  An upgrade starts now, paying the difference for the days left; other changes start at the period's end (a plan row
  with a future `start_date`; `plans_of` gives the plan now and the next). Each payment applies once (a NotificationLog
  claim saved with it). The 1/6/12 Month plans (sold until 30 Oct 2026; the 1-month one cost ₹1 on live 12-30 Oct) keep
  everything until they end. `payments.maintenance` (scheduler, every 10 min): a renewing plan at its end asks Razorpay
  where its subscription is (so a customer charged while the webhook was missing keeps the assistant), reminders 7, 3 and
  1 day before a plan that doesn't renew ends, the ended email, Razorpay subscriptions still to cancel. If Razorpay
  won't make a subscription (feature off, or any refusal), that month is a single payment. Each payment has a receipt
  (`/api/payments/receipt/{id}`, `/dashboard/billing/receipt/[id]`): not a tax invoice until the business has a GSTIN.
  Tests: `tests/test_billing.py`, `tests/test_plan_features.py`; browser: `dev-scripts/ui-checks/billing_ui.mjs` with
  `billing_seed.py`, `plan_features_ui.mjs` with `plan_features_seed.py`.
- Workspaces: owner plus team members (admin/agent); requests act on `ctx.owner_id`; the `X-Workspace` header picks one.
- Encrypted secrets (customer AI keys, phone account tokens): `secretbox` MultiFernet over ENCRYPTION_KEY
  (+ JWT_SECRET, + `ENCRYPTION_OLD_KEYS` decrypt-only); columns store `enc:v1:...`. To replace the key: new ENCRYPTION_KEY
  (and JWT_SECRET), the old values in ENCRYPTION_OLD_KEYS; each start then moves every stored secret to the new key
  (`database._reseal_secrets`, also `SEALED_TEXT` and `SEALED_JSON`: add new sealed places there) and logs how many, and
  how many no key opens. Remove the old keys only once that log says 0 moved and 0 unreadable.

## Chat widget and live chat

- Widget page `dashboard/src/app/widget/[botId]/page.tsx`: visual flow runner, AI chat, voice input,
  "Prefer a call?" call-back request, "Talk to a person" handoff, "Powered by Nimmi" (links to nimmiai.in).
  Sessions: `widget-session-ai-<visitorId>` and `widget-session-human-<visitorId>` (random id in localStorage
  is the visitor's proof).
- Launcher (`static/nimmi-widget.js`, mirrored by the builder's `WidgetPreview.tsx`): a button (circle, rounded,
  square, pill) or `launcher_shape: "character"`: the avatar itself, a standing figure, at `character_height`
  (80-220 px, phones up to 120) with the greeting and chat window above it; without a picture it's the round button.
  Round avatars use `object-top`, so a standing figure shows its face. `character_animation: "violet"` puts Violet,
  Nimmi's animated character, there instead (`static/characters/violet/`: `violet.js` is the owner's design's
  avatar.js adapted for a corner figure, `wave-rig.js` its WebGL arm, `character.webp`), loaded with `import()` only by
  assistants that use her: blinks, looks at a nearby cursor, breathes, waves; still with reduced motion.
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
  `_clean_for_speech`, with an aside in brackets or stars that opens a sentence ("(Waiting for user response)", read out
  on a live call, Oct 2026). The prompt must never give filler examples: models copy them into every reply (seen on real
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
  team notes and the last 5 call summaries ("today at 4:10 pm", "yesterday at 6 pm", else the date: with only "30 Oct"
  the agent said "yesterday" about an hour-old call; summaries name dates, never "tomorrow"), including calls from
  before contacts existed. A known caller gets the
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
- Live calls and "Pick up the call" (LIVE_CALLS_PLAN.md, 30 Oct 2026): a call writes `CallLog.live_at` and its transcript
  every 3 s (`_live`; `handoff.sweep` closes calls silent 90 s as failed). The AI's tool `ask_for_person` (it decides,
  no word lists) rings the team when someone is available (`TeamPresence`: dashboard open in the last 45 s, "Available
  for calls" on): a `CallHandoff` row, the dashboard's `CallDesk` card on every page; the first to accept (atomic) gets
  it in the browser (Twilio: `<Dial><Client>`, Voice SDK token from an API key Nimmi makes on the call's account,
  `TwilioKey`, sealed) or on their phone (Twilio, Exotel). The call's watcher hears the accept within 1 s, says
  CONNECTING, closes the stream; `/twilio/after` and Exotel's steps read the row (any process). Nobody in
  `team_handoff_wait` (45 s): the transfer number, else BUSY + a Schedule to-do, and the call goes on. The agent's
  transfer number uses the same rows (the old in-memory `pending_transfers` lost 3 transfers in 4 on live's four
  processes). `team_handoff` off = the old `[TRANSFER]` marker. The ring (`CallDesk.tsx`): India's double ring made with
  Web Audio on the audio clock (a background tab slows timers, not audio); browsers play it only after a click on the
  page (the first one anywhere wakes it; until then the card says so); one tab per computer rings (Web Locks); Ring sound
  and Test ring are on Calls, with "Available for calls". Tests: `tests/test_live_calls.py`; browser:
  `dev-scripts/ui-checks/live_calls_ui.mjs`, `live_ring_ui.mjs` (measures the sound inside the page).
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
- Calls not made yet (`schedule.open_calls`; live, 30 Oct 2026: a meeting's confirmation call found the line busy, the
  person rang straight back asking why they'd been called, the agent didn't know and booked a call-back on "I called
  back", and the retry rang later to say what they'd heard meanwhile): every call is told the calls tried for this person
  in the last 3 days that didn't reach them (what each was for, when, the next try) and the ones they expect (a
  call-back, a meeting call); not untried follow-ups or campaign calls, test calls, or the call being made. It works with
  every Schedule switch off (missed campaign calls). The analysis gets them too and says which the conversation took
  care of (`handled`): those are done ("Taken care of on their call on ...", linked to that call) and never dialled.
  While they may be returning a missed call, the first call-back the model asks for goes back to it (explain the call
  first): GPT-OSS 20B booked one on "I called back" even when told.
- Meetings: requested -> the team approves (link or default link, host) -> confirmation call + written confirmation
  (WhatsApp inside the 24-hour window, else the approved template `Hi {{1}}, about your meeting with {{2}}: {{3}}. {{4}}`;
  email with an .ics invite) -> day-before reminder and the joining details `link_minutes` before (`meetings.process_due`,
  each tick; each message once via NotificationLog, keyed by meeting and start time). The team can propose another time
  (the agent calls to agree it), decline (with a call to find another time, or in writing), move, mark attended / missed
  (missed: a call to rebook). Unanswered requests expire at their time; unmarked meetings close as attended after 3 days.
- Real-model checks (Oct 2026): call-backs booked right on GPT-OSS 120B and Gemini 3.6 Flash (Tamil too); meetings
  reliable on Gemini 3.6 Flash, about 1 in 3 on GPT-OSS 120B (the after-call recovery covers the rest).
- Tests: `tests/test_voice_schedule.py`. Real models: `dev-scripts/voice/schedule_probe.py` (books under a test number and
  removes it), `missed_call_probe.py` (someone returning a missed call); sample data for the dashboard: `schedule_seed.py` (`--clean`); UI: `dev-scripts/ui-checks/schedule_ui.mjs`.

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

## Instagram (instagram_plan.md phases 5 and 6)

- `backend/instagram/`, built like `whatsapp/`: Business Login for Instagram (`accounts.py`: scopes `instagram_business_basic`,
  `instagram_business_manage_messages`, and `instagram_business_manage_comments`, optional: DMs work without it; Instagram returns to `/dashboard/instagram/settings`, finished with the signed-in person's token and a state naming
  workspace and person; one account per workspace, a disconnected one's old chats stay with the old workspace; the long-lived token (60 days) renewed weekly
  by `tick`, claimed; ran out or refused: status `token`/`permission` with its repair). `graph.py`: graph.instagram.com v26.0, Bearer header, Meta's error
  codes as sentences (190 token, 10/2534022 window, 200/2534041 access turned off, 551 unavailable, 4/613 busy); `INSTAGRAM_GRAPH_URL`, `INSTAGRAM_API_URL`,
  `INSTAGRAM_DIALOG_URL` point at `dev-scripts/instagram/fake_instagram.py`. Needs `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_VERIFY_TOKEN`.
- Webhook `/api/instagram/webhook` (object "instagram", entries by account id, events in `messaging`; a list or one object): signed with
  `INSTAGRAM_APP_SECRET` or `META_APP_SECRET` (Meta's pages don't say which); kept before the 200, each `mid` once (`InstagramMessage.mid` unique); entries
  for an account nobody has connected are ignored. `/api/instagram/deauthorize` and `/deletion` (signed_request) forget the sign-in.
- Windows (`chats.py`): anything within 24 hours of their last message, 7 days after a first message from a Click-to-Direct ad (`ad_window_until`);
  after that only a person's reply with the HUMAN_AGENT tag, up to 7 days (`reply_route`: open, human_agent, closed). The assistant answers only inside
  the first window; `outbound.send_text` refuses the tag for anything but a team member's reply (`TagRefused`). Each send is kept as "sending" before
  Meta is asked, so its echo (which can beat Meta's answer) is recognised; any other echo was written in the Instagram app: kept as `sent_by` "app", the
  assistant paused (`pause_hours`), never answered.
- Replies (`replies.py`): WhatsApp's steps and helpers (claim, sweep, flow, hand-over, `parse`, `script_of`); typing and seen as sender actions;
  "one moment" (`HOLDING`) if nothing is written `HOLD_AT` (20) seconds after their message, as Meta expects an answer within 30; quick replies from
  `[BUTTONS: a | b]`; every message within 1,000 UTF-8 bytes (`pieces`); photos, voice messages and PDFs understood from Meta's CDN address
  (`understand.py`, WhatsApp's `_hear`); plain text only (the prompt's "instagram" channel, `brain.PLACES`).
- Leads (`contacts.py`): a new chat reads their profile (only allowed once they've written) and makes a `Contact` with `instagram_id`/`instagram_username`,
  no phone or email, and `came_in` "Instagram" (answered, no first task, while the assistant is on). A number or email they type
  (`events.lead_captured`, "ig:" sessions) goes on their contact, or joins it to the contact that has it (`leads.core.merge`: everything moves, nothing by
  name or photo). Erase by number or email removes their Instagram chats too. Origins `instagram_ad`, `instagram_link` (`leads/origin.from_instagram`).
- Live chat replies to "ig:" sessions go through `realtime.relay_to_instagram` (`api.team_reply`: the same windows and tag). Plans: `Includes.instagram`
  (Growth up, as WhatsApp).
- Comments (phase 6, `comments.py`, Instagram > Comments): `InstagramRule` per account (posts or all, words in any script matched inside the text after NFKC
  and casefold, one private reply with `{{username}}`, up to 5 public replies, off until turned on). The webhook's comments (Business Login puts `field`/`value`
  on the entry, Meta's other logins `changes`; `comments._value` takes both) are kept once (`InstagramComment.comment_id` unique) before the 200, then
  claimed by one process (`process`, `tick` for retries). Never answered: the account's own comments and Nimmi's public replies coming back; skipped with a
  reason: no rule, over 7 days old (Instagram's limit for a private reply), no Growth plan. A sign-in that ended waits for "Connect again". The private reply is
  addressed to the comment (`graph.private_reply`), one per comment; 750 an hour per account (`HOURLY`, `_slot`: one UPDATE under a row lock on the account,
  which only Postgres needs: `test_two_processes_never_pass_the_hour_together`). The comment (quoted, as data) and the private reply start their chat, a lead,
  origin `instagram_comment` with the rule's name (`rule`, "Comment rule" on the lead) or `instagram_ad`; their comment doesn't open the 24 hours, their answer does. An echo of a private reply that beats Meta's answer
  is recognised (`recent_own_send`). Each rule's report (`report`): comments, private and public replies, conversations (they wrote after it), leads, sales.
- Also phase 6: ice breakers (4) and the menu (5, https links or sent as their message) through `/me/messenger_profile` (Assistant tab, `set_profile`);
  ig.me links with a `ref` (Settings; `origin.instagram_link`; a new chat's ref comes only with an ice breaker tap, an existing chat's restarts the 24 hours);
  story replies (`reply_to.story`, kind `story_reply`) and mentions (`story_mention`) answered like DMs.
- Dashboard: `/dashboard/instagram` (Overview, Inbox, Comments, Assistant, Settings), `lib/instagram.ts`; Instagram in the top bar after WhatsApp; Live chat lists
  "ig:" sessions (it once dropped them: `isLiveSession`).
- Tests: `tests/test_instagram.py`, `tests/test_instagram_comments.py` (a fake Instagram through `graph.client` MockTransport); browser:
  `dev-scripts/ui-checks/instagram_ui.mjs`, `instagram_comments_ui.mjs` (trial with the INSTAGRAM_* variables at `fake_instagram.py` on :8796, started fresh,
  `DASHBOARD_URL=http://localhost:3000`). Never tried against real Instagram yet.

## Email (mail_plan.md)

- Phases 0-9 in `mail_plan.md` (written 1 Nov 2026 from the owner's idea, with market research). Phase 0 live 1 Nov
  2026: sending foundations and the dashboard's Email section (Overview, Inbox, Automations, Journeys, Lead board, Drafts, Lead sources, Bulk email, History,
  Settings, Reports; Integrations > Email points there). Phases 1 to 6 in progress: the status is in mail_plan.md section 11.
- Sending: `notify/email.py` `deliver()` (Resend, else SMTP) returns Resend's email id; `send_email()` wraps it. Every
  customer email carries tags (`ws`, `job`, `kind`: customer / alert) and an idempotency key (`email-<job>-<attempt>`, so
  "Send again" really sends). Nimmi's own emails come from `EMAIL_FROM`; customer emails from `CUSTOMER_EMAIL_FROM`
  (meant: a subdomain such as mail.nimmiai.in) or the business's verified domain. `RESEND_API_URL` points local runs
  and tests at a fake.
- `backend/mail/`: `senders.py` (who an assistant's emails come from: its `EmailSender`, then the workspace's
  IntegrationSettings sender_name / reply_to / sender_local / sender_domain_id, then the bot name; `{{business}}` is
  that name), `domains.py` (a business's own domain through Resend's Domains API: DNS records shown without Resend's
  tracking record, tracking off, a sending-only key per domain sealed with secretbox, checks every 10 min for 4 days,
  bulk email warms up 100/200/400... a day for a week), `webhooks.py` (Resend's signed events at
  `/api/email/webhooks/resend`, Svix scheme, `RESEND_WEBHOOK_SECRET`, kept once by svix-id in `email_events`, purged after
  90 days), `suppress.py` (`email_unsubscribes` with reason unsubscribed / complaint / bounce / team and scope all /
  marketing; `email_bounces` for every workspace: a hard bounce or Resend's suppression; a meeting confirmation still goes
  to someone who unsubscribed), `address.py` (format, typo suggestion, throwaway list `disposable-email-domains`, MX
  lookup with `dnspython`, cached a day; tests never use real DNS: conftest `_no_dns`), `contacts.py` (a website chat
  lead becomes a `Contact` found by number, else email; `contacts.e164` is optional since Nov 2026: Postgres alters it,
  SQLite rebuilds the table at startup, `database._relax_not_null`), `api.py` (`/api/email/...`).
- Automatic emails (`notify/automations.py`): the text is filled in when sent (`subject_tpl`, `body_tpl`, `merge_data`,
  refreshed from the chat or call), the address is checked first (a domain without mail: the email shows "cancelled"
  with the reason and a likely fix), anyone stopped for any reason is skipped. The unsubscribe link only asks (scanners
  open links): its buttons post back (that page's own CSP allows `form-action 'self'`), "Only stop offers and news",
  Resubscribe; mail apps' one-click POST still works. Bulk email skips bounced and throwaway addresses and pauses
  above Gmail's 0.3% spam rate (200+ delivered in 30 days). The widget asks "Did you mean ...@gmail.com?".
- Nimmi agent: email tools in `agent/tools/email.py` (group "email", screens `email_*`).
- An assistant's emails (phase 1): `mail/setup.py` (`EmailSetup`: its own automations and settings over the workspace's;
  a design is what it saved in that language, else in English, else for welcome the workspace's old text, else ready-made),
  `designs.py` (`KINDS`, blocks, languages), `render.py` (blocks to mail-safe HTML and text; a block with nothing to show is left
  out), `links.py` (`EmailLink`: tracked links, downloads; the signed links below; `actions_for`: Book a time and Call me buttons, only
  when Schedule takes those).
- Pages from an email (`mail/public.py`, `/api/email/p/{meeting,book,call}?token=`, signed per meeting or person): a GET only shows,
  because scanners open links; buttons post. Only times on offer are accepted; bookings go through Schedule (`via` in their history).
- Meeting emails (`mail/meeting_mail.py`): the `meeting` design around the text `meetings._texts` writes, with the buttons that fit;
  the team marking one sends the thank-you or "sorry we missed you" (`meetings.after_meeting`, settings `meeting`).
- During a call (`mail/during_call.py`): `send_email` in `CallTools`, on with `settings.during_call`, sent at once, not queued. The agent
  knows an address exists and is never told it; one given on the call is spelt back first. 3 a call. A browser test sends nothing.
- Smaller emails (`mail/small.py`, queued): callback_booked (`book_callback`; `tell_them=False` from an email answer, which says so),
  voicemail, missed_chat (`Conversation.handoff_at`), chat_copy (`POST /api/chat/email-copy`, only to the address given in that chat;
  config `email_copy` shows the widget's button). Owner's daily summary: `notify/digest.py`, `alert_daily`, from 9 am India time.
- The AI's parts are never written in the email loop: `compose.prepare_due` runs by `fire_and_forget`, claims each email
  (`compose_state` pending, working, done, failed) and holds no database connection while a model answers. A sentence with a
  number the sources don't have goes (`keep_known_numbers`). AI-written emails count as AI replies and stop when they're used up.
- Welcome email (`compose.py`): sent when the chat has been quiet `QUIET` seconds (`EMAIL_QUIET_SECONDS`, default 120; each message
  pushes it, for at most 10 minutes), with the AI's note and the files that fit (`WhatsAppFile`). Starter: text and buttons only.
- After-call email (`mail/after_call.py`, queued after Schedule in `pipeline._remember_and_plan`): per direction off / review /
  auto (`settings.after_call`), Growth up. Replaces the fixed call_lead and goal_met emails while on. Only calls where they talked
  to the assistant (never voicemail, opt-out, a transfer, a test call, or someone on the do-not-call list). Address: what the call
  collected, else the contact (not with Remember callers off), else the campaign's list. One model writes it, another checks it
  against the call, the knowledge and what Schedule really has booked ("ok", "fix", "hold"). Code checks the language by its script (`designs.written_in`: a real
  Tamil call got Hindi and English, and the checking model passed it): wrong once, it's written again. It goes to Drafts, even on
  automatic, on "hold", when the language is still wrong, when the check didn't run, or when the caller was unhappy; when no model answers it waits there with a Write again
  button. Unanswered questions go to Questions and the email says the team will reply. Language: `CallLog.language` (designs exist
  in en, ta, hi; other languages get the English frame around the AI's words). Drafts (`status="draft"`, not in History, dropped
  after 14 days): `/api/email/drafts`, `/dashboard/email/drafts`; an approved one goes whatever the setting says by then. After 20
  approvals it offers automatic once. Real calls, Nov 2026 (`dev-scripts/email/compose_probe.py`, 8 calls): no invented numbers, 2-4 s
  for the two model calls when Gemini is quick; the same day it took 20 s for a one-word answer, hence the long time limits.
- Replies (phase 2, off until `REPLY_DOMAIN` is set; then customer emails carry `r-<code>@REPLY_DOMAIN` as Reply-To, `threads.py`). Any
  address at a domain with receiving on reaches the webhook (`email.received`, metadata only); `inbound.py` keeps the row before
  answering Resend (one per Resend id), fetches the text (`GET /emails/receiving/{id}`, needs a full-access key), and keeps only the new
  part, as text, never HTML. Their reply stops follow-ups and sends a copy to the business's mailbox, whose Reply-To is the same address:
  answering it goes on to the person as the business, if `authentication` (from Resend's mail server) passes for a team address.
  Someone testing with their own address is the person, not the team. `replies.py`: per assistant `settings.replies.mode`: ai, draft
  (default), team (no AI at all). It answers only the person in the conversation; a stranger's email waits for the team. "Stop" unsubscribes.
  Call-backs and meetings go through Schedule, at once on ai, when the draft is sent on draft. Answers pass the same checks as the
  after-call email. Machines are never answered; the AI stops at 3 answers a day, 10 in a conversation, and for a day after the team
  answers. Dashboard: `/dashboard/email/inbox`, `mail/inbox.py` (`/api/email/inbox`).
- Leads from other places (phase 3, `mail/intake.py`, `leads_api.py`, `/dashboard/email/leads`): per assistant, off by default, one code
  (`LeadSource`) for `leads-<code>@REPLY_DOMAIN`, `/api/leads/in/<code>/indiamart` and `/form`. Kept once per assistant (`LeadIntake`, a
  query id can repeat across sellers), then handled by one process. The AI reads forwarded emails; a value must be in the email. IndiaMART's
  push has no signature, retries anything but 200 and turns itself off after 48 hours of failures, and its documents don't say whether a
  listener gets the wrapper: `indiamart_lead` takes either. Each lead: a contact (merged by number, else email), the team told, the
  `lead_email` design at once, and on Pro a call in `lead_call.minutes` inside calling hours. Gmail's forwarding code shows on the page.
- Journeys and the lead board (phase 4, `mail/journeys.py`, `journeys_api.py`, `/dashboard/email/journeys`, `/dashboard/email/board`; Growth up): a `Journey` per assistant
  (trigger, goal, steps, off until turned on), a `JourneyRun` per person (slot "active": one at a time; not again for 30 days). `journeys.fire` comes from
  `events.lead_captured`, `intake.act`, `schedule.after_call` (never a test call), the team's rating, the board and meetings; `_dates` once a day for a date in their details.
  `tick` (scheduler, `fire_and_forget`) claims what's due; each step is saved before the next, and no connection is held while a model writes or a message goes out.
  Steps: email (`ai` fits it to the person, one AI reply), wait (a time, a weekday, until something happens), whatsapp (inside the window; else the same words by email; else a
  template), call (a Schedule `follow_up` with `variables.journey`: skips the lead-status check, keeps the 7-day rule, counted from when they came in if they never spoke; needs
  follow-ups on), branch, update, notify (or a to-do). Any reply ends every journey with that assistant; an unsubscribe (offers-only too), do-not-call or the plan ending stop
  it before the next step. One cap (`settings.journeys`, 1 a day, 3 a week) counts everything sent to the person, so a journey's email waits behind a welcome email; only
  journeys wait for it. Quiet hours 9 am to 8 pm, except the first answer to a new lead. A journey starts 30 s after its trigger, so the cap sees a welcome email being
  queued. Their links go through `EmailLink` when sent, so "clicked" works. `{{feedback_link}}` opens `/api/email/p/feedback`.
  Stages (`Contact.stage`) move forward by themselves (`move_stage`, called from `schedule.rate`, the one place a status changes, and on booking); the team can put anyone anywhere,
  and the board keeps customer and lost in step with the status. The older automations and Schedule's follow-ups aren't moved in: the page lists them. Real models
  (`dev-scripts/email/journey_probe.py`, 1 Nov 2026, 1-2 s each): "the next morning" came out as "wait until Monday" and every journey as a new lead until the prompt said
  otherwise; a ready-made email lost its date, so one that drops a placeholder keeps the ready-made words; "customer" as the goal of a customer journey ended it before step 1.
- Answers to who asked (`mail/answers.py`): `assist.record_gap` keeps who asked (`QuestionAsker`, `chat:`, `phone:`, `email:`; a chat's email can come later, so it's looked up when
  needed). On Questions the team ticks who gets the answer (kind `question_answer`, once each). Compliance > Erase removes the record.
- Bulk email (phase 5, `mail/broadcasts.py`, `broadcasts_api.py`, `consent.py`, `/dashboard/email/bulk`; Growth up): only people with a `Consent` record for that
  assistant (purpose marketing: the chat's unticked box, saved by the widget as the readable variable "Offers and news", with the words in `settings.consent`; a form's
  newsletter field; an import that says how they agreed; the team's note on the Lead board). An unsubscribe withdraws it (`suppress.add`), Resubscribe restores it, and
  only the person can give it back after they withdrew it. `EmailBroadcast` (draft, scheduled, testing, sending, paused, sent, cancelled; None = sent before Nov 2026)
  with `rules` for who (statuses, stages, sources, tags, active_days, engaged_days; `EmailSegment` saves them). The list is read when it starts (`tick`, claimed), addresses
  whose domain takes no mail are left out (one DNS lookup per domain, outside the DB connection), and each email gets its own `send_at` at the pace (30/60/120 a minute;
  the queue sends 50 a pass about every 20 s, and takes everything else first, so a big send never holds up a customer's own email). A subject test sends each subject to
  a tenth, then the better (a click 1, a reply 2) to the rest after 4 hours. Spam reports (2+, over 0.3%) or bounces (over 5% of 20+) pause it: its emails become
  "held". Invitations (`event`) link to `/api/email/p/rsvp` (GET only asks), answers in `EmailRsvp` and the contact's details, a reminder the day before to yes and maybe.
  Imports: CSV up to 5,000 rows, "how they agreed" required and kept per person. From Nimmi's address a workspace sends `BROADCAST_SHARED_DAILY` (200) a day; its own
  domain only warms up. `BULK_EMAIL_FROM` (a marketing subdomain, e.g. news.nimmiai.in, once verified in Resend) keeps offers off the address of confirmations.
- Clicks, score, reports (phase 6): links go through `/api/email/l/{token}`, which keeps an `EmailClick` (`mail/clicks.py`) and redirects; HEAD isn't a click. The
  scheduler settles clicks 30 s on (`settle_due`, claimed): a scanner's or an HTTP library's name in the user agent, or 3 of the email's links within 3 s, decide alone;
  otherwise points (20 s after sending 40, 3 links in 10 s 45, one network across 5+ people in 10 s 60, no UA 20, no Accept-Language 10; 60+ is a scanner). Only a
  person's click sets `EmailJob.clicked_at`, `EmailLink.clicks` (scanners: `scanner_clicks`), and so journeys, subject tests and reports never see scanners. The network
  is a keyed hash, never the address. A browser check's own Chrome says HeadlessChrome: set a normal user agent before opening a tracked link. `mail/engagement.py`:
  `Contact.engagement` (reply 40, book/call 30, prices 20, download 15, link 5; once per link; the week before half; two weeks gone; `decay` every 6 h), Hot now
  (30+ in 48 h, on the overview), the team's alert (`alert_engaged`, once a day per person and kind), the Pro fast call (`settings.fast_call`, a follow_up with
  `variables.from_email`, which Schedule's staleness rules treat like a journey's pick). `mail/outbox.py`: `IntegrationEvent` rows for the webhook (5 events) and
  LeadSquared (`leadsquared_activity`, ProspectActivity.svc/Create by EmailAddress, keys in headers), drained by the scheduler with retries (1, 5, 30, 120, 360 min,
  6 tries) and logged in Integrations > Activity. `mail/reports.py` (`/api/email/reports`): a reply or an unsubscribe goes to the last email that address got within a
  week; DMARC through `address.dmarc_of` (the organisation's record when a subdomain has none).
- The email agent (phase 7, `mail/agent.py`, `agent_api.py`, Growth up): per assistant `settings.agent` (level off / drafts / morning / auto, `per_day`), off until turned on. `tick`
  claims each run: the morning queue at 8, the others hourly 9 to 7 India time. `_why_not` decides in code who it leaves alone (customers, lost, not interested, stopped, on a journey, a reply
  waiting; quiet under 2 days; over 30 days without a marketing consent; 3 emails a month, 2 unanswered; a stop rests 90 days, a hand-over 7, a wait or failure 1). `decide`: one model, JSON
  (email, handover, wait, stop), asked twice if unreadable; then `keep_known_numbers`, `designs.written_in` with one rewrite, `replies._checked` with rules of its own. Code works out the
  day counts (models got them wrong). A held email is a draft on every level. A hand-over: `Contact.brief`, a `person` to-do, the team's email once a day. Drafts: `EmailJob` automation
  "agent", `/api/email/agent/...`, top of Email > Drafts, dropped after 7 days (a morning's at midnight). `ai.METER` records tokens per model call. Real models: `dev-scripts/email/agent_eval.py`
  (50 leads, tuned on them: 50/50 right steps, nothing invented, Rs 0.117 an email, 3.1 s).
- Someone's own Gmail or Outlook (phase 8, `mail/mailbox.py`, `connections_api.py`, Email > Settings; not shown until `GOOGLE_MAIL_CLIENT_ID` / `_SECRET` or `MICROSOFT_MAIL_...` are set): `MailConnection`, per person in a
  workspace, tokens sealed. Send-only on purpose (`gmail.send`, `Mail.Send`): a read scope would make the whole app restricted, with a yearly audit. The provider returns to the dashboard's page, which finishes
  with the signed-in person's token (`/finish`), so nobody can attach your mailbox to their workspace. `ONE_TO_ONE` kinds (agent, after_call, journey) go from the assistant's `settings.mailbox`; Inbox answers from the
  person's own, else the assistant's; never bulk or welcome. `send` returns None when it can't (reconnect, its 200 a day, the provider's limit): the caller sends the usual way, so an email never waits. Reply-To stays
  `threads.address`. No delivery or bounce events come back for these. `MAILBOX_API_URL` points at `dev-scripts/email/fake_mailbox.py`. Never tried on real Google or Microsoft yet.
- Calendars (phase 8, `voice/calendars.py`, Schedule > Settings `meetings.calendar`, `calendar_video`): busy times read every 5 minutes onto the connection (a live call never waits), off `free_times` and `_why_not`; `wanted`
  says what the calendar should show and `sync` makes it so (claimed, retried by `tick`), first thing in `send_confirmation` so a Meet or Teams link gets into `Meeting.link`. Its own events aren't busy (they count as seats). Nobody is
  invited on the provider's side. Outlook reads calendarView: getSchedule refuses personal accounts.
- How long email text is kept (phase 9, `mail/retention.py`, Email > Settings; `email_keep_months`, None = 12): `purge` in the 6-hourly block clears the words of sent emails, replies and portal leads and drops old agent notes; the record
  stays; waiting emails, drafts, consent, unsubscribes and bounces are never touched. Compliance > Erase calls `erase` and `erase_leads` (Nov 2026: it left the person's emails behind).
- Languages (phase 9): `designs.FRAMES` gives welcome and after_call in te, kn, ml, mr, bn, gu, pa, od beside en, ta, hi; `language_of` goes by script. A business's own saved English design or old text still comes before a ready-made frame.
  Numbers are compared whatever digits they're in (`compose._numbers`: ৪৫ is 45). Real models: `dev-scripts/email/language_probe.py`.
- HubSpot and Zoho CRM (phase 9, `notify/crm.py`, Integrations, Pro): leads and calls through `events`, email events through `mail/outbox.py` as notes. HubSpot: a private app's token (`hubspot_token`). Zoho: its permission page on `ZOHO_CLIENT_ID` /
  `_SECRET`, back to `/dashboard/integrations`, finished with the signed-in person's token; `accounts-server` and `api_domain` must be Zoho's own; the access token is kept its hour because Zoho limits refreshes. `CRM_API_URL` points at
  `dev-scripts/email/fake_crm.py`. Reports says how far each domain is from its logo in Gmail (`address.bimi_stage`). SES, dedicated IPs and Salesforce aren't built: mail_plan.md section 11 has the trigger for each.
- Before a push that changes tables or queries: `dev-scripts/postgres` (README there): the same tests on a local Postgres (`TEST_DATABASE_URL`), and the upgrade from what's live compared
  with a fresh schema. `init_db` prints errors and goes on, and SQLite accepts things Postgres doesn't.
- A reply address must take mail (`address.reply_address_works`): on live, `admin@nimmai.in` was saved, a domain that doesn't exist.
- Tests: `tests/test_mail_foundation.py`, `test_mail_designs.py`, `test_after_call_email.py`, `test_email_replies.py`,
  `test_call_emails.py`, `test_email_pages.py`, `test_small_emails.py`, `test_lead_intake.py`, `test_journeys.py`, `test_question_answers.py`, `test_broadcasts.py`,
  `test_clicks.py`, `test_engagement.py`, `test_outbox.py`, `test_reports.py`, `test_email_agent.py`, `test_mailbox.py`, `test_crm.py`, `test_retention.py`;
  browser: `dev-scripts/ui-checks/email_ui.mjs`, `email_design_ui.mjs`, `email_drafts_ui.mjs`, `email_inbox_ui.mjs`, `email_pages_ui.mjs`, `email_leads_ui.mjs`,
  `email_journeys_ui.mjs`, `email_bulk_ui.mjs`, `email_reports_ui.mjs` with `email_seed.py`, `email_agent_ui.mjs` (+ `email_agent_seed.py`), `email_mailbox_ui.mjs` (+ `fake_mailbox.py`), `email_crm_ui.mjs` (+ `fake_crm.py`), `dev-scripts/email/bulk_probe.py` (1,000 people, run the trial with `--workers 2`) and
  `dev-scripts/email/fake_resend.py` (domains, keys, sending, received emails, and Resend's signed reports back to the backend).
- Backups (`ops/backup.py`) never run with LOCAL_DEV: a developer's .env can hold the live storage keys.

## Leads (instagram_plan.md)

- Plan: `instagram_plan.md` (2 Nov 2026, from the owner's plan, with research: TRAI's A2P rules read from the regulation, Meta Lead Ads, Instagram
  messaging, Google lead forms): phases 0-11, status in its section 11. Phases 1 (Leads home), 2 (sources that need no review) and 3 (Meta lead ads
  connected directly) built 2 Nov 2026, phases 4 (first response and one set of stop rules), 5 (Instagram DMs), 6 (Instagram comments, stories, links) and 7 (promises, one
  follow-up plan per lead) 3 Nov 2026, local.
- One person is one `Contact` per assistant, whatever brought them and however often they ask; each submission stays in `LeadIntake`, each outcome in
  `LeadDeal` (won with an amount, lost with a reason), so someone who bought and asks again keeps the old sale and gets new work. `LeadTask` (the next step:
  due, whose, finished once by an atomic update), `LeadEvent` (the story, stamped in code each later than the last: the database's clock gives a whole save one
  time), `LeadSettings` (per assistant: new leads to nobody, one person or by turns, a backup, minutes to respond; a turn is one UPDATE, so four processes never
  give one lead twice). `Contact.quality`: None, ok (a manager overruled junk), junk, wrong_number, old (imported).
- `backend/leads/`: `core.py` (`visible(ctx)` is the one place saying who sees what: an agent only the leads given to them; `came_in` once per ref through
  NotificationLog, never raises, claims `last_enquiry_at` first so two submissions at once make one first step; `after_call`: someone who rang and talked is a
  lead the assistant answered, no first task; `queues` (Needs attention; Schedule's waiting calls and meetings count as next steps); `tick` (scheduler):
  reminders to whoever has the task, a first step nobody took moves to the backup, each claimed; `timeline` reads calls, meetings, emails, replies, chats and forms
  from their own tables, only this assistant's), `api.py` (`/api/crm`), `origin.py`, `quality.py`.
- Hooks: chat and WhatsApp leads (`events.lead_captured`, which also links the chat to the lead), forms and portals (`mail/intake.process`), callers
  (`pipeline._remember_and_plan`), the board (`journeys_api.update_lead` closes through `leads.close`), someone leaving the team (`routers/team.py`: their leads and
  tasks wait for a manager), Compliance > Erase (by number or now email; tasks, events and deals go by cascade).
- The 7 days: TRAI (Regulation 05 of 2026) lets an enquiry kept in writing be followed up for seven days; a lead shows the days left from `last_enquiry_at`.
  An imported list isn't an enquiry: no days.
- Sources that need no review (phase 2): Google lead forms (`/api/leads/in/<code>/google`; the key comes in the body, `LeadSource.google_key`; Google retries a 5xx
  and never a 4xx: a wrong key or the switch off is 403, busy 503, a repeated lead_id 200; a test lead is kept apart and reaches nobody, even with another key,
  as Google's documents don't say which key its test button sends). Facebook and Instagram lead ads by the business's own Zapier, Make or Pabbly (`/connect`:
  Meta's field names, lead_id once, platform ig is Instagram, no limit per address: every lead comes from their servers). Website forms keep the page's tags.
  The embed (`nimmi-widget.js` `firstTouch`: UTM tags and click ids from the host page's address, the landing page and the site before, kept 30 days on that
  site) passes the first touch to the widget, which sends it with the chat (`Conversation.origin`, kept once; `origin.from_widget` takes only a page's own tags, as
  anyone can post to the chat). A Click-to-WhatsApp ad's referral is kept on the
  chat (once) and the assistant is told the ad's words. `origin.py` keeps only known keys, as plain text; the dashboard shows them as text, never links.
- Facebook and Instagram lead ads, connected directly (phase 3, `backend/meta_leads/`, `/api/meta`; shown when META_APP_ID, META_APP_SECRET and
  META_LOGIN_CONFIG_ID are set, else Sources says to use the Zapier link): Facebook Login for Business returns to Leads > Sources, which finishes with the
  signed-in person's token (`read_state` must match workspace and person); a long-lived user token (60 days) gives each Page its own token, which doesn't
  expire; both sealed (`EncryptedText`). A Page belongs to one workspace (`MetaPage.page_id` unique; another's is named, not taken). A manager starts a Page's
  leads (`subscribed_apps`, leadgen), and gives each form an assistant (Growth); a form with none holds its leads (`MetaEvent` "waiting") until it gets one.
  Meta's webhook (`/api/meta/webhook`, `X-Hub-Signature-256` on the raw body with the app secret, `META_LEADS_VERIFY_TOKEN`) only names leads: each is kept
  once (`MetaEvent.leadgen_id` unique) before the 200, then one process (claimed) fetches it with the Page's token and hands it to `mail/intake.process` as
  channel "meta", source Facebook or Instagram lead ads, with the campaign, ad set, ad and form (`origin`) and Meta's tick boxes (`consents`). A form's email
  and call are off until its own switches are turned on (`act(email=, call=)`). Meta busy: tried again 1, 5, 15, 60, 180, 720 minutes on, then failed; a
  sign-in that ended or a missing permission shows on the Page with its repair, and its leads wait however long it takes (connecting again frees them). A
  catch-up every 15 minutes (`tick`) reads each routed form's leads since `checked_through` less 30 minutes, page by page, and moves on only past a complete
  read. "Bring in older leads" (90 days, Meta's limit) adds them as old leads, nobody contacted. Meta's deauthorize and data deletion callbacks
  (`/api/meta/deauthorize`, `/deletion`, signed_request) forget the person's sign-ins. Tokens go in a header, never an address, and the httpx log line hides
  `access_token`, `client_secret`, `code` and `fb_exchange_token` (`graph._HideSecrets`). `META_GRAPH_URL` and `META_DIALOG_URL` point at
  `dev-scripts/meta/fake_graph.py`. Graph v26.0; Meta's documents read 2 Nov 2026 (see `meta_leads/graph.py`). Never tried against real Meta yet.
- Junk (`quality.why_junk`): only when nobody could ever reach them: a number nobody has (one digit over and over, an Indian number starting with 0 or 1;
  98765 43210 isn't junk, it's someone's real number too) and no real email, or only a throwaway email. Kept, marked, told to nobody (no alert, email, call,
  journey or first task), hidden from All leads unless asked for, counted apart in Reports; such a number is never kept as `e164`, so strangers who typed it aren't
  joined together. Only a lead nothing real has happened with (`quality.fresh`): someone who called is real whatever they type. A manager overrules it (not marked
  again). The same person within 24 hours (`quality.REPEAT`): told to nobody again, noted "asked again"; their own consent tick is still kept.
- Import (`POST /api/crm/import`, managers): old leads from a CSV (the email import's column names, plus source, stage, notes), `quality` old: in All leads, not in
  Needs attention or Reports, no task, email, call or journey; when they ask again they're a lead like any other.
- Dashboard: `/dashboard/leads` (Needs attention, All leads, Board and Sources for managers, Reports; a lead at `/dashboard/leads/[id]`), `components/leads/`,
  `lib/leads.ts`. The Lead board and Lead sources moved here from Email (the old addresses redirect). Top bar: Leads after Assistants; Reference is in the account menu.
- Nimmi: `agent/tools/leads.py` (leads_attention, find_leads with junk, lead_details, leads_report); the board's and sources' tools come on Leads' screens too;
  `go_to` opens one lead (`leads_lead`, through `_lead`, so an agent can't open another's).
- Who may be contacted (phase 4, `leads/contact.py`): `can_contact(contact, channel, purpose)` is the one check every automatic channel makes just before it sends
  (the first email, call and WhatsApp to a new lead in `mail/intake.act`, `schedule.dial_check` for follow-ups and first calls, journeys, the email agent); each
  `Verdict` has a sentence for people and a code. `blockers` (whatever else says yes): junk or a wrong number, no number or email, do-not-call, unsubscribe or
  bounce, their own refusal (`ChannelPermission`, per channel and purpose, with where it came from; the team can't turn their no into a yes), and unless they asked
  for it themselves (`cause`): a closed lead, a meeting waiting (a request is never called booked: `MEETING_STATE`), or a person on it (`person_on_it`: a chat
  taken over, the WhatsApp chat paused, a result logged in 24 h, a team task due within 24 h). Then what allows it: a call, their enquiry in 7 days (TRAI) or a
  call they agreed to (lasts 7 days); WhatsApp, a message from them in 24 h, their yes (a form's tick: `whatsapp_ok` / a Meta form's `whatsapp_tick`), or a chat
  they started (a form alone never is); email about their enquiry for 30 days, offers only with `Consent`. Calls also need credits. A call-back they asked for
  stops only for a refusal given after they asked (`since`).
  One chase at a time (`stop_chase`): their email reply, their WhatsApp message, a team takeover (live chat, WhatsApp Inbox or phone app), a meeting asked for,
  do-not-call, won or lost cancel waiting follow-up calls, journeys and the email agent's queued emails, never a call-back they asked for; journeys wait 6 h while a
  person works the lead (`PERSON_WAIT`). Two submissions at once make one first contact (a NotificationLog claim keyed by the `last_enquiry_at` both saw).
  TRAI's A2P declaration: an Indian number (`+91`) dials nothing automatic until it's marked declared with proof (`PhoneNumber.a2p_*`, Voice > Numbers,
  `PUT /api/voice/numbers/{id}/a2p`); checked in `dial_check` and in the dialler (campaigns pause); `A2P_GATE=off` only in tests. "Call me" isn't gated. A dial
  whose request went out without an answer (`scheduler.maybe_placed`: read timeout, dropped connection) goes to `review`, never retried by itself.
  WhatsApp templates per assistant (`LeadSettings`: `whatsapp_first` to a new lead who said yes, {{1}} first name {{2}} business; `alert_template` to the person
  given the lead and the backup, {{1}} the lead {{2}} the link, to `User.whatsapp` from Profile), Growth up; the settings route saves only the fields sent.
- Plans as built: Leads home on every plan; reminder emails need Starter (`team_alerts`); Google and Zapier ride on Take leads from other places (Growth, as before);
  what each lead gets stays per plan (team alert Starter, lead email Growth, call Pro). instagram_plan.md 8.1's table is a proposal for the owner.
- Promises (phase 7, `leads/promises.py`, `LeadPromise`, the lead page's Promises card, Needs attention, Reports): what the business promised a lead (kind send,
  price, callback, visit, other), open until a record shows it was done, never because the AI said so. Found by the after-call analysis (`llm.summarize` key
  `promises`, with the assistant's own words; a `call_back_at` is one too; no extra model call; `pipeline._remember_and_plan` -> `from_call`; not test calls), by
  one fast model call (`_ask`, Groq then Gemini, JSON) on a chat or email conversation with a lead quiet for 30 minutes (`scan`: claimed by `Conversation.promises_at`
  / `EmailThread.promises_at` set to the last message's time; only what's new; email by `promises_seen` ids, as a draft can go out long after it was written; a plan
  needed), or added by the team. A quote that isn't really in what the business said is dropped (`quoted`, after NFKC and quote marks); the same promise again isn't
  kept twice. Closed by records after it was made (`evidence`/`actions`, `settle` every 2 minutes per promise, claimed, and when the lead's page opens): a call-back by
  an outgoing call they talked on or the team's "Spoke to them"; send by a file on WhatsApp or an email with a file; price by an amount (`MONEY`, any script's
  digits) or a file named like a price list or quotation; visit by a confirmed meeting; other only by a person. A person closes one by choosing a record since it
  (`/api/crm/promises/{id}/evidence`, `/done` with kind and id) or writing what they did (`how`, `note`); never a bare done; Nimmi's agent never closes one
  (coverage.py). Lost cancels what's open (`core.close`); a customer keeps theirs; do-not-call cancels a call-back. Due ones: the lead's person is told once
  (`remind`, Starter up, `core._alert`). `Conversation.last_message_at` is set by a hook on every new Message (models.py `_conversation_moved`); `messages` has an
  index on `conversation_id` since phase 7 (every chat answer reads its history by it).
- Journeys for the new sources (phase 7): `new_lead` values `meta` (Facebook or Instagram lead ads, direct or by Zapier), `google`, `ads`, `any_ad`
  (`origin.from_ad`: an ad's channel, gclid/gbraid/wbraid/ctwa_clid/ad_id, utm_medium paid; never fbclid alone, Facebook adds it to every link), `instagram`
  (fired when they first write, `instagram/contacts.first_dm`). `journeys.fire` takes values from the most specific; a new lead gets one follow-up plan: the
  most specific matching journey, else one for any lead, and none while they're on a new-lead journey already (status, meeting and customer journeys still run
  beside it, under the one cap). Reports: `lost_by_source` and `promises` (made, kept, on time, late, cancelled, by where made).
- Tests: `tests/test_leads.py`, `tests/test_lead_sources.py`, `tests/test_meta_leads.py` (a fake Graph shaped like Meta's documents), `tests/test_lead_contact.py`
  (phase 4; its lead page checks pin the clock to daytime, `daytime`), `tests/test_promises.py` (phase 7); browser: `dev-scripts/ui-checks/leads_ui.mjs` with
  `leads_seed.py` (after `email_seed.py`), `meta_leads_ui.mjs` (trial in "meta" mode, `fake_graph.py` on :8795), `lead_contact_ui.mjs` with `lead_contact_seed.py`
  (after `leads_seed.py`), `promises_ui.mjs` with `promises_seed.py` (after `email_seed.py`).

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
- NIMMI, Nimmi's own assistant, is on every public page through `components/site/SiteAssistant.tsx`: the customers'
  "Add to website" script, loaded `lazyOnload`, never on dashboard, auth, widget or demo pages. NIMMI has the same id
  (130cc13a-...) in the live and local databases (copied by `dev-scripts/site/nimmi_to_live.py`); `NEXT_PUBLIC_SITE_ASSISTANT_ID`
  picks another, empty turns it off. Its setup (knowledge, flow, lead capture, look, voice scripts, Schedule) is
  `dev-scripts/site/setup_nimmi.py`, written from the pricing table and FAQs: change both together.

## Nimmi agent (the dashboard's own assistant)

- Plan, phases and results: `NIMMI_AGENT_PLAN.md` (phases 0-6 built Oct 2026, local; not pushed yet).
- Backend `agent/`: `router.py` (`/api/agent`: messages stream server-sent events; runs replay from any process; stop;
  threads; actions confirm/cancel/undo, runs/{id}/undo (Undo all); jobs for the builder's cards; usage), `loop.py` (the
  answer in layers, below; a heartbeat reads stop_requested; also runs builder steps), `intake.py`, `plan.py`, `check.py`,
  `output.py` (no emojis, in code), `flows.py` (flows as steps), `providers.py` (Gemini, OpenAI, Groq with tools;
  AGENT_MODELS order, AGENT_FAST_MODELS for the quick checks; a model at its limit rests as the service says, up to an
  hour; `ask_json`; `cost_inr`),
  `events.py` (AG-UI event names, saved in agent_events), `registry.py` (levels read / change / confirm; Change and
  adapters for undo; confirm_action, undo_action), `screens.py` (notes per screen, AREAS, POINTS), `prompt.py`,
  `builder.py` + `brand.py` ("create an agent for me"), `guides.py`, `coverage.py` (every route: tool, excluded with
  a reason, or pending), `mcp.py` (POST /mcp and Nimmi keys), `tools/` (assistants, changes, flow, confirm, build,
  connections, voice, workspace, more, navigate, work).
- An answer in layers (NIMMI_AGENT_PLAN.md section 14; built 30 Oct 2026 after live failures: "make GBOT like GTBOT" did
  one change and claimed five; "create a flow" pasted a table): intake (one fast-model call: "do" or "ask", the areas
  whose tools it needs whatever page is open, a first plan) -> plan (a checklist in the panel, agent_runs.plan, kept
  current with update_plan) -> tools (intake's areas, load_tools; a tool's `after` waits for another, write_flow after
  get_flow; a call made twice in one answer isn't made twice; errors carry a kind) -> guard (an answer while a followed
  plan has open steps goes back to work) -> check (`<done>`, what the tools really did, in every round; a task's answer
  is held and reviewed by a fast model: ok, fix (the corrected answer goes) or continue (once), and the plan's statuses
  set from the ledger). No rule about particular words anywhere: models read the requests.
- Flows as steps (`flows.py`: outline/build, checked: links lead somewhere, all reachable, no endless loop without a
  question; blocks keep their place): get_flow, write_flow, draft_flow (from the assistant's knowledge; a sentence
  with a number the knowledge doesn't have is left out). copy_assistant_settings copies design, avatar, instructions,
  reply settings, knowledge, flow between assistants in one undoable change (not which pages it shows on).
- Tools call route functions directly with the person's AuthContext, which skips FastAPI's dependencies: a tool must
  declare the roles its route requires. Read tools never call an AI model or write (a test checks). Change tools return
  a Change (exact settings before/after); confirm tools need a preview and run only on Confirm. Each area's tools come
  on its own screens (AREAS); an unknown screen gets all.
- Tables: agent_threads, agent_messages, agent_runs (cost_inr, kind, plan), agent_events, agent_actions, agent_jobs,
  agent_keys.
- Dashboard: `components/agent/` (AgentProvider in `app/dashboard/layout.tsx`; AgentPanel: header with status and a
  More menu, history, Changes tab, keyboard shortcuts; AgentComposer: the box, the mic, "/" shortcuts; AgentMessages:
  welcome, turns, the plan's checklist, Copy / Read aloud / thumbs / Try again / Undo all; AgentCards, AgentText (tables
  too), AgentToggle, AgentKeys on Profile),
  `lib/agent/` (screens, stream, changes, useRecorder, useSpeaker). The mic posts a recording to
  `/api/agent/transcribe` (Sarvam, language found by itself); Read aloud is `/api/agent/speak` (Sarvam, Priya, the
  language from the script); thumbs are `/api/agent/runs/{id}/feedback` (agent_runs.feedback).
- Sarvam STT refuses a content type with codecs ("audio/webm;codecs=opus", Chrome's recorder): `sarvam.transcribe`
  sends the plain type, and an unlisted one as application/octet-stream (widget mic, panel mic, WhatsApp voice notes). `useApi` reloads
  when Nimmi changes something (`nimmi:changed`); the builder saves unsaved edits before each message (`useAgentScreen`
  flush). Pointable elements carry `data-agent="..."` (a test checks the names). The builder opens a tab from `?tab=`;
  Voice > Numbers and WhatsApp > Settings open their connect form from `?connect=1`.
- Limits: AGENT_DAILY_FREE / AGENT_DAILY_PAID per workspace in 24 hours.
- Keys (Oct 2026): Gemini key free tier (20 requests a day); Groq free tier (8,000 tokens a minute and 200,000 a day per
  model; an answer with a tool is 5,000-8,000); OpenAI no credits.
- Tests: `tests/test_agent.py`. Real models: `dev-scripts/agent/model_probe.py`, `eval.py`, `build_trial.py`,
  `task_trial.py` (real tasks checked in the database, on a backend and database of its own). Browser:
  `dev-scripts/ui-checks/agent_ui.mjs`, `agent_changes_ui.mjs`, `agent_builder_ui.mjs`, `agent_more_ui.mjs`
  (AGENT_PACE_MS=30000 on free tiers).

## Testing conventions

- Fakes in `tests/test_pipeline.py` (FakeTransport, FakeStt, fake_tts, replier_saying); `run` fixture runs
  coroutines on the app loop; `make_user` makes a signed-up user with `.bot()`.
- For timing-sensitive tests, make ordering deterministic (Windows timers are coarse: ~16 ms).
- New behaviour gets a test that fails without the fix (check by reverting the fix once).
