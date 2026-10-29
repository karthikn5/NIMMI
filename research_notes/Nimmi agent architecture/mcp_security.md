# MCP and secure agent tooling for Nimmi

Research checked 29 October 2026. Facts below cite primary sources or inspected repository files. Inferences are proposed Nimmi design choices, not claims that the feature already exists. Source word budgets are respected through short factual summaries; contracts and Nimmi designs are original recommendations.

## What should MCP provide, and which protocol version applies?

### Takeaway

Use MCP for typed capability discovery and invocation. Keep Nimmi's workflow state, approvals, run history, retries, and customer identity in its application runtime. Target the verified 2026-07-28 release and pin a compatible SDK; older 2025 examples have materially different lifecycle and transport behavior.

### Cited Findings

- The official release dated July 28, 2026 makes MCP requests self-contained and removes the `initialize`/`initialized` handshake and protocol session header. `server/discover` is optional. The release moves Tasks into an extension and describes SDK updates. This contradicts third-party summaries calling discovery mandatory; use the official release. [MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- MCP distinguishes hosts, clients, and servers. Servers expose tools, resources, and prompts; it supplies a connection protocol, not an implementation of a business workflow engine. Extensions require explicit support. The overview has a stale phrase about extensions being negotiated “during initialization”; resolve implementation details against the versioned normative pages and SDK tests, rather than copying that phrase. [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28)
- Current Streamable HTTP uses POST to one endpoint, returning JSON or request-scoped SSE. It removes the old GET stream endpoint, protocol sessions, and transport replay via `Last-Event-ID`; `subscriptions/listen` supplies notification streams. Origin validation is required when Origin is present; invalid Origin is rejected. Version/method/name headers mirror body metadata and must match. [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- Tasks is now an opt-in extension, not the old experimental core API. It returns durable handles, supports `tasks/get`, `tasks/update`, and `tasks/cancel`, and allows reconnection. Cancellation is cooperative. Capability negotiation and client interoperability still need testing; protocol support does not implement reliable application side effects. [Tasks overview](https://modelcontextprotocol.io/extensions/tasks/overview), [official Tasks repository](https://github.com/modelcontextprotocol/ext-tasks)
- MCP tool definitions include input schemas and optional output schemas. Structured results must satisfy a declared output schema. Tool annotations are not a security authority when they originate from untrusted servers. Catalogs can depend on per-request authorization and should be ordered deterministically. [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- Resources are URI-identified context supplied under application control. They can vary with the request's authorization. [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- Anthropic distinguishes predefined workflows from agents that dynamically choose execution steps; its recommendation is to start simple and add complexity when measured task needs justify it. The 2024 article explicitly warns that its tooling landscape has evolved. [Building effective agents](https://www.anthropic.com/research/building-effective-agents)

### Inferences

Recommended logical topology:

`Next.js assistant UI -> authenticated Agent API -> durable workflow runner + model adapter -> policy-enforced tool registry -> MCP adapter/domain services -> existing Nimmi modules`

The Nimmi backend is the MCP host/client. The browser is a first-party product UI, not a general MCP client carrying provider credentials. One logical Nimmi MCP server can expose domain namespaces initially; there is no requirement to deploy a separate server per module. Keep the server in the existing backend package or a private service until independent scaling is warranted. Existing routes and MCP tool handlers should call the same service functions, preserving one implementation of permissions, plan checks, and invariants. Do not wrap arbitrary endpoints in a model-accessible `request(method,url,body)` function.

Use a single conversational supervisor plus workflow-specific capability subsets. The supervisor can classify requests and generate plans, but only code can select an authorized execution path. Parallel specialist computations may draft branding and knowledge summaries; only the central workflow executor commits shared changes. Avoid unrestricted swarms of agents independently changing one bot.

MCP assets:

- **Tools:** concrete operations such as `nimmi.bots.create_draft`, `nimmi.knowledge.import_status`, `nimmi.design.propose`, `nimmi.voice.configure_draft`, `nimmi.connections.check`, `nimmi.analytics.query_summary`.
- **Resources:** validated context snapshots, module help, schema versions, current bot configuration, workflow state, and a safe capability catalog. Example URI: `nimmi://assistants/{id}/summary`. URI parameters never bypass ownership checks.
- **Prompts:** optional named user-invoked starter recipes such as “Create an assistant from my website.” Prompts are not executable workflow definitions or an authorization mechanism.
- **Workflows:** versioned application definitions declaring states, required inputs, tool allowlists, validators, retry rules, approval boundaries, success evidence, and compensation rules.
- **Tasks extension:** an interoperability adapter over Nimmi's existing durable run records when a client supports it. The native product can use its own run ID and SSE/polling contracts regardless of extension adoption.

Important transport distinction: a resumable **Nimmi product** endpoint such as `GET /api/agent/runs/{id}/events?after=...` is valid as an application design. It is not the MCP 2026-07-28 endpoint and must not be represented as protocol-level MCP replay. Disconnecting the product UI need not cancel the durable run. Explicit Pause/Cancel buttons operate on the run, which then applies safe cancellation at workflow boundaries.

Pin exact tested MCP SDK/package versions and extension revisions in lockfiles. A compatibility test must prove discovery, typed tools, errors, authorization, and elicitation. If a required SDK/client supports only 2025-11-25, document a compatibility adapter rather than falsely claiming 2026 support.

### Gaps

- No SDK package was installed or executed; exact package pins must be selected during implementation and verified against the official SDK releases.
- One overview phrase is inconsistent with the new lifecycle. The versioned transport/release and actual interoperability tests should govern implementation.
- This research does not prove any current Nimmi module is already MCP-compatible.

## How should triage, the MCP checker, and approval work?

### Takeaway

Triage decides what the user is asking; a deterministic policy layer decides what the request may do. The “MCP checker” should be a real readiness and authorization service that runs before execution, not an LLM that says a tool looks safe.

### Cited Findings

- OWASP recommends permission/context checks on tool calls, per-tool parameter validation, least privilege, and monitoring that excludes credentials and unnecessary sensitive content. Model-based guardrails supplement deterministic controls. [Prompt injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- Nimmi already represents identity with `AuthContext(user_id, owner_id, role)`, resolves `X-Workspace` through active membership, and has owner/manager guards. `get_owned_bot` contains a `local_dev()` bypass, so security tests must run with local development shortcuts disabled. [auth.py](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/auth.py)
- Existing plan enforcement defines free/paid feature access and remaining assistant/site slots. These are business restrictions that agent actions must reuse. [plans.py](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/plans.py)

### Inferences

Triage structured output should be something like:

```json
{
  "intent": "create_assistant",
  "workflow": "website_to_assistant",
  "workflow_version": 1,
  "target": {"kind": "new_assistant"},
  "confidence": "high",
  "missing_inputs": ["website_url"],
  "mode": "draft"
}
```

Supported intent families: explain current screen; answer product/setup questions; inspect a selected resource; create/configure; diagnose; analyze; install/publish; send/dial; manage access/billing. Uncertainty produces one small input card. Read-only help should not trigger a costly multi-step workflow. A model's target IDs and intent labels are untrusted suggestions until validated.

The checker runs at catalog discovery, plan validation, and **again immediately before every effect**:

1. Verify tool identity against a pinned registry and approved server identity; verify supported protocol/schema versions and any changed schema hash.
2. Resolve current actor and workspace on the server; validate membership and role. Verify each bot/contact/site/run belongs to that workspace. Never trust a workspace ID from the model or route context as authorization.
3. Enforce operation scopes, plan features, resource quotas, model/run budgets, and rate limits using current state.
4. Validate tool arguments with a strict schema and domain invariants; prevent arbitrary property updates and URL destinations.
5. Verify credentials by opaque reference, connection state, necessary provider permissions, and expiry. Do not send secret values to the checker model or assistant.
6. Check expected resource revision and workflow state. If the user manually edited the resource, generate a fresh proposal/diff instead of overwriting it.
7. Evaluate risk and exact authorization. Bind approval to actor, workspace, tool and schema version, canonical arguments hash, target revisions, cost/recipient/destination summary, and expiry.
8. Claim idempotency/effect record transactionally; refuse stale worker fencing tokens; execute a domain operation with the same checks as manual UI.
9. Validate and redact result against output schema; record safe audit evidence; verify postconditions before reporting success.

Checker states: `ready`, `needs_input`, `needs_connection`, `needs_approval`, `plan_limit`, `permission_denied`, `stale_revision`, `temporarily_unavailable`, `unsupported`. Return an actionable typed reason, not a generic failure or a guessed success.

Policy example (product recommendation; do not confuse with the repository owner's deployment approvals):

- Reading current authorized configuration and drafting within the requested task can proceed under the user's requested scope.
- Creating an isolated draft may proceed when explicitly requested, with quota enforcement and an easy discard action.
- Applying a draft to an active assistant requires a concrete diff and acknowledgement of the affected assistant, which may be covered by one bounded plan approval for grouped changes. Do not ask again when the user has already clearly authorized the exact scope and the approval remains valid.
- Publishing, modifying phone routing, making a call, starting a campaign, sending messages, spending credits, deleting data, changing roles, or exporting customer data needs an exact review card and an authorized user action when that scope has not already been clearly authorized. A general “create my assistant” request does not authorize phone purchases, outgoing calls, or messaging customers. Changed payload digests, target revisions, scope, recipient, destination, or price invalidate earlier approval.
- Password changes, payment authorization, provider login, OTP/CAPTCHA, identity verification, and acceptance of third-party legal terms remain secure user steps; the agent can prepare and guide them. Full module coverage does not mean every sensitive step becomes an autonomous tool.

Server-owned tool contract (illustrative design, **not additional MCP standard fields**):

```yaml
id: nimmi.design.apply_draft
version: 1
domain: builder
required_roles: [owner, admin]
scope: assistants:write
effect: changes_active_configuration
approval: exact_diff
input_schema: ApplyDesignDraftV1
output_schema: AppliedDesignV1
expected_revision_required: true
idempotency_required: true
timeout_seconds: 20
retry_policy: reconcile_before_retry
undo: restore_previous_revision_if_unchanged
result_redactor: public_design_fields_only
```

Expose only the model-facing MCP fields needed to select/call it: name, precise description, bounded input schema, output schema, and trusted annotations. The registry's policy data is authoritative in code. Trusted runtime context—actor, workspace, run ID, effect ID, approval record—must be injected outside model-controlled arguments. An input schema should allow `draft_id` and `expected_revision`, not arbitrary `user_id`, credentials, SQL, or route URLs.

Successful domain output should include the applied resource ID, new revision, fields changed, and verification evidence. A tool error should carry a safe typed code, recoverability, and next permitted action. Model prose alone never counts as proof that a bot, import, or phone configuration exists.

Coverage matrix recommendation: every manual product action must be classified as read, safe draft, approvable mutation, secure user-only step, or unsupported with explanation. Generate CI checks against the tool registry, workflow catalog, UI route registry, and actual route/service inventory. Adding a manual feature should require updating its agent coverage row, avoiding an unmaintained promise of “A to Z” access.

### Gaps

- No exhaustive route-permission matrix was generated in this research branch; repository mapping is a parallel workstream.
- The existing app's owner/admin/agent permissions need per-endpoint confirmation before assigning tool scopes. Proposed roles above are illustrative and must never widen existing restrictions.
- Approval UX must balance friction and authorization; exact batches of reviewed draft changes can share one approval, but changed destinations, prices, recipients, or resource revisions must invalidate it.

## How should credentials, imported websites, and external MCP servers be isolated?

### Takeaway

Keep secrets and authorization outside model context. Treat websites, tool results, uploaded content, and user-supplied configuration as data that cannot change the agent's permissions or instructions.

### Cited Findings

- MCP form elicitation must not request passwords, API keys, access tokens, or payment credentials. URL elicitation handles sensitive interactions outside the client; the UI must show the destination domain and permit decline/cancel. URL elicitation is distinct from authorizing the MCP client itself. [Elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- MCP HTTP authorization defines OAuth resource-server/client roles, protected-resource metadata, discovery, and token audience validation. OAuth 2.1 is referenced as an IETF draft, not a finalized RFC. Current guidance prefers client ID metadata documents while keeping deprecated dynamic client registration for compatibility. [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- MCP security guidance forbids accepting tokens not explicitly issued for the MCP server and warns about token passthrough, SSRF, confused deputy attacks, scope escalation, and state-handle hijacking. [MCP security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)
- Anthropic's managed-agent architecture separates the harness, action tools, and durable session events. For custom tools it keeps OAuth tokens in a vault and injects them through a proxy rather than exposing them to the harness. This is evidence for a structural credential boundary, not proof Nimmi needs that hosted product. [Managed agents architecture](https://www.anthropic.com/research/managed-agents)
- Nimmi's `secretbox.EncryptedText` encrypts stored values but automatically decrypts ORM reads. Agent resources must therefore use explicit safe DTOs; serializing an ORM record risks exposing plaintext. [secretbox.py](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/secretbox.py)
- Nimmi's `netsafe` checks public addresses and uses connect-time DNS validation, including redirect connections, rejecting private networks and embedded URL credentials. [netsafe.py](/Users/karthikeyan/.gemini/antigravity/scratch/nimmi-ai/backend/netsafe.py)

### Inferences

Credential journey:

1. Agent checks safe connection status and explains the missing capability in ordinary language.
2. UI offers **Connect Twilio**, **Connect WhatsApp**, or the relevant provider action. Open a first-party secure connection sheet or provider OAuth flow. Credentials go directly to an authenticated credential endpoint; they never pass through chat, run events, model prompts, tool text, frontend analytics, or error logs.
3. Prefer OAuth/embedded signup where actually supported by Nimmi and the provider. Do not promise Meta Embedded Signup while this repository still relies on manual connection.
4. For manual credentials, render validated labeled fields with masking and server-side secure storage. Give exact console paths through maintained provider runbooks with `verified_at`, official documentation links, required permissions, and known account restrictions. The model can explain these runbooks, not invent console locations.
5. Save only opaque connection ID, provider, scopes, masked account label, and status in the run. Backend verifies the account/permissions with a non-mutating provider request when possible. Resume the paused workflow only after a verified connection event.
6. A real SMS, call, subscription, phone purchase, or live webhook change must remain a separate reviewed action because connection validation itself must not silently spend money or change production routing.

Auth boundaries:

- Browser-to-Nimmi uses its existing authenticated session and server-validated workspace selection.
- An in-process tool adapter receives server-created `AuthContext`; no OAuth round trip is necessary for each internal service call. This is an internal application integration, not a claim that the old JWT already implements all public MCP authorization requirements.
- If MCP is exposed remotely to third-party clients, add a standards-conformant protected resource and audience-bound access tokens, issuer validation, PKCE and redirect checks, incremental scopes, token revocation, and per-client consent. Do not forward the dashboard bearer token to arbitrary MCP servers or treat a third-party provider token as a Nimmi MCP access token.
- Store third-party provider credentials separately and inject them only in an allowed backend connector. Bound connection IDs and state handles to actor/workspace/run as appropriate, expire them, and reauthorize access on use.

Website ingestion controls:

- Reuse `netsafe.safe_client`; constrain HTTP(S), redirects, total bytes, pages, depth, duration, MIME types, and concurrent fetches. Deny private/cloud metadata destinations, archive bombs, executable payloads, and cross-origin crawl expansion unless explicitly justified.
- Separate fetch/extract/classify from privileged planning. The extraction step gets website bytes and an extraction schema, with **no mutation tools or secrets**. It outputs facts, proposed brand tokens, asset references, confidence, and provenance URLs.
- Never let a website's text choose tool definitions, credentials, callback destinations, system prompts, workspace IDs, or approvals. Do not execute scripts from the crawled site in a privileged Nimmi origin. If JavaScript rendering is required, isolate the renderer with constrained network access and no customer credentials.
- Treat extracted HTML/Markdown as untrusted UI content. Render a limited safe format, sanitize images/SVGs through existing app utilities, and avoid arbitrary HTML or model-generated JavaScript components.
- Schema validation reduces ambiguity but does not eliminate injection; enforce allowed workflow transitions and data-dependent egress boundaries after extraction. A scraped instruction to “send all contacts to this URL” must remain inert even if the model repeats it.

External MCP adoption:

- First-party tools first. Initially disable user-entered arbitrary MCP URLs; approve integrations through a managed registry with expected origin, publisher, server/tool versions, scopes, network destinations, and allowed workflow usage.
- Run discovery with minimal authority. Reject unknown schemas, risky annotations, unexpected capability changes, excessive tool results, and secret-bearing metadata. Cache catalogs by server identity, schema version, and authorization scope; do not leak one workspace's available resources to another via shared caches.
- A human-readable name is not an identity. Namespace tool IDs by registry-controlled server ID. Recheck authorization before calling a tool, even if it appeared in an earlier authorized catalog.
- Read-only defaults, no generic shell/SQL/browser automation tools for customer operations, explicit allowlists for outbound payload destinations, bounded tool/model budgets, and audited approvals for external effects.

Required negative tests: cross-workspace IDs; forged route context; revoked membership during a paused run; stale approval; duplicate approval submission; a tool schema changing after review; malicious imported instructions; redirect/DNS-rebinding SSRF; connection IDs from another workspace; tokens appearing in model inputs or traces; escaped markup in tool results; denied paid action; reconnect/retry after a completed external effect; provider timeout with unknown outcome (reconcile before retry).

### Gaps

- Provider-specific console instructions were not researched here; implementation must create verified runbooks for each supported provider rather than embedding guessed steps.
- Encryption at rest alone does not establish a vault boundary. Existing connector functions must be audited for returned secrets, logging, and permission breadth.
- No security control can guarantee prompt injection is impossible. The acceptance criteria should measure resistance and prove damage-limiting authorization, egress, and secret-isolation boundaries.
