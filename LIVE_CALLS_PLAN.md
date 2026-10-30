# Live calls and "Pick up the call": plan

Written 30 Oct 2026 from the owner's idea: the Calls page shows which calls are going on right now, and when a caller
needs a person (they ask for one, or what they need takes a person), a notice pops up on the team's screen with
"Pick up the call", and someone from the team joins the call and talks to the caller themselves.

## 1. What exists today (read from the code, 30 Oct 2026)

- A call's record (`CallLog`) is created the moment the call connects, with outcome `in_progress`, but its transcript is
  written only when the call ends, and nothing shows live calls: the Calls page lists records and never refreshes.
- A call that dies with its server process (a deploy, a crash) stays `in_progress` for ever.
- Transfer to a phone number (agent page): the AI writes a transfer marker, says it will connect them, the call's audio
  stream is closed, and the provider asks us what next (Twilio: the `<Connect action>` URL; Exotel: the Passthru
  applet, then Connect dials the number from our URL). Cold or warm (a spoken brief to the person first).
- **A bug in it**: which number to transfer to is kept in the memory of the server process running the call
  (`scheduler.pending_transfers`), but the provider's next request can reach any of the four live processes. Three
  times in four it finds nothing and the caller is hung up on. This is fixed as part of this work (section 4).
- Live chat (website) already alerts the team: the backend emits to the workspace's socket room and the page reloads.
  A socket only reaches dashboards connected to the same process unless REALTIME_REDIS_URL is set.

## 2. Research (Oct 2026)

- Twilio: the instructions after `<Connect><Stream>` run as soon as our server closes the stream, and a live call can
  also be given new instructions at any time (the Calls API). A browser joins with the Voice JavaScript SDK
  (`@twilio/voice-sdk` 2.18.5, Apache-2.0): an Access Token with a Voice grant that allows incoming calls, then
  `Device.register()`, which must follow a click (browsers block audio otherwise); the call reaches it only through
  `<Dial><Client>identity</Client></Dial>`. Tokens need an API key of the same Twilio account as the call.
  ([Access Tokens](https://www.twilio.com/docs/iam/access-tokens), [Device](https://www.twilio.com/docs/voice/sdks/javascript/twiliodevice),
  [Best practices](https://www.twilio.com/docs/voice/sdks/javascript/best-practices), [Stream](https://www.twilio.com/docs/voice/twiml/stream))
- Exotel: the documented way from a voice bot to a person is the Connect applet straight after the bot, dialling a
  phone number (Nimmi's Exotel flow already has it). No browser path for a bot's call was found, so on Exotel the
  person takes the call on their phone. ([Exotel AgentStream](https://developer.exotel.com/docs/agentstream/connect-voice-ai-flow),
  [ElevenLabs on Exotel transfers](https://elevenlabs.io/docs/eleven-agents/phone-numbers/telephony/exotel))
- How AI voice platforms do it in 2026: warm handoff is the norm; the person gets the context (a one-line summary, what
  was collected, the transcript so far); the AI keeps the caller company while a person is found; when nobody is
  free, a call-back instead of a dead end.
  ([Telnyx guide](https://telnyx.com/resources/ai-to-human-handoff-voice-ai), [Stream: warm vs cold](https://getstream.io/blog/warm-vs-cold-transfer/))

## 3. How it works

1. **Live calls.** While a call runs, its record says it's alive (`live_at`, every few seconds) and carries the
   transcript so far. The Calls page shows "Live now" at the top: who, which assistant, how long, and who is on it
   now (the assistant, "asking for a person", or the team member). Opening one shows the transcript as it happens.
   A call whose process died is closed as "interrupted" a minute later.
2. **A caller needs a person.** The AI decides, from the conversation, not from a list of words: it has a tool,
   `ask_for_person`, for when the caller asks for a person or needs what only a person can do. Nimmi then:
   - checks who in the team is available (their dashboard is open and "Available for calls" is on);
   - if someone is: alerts them, and the AI tells the caller it's getting someone and keeps helping meanwhile;
   - if nobody is: the AI offers a call-back (a to-do for the team in Schedule), or the agent's transfer number.
3. **The alert.** On every dashboard page of every available team member: a card with the caller (name if known),
   the assistant, why they want a person (the AI's words), how long they've waited, and the last lines of the
   conversation; a ring; a desktop notification when the tab is in the background. Buttons: **Pick up here**
   (browser, on Twilio numbers), **Call my phone**, **Let the assistant handle it**.
4. **Picking up.** The first to accept gets it (the others see who took it). The AI finishes its sentence, says it's
   connecting them, and hands the call over: to the team member's browser (Twilio) or phone (Twilio, Exotel). The
   person sees the summary and transcript before speaking. In the browser: a call bar with mute and hang up.
5. **Nobody in time** (the agent's wait, 45 s by default): the transfer number if set, else the AI says the team is
   busy and that someone will call back, and a to-do lands in Schedule. The call goes on with the AI.
6. **The record.** The call's transcript shows "Priya picked up at 2:31"; the call's outcome is "Transferred"; the
   handoff (who, how, how long they waited, how long they talked) is kept with the call.

## 4. Building blocks

- `call_handoffs` (new table): one per hand-over: the call, why, status (ringing, accepted, connected, ended,
  missed, cancelled, failed), how (browser, phone, transfer number), who took it, the brief, times. The provider's
  "what next" requests read it from the database, so any process can answer: the transfer bug is gone.
- `team_presence` (new table): who is available for calls in a workspace, seen within the last 45 s.
- `CallLog.live_at` (new column) and the live transcript.
- `voice/handoff.py`: the tool, the alert, the watcher inside the call (connect on accept, the fallback on time-out).
- `voice/live_api.py`: `GET /api/voice/live` (live calls and open requests; it also marks the caller of it as present),
  accept / decline, the browser token.
- Dashboard: a `CallDesk` mounted in the dashboard layout (alert card, ring, desktop notification, the browser call
  bar), and "Live now" on the Calls page.

## 5. Phases

1. Live calls on the Calls page; live transcript; dead calls closed; transfers kept in the database (the bug).
2. `ask_for_person`, availability, the alert on every page, Call my phone (Twilio and Exotel), the fallback with a
   call-back to-do, agent settings (ring the team, how long to wait).
3. Pick up in the browser (Twilio): tokens from an API key Nimmi creates on the call's Twilio account the first time
   (stored sealed), the Voice SDK loaded only when someone picks up, the call bar.
4. Later: hand back to the assistant when the person hangs up; recording and transcript of the person's part;
   listening in without joining; billing the person's part.

## 6. Decisions for the owner

1. Browser pickup creates a Twilio API key on the call's Twilio account (Nimmi's own, or a customer's connected one)
   the first time it's used. OK to do this automatically?
2. Billing: the person's part of a call uses no AI. Bill it at the base 1 credit a minute on Nimmi's numbers (the line
   still costs), or free?
3. A real test needs a phone call: you call the test number on live (or "Call me"), ask for a person, and pick up in
   the browser. Twilio charges a few cents.

## 7. Status (30 Oct 2026, pushed in beed98d)

Built: phases 1 to 3.
- Backend: `voice/handoff.py` (the tool, availability, rows, phrases in 11 languages, the sweep), `voice/live_api.py`,
  `CallHandoff`, `TeamPresence`, `TwilioKey`, `CallLog.live_at`, the agent's `team_handoff` and `team_handoff_wait`
  (per direction, like the transfer settings), the pipeline's heartbeat, watcher, hand-over and fallback, Twilio's
  `<Dial><Client>` and the person-done step, Exotel's steps from the database. The agent's transfer number now goes
  through the same rows: transfers no longer depend on which server process Twilio's or Exotel's next request reaches.
- Dashboard: `components/voice/CallDesk.tsx` on every dashboard page (the card, the ring, desktop notifications,
  picking up in the browser with `@twilio/voice-sdk` 2.18.5 loaded only then, Call my phone, the call bar),
  `lib/voice/live.ts` (checks every 3 s, and at once on the socket's `call_handoff`), "Live now" and a live transcript on
  the Calls page, "Live" for calls still going on, the agent page's "Ring my team in the dashboard".
- The ring (owner, after trying it: "i am getting notification ... i need sound"; the first ring was two 0.16 s blips
  peaking at -23 dBFS): India's double ring (0.4 s on, 0.2 off, 0.4 on, 2 off), two notes with a 25 Hz wobble like a
  phone's bell, measured in Chrome at -5.5 dBFS peak and -15 dBFS RMS while ringing. It's scheduled on the audio clock
  (a background tab slows timers, not audio). Browsers play sound only after a click on the page: the first click
  anywhere wakes the audio up, and until then the card says why it's quiet. One tab rings per computer (Web Locks); when
  it's closed, another takes over. Ring sound on/off (remembered in this browser) is on the card and on Calls, in an
  always-shown strip with "Available for calls" (before, a person who chose "I'm not taking calls now" could turn it back
  on only while a call was live) and Test ring. The tab's title flashes "(1) Caller waiting"; desktop notifications also
  when the window isn't the one in front, and they stay until the caller is answered.
- Tests: `tests/test_live_calls.py` (9: whole calls with a team member accepting from another process, nobody in time,
  nobody available, the caller leaving, the API and its permissions, the token and its sealed key, Exotel, the
  sweep); each new rule checked to fail without its fix; 376 backend tests pass. Browser:
  `dev-scripts/ui-checks/live_calls_ui.mjs` with `live_calls_seed.py` on a trial backend (Twilio off): 16 of 16.
  The ring: `live_ring_ui.mjs` (Chrome's normal sound rules, speakers muted; what reaches the speakers is measured in
  the page): quiet and explained before a click, the rhythm within 5 ms, the level, one ring with two tabs and the
  hand-over when one closes, Sound off/on, silence once the caller is let go, Test ring: 28 of 28.
- Proven on a real call (30 Oct 2026, local through a tunnel): the owner picked up in the browser; Twilio connected it
  in 6 s and they talked 23 s. The API key was created on the account by that click.

Not proven yet (needs the owner): a real phone pickup ("Call my phone"), and the ring heard on a real computer's
speakers (checked only by measurement in a muted browser).
