# NeuralOps Nexus — Nexus-AI Revamp

**Baseline:** `upstream/dev` @ `939af00` — "chore: server version 0.8.0". **Not the fork**, which is at 0.2.0 and ~7 minor versions behind (migrations end at 0018 vs upstream's 0028).
**Scope:** nexus-ai is being rebuilt. nucleus schema and API are largely kept — so "built" below is split by which side it lives on.
**Framework:** pydantic-ai + `pydantic-ai-harness`.
**Method:** finalize the list → settle each item in discussion → expand it here.
**Date:** 2026-10-07

Status values: **Built** (exists at 0.8.0) · **Partly built** · **Remaining** · **Settled** (our design, not yet built) · **Not audited** (status against 0.8.0 unverified) · **Dropped**.

---

## 0. Expansion template

Every item is expanded under these nine headings, in this order. An item is not "done" until all nine are filled or explicitly marked N/A.

| # | Heading | What goes in it |
|---|---|---|
| 1 | **Problem** | Why the item exists. Two or three sentences. |
| 2 | **Decision** | What was settled — **and what was rejected, with the reason.** The rejections are the part that stops the same argument being had twice. |
| 3 | **Mechanism** | Where it attaches: which pydantic-ai or harness seam, which nucleus model and field, which event. |
| 4 | **At 0.8.0** | What already exists, so the rebuild does not redo it. Quote `file:line`. |
| 5 | **Open** | What is still undecided, as questions rather than prose. |
| 6 | **Acceptance** | How we would know it works — a falsifiable check per behaviour. This is also where a silent-failure defect earns its test. |
| 7 | **Classes and methods** | Signatures, both sides of the boundary. New, changed, deleted. |
| 8 | **API** | Endpoints: method, path, request, response, auth, and which side calls it. |
| 9 | **Sequence** | A diagram of the real call chain — who calls what, in order, including the failure and pause paths. Anchored to actual call sites, not an idealised flow. |

Section 6 does double duty: with an acceptance check on every item, the open question of whether the four silent defects get tests answers itself.

Sections 7–9 are written against the real call chain, which at 0.8.0 is:

`POST .../messages/` → `send_message` → `MessageDirectives` → `_save_user_message` → `_trigger_personas` → `asyncio.create_task(trigger_ai_response_async)` → `create_ai_message` + publish `message_start` → build `job_payload` → `POST {nexus_ai}/api/v1/trigger/` → `_event_stream` → `NewImprovedAgenticManager.run(job)` → `nucleus_client.resolve_persona` + `fetch_history` → `FallbackRun` → `PydanticAIRunner.build_agent` → `Agent.run_stream_events` → SSE back through `stoppable_lines` → Centrifugo `topic-{id}`.

The internal endpoints the worker calls back on: `GET /internal/personas/{id}/`, `/routines/{id}/`, `/topics/{id}/history/`, `/topics/{id}/contexts/`, `/companies/{id}/ai-config/`, `/messages/{id}/approvals/{call_id}/`, `/messages/{id}/nudges/`, and `POST /internal/recall/`, `/internal/ai-request-logs/`.

> Items marked **Built (nexus-ai)** are code the rebuild will replace. The decision for each is whether to keep the *approach*, not whether the code exists.

---

## 1. The list

| # | Item | At 0.8.0 | Where |
|---|---|---|---|
| 0 | Known defects the rebuild must not inherit | Verified — see Appendix A | both |
| 1 | Tool matching and the permitted set | **Partly built** — persona-level only | both |
| 2 | Tool permission before use | **Built** | both |
| 3 | Persona tool/MCP tick list | **Partly built** — servers yes, tool names no | nucleus |
| 4 | MCP scope: project / channel / topic | **Partly built** — project-scoped | nucleus |
| 5 | Model asks the user questions | Not audited — **first consumer is 39** | — |
| 6 | New topic button; summarize when prompt gets long | **Remaining** | both |
| 7 | Self-hosted / custom endpoints | **Built** — `api_base` → `base_url` | both |
| 8 | Logfire inside nexus-ai only | Not audited | nexus-ai |
| 9 | Persona call rights | Not audited | nucleus |
| 10 | Per-user rate limits on persona calls | Not audited | nucleus |
| 11 | Per-model rate limits | Not audited | nexus-ai |
| 12 | Multiple models per persona | **Built** — own retry, not `FallbackModel` | both |
| 13 | Model choice by query depth | **Remaining** — nothing exists | nexus-ai |
| 14 | Fixed budget per project | Not audited | nucleus |
| 15 | Prompt / model caching | Not audited | nexus-ai |
| 16 | Tool loop and context limits | **Settled** — tiers right, budget wrong | nexus-ai |
| 17 | Connectors | Not audited | both |
| 18 | Claude Agent SDK runtime | Not audited | nexus-ai |
| 19 | Tool activity visibility | **Built** — `tool_activity` / `_end` | both |
| 20 | Swarm — automatic persona handoff | **Dropped** — replaced by sub-agents | — |
| 21 | Usage recording | **Built** — on message metadata | both |
| 22 | Execution sandboxing | **Settled** — stays as-is | nexus-ai |
| 23 | Output types and rendering | **Partly built** — `message_type` not carried | both |
| 24 | Context retrieval / RAG | **Settled** — strategy is 33 | nexus-ai |
| 25 | Event contract | **Built** — 11 worker / 15 nucleus events | both |
| 26 | History selection | **Remaining** — three filters absent | both |
| 27 | Conversation state persistence | **Built** — poll, not a run table | both |
| 28 | Attachments and vision | **Settled** | both |
| 29 | Scheduled runs | **Built** — routines + runbooks | nucleus |
| 30 | Migration of existing data | **Dropped** — DB will be reset | — |
| 31 | Vector store — pgvector | Not audited | nexus-ai |
| 32 | Code graph — bundled MCP, per project | **Remaining** | both |
| 33 | Content-type routing | **Remaining** | nexus-ai |
| 34 | Large CSV / data files — DuckDB | **Remaining** | nexus-ai |
| 35 | Bundled capability MCPs | **Partly built** — `is_internal` exists | both |
| 36 | Object storage for attachments | **Remaining** | both |
| 37 | Run cancellation | **Built** | both |
| 38 | Concurrent runs in one topic | **Settled** | both |
| 39 | Provisioning MCP — agentic project setup | **Proposed** | both |
| 40 | Credential verification — Test button, fingerprinted | **Partly built** — only persistence missing | both |

**Real remaining work:** 1, 6, 13, 16, 26, 32, 33, 34, 36, 39 — plus item 40's persistence, Appendix A's defects, and the twelve items not yet audited against 0.8.0 (5, 8, 9, 10, 11, 14, 15, 17, 18, 23, 31, 35).

---

## 2. What 0.8.0 already provides — do not rebuild these from scratch

- **Tool approval, item 2.** `Persona.tool_levels` (JSON: `"auto" | "ask" | "off"`, keyed by capability id or `"<capability>/<tool>"`). Worker-side `ToolApprovalGate` is a **harness `AbstractCapability`**, not pydantic-ai deferred tools: `prepare_tools` drops `off`, `before_tool_execute` awaits a decision on `ask`. Defaults when unset: MCP tools with `readOnlyHint` → `auto`, acting tools → `ask`, else `auto`. "Always allow" clears the key for the run. Unattended runs refuse rather than hang. Events: `approval_requested` out, `POST …/approvals/{call_id}/` in, nucleus-held state read by a worker poll.
- **Cancellation, item 37.** `POST …/messages/{id}/stop/` → Redis key `nx:stop:{msg_id}` (TTL 600s) → the relay polls every 0.15s wrapping **both** the connection open and the line iteration, so a stop lands while the model is silent. Partial content is kept; the row goes to `COMPLETED` with `metadata.stopped = True` (never `Status.CANCELLED`).
- **Run pause without decoupling, item 27.** The run parks *inside* the existing stream — the worker emits `keepalive` every 30s so the 120s read timeout never fires. **This corrects an earlier conclusion in this document that item 2 forced a transport change. It does not.**
- **Fallback models, item 12.** `PersonaFallbackModel` through-model, ordered, max 3. Worker retries the whole stream per candidate (`FallbackRun`), suppressed once any token has reached the reader. pydantic-ai's `FallbackModel` is **not** used but is available.
- **Event contract, item 25.** 11 worker event types, 15 nucleus types, channel `topic-{topic_id}`.
- **Usage, item 21.** `prompt_tokens`, `output_tokens`, `context_window` on `ChatMessage.metadata["usage"]`, end to end.
- **Compaction, item 16.** `TieredCompaction` with `DeduplicateFileReads` → `ClearToolResults` → `SummarizingCompaction`, wired unconditionally. *(But see Appendix A — its target is miscomputed.)*
- **Beyond the list.** Routines (per-turn capability intersection, `/name` token), runbooks, recall entries, inbound hooks, deliverables, plan-first preflight, nudges, browser and terminal routers, message search.

---

## 3. What is settled but not built

- **1 — Permitted set.** Permitted ≠ sent. A per-**topic** cache: admitted by permission or mention, hit by per-message match, evicted only under token pressure. 0.8.0 has `tool_levels` at **persona** scope only, no tool tags, no semantic matching (`ToolSearch(strategy=None)` — selection explicitly disabled), and no modelled distinction between permitted and sent.
- **6 — Summarize / new topic.** `SUMMARY` added to `MessageType`; last-N history stops at the barrier; a button copies setup and archives the topic. Nothing exists: `SUMMARY` appears nowhere in 0.8.0.
- **13 — Depth routing.** Nothing exists. `CompanyAIConfig.utility_model` is a fixed company-level small-pass model with one caller (recall). Zero hits for `escalat`, `complexity`, `depth`, `tier`.
- **20 — Swarm.** Automatic handoff **dropped**: it broke item 2's permission model (A gets approval, B inherits the run), left nobody in charge of the chain, lost context per hop, and billed personas the user never chose. Replaced by user-driven @mention (a separate run) and model-driven `SubAgents` (parent keeps its identity). Repoint `swarm_transition` at sub-agent delegation rather than deleting it.
- **22 — Sandboxing.** Stays as-is: project folder bind-mounted, filesystem and shell allow-lists. No container-per-run, no microVM.
- **26 — History selection.** Last 5–10 messages, back to the most recent `SUMMARY`; filter out `FAILED`/`CANCELLED`/`PENDING`/`STREAMING`; honour `is_deleted_from_context`. 0.8.0 does none of the three.
- **28 — Attachments.** Bytes as now, plus an embedded **one-line description** per attachment for discovery (works for code, where embedding source would not), plus chunks in pgvector for prose only. Needed because attachments go unreachable once 26's barrier passes them. Pasted source files are offered a home in the project folder instead.
- **30 — Migration.** Dropped; DB reset, migrations for new data only.
- **38 — Concurrent runs.** Independent and separately cancellable. Consequences: each message must persist **what it replied to** (`TriggerJob` already carries `user_message_id` in flight — land it as `in_reply_to`), or transcript order stops matching causality; the rate limiter must live **outside** the run (shared Redis) or concurrent runs each claim the full TPM allowance; `sequence` needs safe concurrent allocation; and the permitted set is read at run start, so concurrent runs legitimately differ — correct, not a bug.

### 16 — Context budget, compaction and the tool loop

**The trigger is a budget, not a constant.** The prompt must leave room for the model's own output and for the loop to grow mid-run:

```
input_budget = context_window − max_output_tokens − loop_headroom
```

`context_window_for(model)` already exists and returns the real window; it is simply not used for this. Two numbers, not one: a **target** (what compaction compacts down to, ~70% of budget) and a **trigger** (~90%). Firing at the target means re-compacting constantly; the gap is what lets the loop grow between compactions.

**Selection and compaction are different mechanisms.** Conflating them is how the budget got wrong in the first place.

| | What | Mechanism |
|---|---|---|
| Before the run | history window (26), retrieved chunks (24), attached files, tool schemas (1) | **selection** — do not put it in if it will not fit |
| During the run | tool results accumulating | **compaction** — unforeseeable, so it must be cleaned up |

Items 26 and 1 are selection. Compaction exists for growth that cannot be predicted, not to clean up after a carelessly assembled prompt.

**Where it applies, in order — and only one layer is ever summarized:**

1. **Duplicate tool results** — same file read twice, keep the last. Lossless, free, drop first.
2. **Old tool results** — search hits, graph queries, greps, DuckDB output. **Evicted, not summarized.** Summarizing a grep is pointless: it was fetched for one turn, is stale after it, and is re-runnable if needed. This is the bulk of the saving in a tool-heavy run.
3. **Old history** — the only layer where summarizing makes sense, because conversation is narrative and compresses well.
4. **Never touched:** the current user message, the system prompt, and **user-attached files**. Compacting an attached file silently corrupts the task — "fix the typos in this file" against a summary of the file.

So, by source: history → summarize (last resort); search and graph output → evict; attached files → protect.

**0.8.0's tier order is already correct** — `DeduplicateFileReads` → `ClearToolResults` → `SummarizingCompaction` is exactly 1 → 2 → 3. Only the target number is wrong (see Appendix A). But `ClearToolResults(max_fraction=0.9, keep_pairs=5)` and `DeduplicateFileReads`'s `read_file`-only key both need revisiting once graph (32) and DuckDB (34) results flow through, since neither is keyed for them.

**Limits still absent:** `UsageLimits` is unused and `max_steps` is dropped on the wire, so nothing caps agent rounds. Tool results have no size cap before entering the transcript.

**The escape valve.** Content that can neither be compacted (authoritative) nor fitted is not a compaction problem — it becomes a *retrievable source* instead of inline content. Same rule as item 28: **indexing answers "too big to send."** That is what 33 and 34 are for.

### 32 — Code graph

CodeGraphContext (MIT) — integrated, not built. An **internal** MCP (`is_internal`), never in the Add-MCP form. **One shared HTTP service**, always running; not a container per project (that needs the Docker socket = root on host). **One named graph per project** (`p_<uuid>`) — deliberately unlike 31's shared table, because traversal is recursive and a missing filter walks into another tenant's subgraph. FalkorDB server mode likely, on an instance **separate from Celery's Redis**. Project folders mounted **read-only**; graph volume separate and writable. Activation: auto above a file-count threshold, prompt below; one click, and the click is the onboarding; **maintenance automatic** on checksum change. **Three-layer ignore:** repo `.gitignore` → our vendored/generated defaults (`vendor/`, `*.gen.ts`, `*_pb2.py`) → `.nexusignore`, written on first build so it explains itself; real `pathspec` semantics so `!negation` works. Language allow-list is **system** config, separate from the ignore deny-list. **Model-driven, not pre-injected**, with three scaffolds: a line in `instructions=`, rewritten tool descriptions, and 13 escalating code-modification queries away from the cheap model. **Hard dependency on the filesystem MCP** — traversal needs an entry point. Graph retained on soft delete, dropped on hard delete.

**Open:** does CodeGraphContext support per-request graph targeting? If it is one-server-one-repo, the shared service collapses into a process per project. Second: language quality beyond Python and TypeScript.

### 33 — Content-type routing

| Content | Graph | pgvector | Reached by |
|---|---|---|---|
| `.py` `.ts` `.tsx` `.go` `.rs` … | ✓ | ✗ | graph + grep/read |
| `.md` `.rst` `.txt` `.pdf` `.docx` | ✗ | ✓ | semantic search |
| `.csv` `.xlsx` `.parquet` | ✗ | ✗ | query engine (34) |
| `.yaml` `.json` `.toml`, lock files, images | ✗ | ✗ | grep/read on demand |

**No code embeddings anywhere** — identifiers are poor semantic targets; grep plus the file tree does that job better and never goes stale. No file in two stores. The router is ours.

### 34 — Large CSV and data files

Tabular data is a third retrieval mode: **computational**. **DuckDB** over files in place from the project mount — no ingestion, handles larger-than-RAM, infers schema, reads CSV/Parquet/JSON/Excel, joins two files in one query, a library not a service. **Schema before rows**: store columns, types, row count, nulls and ~5 samples (~200 tokens) on upload. **Cap the result and say it was capped.** **Read-only.** **Two tiers behind one interface** — bundled DuckDB, or a remote HTTP MCP the user supplies (DuckDB+MinIO, ClickHouse, BigQuery) — same tool shape (`describe_schema`, `query`), so the backend swaps with no other change. Results render as tables and charts, which is why 23 matters.

### 39 — Provisioning MCP (agentic project setup)

An **internal** MCP (item 35's category) reached through a reserved channel, where the agent interviews an admin and then *performs* the setup: what kind of project, who to invite, what scope, what each AI team member's role is, which models to use. It is the first item whose tools **write** to nucleus — everything else on the list reads.

**Tools:** `create_project`, `invite_member`, `create_persona`, `assign_role`, `set_permission`, `configure_mcp`, `set_budget`, `create_model_config`. Read-side: `list_available_models`, `list_members`.

**Access:** project owner / project admin / company owner / company admin only — a new `Right` code at PROJECT and COMPANY scope plus a `row_rules.visible_channels` exclusion. Note this is a new pattern: today channels are visible by *membership*, not by role. The reserved channel name also needs protecting, or a user creates their own and shadows it.

**The non-negotiable: it acts as the caller, never as itself.** If the MCP holds a privileged credential of its own, anyone who can reach the channel gains admin-equivalent power through the agent. Every tool call carries the caller's identity through `PermissionChecker.can()` — same check, same scope chain. This is invariant I2 made concrete: a run parked overnight on an approval must **re-check rights on resume**, because the person's role may have been revoked while it waited.

**Two anti-escalation rules:** no self-elevation (the agent cannot grant the caller a right the caller does not hold — otherwise "make me company owner" is a working prompt), and no granting beyond the caller's own grant. `PermissionChecker` may not express these today, since granting rights is normally a UI-only action.

**Secrets never enter a message.** A key typed into chat is already in `ChatMessage.content`, broadcast over Centrifugo, embedded into pgvector by `embed_message_async`, replayed into the next prompt by `fetch_history`, and **sent to the model provider** — the last two being unrecoverable. So: **the agent creates the row with the secret left `null`**, never a placeholder string (a fake key is indistinguishable from a real one by inspection, and fails as an opaque provider 401). The user supplies it through the normal UI. Same pattern for MCP auth tokens. This means item 5's question cards stay simple — radio, checkbox, multi-select — with no secret-input variant and no second response path.

**Setup therefore ends with a punch list, not a completion:** "3 personas and 2 models created; these 2 need keys before anyone can use them." Item 40 lets that list clear itself.

**Scope bounds for v1:** no deletes — create and invite only, destructive operations stay in the UI. And bound it explicitly to provisioning: "set up a project" grows naturally into "manage everything", and a general-purpose admin agent is a far larger security surface.

**Depends on:** 2 (every tool here is an acting tool → `"ask"` by default, which `ACTING_TOOLS` already expresses), 5 (its first real consumer), 9 (the new right), 35 (bundled internal MCP), 40 (verification), 13/21 (model suggestion needs cost data, which does not exist — no `cost` column anywhere).

**Open:** company scope, project scope or both; whether it can reconfigure an existing project or only create; whether a half-finished setup rolls back or leaves partial state (invariant I5, and worse here — a double-resumed run that invites five people twice is visible to five people).

**Audit gap this exposes.** Every tool here changes who can do what, or what gets spent — which needs a durable record of who approved what. But `AgentRun` and `AgentApproval` were **deleted** upstream (migrations 0006/0007), and approval decisions currently live in Redis with a 600s TTL. Either provisioning writes its own audit rows, or approval decisions become persistent for acting tools. Decide before building.

### 40 — Credential verification (Test button)

A model config is not trusted until a real call has succeeded with it, and verification **expires when anything it depended on changes**.

**Already built at 0.8.0 — do not rebuild:**

- `POST /api/v1/model-configs/check/` — `intelligence/api.py:218`, schemas `ModelCheckIn` / `ModelCheckOut`
- `check_model_config(company, data)` — `intelligence/services.py:121`; proxies to the worker, 30s timeout
- `POST /api/v1/models/check/` on nexus-ai → `check_model(config)` in `apps/managers/model_check.py`
- The probe is `"Reply with the single word OK."` at `max_tokens: 5`, built **through `PydanticAIRunner.build_model`** — so "passed" means "a persona on this model will run", not merely "the HTTP call worked"
- Error codes `unsupported_provider` / `model_failure` / `timeout` / `error`; `MODEL_CHECK_TIMEOUT_SECONDS = 20`; latency returned on success
- Failures categorised via `chat/reasons.py`; **the provider's raw text is never returned** (it can carry the key) and the key is never logged
- Re-check of a saved config works: omit `api_key`, pass `config_id`, and the stored key is used

**What is missing:** the result is returned to the caller and thrown away. `ModelConfig` has no verification state, so nothing can expire.

**Add a fingerprint, not a flag:**

```
verified_at           datetime | null
verified_fingerprint  char(64) | null   # sha256(provider|model_id|api_base|api_key_ciphertext)

@property
def is_verified(self):
    return self.verified_at is not None and self.verified_fingerprint == self._fingerprint()
```

The check endpoint stores `verified_at` and the current fingerprint on success. Verification then expires **by itself** the moment provider, model_id, api_base or the key changes — no `save()` hook, no signal, nothing to forget, and it cannot be bypassed by an ORM update in a shell or a data migration. A flag plus invalidation logic always has a code path that forgets; a fingerprint compared at read time does not.

**Save policy:** enable Save on pass, **allow save-anyway**. An unverified row is harmless because `is_verified` reads false, and a briefly-down provider should not trap someone in a dialog. Surface it instead — "Not verified" on the model, a warning on personas pointing at it.

**Also:** expose `is_verified` and `verified_at` on `ModelConfigOut` so the UI needs no second call. **Rate-limit `/model-configs/check/` per company** — it makes outbound paid calls on user-supplied input, so uncapped it is an amplification vector.

**Generalises to `MCPServer`:** fingerprint over url + auth_type + `secrets_encrypted`, verified by "connect and list tools".

### 35 / 36

- **35.** Filesystem, code graph and data query are *bundled capability MCPs*: internal, activated by content type, model-driven, shipped with the product. 0.8.0 already has `is_internal` (migration 0017). Open: an admin **egress allow-list** for external MCP hosts at company scope, and visible indication when a project sends data off-box.
- **36.** `MEDIA_ROOT` is container-local disk — caps the product at one node and loses files on container replacement. An S3-compatible store (MinIO) for attachments, data files and exports also lets 34's two tiers read from the same place.

---

## 4. Blocking the list

1. **Sixteen items are unaudited against 0.8.0** — 5, 8, 9, 10, 11, 14, 15, 17, 18, 31 among them. Several may already exist, as 2, 25, 27 and 37 did. Audit before designing.
2. **Item 32's blocker:** per-request graph targeting in CodeGraphContext. Decides one service vs one process per project.
3. **Four defects are silent failures** (Appendix A: compaction target, dropped generation settings, no step cap, FAILED messages in history). Undecided whether they become constraints with tests or stay a defect list. Two of the four cannot be noticed without a test.
4. **`Status.CANCELLED` has no writer** — stopped runs land on `COMPLETED` with `metadata.stopped`. Decide whether the rebuild uses the status or keeps the flag.

**The items that decide the class structure:** 1, 13, 16, 26, 33. Items 2, 25 and 27 are answered by 0.8.0's shapes; 5 and 12 need auditing first.

---

## Appendix A — defects at 0.8.0 (verified 2026-10-07)

**Severe — silent quality loss**

- **Compaction squeezes every transcript to 3,686 tokens.** `token_target = max(max_tokens - 20_000, int(0.9 * max_tokens))` where `max_tokens` is `persona.model.max_tokens` — the **output** cap, default 4096. So `max(-15904, 3686)` = 3686, on every model regardless of a 200k window. `context_window_for()` exists and is used for the event payload but not here. [16]
- **`temperature` and `max_tokens` are dropped.** Nucleus deliberately moved them onto the persona (`internal/api.py:109` says so) but `model_from` still reads them off the model dict → always 0.7 / 4096. This is the cause of the line above. Temperature never reaches the model at all: `build_agent` passes no `model_settings`. [12, 16]
- **`max_steps` is dropped** by `persona_from`; `PersonaConfig` has no such field. `UsageLimits` appears zero times. **Nothing caps agent rounds** — `retries={"tools": 3, "output": 3}` is the only bound. [16]
- **FAILED messages re-enter the prompt as the model's own words.** `fail_ai_message` writes the user-facing sentence into `content`, and the history query filters no status — so the model reads *"The model provider rate-limited this request. Try again in a moment."* as something it said. [26]

**Dropped on the wire**

- `advisor_model` is sent and discarded — `PersonaConfig` has no field; the `Advisor` capability is reachable only through an opaque `capability_config`. [12]
- `supports_vision` is sent and discarded. [28]
- Only `capabilities[0]` is read, with bracket access that raises `KeyError` rather than degrading. A persona with two internal capability rows keeps one. [1, 3, 4, 17]
- `qualified_id` is composed server-side and unused; `build_model` re-derives it.

**History**

- `is_deleted_from_context` has a **writer** (`context/panel_providers.py:156`) and no reader in the history query — so remove-from-context has no effect on the prompt. [26]
- No status filter: all five statuses are admitted. `PENDING` rows are skipped only incidentally, by empty content. [26]
- `limit` has no server-side ceiling, unlike `list_messages` (`le=200`). [26]
- No `SUMMARY` type anywhere; `SummarizingCompaction` output is never persisted back. [6, 26]

**Usage / tenancy**

- `AIRequestLog` has **zero live writers** — `_post_ai_request_log` exists only in `litellm_runner.py`, which `AgentFactory` cannot reach. The endpoint's docstring still claims it is "called by nexus-ai after every model completion". [21]
- A **stopped run loses its usage**: published as three `None`s, because usage only arrives on `message_done`, which a stopped run never reaches. Cancelled runs' tokens go uncounted. [21, 37]
- `internal/api.py:443` picks the company with `Company.objects.filter(is_active=True).first()` rather than deriving it from the job — a single-tenant assumption in a multi-tenant product. Same pattern in eight other service modules. [21]
- No `cost` column; `ModelUsageLog` and its `cost_usd` were dropped in migration 0008 having never had a writer. [14, 21]

**Contract / dead code**

- `message_type` is never carried on `message_done`. AI rows stay `message_type="text"` permanently even when resolved as `chart` or `code`. [23, 25]
- `keepalive` is emitted by the worker and matched by no branch in the nucleus relay. `persist_internal_state` never reaches nucleus — the manager `continue`s past it. [25]
- `chat/tasks.py` is unreferenced dead code using a **different** channel (`topic:{id}`, colon) and vocabulary (`token`/`done`/`error`), and is the only writer of `Status.STREAMING`. [25]
- `Status.CANCELLED` has no writer. [37]
- Tool results have no size cap before entering the transcript — the 600-char cap is only the preview sent to nucleus, and the 50k cap is shell-only. `ClearToolResults` is the only backstop and fires after the fact. [16]
- `DeduplicateFileReads` keys only on `read_file`. [16]
- The per-persona `COMPACTION` capability route is unreachable — `_resolve_capabilities` reads only shell/thinking/web_search/web_fetch/filesystem. [16]
- `_MODEL_REGISTRY` has four providers; no `ollama`, no `google`. `openai_compatible` + `api_base` covers Ollama/vLLM/LM Studio, so this may be deliberate. [7]
- `api_base` is applied **only** when the provider class is `OpenAIProvider` — ignored for `anthropic` and `deepseek`. [7]
- Tool approvals are wired into the pydantic-ai runner only; `OPEN-ITEMS.md` notes LiteLLM would need its own gate. [2]
- `MEDIA_ROOT` is container-local disk. [36]
- `httpx.AsyncClient(timeout=120)` on both relay paths — survivable only because of the worker's 30s keepalive. [2, 16]

---

## Appendix B — framework seams (verified 2026-10-07)

A fresh `Agent` is built per trigger, so: **anything settled before the run is a construction parameter; anything that must change mid-run is a capability hook or a per-run override.**

| Seam | When | Items |
|---|---|---|
| `model=` | construction | 7, 12 |
| `instructions=` | construction | persona prompt, 32's scaffold |
| `capabilities=` | construction | 1, 2, 4, 16, 17, 32, 34 — bundles tools, hooks, instructions **and model settings** |
| `tools=` / `toolsets=` | construction | 5, 6, 13 |
| `model_settings=` | construction | 12, 15 — **currently passed as nothing at all** |
| `deps_type=` | construction | caller / topic / permitted set into tools |
| `retries=` | construction | the only loop bound today |
| `run_stream_events(message_history=…)` | run | 25 |
| model override on the run call | run | 13 — escalation needs no second Agent |
| `UsageLimits` | run | 16 — unused |
| `message_history: list[ModelMessage]` | run | 24, 26 — no prompt builder exists; we construct these |

**Mid-run pause is a capability hook, not deferred tools.** 0.8.0's `ToolApprovalGate` implements `prepare_tools` and `before_tool_execute` on a harness `AbstractCapability`, and awaits an HTTP poll of nucleus-held state. The pydantic-ai primitives `requires_approval`, `DeferredToolRequests`, `DeferredToolResults`, `ToolApproved`, `ToolDenied`, `CallDeferred` and `HandleDeferredToolCalls` appear **zero times** in the repo; `DECISIONS.md` records the substitution as deliberate. Earlier versions of this document assumed the deferred-tool route — that was wrong about the code, though the primitives remain available if the rebuild prefers them.

**`WrapperModel` exists** — `InstrumentedModel` and `ConcurrencyLimitedModel` are both instances of it. A custom subclass is a legitimate mechanism for item 11's tokens-per-minute enforcement. `ConcurrencyLimitedModel(model, limiter=N)` caps concurrent requests, not token rate.

**Usage is already modelled by the framework.** `UsageBase` carries `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cache_audio_read_tokens`, `details`, `total_tokens`, **`cost`** and **`cache_hit_ratio`**, plus `opentelemetry_attributes()`. `RunUsage` adds `requests` and `tool_calls`. 0.8.0 reads only `input_tokens` and `output_tokens` — cache fields and cost are available and unused, and `cache_hit_ratio` would let 15 prove caching works rather than assuming it.

**Telemetry is not the billing source.** `InstrumentedModel` emits OTel GenAI spans and takes standard `TracerProvider`/`MeterProvider`, so item 8 is not locked to Logfire's cloud. But spans are sampled and droppable. Central telemetry is deliberately **only two numbers** — instance count keyed by the existing `NEURALOPS_INSTALL_TOKEN`, and total tokens — documented and disableable by one env var, since the product is sold on nothing leaving the network. Per-project budgets (14) are a customer-side feature and separate.

**Stays ours (no framework equivalent).** pydantic-ai has no retrieval abstraction: `EmbeddingModel`, `VectorStore`, `ContextAdapter`, `ContextSource` and their factories; the content-type router (33); `AgentEvent` / `TriggerJob` / `PersonaConfig` (the wire contract with nucleus); the `output_types` registry; `AgentRunner`.
