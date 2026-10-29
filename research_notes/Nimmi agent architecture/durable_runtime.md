# Durable agent execution and live progress

Research date: 29 October 2026. The cited facts below come from official documentation inspected during this task. Architecture choices, schemas, limits, and implementation tests are recommendations for Nimmi, not measurements of a running implementation. No application code, database, production settings, or paid services were changed or exercised.

## Which execution architecture best fits Nimmi now?

### Takeaway

Use one self-hosted LangGraph StateGraph orchestrator, Postgres checkpoint storage, a dedicated bounded worker, and Nimmi's existing FastAPI service layer. Add a thin durable command/job ledger and a separately versioned UI event stream; do not add Temporal, PydanticAI, a second orchestration engine, or a fleet of independent agents to the initial build.

### Cited Findings

- LangGraph checkpointers save graph state by thread and step; persistent checkpointers support human input and recovery. Postgres and async Postgres implementations are available separately. In-memory persistence disappears when the process stops. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers).
- LangGraph interrupts persist a pause and accept a later resume value. The interrupted node begins again on resume, so effects before that point can repeat. [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
- LangGraph's sync durability mode persists state before the next step; async allows persistence alongside execution; exit persists at graph exit. [Durability reference](https://reference.langchain.com/python/langgraph/types/Durability).
- Temporal recovers workflow execution through event-history replay and runs external work in activities. Activities can execute more than once if their completion was not reported; downstream idempotency remains the application's responsibility. [Workflow execution](https://docs.temporal.io/workflow-execution), [Activity definition](https://docs.temporal.io/activity-definition).
- Pydantic AI distinguishes saving settled steps from keeping an in-flight run alive across a failure. Its current durable execution integration supports multiple engines and permits one engine per agent. [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/).
- Nimmi currently runs four Gunicorn API processes. Its SQLAlchemy defaults allow two retained plus one overflow connection per process, and its repository comments describe a 15-client session pool budget. The dashboard authenticates using bearer tokens and the X-Workspace header. These are repository findings, not a live service audit. [Deployment config](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/nixpacks.toml), [Database configuration](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/database.py), [Dashboard API client](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/dashboard/src/lib/api.ts).
- Supabase's shared transaction pooler does not support prepared statements or query pipelining; session state is not preserved between transactions. This includes session advisory locks and LISTEN/NOTIFY. Driver configuration and connection mode must be checked together. [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres). Psycopg's prepare_threshold=None disables automatic preparation. [Psycopg prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).

### Inferences

**Comparison and decision:**

| Choice | Strength | Nimmi-specific cost or limitation | Recommendation |
|---|---|---|---|
| Small custom state machine + Postgres | Reuses current SQLAlchemy, minimal dependencies, clear finite workflows | Nimmi must implement and maintain checkpoint compatibility, interrupts, branching, replay, repair, and execution history | Suitable for a tiny fixed wizard; too much custom runtime engineering for the proposed broad agent |
| LangGraph + Postgres | Explicit state/branches, resumable human input, graph checkpoints, model-provider independence | Requires a dispatcher, policy gateway, durable side-effect ledger, and careful driver/pool management | Initial choice; use the library inside Nimmi rather than adopting an unrelated hosted control plane |
| Temporal | Strong durable job execution, timers, activity histories, operational visibility | Additional service or paid managed dependency; workflow determinism/versioning and activity integration training; still needs idempotent tools | Reconsider when cross-service business automation becomes a major operating workload, not merely because an agent exists |
| Pydantic AI plus a durable engine | Useful typed agent interface and engine integrations | Another model/agent abstraction plus another runtime to choose and operate | Alternative implementation direction, not an extra layer on top of the chosen graph |

Recommended component boundary:

1. **Next.js agent UI** sends a command with user message and a bounded, typed page-context snapshot.
2. **FastAPI control API** resolves actor and workspace, validates the request, inserts a run/command, and immediately returns its identifier.
3. **Dedicated agent worker** claims runnable work, executes the LangGraph workflow, checkpoints, and yields at input/approval/credential waits. It does not occupy an API response coroutine for the life of a run.
4. **Model adapter** performs bounded interpretation and generation using a provider that passes Nimmi's actual evals; model output has a validated schema. Do not hard-code a purported “best” model without measurements.
5. **Capability/policy gateway** checks the concrete proposed operation before calling the same domain service used by the manual UI and by the MCP adapter.
6. **Postgres** holds graph checkpoints, durable commands, approved plans, tool-call outcomes, and user-visible events. Redis, if enabled later, only wakes consumers; it is not the source of truth.
7. **FastAPI progress endpoint** streams the persisted event ledger to the browser independently of the graph process.

Graph structure: `resolve_context -> triage -> select_workflow -> gather_missing_inputs -> plan -> readiness_check -> stage_changes -> validate -> request_approval_when_required -> execute -> verify -> summarize`. A workflow may loop through several bounded input cards. Specialist work is functions or subgraphs with narrow tools, not autonomous agents all granted every module. Run independent read-only analysis in parallel only after quota accounting and cancellation are safe; serialize writes to a single bot/draft.

The initial stack is one orchestrator. Do not run both LangGraph and Temporal as competing sources of workflow state. MCP defines tool access and interoperability; it does not replace the workflow runtime, authorization policy, or database.

The Nimmi action ledger is not a second workflow engine: LangGraph owns control flow and checkpoints; the ledger owns authorization evidence, idempotency, external outcomes, and audit. The dispatcher only queues/claims/resumes runs. Keep those responsibilities separate.

Practical first increment: ship the panel shell, avatar controls, explicit page-context registry, read-only route-aware explanations, connection/readiness status, and streamed answers behind a feature flag. Expose only allowlisted read tools at this stage, with auth, redaction, bounded generation, and context tests. Use this to measure answer usefulness and context accuracy before adding staged bot-creation workflows. Do not pretend a read-only assistant completes the full scope; it is the first validated milestone toward all modules.

**Nimmi database deployment requirement:** the current API connection maximum is 4 × (2 + 1) = 12 before any new worker/checkpointer connection. This is arithmetic from configuration, not measured consumption. Count SQLAlchemy pools, the checkpoint driver's separate psycopg pool, deploy overlap, migrations, maintenance, and spare capacity. Never instantiate a new checkpoint pool inside each request or each of four web processes. Start with one dedicated worker and explicit low concurrency; choose and test a total allocation before production enablement. Do not casually switch to transaction pooling: the selected saver version might use pipelining, and prepared statements are only one compatibility issue. Use bounded pooled connections returned after DB operations; do not hold a DB transaction or a checked-out connection while a model answers or a person enters credentials.

Pin and verify supported releases of LangGraph, langgraph-checkpoint-postgres, psycopg, and Python 3.12 in a local compatibility spike before writing application integration. Current docs show changing streaming APIs, so the report should specify behavior and contracts, not untested copy-paste library calls. Explicit versioned migration scripts must create required tables/indexes/constraints; nullable-column startup repair is insufficient for these invariants. Production application remains a separate approval.

### Gaps

- This task did not install or benchmark a specific package combination or test psycopg against the owner's exact Supabase pooler. The implementation must validate it.
- No concurrency target, usage budget, availability SLO, or expected tenant count was supplied. Queue/concurrency limits should begin conservatively and be tuned from measurements.
- No evidence establishes that a specific model is best for Nimmi's triage, planning, and tool use. A small evaluation set should determine the model and fallback choices.

## How must runs survive interruption without duplicate or unauthorized effects?

### Takeaway

Persist the user's intent, exact target, workflow version, approved plan, and operation identity. Checkpointing prevents losing graph progress; idempotent domain operations and reconciliation prevent repeating real-world effects. Treat uncertain external outcomes as a distinct state.

### Cited Findings

- Postgres SKIP LOCKED is intended for queue-like consumers, where avoiding row-lock contention is useful; it does not provide a generally consistent view for arbitrary queries. [PostgreSQL SELECT locking](https://www.postgresql.org/docs/current/sql-select.html).
- The documented Temporal crash-after-external-success case illustrates why execution cannot guarantee a remote action happens once: idempotency must be enforced by the called service. [Temporal activity definition](https://docs.temporal.io/activity-definition).
- LangGraph resume re-executes node code, and its guidance recommends idempotent pre-interrupt operations or separate side-effect nodes. [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
- LangGraph offers separate checkpoint state and cross-thread stores; these serve different scopes. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

### Inferences

**Proposed persisted state contract (application design):**

```text
RunStatus = queued | running | waiting_input | waiting_credentials |
            waiting_approval | retry_wait | paused | reconciling |
            cancelling | cancelled | succeeded | completed_with_warnings | failed

Run = id, workspace_id, initiating_actor_id, conversation_id,
      workflow_key, workflow_version, schema_version, model_policy_version,
      bound_target_ids, target_versions, initial_context_id,
      status, accepted_checkpoint_id, lease_owner, lease_epoch, lease_expires_at,
      cancel_requested_at, spend_budget, spend_reserved, spend_used,
      created_at, updated_at, expires_at
```

Workflow transitions must be code-controlled and validated. A model can propose an intent, form, tool call, or step; it cannot set `succeeded`, skip prerequisites, or grant permission. Completion is derived from verified tool results.

**Conceptual tables:**

| Record | Purpose and invariants |
|---|---|
| agent_conversations / agent_messages | Actor/workspace scoped thread and bounded messages; role/visibility policy explicit |
| agent_runs / agent_commands | Versioned execution and durable start/resume/cancel request; unique client command ID prevents repeated clicks from duplicating runs |
| graph checkpoint tables | Use the selected library's supported schema and serializer; namespaced to workspace/run and controlled by server ownership checks |
| agent_tool_calls | Stable logical operation ID; tool/schema version; redacted normalized input and hash; planned/running/succeeded/failed/unknown; result reference; idempotency key; timestamps and attempts |
| agent_approvals | Exact action or plan hash, actor, scope, target/version, expiry, decision; one-use consumption is atomic |
| agent_artifacts / draft revisions | Website facts with provenance, proposed bot config, branding, flow, and voice script; before/after versions and validation reports |
| agent_events | Append-only sequence per run, semantic progress, cards, result references; unique `(run_id, sequence)` |
| agent_outbox | Event/job publication committed with the underlying mutation; dispatch may repeat but consumers deduplicate |
| agent_connection_requests | Provider, required capability, status, opaque credential reference; no secret value in graph state or messages |

Every row is tenant-bound. A globally unique run ID is not authorization. Check actor access when listing, reading, subscribing, approving, resuming, and executing; do not let any member of a workspace automatically view another member's private conversation. Roles may permit designated shared runs, but sharing must be explicit.

**Operation correctness:**

- Derive a logical operation key from workspace + run + stable workflow step + target + approved input revision. Keep the same key on retry; a changed payload requires a new operation and new approval where required.
- For local DB changes, put the domain mutation, idempotency result, audit record, and outbox entry in one transaction. If the graph checkpoint fails afterwards, replay reads the existing operation outcome rather than changing the bot again.
- For external calls, persist intent before dispatch, pass an idempotency key if the provider supports it, then persist the observed result. If a timeout occurs after dispatch, use `unknown` and reconcile via the provider's operation/status API or a well-defined lookup before retrying. If neither exists, stop for human review instead of risking duplicate calls, messages, purchases, or bookings.
- Claim work atomically using short transactions and an expiring lease. Increment a fencing epoch on takeover. Check the epoch before every guarded write and before scheduling the next effect. A lease alone does not prevent a stalled old worker from later completing an external request; the operation ledger, provider idempotency, and reconciliation handle that boundary.
- Do not assume the stock graph checkpointer itself enforces application leases. Require a tested fencing integration: stale attempts must not advance the accepted run checkpoint or overwrite the current run state. One viable implementation uses attempt-scoped checkpoint namespaces and a compare-and-swap accepted-checkpoint pointer; resumes load the last accepted checkpoint. The chosen implementation must prove worker-takeover safety in fault tests.
- Keep approvals in a separate node from execution. Save the immutable concrete proposal before asking. Resume rechecks current membership, feature/plan eligibility, budget, target revision, and approval hash. A changed bot or edited plan invalidates approval. Never infer permission from old conversational text alone.
- Use optimistic concurrency for bot/config updates. If a person edits the builder while the agent is preparing changes, show the conflict and a refreshed diff rather than silently overwriting.
- Separate drafting from publication, number purchase, campaigns, outbound calls/messages, destructive deletes, and credentials. “Create my assistant” can authorize a bounded draft workflow; it does not authorize every later paid external action.
- Configuration is not automatically free of effects. Repository research from the companion agent found voice configuration saves can prepare opening TTS. Tool classification must include nested synthesis, webhook activity, or notification work. Staging must suppress these effects or obtain the required budget/permission before invoking them.

**Retry policy by failure:** reads may retry transient transport/rate-limit errors within budget; model calls may retry transient failures but reserve/record possible spend; schema failures get a small bounded repair budget; missing credentials/403/plan limits/invalid URL pause for correction; revision conflicts refresh and replan; external uncertain outcomes reconcile; definitive business rejections are not transient errors. Cap elapsed time, attempts, tokens, pages, bytes, and total spend. Retry-After and jittered backoff reduce bursts. Exhaustion yields a precise recoverable status with retained artifacts.

**Cancellation and partial success:** Stop means stop scheduling new work, request cooperative cancellation, and reconcile in-flight external effects. It cannot unsend a message or reverse a phone call. Show completed changes and remaining work. Compensation is an explicitly supported operation with its own permission/idempotency record; do not promise universal rollback. Draft revisions can be discarded; configuration rollback is conditional on current version; outside effects need documented remedies. Closing the sidebar does not cancel a run; disabling the avatar only hides the character. A separate Stop button controls execution.

**Page-context race:** Bind each run/action to server-validated target IDs and versions. New navigation updates the assistance context but never silently retargets an active mutation. If a user says “change this one” after switching pages, capture a new context revision and explicitly resolve the intended entity. Workspace switching aborts the current frontend stream, clears visible old workspace data, and does not migrate a run between tenants. Server runs remain under their original workspace and authorization.

### Gaps

- Existing domain APIs need a capability-by-capability inventory of idempotency, version checks, paid nested effects, and compensations. They cannot all be safely auto-wrapped as generic HTTP tools.
- Fencing integration with the selected graph/checkpointer version requires an implementation spike; this is an acceptance requirement, not a verified library feature.

## How should the UI receive real-time progress, and how is commercial readiness proven?

### Takeaway

Use authenticated fetch streaming with SSE framing for Nimmi's application event feed, durable event sequence numbers, replay, and periodic authoritative snapshots. Display actual stages, input forms, approvals, and verified outcomes; measure quality and reliability before publishing performance claims.

### Cited Findings

- SSE is a one-way server-to-browser event stream with event names, IDs, reconnect hints, and heartbeat comments. [MDN SSE](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).
- Native EventSource accepts a URL and an options dictionary whose supported option is withCredentials; it does not expose arbitrary request-header options. [EventSource constructor](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource).
- Current LangGraph documentation recommends a typed event streaming API for new applications, introduced in v1.2. [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming).
- OpenTelemetry advises minimizing sensitive telemetry and applying filtering/redaction; collectors provide additional control over exported data. [Handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/). Its GenAI conventions moved to a dedicated repository, so pin the adopted convention version rather than assuming old URLs define a permanent schema. [GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai).

### Inferences

**Application endpoints, distinct from MCP protocol transport:**

```text
POST /api/agent/conversations
POST /api/agent/runs                      -> 202 {run_id, status}
GET  /api/agent/runs/{id}                 -> authoritative state/cards/artifacts
GET  /api/agent/runs/{id}/events?after=N   -> text/event-stream via fetch + auth headers
POST /api/agent/runs/{id}/input           -> typed form response + command id
POST /api/agent/runs/{id}/approvals/{aid}  -> concrete decision + command id
POST /api/agent/runs/{id}/cancel          -> idempotent cancellation request
POST /api/agent/connections/{id}/submit  -> secret goes directly to secure backend
```

These are proposed Nimmi APIs. The GET event feed is not a claim about MCP's current Streamable HTTP transport. MCP research found the current spec has different transport/session behavior; keep its adapter contract separate.

Existing auth uses bearer and X-Workspace headers, so fetch-based streaming is a natural fit. Use a vetted SSE parser, AbortController, explicit reconnect/backoff, refreshed authentication, and last processed `sequence`. Do not place JWTs in URLs. An SSE connection must release database sessions between bounded reads and never reserve a connection for its whole lifetime. Poll the durable log in bounded batches or use optional Redis wakeups, with polling recovery for missed notifications. Authorize every run lookup and reconnect; use short maximum stream lifetimes or explicit revocation signals so removing workspace membership takes effect during long-lived streams. Slow subscribers must not block the worker.

Example persisted event:

```json
{
  "schema_version": 1,
  "run_id": "run_...",
  "sequence": 42,
  "type": "input.required",
  "step_id": "voice_preferences",
  "context_revision": 7,
  "payload": {
    "card_id": "voice_preferences_1",
    "title": "Add phone calls to this assistant?",
    "fields": [{"name": "enable_voice", "type": "choice", "options": ["Yes", "Later"]}]
  }
}
```

Event family: `run.queued`, `run.started`, `context.updated`, `step.started`, `step.progress`, `input.required`, `connection.required`, `approval.required`, `artifact.ready`, `tool.succeeded`, `tool.failed`, `run.reconciling`, `run.completed`, `run.cancelled`. Keep secrets and raw tool traces out of payloads. Stream answer deltas for responsiveness but persist semantic transitions and message snapshots; a reconnect must recover from the latest snapshot even if ephemeral tokens are gone. Never show a made-up percentage when the total amount of work is unknown. The UI describes tasks such as “Reading website pages” and “Checking the draft,” not private chain-of-thought.

One stream per open agent panel is sufficient. De-duplicate events by run and sequence; reconnect to any API process; use snapshot resync when cursor retention has expired. Avoid directly exposing LangGraph's complete graph/debug stream, which can leak tool arguments, internal prompts, or provider-specific structures. Nimmi's event schema isolates the UI from framework upgrades.

Text assistance and tool activity only need SSE plus POST commands. If conversational audio with the sidebar is added later, design it as a separate optional media channel with microphone consent, transport choice, and recording policy; it is not the existing customer's PSTN voice-agent configuration workflow. Do not disturb the live phone pipeline to build the dashboard assistant.

**Observability and budgets:** record run, step, model attempt, provider request and tool operation IDs; timing, queue wait, token counts if returned, estimated/actual cost provenance, retries, policy denials, reconciliation, and result verification. Correlate with existing backend traces. Redact headers, credentials, customer documents, personal details, and entire URLs with secret queries before export. Store only the necessary sanitized audit summary; raw prompts/traces require a separate controlled policy. Content-free operational telemetry is the default.

**Required tests before release (proposed gates, not already achieved):**

1. Happy path: URL -> verified website facts -> editable brand/name -> valid knowledge retrieval -> validated flow -> preview -> optional voice draft -> readiness report. Never fabricate unsupported website facts.
2. Correct context: every supported screen route, nested tab, selected assistant, unsaved edits, navigation mid-run, explicit target override, two tabs, and workspace switch.
3. Authorization: owner/admin/agent restrictions, another tenant's IDs, revoked membership mid-run, event-stream visibility, stale approval, expired approval, and changed target version.
4. Reliability: kill worker before mutation, after mutation/before checkpoint, while awaiting input, while streaming, and after external response loss. Simultaneous worker claims, lease expiry and stale worker writes, repeated form submissions, browser reconnect to another API worker. No duplicate local effects; uncertain remote outcomes visible and reconciled.
5. Security: injected website content, redirect to private address, unsafe tools, forged MCP output, accidentally pasted credentials, oversized payloads, and secret leakage in UI/logs/events/model payloads.
6. Side effects: paid opening synthesis on voice save, live publish, message/call/book/purchase actions all honor approved scope and budgets. Do not run real paid calls in automated tests; separate live-provider validation requires approval.
7. UX/accessibility: keyboard and focus order, reduced motion/avatar off, panel resize, desktop/mobile, slow network, suspended laptop, retry/wait/cancel states, truthful results and accessible contrast.
8. Performance/load: measure time to first visible acknowledgment, first useful model response, individual tool latency, queue wait, reconnect recovery, end-to-end success by workflow, cost/run, DB connections, and voice-call latency while the agent is busy. Report p50/p95 and failure counts from a specified dataset; select release thresholds before testing. No fabricated “instant” or “100%” claims.

Rollout: feature flag off by default -> local fake-provider tests -> staging/internal accounts with approved paid probes -> small tenant cohort -> wider rollout only after measured gates. Provide global disable, per-tenant budget, concurrency controls, and a read-only fallback when tools are unavailable. A failed capability must be shown honestly with a guided manual path.

### Gaps

- No UI, end-to-end run, external provider, model evaluation, latency, or load test was executed in this research task.
- SSE proxy buffering/timeouts on the exact Railway path must be tested; documentation of SSE alone cannot establish its production behavior.
