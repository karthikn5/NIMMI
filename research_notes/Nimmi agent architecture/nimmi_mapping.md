# Nimmi repository capabilities and agent experience

Research date: 29 October 2026. Repository inspection only; no application source changes, production access, live provider calls, or test runs. Web sources below support interface guidance, not a claim that the proposed agent already exists. All proposed names below are design recommendations.

## 1. What exists in Nimmi, and what must the new agent add?

### Takeaway

Nimmi already has substantial authenticated business APIs. The agent should use a shared business-service layer behind those APIs, with a new draft/run/audit layer; it should not impersonate the public marketing chatbot or expose a generic arbitrary-HTTP tool. Product parity means every operation the signed-in role is authorized to perform has an explicitly reviewed capability or a guided secure handoff, not access to administrative internals or external consoles.

### Cited Findings

- The public `SiteAssistant` loads the normal customer widget for NIMMI and deliberately excludes dashboard, auth, widget, and demo routes. This is a public chatbot identity, not a workspace-management identity. [SiteAssistant.tsx](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/components/site/SiteAssistant.tsx:11)
- Violet already exists as a custom element dynamically imported from the backend, with reduced-motion handling and cleanup on disconnect. Reuse that renderer/asset behind a dedicated dashboard avatar component. [widget launcher](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/static/nimmi-widget.js:322), [Violet implementation](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/static/characters/violet/violet.js:90)
- Dashboard layout currently returns its children without a persistent application shell. `AppHeader` supplies role-filtered navigation and workspace switching, while the builder uses its own header and local editing state. [dashboard layout](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/dashboard/layout.tsx:11), [AppHeader](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/components/AppHeader.tsx:13), [builder](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/dashboard/builder/[id]/page.tsx:29)
- Shared interface primitives already provide buttons, cards, inputs, switches, dialogs, segmented controls, and focus styling. Existing brand tokens include plum `#550a64`, ink `#1c1719`, line `#e8e5e0`, and paper `#faf9f7`; use the existing theme. [UI kit](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/components/ui.tsx:1), [theme](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/globals.css:20)
- Dashboard requests carry a bearer token and optional `X-Workspace`; backend resolves a person, workspace owner, and role. Manager means owner/admin. Resource ownership is enforced server-side; local development has ownership relaxations, so isolation tests must use `LOCAL_DEV=false`. [API helper](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/lib/api.ts:1), [auth](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/auth.py:121)
- New bots are created immediately with `Bot.is_active` defaulting true; current schema does not provide a separate staged agent-created bot revision. New drafts must not simply call `create_bot` and gradually mutate public config. [create_bot](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/bots.py:89), [Bot](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/models.py:21)
- Existing crawler returns content and URL information; it strips style/script elements and skips CSS assets. It is not a website visual-brand extractor. It discovers sitemaps from robots.txt, but that alone is not proof of robots disallow enforcement. [crawler](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/crawler.py:1)
- Knowledge sources are presently blocks inside `Bot.knowledge_base`; crawling writes them immediately, then `_after_change` fires background summary/index work. Its `chunks_indexed` response is calculated from chunk count before the background work finishes. Therefore the agent must verify a durable indexing result and never claim indexing succeeded from this response alone. [source storage](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/knowledge_sources.py:1), [knowledge ingestion](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/bots.py:397)
- Config writes accept fairly broad dicts, and flow validation lives in the dashboard's `flowKit.checkFlow`; a typed authoritative server-side schema and equivalent validator are required before model-produced flows can be applied. [config endpoints](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/bots.py:250), [flow checks](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/dashboard/builder/[id]/components/flowKit.ts:18), [flow runner](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/widget/[botId]/flow.ts:1)
- Voice saves prepare an opening when the resulting agent is enabled and has a voice. This can invoke speech providers. A draft/preview path must avoid this implicit side effect; the agent cannot classify every configuration write as free or local. [update_agent and opening preparation](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/voice/router.py:285)
- Site uploads/git deployments start background publish work; email broadcast creation queues actual messages. They are not inherently private previews. [sites upload](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/sites.py:237), [git deploy](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/sites.py:297), [broadcast creation](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/email_center.py:186)
- Plan limits are already available from `/api/account/limits`; free workspace limits include one assistant and one website, voice allowed, integrations/custom domains restricted. Installation separately checks an active per-bot subscription. The proposed agent must evaluate both existing rules rather than assume that a free assistant is installable everywhere. [plans.py](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/plans.py:35), [install eligibility](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers/bots.py:117)
- The checkout already contains local edits to AppHeader and untracked reference-page/video content and AGENTS.md. These were left untouched. [AppHeader](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/components/AppHeader.tsx)

### Capability coverage matrix grounded in existing routes

Tool names in this table are proposed namespace families, not existing tools. Each family must expand into individually typed tools with action-specific permissions and tests. Do not route `action: string` directly to backend action routes without a finite enum. API verbs and paths listed are existing representative operations, not exhaustive generated parity output.

| Product area and proposed family | Existing implementation and representative API | Agent behavior and boundary |
|---|---|---|
| Workspace discovery `workspace.*` | `auth.py`, `routers/team.py`: `GET /api/team/workspaces`; `plans.py`: `GET /api/account/limits`; `routers/workspace.py`: `GET/PUT /api/workspace/settings` | Read role, workspace, limits and safe readiness. Derive workspace from authenticated run; never accept model-supplied owner identity as authority. Settings changes use a diff. |
| Assistants `assistants.*` | `routers/bots.py`: `GET /api/bots`; `POST /api/bots/create`; `GET /api/bots/{bot_id}/config`; `PATCH /api/bots/{bot_id}`; `DELETE /api/bots/{bot_id}`; restore endpoints | List/get, propose/create draft, review changes, apply version, delete/restore with impact review. Keep new drafts separate until ready and preserve current manual behavior. |
| Builder design and behavior `design.*`, `behaviour.*` | Builder `DesignPanel.tsx`, `BehaviourPanel.tsx`, `design.ts`; `PATCH /api/bots/{bot_id}` | Theme generation writes a typed draft. Business facts come from sources; style inference includes confidence and editable preview. Include normalizing old/new visual keys. |
| Knowledge `knowledge.*` | `crawler.py`, `knowledge_sources.py`, `vector_store.py`, `brain.py`; `POST /api/knowledge/crawl`; upload, sources, summary, reindex, stats under `/api/bots/{bot_id}/knowledge/*` | Preview crawl scope, bounded scrape, durable ingestion, source provenance, refresh/delete sources, index validation. Draft ingestion must not mutate an existing live bot. |
| Flow `flows.*` | `flowKit.ts`, `flow.ts`; `flow_data` through bot config | Typed graph proposal, deterministic validation, simulation, review/apply. Validate start count, node types, references, reachable exits, required fields, handles, cycles/step limits, allowed external function destinations. |
| Leads, contacts `leads.*`, `contacts.*` | `GET /api/bots/{bot_id}/leads`; `GET/PATCH /api/voice/contacts/{contact_id}`; `POST .../forget`; schedule lead update route | Answer scoped questions, filter, propose notes/lead status. Limit transcript/PII to task needs. Erasure and memory changes require explicit impact review. |
| Live chat `handoffs.*` | `routers/handoffs.py`: `/api/handoffs/pending`, `/{conversation_id}/accept`, `/close`, `/messages`, `/reply`, `/notes` | Read context, draft reply, accept/close, add note where role permits. Sending is outward-facing and requires approval of exact recipient/conversation and text. |
| Questions and saved replies `questions.*`, `replies.*` | `routers/workspace.py`: `/api/questions`, `/{gap_id}/answer`, action/delete; `/api/workspace/replies` CRUD | Explain unanswered questions; draft grounded answers; apply approved answer/knowledge changes. Maintain same manager restrictions. |
| Analytics `analytics.*` | `routers/analytics.py`: `GET /api/analytics`; channel overview endpoints | Read scoped aggregates with date/filter context; label facts vs suggestions; do not invent performance metrics. |
| Voice settings `voice.agents.*`, `voice.scripts.*` | `voice/router.py`: `/api/voice/agents/{bot_id}?direction=`, `/scripts/{bot_id}/{direction}`, `/scripts/.../draft`, `/voices`, `/models`, `/rates`, `/agents/{bot_id}/details` | Configure inbound and outbound separately; preserve shared settings. Choose only available models/voices; ask languages, direction, goals and any missing business details. Prepare disabled draft; activate only after checks/approval. |
| Voice functions `voice.functions.*` | `voice/functions.py`; functions in agent settings; `POST /api/voice/agents/{bot_id}/functions/test` | Define typed HTTP/Cal.com functions, masked secret slots, dry validation. A live test may make external changes; never assume the test button is side-effect free. |
| Phone numbers/accounts `telephony.*` | `voice/numbers_api.py`, `connections_api.py`, `router.py`: `/numbers/available`, `/numbers/buy`, `/numbers/{id}/replace`; `/phone-accounts`, `/phone-accounts/{id}/numbers`; route/delete/document routes | Availability read is separate from purchase. Secure credential UI, ownership/entitlement/price checks. Buying, replacing/routing active numbers and external account configuration require specific approval. Provider KYC requires the owner and provider review. |
| Browser/phone tests `voice.tests.*` | `POST /api/voice/session`, `/ws/browser`, `POST /api/voice/test-call`, call detail/recording endpoints | Use fakes for automated development verification. Browser speech may still consume AI/speech credits. Actual calls require destination and cost review, consent and current wallet checks. |
| Campaigns `campaigns.*` | `voice/campaigns_api.py`: `/api/voice/data`, `/campaigns`, `/campaigns/{id}`, `/campaigns/{id}/{action}` | Separate audience validation/draft from real creation/start; respect DNC/hours/credits/concurrency. Review exact audience and schedule before dialling. Pause/cancel must show already-started call limits. |
| Schedule and meetings `schedule.*`, `meetings.*` | `voice/schedule_api.py`: `/api/voice/schedule/settings/{bot_id}`, `/items`, `/items/{job_id}/{action}`, `/meetings/{id}/approve|propose|decline|mark`, `/free-times` | Read and plan. Approval/proposal can cause calls/messages; show downstream effects. Never represent meeting approval as only a DB field change. |
| Compliance `compliance.*` | `/api/voice/compliance`, `/dnc`, `/erase`; `voice/router.py` | Explain and maintain owner controls. Destructive erasure and removing DNC entries require explicit approval and role checks; no bypass via agent. |
| WhatsApp `whatsapp.*` | `whatsapp/api.py`: `/numbers`, `/numbers/{id}/refresh|test`, `/chats/{id}/send|pause|resume|assign|status|notes`, `/files`, `/confirmations` | Configure existing supported connection modes, secure token entry, preview replies/settings. Enforce message window/template rules in domain service. Test/send are external actions, pause/resume changes customer-facing behavior. |
| Integrations `integrations.*` | `routers/integrations.py`: `GET/PUT /api/integrations`, `/test`, `/log` | Read masked readiness; guide exact provider steps; secure credentials go directly to backend. Integration tests can send messages; classify individually. |
| Email `email.*` | `routers/email_center.py`: `/api/integrations/email/history`, `/jobs/{id}/resend|cancel`, `/audience`, `/broadcasts`, `/broadcasts/{id}/cancel`, `/stop` | Recipient preview and content drafts; review recipients, message and automation side effects before queue/send. Bulk creation already queues jobs. |
| Deployments `sites.*` | `routers/sites.py`, `sites/*`: `/api/sites`, `/{id}/deploys`, `/{id}/deploys/git`, `/{id}/deploys/{deploy_id}/promote`, `/{id}/domain`, domain check, hooks | Read status and prepare private artifact. Existing deploy entry points publish; cannot call them during preview. Publication/custom domain/hooks/delete need impact approval. DNS ownership/registrar remains a guided external task unless a separately authorized connector exists. |
| Team `team.*` | `routers/team.py`: `/api/team/members`, `/invite`, `/members/{id}` PATCH/DELETE | Permission-aware read. Sending invites, role changes/removal are reviewed owner actions. Agent itself cannot accept another person's invite. |
| Billing `billing.*` | `payments.py`: `/api/payments/subscriptions`, `/history`, `/create-subscription-order`, `/create-minutes-order`, `/create-balance-order`, `/toggle-auto-renew`; `/api/billing/balance` | Explain current entitlements/rates and prepare order for secure hosted checkout. Never collect card data or forge verify/webhook events. Purchases/renewal changes require owner approval. |
| Profile/account `account.*` | `routers/auth_routes.py`: `/api/auth/profile`, `/change-password`, `/logout-all` | Profile facts and guided changes. Password/email-sensitive steps open a secure form requiring current credential or reauthentication; model never receives passwords. |
| Installation `install.*` | `routers/bots.py`: `/api/bots/{id}/install`, `/wordpress-plugin`, `/bots/export`; dashboard `components/install/platforms.ts` | Generate code/downloads after current eligibility check and provide platform steps. Confirm installation with a real approved verification, not just a generated snippet. Cannot edit arbitrary customer CMS without a connected authorized integration. |
| Internal administration | `/api/voice/admin/numbers/{id}/activate`, `/api/sites/admin/{slug}/{action}`, webhooks/payment verification | Explicitly excluded from workspace-agent tools; these are provider/system/admin paths, not regular customer capabilities. |

Matrix source roots: [backend routers](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/routers), [voice modules](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/voice), [WhatsApp API](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/whatsapp/api.py), [payments](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/payments.py).

### Inferences

- Add an explicit maintained capability catalog per module: UI action, existing endpoint/service, tool name, roles, entitlement, read/write/external/deletion classification, approval rule, idempotency, input/output schema, rollback/reconciliation strategy, workflow coverage, tests. CI should detect a new manual operation lacking a reviewed tool or explicit guided/unsupported reason.
- Refactor domain logic incrementally from route functions into services accepting a trusted execution context. Both manual APIs and agent tools call those services. Do not copy business logic or HTTP-call localhost with an all-powerful token.
- Add durable `AgentDraft`/configuration revision state and pending knowledge artifacts. New bots become visible as finished configurations only after all required artifacts are ready; existing active bots continue serving their prior revision until apply. Per-bot public config currently exposes visual/flow even if inactive, so merely setting `is_active=false` is not a complete private-draft mechanism.
- A separate draft count/retention/quota prevents free-plan bypass or abandoned drafts consuming the sole assistant slot forever. Recheck plan capacity atomically at final create/apply.
- Brand discovery should read validated same-site HTML metadata, theme-color, logo links and limited CSS safely, recording candidate colors with provenance. A sandboxed rendering worker can be optional later for JS-only pages; it must have strict outbound controls and no dashboard credentials. Never execute crawled HTML in the dashboard origin.
- Every proposal should show fields inferred vs user-supplied, sources, missing data, preview and proposed changes. Missing website pricing or policy is a question, not permission to invent it.

### Gaps

- Repository inspection does not confirm live deployment configuration or external provider account state.
- Complete parity requires an implementation-time inventory of every current manual UI action and endpoint, including endpoint side effects. The matrix above identifies major modules and hazards, not a claim of completed parity.
- No new user-facing dashboard agent, durable draft system, workflow engine or MCP registry was observed in the inspected files. They are proposed work.
- This pass did not run browser accessibility testing, UI screenshots, unit tests or live calls.

## 2. What should the route-aware interface and workflows do?

### Takeaway

The visible avatar is a launcher and status indicator. The actual agent is a persistent authenticated dashboard panel with typed page context, structured question cards, explicit progress, reviewable drafts, safe credential forms and resumable runs. Navigation must never silently change the target of a running workflow.

### Cited Findings

- The builder has internal tab selection and unsaved state beyond the URL, so pathname alone cannot express whether the user is editing Design, Knowledge, Behaviour, Flow or Leads. [builder state](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/app/dashboard/builder/[id]/page.tsx:29)
- The dashboard switches workspace using a reload, and its API helper reads active workspace from localStorage. A long-running agent run must have workspace identity stored server-side and be reauthorized rather than relying on mutable browser storage. [AppHeader.switchTo](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/components/AppHeader.tsx:62), [API helper](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/lib/api.ts:80)
- WAI-ARIA's modal-dialog pattern requires focus behavior appropriate to a genuinely modal surface; the background is inert, focus is contained and restored on closure. A desktop dock that leaves the page usable is not a modal dialog. [WAI-ARIA dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
- WCAG status messages should be programmatically available without moving focus. Progress and completed-action announcements should be polite and concise, not every streamed token announced as an alert. [WCAG 2.2 status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
- `prefers-reduced-motion` communicates a preference to reduce nonessential motion; the agent avatar should honor it with a static fallback. [MDN reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)

### Inferences

**Shell and controls**

- Add `AgentProvider` once in the dashboard layout; portal/render `AgentDock` there so it survives route changes. Add one reusable `AgentLauncher` to AppHeader and builder's custom header. Keep authentication/workspace reset handling in the provider.
- Label the header button `Nimmi agent`; show a count/dot only when action is needed. Desktop default: right dock about 400 px, resizable within sensible bounds, with a separate floating mode. Those dimensions are design proposals to verify visually, not existing measurements. Mobile: full-height sheet/dialog with close control, focus containment and safe-area support. Tablet should avoid squeezing the builder into unusable width.
- Four distinct controls/state concepts: `Show avatar` preference, panel open/closed, agent enabled/disabled, and current run status. Hiding avatar or closing panel does not cancel work. Disable prevents new execution and pauses before the next side effect; report any already-started external action. `Stop task` requests cancellation and must state that completed effects remain. A minimized running task remains visible in the header.
- Keep token streams inside a transcript pane, an always-visible current-page chip, a compact task list with real statuses, one primary next-action card, and a composer. User-facing vocabulary: `Reading your website`, `Preparing design`, `Needs your input`, `Review changes`, `Connecting your number`, `Ready to test`. Avoid MCP, tool names and JSON in normal UX.
- Use the existing plum theme, typography, spacing and UI kit; no emoji, competing neon palette or distracting avatar animation. Avatar transitions reflect idle/working/waiting/complete/error without claiming emotions or activity when no run exists.
- Context display might read `Builder · Acme · Knowledge · unsaved changes`. User can turn off sharing the selected page's optional data while retaining route-level help.

**Typed page context**

Proposed shape:

```ts
type AgentPageContext = {
  schemaVersion: 1;
  contextVersion: number;
  tabId: string;
  routeKey: string;
  routeParams: { botId?: string; campaignId?: string; siteId?: string };
  section?: 'design' | 'knowledge' | 'behaviour' | 'flow' | 'leads' | string;
  selection?: { kind: 'flowNode' | 'call' | 'contact' | 'chat'; id: string };
  filters?: Record<string, string | number | boolean>;
  dirty: boolean;
  savedRevision?: string;
  draftPreview?: { fieldNames: string[]; safeValues: Record<string, unknown> };
};
```

Use an allowlisted schema per route instead of arbitrary `Record` in production. IDs are hints that the backend validates. Do not include tokens, passwords, entire DOM, arbitrary localStorage, invisible form values or unrelated messages. Include unsaved values only from deliberately registered safe fields and user agreement; never silently save over them. On each user turn, capture an immutable context snapshot. Bind a run to confirmed workspace/resource/revision. Subsequent navigation updates help context but not the run target. When the user says “change this” after navigating, ask a short choice card between the current page target and ongoing task if ambiguous. Workspace switch detaches subscriptions/caches, resets visible context and scopes history; no transcript from workspace A may flash in workspace B.

**Workflow contract**

Each versioned workflow declares trigger, required role, applicable page/resource, required inputs, source policy, allowed tools, typed states, bounded loops, success criteria, approval points, retry/reconciliation rules and checkpoints. Triage returns one workflow ID and missing inputs, or a read-only answer path. The deterministic capability checker verifies permission/plan/provider/credential/schema/target readiness before every tool, not just at run start.

**Minimum workflow catalog**

1. `screen_help`: read current route/section plus authorized configuration, answer with the actual screen's fields, cite product help, navigate/highlight an allowlisted control on user request; no write.
2. `create_assistant_from_website`: intake URL or upload/manual alternatives; business-goal/lead questions only if absent; verify quota; safe crawl with scope/source report; extract grounded facts; infer brand/name and confirm uncertain items; prepare knowledge/design/behavior/flow in a draft; validate and simulate; ask whether voice is wanted; review one cohesive draft; create/apply after current-version checks; verify persisted settings and knowledge indexing; hand off installation instructions and remaining blocked tasks honestly.
3. `configure_voice`: collect inbound/outbound direction, languages, business goal, approved opening, needed data, transfer policy/hours; propose supported voice and available model with current rate; draft scripts separately by direction; validate; ask whether an existing business number/account will be used or a new number is wanted; secure connection handoff; current funds/number routing/provider readiness; approval; activate; approved browser/phone test; report measured result. Credentials and KYC are human steps.
4. `connect_service`: identify provider, show current verified prerequisite guide, create expiring credential-entry handoff, pause run, backend validates credentials with least-invasive provider request, stores encrypted secret and returns only masked readiness, resumes from waiting step. Invalid/revoked credentials yield repair instructions, not guessed success.
5. `edit_existing_assistant`: read saved revision and optional approved unsaved buffer; create patch draft; validate impact; preview diff; apply with optimistic version guard; show rollback-to-previous-config where possible. Existing live bot remains on last active revision until apply.
6. `diagnose_and_repair`: inspect scoped diagnostics and configuration; show evidence and proposed fix; execute only authorized bounded repair; verify result; escalate external/unavailable issues rather than looping indefinitely.
7. `knowledge_refresh`: crawl/upload preview; source-level diff, removed/stale content and unavailable pages; reindex draft revision; verify index before active pointer change.
8. `launch_or_install`: check eligibility, known installation target and resources; show exact embed/plugin steps; customer grants CMS access separately if supported; verify reachable placement/config. “Code generated” and “installed” are different outcomes.
9. `whatsapp_setup_and_reply`: prepare settings and supported connection path; secure secret handoff; verify number/subscription readiness; approve actual test/send, respecting service window; confirm provider receipt.
10. `schedule_and_campaign`: target audience/individual, purpose, consent/DNC, time and timezone; draft; verify voice capacity/current rates; review downstream calls/messages; schedule; report status and allow pause/cancel with in-flight limits.
11. `team_billing_sites`: dedicated typed workflow per invite/role change/purchase/publish/domain action, restricted role, exact reviewed impact and provider handoff where necessary; no omnibus administrator tool.

**Structured question cards**

Use schema-rendered URL/text/textarea/select/radio/upload/date-time cards with field labels, validation, helpful default and “Skip for now” only for optional fields. Do not let the model emit executable JSX/HTML. Server owns schemas and validates responses with question ID/version so a late answer cannot resume the wrong step. Examples: website URL; primary goal choices (answer questions, collect leads, book meetings); supported languages; voice yes/no/later; existing number vs new number; a credential form button. Source extraction should reduce repeated questions, but guessed facts must be visibly marked.

Website onboarding question/branch detail:

- First card: `How should I learn about your business?` with Website, Upload PDF/TXT, Describe business. URL is optional when another source is chosen. If source reading fails, retain the draft and explain exact failed pages; offer retry, fewer pages, upload or manual details. Never bypass login/paywalls/CAPTCHA. For JavaScript-only sites, offer secure rendering if implemented or ask for an export; do not claim a complete crawl from an empty HTML response.
- Then collect only missing requirements: business name to confirm when inferred; target audience; primary goal; supported language(s); whether to collect leads, which minimum fields, and consent wording. Contact capture must use the business's chosen consent/purpose instead of automatically copying every website contact into lead settings.
- Brand card shows proposed palette and logo plus source URLs; label observed CSS/logo evidence, inferred theme choices and user-confirmed fields separately. Deterministic validation must enforce WCAG text contrast (4.5:1 for normal text, 3:1 for qualifying large text) rather than ask the model whether colors look readable. If a brand accent fails, preserve it decoratively and derive an accessible text/button shade with an explanation. [WCAG contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- Before apply, show named preview variants and actual widget simulation, including fallback question, handoff, lead validation and all reachable flow branches. A graph that validates structurally still needs runtime scenarios to establish useful behavior.
- After the chat draft is ready, ask `Would you like phone assistance too?` with Yes/No/Later. Yes opens incoming/outgoing/both, languages, goal, opening, transfer settings, necessary function integrations and phone number connection cards. Unsupported/missing credentials leave `chat ready; voice waiting for connection` with a resume link; they never produce a false `fully configured` result.
- Voice readiness requires supported configured model and voice, direction-specific script, valid fields and functions, actual validated phone account/number route for the chosen direction, current entitlement/wallet checks, callback reachability where required, and provider-side status. Automated local tests use mocked AI, STT, TTS, browser audio and telephony, with external network access prevented; those tests prove workflow behavior but not a real number's ability to receive/place calls. An approved real call remains a separately reported validation step.

**Credentials and provider guidance**

Guides are maintained product content with provider, prerequisite list, last verified date, official documentation links and step-by-step console paths. The agent retrieves the relevant guide and may acknowledge UI changes. Do not bake unverified console paths into its prompt. Secure form posts credentials directly to a backend secret store. Return an opaque connection ID, secret-present flags and validation status to the workflow. Secret values never enter model context, transcript, trace, event payload or analytics. For MFA/CAPTCHA/KYC/provider review, state who must act and resume only after real server-side verification. Being able to explain an external console does not imply access to it.

### Gaps

- Exact responsive dimensions and avatar placement require browser testing with the builder, voice editors, live-chat layout and deployment screens. This is an architecture proposal, not completed UI validation.
- Provider console click paths should be verified when each integration guide is written; this research did not inspect customer accounts or verify all current consoles.
- There is no basis to promise that any arbitrary business website can be crawled/rendered or that any external account can be connected without its owner's actions.

## 3. What implementation sequence and acceptance criteria make this commercially reviewable?

### Takeaway

Deliver complete vertical workflows behind a feature flag, starting with read-only page help and then website-to-draft-to-verified-apply. Expand module coverage only after correctness, recovery, permissions and UI behavior are tested; track unfinished parity explicitly.

### Cited Findings

- Backend tests already provide an isolated SQLite path, disable the scheduler and real AI service keys, use `LOCAL_DEV=false`, and supply signed-up workspace users. Build on those fixtures for offline agent tests. [test fixtures](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/tests/conftest.py:1)
- Existing suites cover workspace isolation, security, voice reliability, voice functions/scheduling, WhatsApp, payments and sites; changes should retain the relevant suites and add agent-specific regression coverage. [tests](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/tests)
- The project requires approval before commit/push, production, paid or outward-facing actions and prohibits port 8000. Local services use 3000 and 8001. [AGENTS.md](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/AGENTS.md:8)

### Inferences

**Suggested phases**

1. Inventory and contracts: machine-readable capability matrix; route contexts; schemas; state model; service boundaries; security/side-effect classification; architecture decisions. Confirm ambiguous product behavior without silently changing existing entitlement rules.
2. Read-only shell: persistent panel/launcher/avatar settings, typed context, scoped sessions, streamed answers, page-help workflow, accessible forms/status. No hidden autonomous writes.
3. Durable runs and drafts: database tables/migrations, typed tool adapters, checkpoints, approval records, event replay, idempotency, conflict checks, audit redaction, secure credential handoffs. Run tests for multi-worker/restart behavior before product mutations.
4. Complete website onboarding: crawl and brand extraction; provenance; knowledge draft/index state; design/behavior/flow validation and simulation; cohesive review and atomic apply/activation; no-website path; measured verification.
5. Voice and integrations: disabled voice drafts; direction/language/model/rate selection; secure connection flow; number purchase/routing approval; test fixtures first, owner-approved real trial later.
6. Remaining parity: WhatsApp, live chat, schedule, campaigns, contacts, analytics, questions, email, sites, team, billing, account. Each workflow must have review, audit, side-effect checks and tests before enabled.
7. Release: production-sized concurrency and recovery staging checks; observability; operational runbook; migration/backfill and rollback plan; restricted rollout; explicit owner approval to deploy.

**Definition of done / concrete tests**

- Route awareness: Design vs Knowledge internal tabs resolve different help; selected flow node/call is registered correctly; refresh/deep link restores context; two browser tabs do not overwrite one another's context.
- Target integrity: start work on assistant A, navigate to B, then approve; A's proposal cannot silently mutate B. Workspace switch during streaming/approval never leaks data; stale approval is refused after resource/version/role changes.
- Unsaved edits: human changes same field after proposal; apply returns conflict and shows merge choices. Separate field changes can be rebased only after explicit safe policy and new diff.
- Permissions: owner/admin/agent and removed-member matrix; guessed IDs in context/tool args; run/event/draft/attachment/secret handoff access; enforce isolation with local bypass disabled and meaningful Postgres tests for concurrency semantics.
- Autonomy boundaries: low-risk authorized draft work proceeds; send/publish/purchase/number routing/voice activation/erase/role change requires reviewed payload and execution-time permissions. Hidden downstream TTS, email or calls are captured by side-effect classification.
- Source safety: test malicious website instructions, private URLs/redirects/DNS rebinding, oversized pages, malicious SVG/logo, blocked site, no readable content and inaccurate brand confidence. Crawl content never becomes system instructions or changes tool permissions.
- Knowledge correctness: partial crawl/index failures produce partial results and retry choices; restart after source save but before indexing resumes safely; active revision remains usable; reported page/chunk numbers come from completed records.
- Flow correctness: missing start, invalid node type, broken edges, unreachable nodes, invalid input fields, infinite loop, unauthorized HTTP destinations and fabricated functions cannot be applied. Valid graph runs in widget preview with deterministic fakes.
- Credentials: plaintext entered via secure form never appears in prompts, tool args, run events, logs, replay store, analytics, error messages or cached page context. Expired/replayed handoff, wrong workspace and revoked credential are rejected.
- Recovery: browser disconnect and server restart resume same run; duplicate stream delivery deduplicates; two workers cannot apply same step twice; stale worker cannot write after lease loss; external unknown outcome reconciles before retry. User receives actual status, not synthetic completion.
- UI: dock and floating mode at desktop/tablet/mobile, keyboard open/close and resize controls, mobile focus trap/restoration, status live region, reduced motion, avatar asset failure fallback, no duplicate panel instances, composer usable under long errors and network loss.
- Voice: simulated model/STT/TTS and telephony verify inbound/outbound settings, missing credentials, missing number, insufficient credits, late provider result and disabled-run paths. Real browser speech/call/provider test needs separately approved budget and destination; no “end to end tested” claim until actual authorized measurements exist.
- Regression: existing manual builder, widget, WhatsApp/voice/live-chat functions still operate through shared services. Run relevant pytest tests and dashboard TypeScript check plus focused browser checks; no invented metrics or unexplained skipped failures.
- Final delivery includes changed-file summary, migration notes, capability coverage report with remaining gaps, measured tests, known limitations and exact owner actions still needed. Do not mark the entire agent complete when only chat streaming and a few mock tools exist.

### Gaps

- Success rates, latency, per-run cost and production capacity must be measured after implementation against a versioned representative evaluation set. No numerical production performance claim is warranted from source review.
- Safe migration strategy for revisioned bot config, source/index persistence, leases and unique constraints needs explicit design and staging rehearsal; current startup nullable-column addition alone is insufficient for all such guarantees.
