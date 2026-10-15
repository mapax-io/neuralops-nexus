# NUCLEUS HANDOFF — what nexus-nucleus must change for the rebuilt nexus-ai

Written 2026-10-13. This document is the PROMPT for the nucleus-side work, the
same way docs/NEXUS-AI-REVAMP.md is the prompt for nexus-ai. The rebuilt module
(modules/nexus-ai, 86/86 acceptance tests) is one half of a conversation; every
section below is an obligation only nucleus can fulfil. Until a section lands,
the corresponding nexus-ai feature degrades gracefully (defaults are noted) —
nothing crashes, but the feature does not reach users.

Contracts below are quoted from the BUILT code, not from memory:
`modules/nexus-ai/ai_engine/core/nucleus_client.py` (what nexus-ai calls and
reads), `fastapi_app/contracts/trigger.py` (what it accepts and emits),
`fastapi_app/routers/embed.py` (the embed endpoints). Where this document and
that code disagree, the code wins — then fix this document.

The three fixed contracts: `TriggerJob` in · `AgentEvent` out · the
`/internal/*` back-calls. Everything else is free to change on either side.

---

## Change 1 — usage recording endpoint (Layer 0, item 21)

`POST /api/v1/internal/usage/` ← `{"records": [UsageRecord…]}` (nucleus_client.py:23).
Each record: who/where (`company_id, project_id, topic_id, persona_id, user_id,
message_id, job_id`), what (`model config id, model_id, provider, role
STANDARD|ROUTER|DEEP|FALLBACK, kind` — note `kind="router"` for router calls,
`kind="remote_embedder"` reserved for Layer 3 remote embedding), counts
(`input_tokens` total incl. cache, `uncached_input_tokens`,
`cache_read_tokens`, `cache_write_5m_tokens`, `cache_write_1h_tokens`,
`output_tokens` total incl. reasoning, `reasoning_tokens`), `finish_reason`,
`estimated` (true on cut streams / failed calls — a failed call's input is
never free), `source` (`"router_failed"` on an abandoned router call, else
null), `called_at` ISO. Cost is computed WHERE PRICES LIVE — nucleus — per
§1.5's Decimal formula (tests T11/T12 pin the arithmetic).

A failure here never fails a reply (nexus-ai logs and continues), so nucleus
must treat this endpoint as append-only and idempotent-friendly.

## Change 2 — history rows carry `status`

`GET /api/v1/internal/topics/{topic_id}/history/` rows gain `status`
(COMPLETED | FAILED | CANCELLED | PENDING | STREAMING). nexus-ai drops
non-COMPLETED rows; a row WITHOUT the field is kept (works against today's
nucleus, test_t13_status_none_is_kept).

## Change 3 — persona model seats (items 13/46)

`GET /api/v1/internal/personas/{persona_id}/` gains optional `router_model`
and `deep_model` (same ModelInternal shape as `model`), plus the existing
`fallback_models` (ordered, item 12 — opt-in). Owner's routing rule: the
ROUTER seat is the default screen; a persona with NO router seat uses STANDARD
in the router's place only when a DEEP seat exists (nexus-ai implements the
fall-through; nucleus just ships the seats). Owner also wants a COMPANY
DEFAULT router model fill an empty router seat — that default lives in company
settings nucleus-side and is resolved INTO `router_model` before the persona
is served. `max_steps` on the persona caps agent rounds (item 16).

## Change 4 — ids on the trigger

`TriggerJob` carries `company_id`, `project_id`, `user_id` (contracts/trigger.py:71-73).
Absent = empty string defaults (works today); usage records and Layer 3
scoping are only correct once these are real.

## Change 5 — internal key, both directions

`X-Internal-Key` on everything: nucleus → nexus-ai (`/api/v1/trigger/`,
`/api/v1/models/check/`, every `/api/v1/embed/*`) and nexus-ai → nucleus
(every `/api/v1/internal/*`). Same shared secret (INTERNAL_API_KEY from
secrets.env).

## Change 6 — stored MCP tool lists + drift sync

`MCPServerInternal` stores `tools: [{name, description/one_line, read_only}]`.
With it, the catalog has one line per tool and the approval policy knows reads
from writes BEFORE dialing. Without it (today), the whole server is one
catalog entry and unlabeled tools ask on first use — degraded, not broken.
Drift-sync shape (how/when nucleus refreshes the stored list from a live dial)
is OPEN — decide nucleus-side; nexus-ai already tolerates stored-vs-live drift
(stale ids are dropped, test_l1_unknown_topic_tool_ids_are_dropped).

## Change 7 — `tool_access` + `approval_scope` on the persona

`tool_access: "all" | "selected"` (item 3) and `approval_scope: "topic" |
"requester_only"` (item 2 decision 5) ship on the persona. Approval RIGHTS are
enforced by nucleus under `persona.approve_run` + the scope — nexus-ai never
checks who clicked.

## Change 8 — the topic's tool memory (items 1/2/4 + Layer 3 bridge)

- Ship `topic_tools` (the stored loaded set) and `topic_tool_clearances`
  (catalog ids the topic cleared as reads) in every TriggerJob.
- On a topic's FIRST reply, store `loaded_tools` from `message_done` /
  `message_paused` as the topic's set. `loaded_tools: null` = no tool-bearing
  run happened (e.g. the router answered) — store NOTHING, the set stays
  undecided on purpose.
- An approval card's "always allow" adds that tool id to the clearances
  (READS only — a known write asks every time, nexus-ai enforces that side).
- Approving a DISCOVERED tool's first use also appends it to `topic_tools`
  (decision 4: ask-on-first-use is the discovery gate).
- Store `used_tools` from `message_done`/`message_paused` on the message row.
- NEW (Layer 3 decision 10): store `retrieved_sources` from `message_done` on
  the message row beside `used_tools`.
- When calling `POST /api/v1/embed/message/` (change 10), pass the row's
  `used_tools` along — it becomes vector metadata (item 44).

## Change 9 — pause / resume (item 2)

- Implement `POST /api/v1/internal/messages/{msg_id}/pause/` ←
  `{job_id, topic_id, persona_id, state, catalog_hash, pending: [{call_id,
  tool, capability_id, args_preview}], role}` (nucleus_client.py:66-84).
  nexus-ai POSTs this BEFORE emitting `message_paused` — by the time the UI
  sees the event, the state is guaranteed stored.
- The resume is the SAME `POST /api/v1/trigger/` with
  `resume: {state, approvals: {call_id: {decision: approved|denied, reason?}},
  role}` — no new endpoint. `role` comes back from the pause payload (the run
  resumes on the same model seat).
- Relay note: a resume emits a SECOND `message_start` on the same msg_id —
  treat it as the stream reopening, not a new message.
- Pause expiry is nucleus's job (e.g. a 24h cron that resumes-with-deny);
  nexus-ai holds nothing while paused.
- New event types the relay must pass through and the UI should render:
  `approval_requested` (ApprovalRequestData — 0.8.0's card shape),
  `message_paused` (a FINAL event — no message_done follows),
  `tool_call_start` / `tool_call_end` (0.8.0 shapes, item 19),
  `deep_escalation` (`escalated_to` — item 46),
  `context_retrieved` (Layer 3, below).
  `message_done` gains: `answered_by_model` (may say "<name> (fallback)"),
  `loaded_tools`, `used_tools`, `retrieved_sources`.

## Items 10/11 — rate limits (owner's decisions, 2026-10-13)

Enforced BY NUCLEUS, PRE-trigger, from the usage records (change 1): limits
per persona and/or per user, expressed in REQUESTS or TOKENS, per HOUR or DAY
(no finer). A trigger over the limit is refused nucleus-side with a worded
message; nexus-ai is never involved. Item 14 (spend caps in money) comes
later — the WrapperModel seam is reserved in nexus-ai for a per-call guard if
pre-trigger proves too coarse.

## Change 10 — Layer 3: vectors, embedder, reindex (items 24/31/33/44)

Deployment first: the `nexus_vectors` database on the SAME postgres instance,
image `pgvector/pgvector:0.8.7-pg17` (dev already swapped 2026-10-13;
production `postgres` service needs the same one-line swap + one-time REINEX
and `CREATE EXTENSION vector` in `nexus_vectors`). nexus-ai's service gets
`NEXUS_VECTOR_DB_URL=postgresql+psycopg2://<user>:<pass>@postgres:5432/nexus_vectors`
(env unset = whole feature off, endpoints answer 503). The nexus-ai image
needs the Layer 3 pins (requirements.txt) with CPU torch installed FIRST.

Nucleus-side work:

1. **Per-project embedder setting** (decision 3): project settings hold an
   embedder spec `{provider: "fastembed" | "openai_compatible" | "hash",
   model_id, api_base?, api_key?}`; UNSET = the system default (local
   fastembed `nomic-ai/nomic-embed-text-v1.5`) — there is NO company-level
   default (Open (a) resolved). Changing it is restricted to the COMPANY
   OWNER/ADMIN (decision 8) — enforce at the settings endpoint.
2. **On embedder change** (decisions 4+8): make the project INACCESSIBLE to
   users → `POST /api/v1/embed/reindex/` `{company_id, project_id, embedder}`
   (202; 409 = one already building, surface it) → poll
   `GET /api/v1/embed/reindex/{project_id}/status/` → `{status, done, total}`
   until `active` → unlock the project. A crash mid-rebuild is safe: the old
   index stays active underneath the lock; re-trigger the reindex.
3. **Keep calling the embed endpoints as 0.8.0 did**, shapes unchanged plus
   the settled additions:
   - `POST /api/v1/embed/` — documents only; include the project's `embedder`
     spec; STOP SENDING `type="code"` (it is now refused 422 — decision 5;
     code files ride the prompt, the code-graph MCP inspects code). Store the
     returned `collection_id` (now `"{project_id}:{source_id}"`).
   - `DELETE /api/v1/embed/context-source/{collection_id}/`
   - `POST /api/v1/embed/message/` for EVERY stored chat message — persona
     answers included — with `used_tools` from the message row and the
     project's `embedder` spec.
   - `DELETE /api/v1/embed/message/{message_id}/?company_id=…` (add
     `&project_id=…` to skip the company scan — optional).
   - `POST /api/v1/embed/recall/` + `DELETE /api/v1/embed/recall/{entry_id}/`
     (W5, ported — same contract, entry_id upserts).
   - `GET /api/v1/directives/` is NOT ported — confirm nothing nucleus-side
     calls it, then delete the caller.
4. **Relay + store retrieval**: pass the `context_retrieved` event through
   (references + scores only — render as "searched project memory, using N
   items"; ids are message/source/recall ids nucleus can link); store
   `retrieved_sources` from `message_done` (change 8).
5. **Billing**: remote embedder calls will be billed as usage records with
   `kind="remote_embedder"` (seam reserved; local fastembed is free).

## Change 11 — Layer 4: output types, questions, nudges, memory (items 23/5/W8/27)

Engine side built and tested 2026-10-14 (suite 99); the nucleus half:

1. **Output types on the message row** (item 23): `message_done` now carries
   `output_type`, `render_as` and `embed_description`. Store all three on the
   AI message row — `output_type` fixes 0.8.0's defect where AI rows stayed
   `message_type="text"` forever; the frontend renders by `render_as` (a
   broken typed reply arrives already downgraded to text — never trust-parse
   content client-side). Keep sending `TriggerJob.output_type` exactly as
   0.8.0 did ("auto" default; an explicit user pick wins engine-side).
2. **Feed `output_type` back in history** (item 23's request-behind-pick):
   the history endpoint's message rows gain `output_type` — the engine's
   classifier reads it to resolve "show it as a chart" follow-ups.
3. **Embed rendered replies by their description** (item 44): when a stored
   AI message has `embed_description`, send THAT text (not the chart JSON /
   HTML) as the content of `POST /api/v1/embed/message/` — a JSON blob is a
   useless embedding; the model wrote the description for exactly this.
4. **The question card** (item 5): the pause payload's `pending[]` rows now
   carry `kind: "approval" | "question"` — render kind=question as a question
   card (question + options from the `question_asked` event, free-text always
   allowed; options are radio-style suggestions, not an enum). The person's
   answer resumes the SAME `/api/v1/trigger/` road with the stored state and
   `resume.answers = {call_id: "the answer text"}` beside the existing
   `resume.approvals`. Relay `question_asked` to the client like
   approval_requested. Pause expiry (change 9) applies unchanged — an expired
   question resumes with an empty answer or a worded deny, nucleus's wording.
5. **Nudges** (W8): store what the person types while a reply runs, per
   message. Serve `GET /api/v1/internal/messages/{msg_id}/nudges/` →
   `{"nudges": ["text", …]}`, CONSUME ON GET (the engine polls after each
   tool call; one GET = taken). X-Internal-Key required. After the reply ends
   (done/paused/error), post any LEFTOVER nudges as ordinary user messages to
   the topic — 0.8.0's never-lost rule. Relay the `nudge_taken` event
   (field `nudge` = the text) so the UI can mark the typed line as "seen by
   the persona".
6. **The memory pass** (item 27, decision 8): expect usage records with
   `kind="memory"` (one cheap call after tool-bearing replies, billed under
   the persona's UTILITY seat — add `utility_model` to PersonaInternal, same
   shape as router_model; unset = the engine falls back ROUTER → STANDARD).
   Memory rows live in the project's vector index with
   `source="toolres:{message_id}"` — when a message is deleted, call the
   existing `DELETE /api/v1/embed/message/{message_id}/` AND nothing more:
   the engine's delete-by-source covers tool memory via the same id. No new
   endpoint needed.
7. **Queue per topic** (item 38, decision 5): nucleus SERIALIZES triggers
   within one topic_id (lock or chain — replies in order, no topic_tools
   race); across topics, fire freely — the engine is stateless-per-run and
   fully parallel.
8. **Continue in new topic** (item 6, decision 4): a UI action, zero engine
   code — send an ordinary trigger asking the persona for a handover summary,
   create the new topic with that summary as its first message. Chat memory
   is same-topic-only, so the summary IS the carryover.

## Change 12 — item 29: scheduled runs / routines (parked here 2026-10-14, verify-first)

Owner's decision (2026-10-14): ALL of item 29 lives in the nucleus project.
The engine side is already built and tested — nothing more is planned there.

1. **Verify before designing** (Layer 4 decision 7): read 0.8.0's scheduling
   code (routines, cron-like triggers) and confirm a scheduled run needs
   nothing from nexus-ai beyond an ordinary `POST /api/v1/trigger/` with
   `interactive=false`. If the read finds anything more, it becomes a new
   settled item — do not assume.
2. **What the engine already guarantees for `interactive=false`** (tested:
   a6, f3, q3): ask-gated tools are REFUSED with the worded "needs a
   person's approval" tool result — never paused (nobody can answer); a
   discovered tool's first use is refused the same way; `ask_user` is never
   offered. The run always ends in message_done / message_error, never
   message_paused, so a schedule cannot strand a pause.
3. **Nucleus's half**: the scheduler fires the trigger with
   `interactive=false`, stores the reply like any other, and words any
   refused-tool outcome for the routine's log. Nudges don't apply (no one is
   watching); the memory pass still runs (it keys off tools-ran + an active
   index, not interactivity).

## Change 13 — Layer 5: connectors, the MCP gateway, provisioning (items 17/39/9, parked 2026-10-14)

Owner's rule for all of it: keep it simple — "our app API behaves like an MCP
as well, accessed internally and externally." Zero engine work in any of this.

1. **The NeuralOps MCP gateway is the FIRST-CLASS CITIZEN** (owner's ranking;
   own project on the MCP track): one MCP server over nucleus's EXISTING
   APIs, available BY DEFAULT, internally (personas use the product itself as
   a tool) and externally (Claude Desktop/Code, Cursor, …) — ask_persona
   (→ the normal trigger road), search_memory (→ embed/search),
   list_projects, list_topics, post_message. Auth: a PER-USER token minted in
   the UI (create/revoke page); every call runs as the caller through
   `PermissionChecker`; no shared master key. Thin front-door only — if a
   tool needs new business logic, it is out of scope.
2. **The other bundled connectors are ONE CLICK away** (item 35's
   `is_internal`): the data MCP (34+36), code-graph MCP (32) and provisioning
   MCP (39) ship in the product's code and appear on every new project, OFF
   until the admin's one click. Internal NATIVE tools (filesystem, web
   search, shell, …) stay capabilities, on by default as today. Nucleus's
   job: the one-click per-project UI and attaching the chosen servers to
   personas like any other MCP server row.
3. **Provisioning MCP fence** (item 39): a reserved per-project topic named
   "configure", auto-created with the project, visible to exactly four roles
   — Project Admin, Project Owner, Company Admin, Company Owner. The
   provisioning MCP is attached only there. §4.5 of the revamp doc holds the
   full design (acts-as-caller, no self-elevation, secrets stay null, audit
   question). Item 5's question cards (change 11.4) are its interview UI.
4. **Item 9 (persona call rights)**: already built (`persona.mention`,
   `persona.approve_run`), enforced pre-trigger — nothing new; just keep
   enforcing before firing the trigger, including for gateway calls.

5. **Deployment (owner, 2026-10-14): both approaches, split by weight.**
   Heavy connectors (data MCP + MinIO; code-graph MCP + FalkorDB) are their
   OWN compose services, pre-defined in `docker-compose.neuralops.yaml`
   behind a profile; thin connectors (gateway, provisioning) share ONE
   lightweight "neuralops-mcp" service. Nothing downloads at click time —
   the one click only flips availability. A heavy connector can also run
   REMOTELY (Amazon, RunPod): same container image, the admin repoints that
   server's URL in nucleus — plan a per-server secret for stack↔remote auth.

6. **Item 8 — the phone-home (owner, 2026-10-14): ONE value, always on,
   nucleus-side.** Reports **total tokens**, identified by
   `NEURALOPS_INSTALL_TOKEN` (that is how the vendor knows who owns the
   server). Cadence (owner): **when the application opens and when it closes**
   — a POST on startup and one on shutdown, that's all; NOT
   customer-switchable. Nucleus already holds every usage record (change 1),
   so it is a sum + one HTTPS POST to the vendor endpoint. MUST fail silently
   when offline (air-gapped installs stay unharmed). No tracing ships
   anywhere: full request traces never leave the customer's server. And to be
   explicit (owner): ALL detailed usage values stay recorded LOCALLY on the
   customer's install — change 1's full records are exactly how users keep an
   eye on their own budget; only the single total leaves.

Open within change 13: whether company-level setup (create projects, company
model configs) gets its own "configure" place or rides any project's configure
topic; token scopes for the gateway (full user vs read-only); the exact
stack↔remote connector auth shape; the vendor endpoint URL for the
phone-home (13.6; cadence settled: app open + close).

## Change 14 — Layer 6: persona chains, the workflow MCP, runbooks (items 45/46, parked 2026-10-14)

Engine side built and VERIFIED BY THE OWNER 2026-10-14 (suite 106 passed, 0
skipped, dev pgvector stack) — with this, the nexus-ai layered build (0–6)
is complete; everything below is the nucleus half.

1. **Nucleus orchestrates the chain** (Layer 6 decision 1): chain state +
   checkpoints live in nucleus; every worker stage and every supervisor
   review is an ORDINARY trigger; on each verdict nucleus fires the next
   stage (or the bounded redo, max 2–3, then ask the user). Each finished
   stage posts into the topic. A crash re-fires from the checkpoint.
2. **The workflow MCP** (own project, bundled Tier-2 connector): tools
   `define_chain / start_stage / approve_stage / send_back /
   get_stage_output`, all writing chain state to nucleus as the caller.
   `start_stage` returns immediately; when the stage's run finishes, nucleus
   re-triggers the supervisor with "stage n done — review" (step_context or
   the message carries the stage's handover).
3. **Runbooks = saved chain definitions** (verified against legacy
   runbooks.py: W6 was already nucleus-sequenced via
   `TriggerJob.step_context`): store team + stages + criteria + per-stage
   model seats; keep SENDING step_context exactly as 0.8.0 did — the engine
   ports its prompt block (clip kept).
4. **Preflight** (verified against legacy preflight.py): nucleus's half is
   unchanged from 0.8.0 — send `preflight=true` while a gated persona has no
   approved plan, store the plan the user approves, send it back as
   `approved_plan`. The engine ports plan_turn (no-tools preflight turn →
   output type "preflight"; approved_plan block ahead of the prompt).
5. **Default chain template** (decision 6): workers on the project's main
   model, supervisor on the DEEP seat, utility cheap — ship it as the
   starting runbook.
6. **`delegation_enabled` on PersonaInternal** (engine built 2026-10-14): a
   boolean — the supervisor checkbox. When true, the engine gives that
   persona the `call_persona` tool (one-shot delegation to another persona of
   the project, depth 1, unattended inner run, max 3 calls / 600s each).
   Until nucleus sends the flag, no persona gets the tool — safe default.
7. **Delegation billing**: expect usage records with message_id
   `{msg_id}:cp{n}` carrying the CALLEE's persona and model ids — the inner
   run of a call_persona. Sum them into the message's cost; show them under
   the callee persona in per-persona spend. The preflight/approved_plan/
   step_context trigger fields are now LIVE engine-side (turn_rules) with
   their 0.8.0 shapes unchanged — keep sending them exactly as before.

## Open questions parked here

- Drift-sync shape for stored MCP tool lists (change 6).
- Where pause-expiry's resume-with-deny is worded for the user (change 9).
- Whether delete-message should always carry project_id (cheap win).
- Retrieval threshold/top_k tuning after real use (nexus-ai settings
  RETRIEVAL_MIN_SCORE=0.30, RETRIEVAL_TOP_K=6).
- Question-card UX for an expired/abandoned question (change 11.4 — empty
  answer vs worded deny).
- Whether leftover nudges post as one combined message or one each
  (change 11.5 — 0.8.0 posted one each).
