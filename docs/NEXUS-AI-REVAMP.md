# NeuralOps Nexus — Nexus-AI Revamp

**Baseline:** `upstream/dev` @ `939af00` — "chore: server version 0.8.0". The fork was merged up to this on 2026-10-08 (was 0.2.0, 74 commits behind), so every status below describes the code on disk.
**Scope:** nexus-ai is being rebuilt. nucleus schema and API are largely kept — so "built" below is split by which side it lives on.
**Framework:** pydantic-ai + `pydantic-ai-harness` + `logfire` (observability, **nexus-ai only** — item 8). Logfire is the chosen backend, not a lock-in: `InstrumentedModel` takes any OTel `TracerProvider`/`MeterProvider`.
**Method:** finalize the list → settle each item in discussion → expand it here.
**Date:** 2026-10-08

Status values: **Built** (exists at 0.8.0) · **Partly built** · **Remaining** · **Settled** (our design, not yet built) · **Not audited** (status against 0.8.0 unverified) · **Dropped**.

> **This document is the prompt for every change to nexus-ai.** Read §1–§1.5 first: they hold the list, scope, layers, architecture decisions, APIs and the architecture reference (2026-10-09/10). **Where §1.1–§1.5 disagree with §3, §4, Appendix B/C or `docs/NEXUS-AI-REVAMP-SPEC.md`, §1.1–§1.5 win.** Those older sections describe the 0.8.0 analysis and an earlier design; they remain for their facts and reasoning, not as the target structure. **Paths:** old-code references written as `modules/nexus-ai/...` (and the `NA/` shorthand) mean the 0.8.0 code, which moves to `modules/nexus-ai-legacy/` when the rebuild starts (§1.3); the new code then lives at `modules/nexus-ai/`.

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

Sections 7–9 are written **per item, when that item is expanded** — the new architecture comes out of the settled items, not out of what 0.8.0 happens to do now. Where an item's §4 needs the current call path for contrast, it quotes only the part it touches.

**Not every class belongs to an item.** The request pipeline is where items 1, 13, 15, 16, 24, 26, 28, 33 and 34 all meet, and the classes that carry it are owned by no single one of them. Those live in **§3**, and each item's §7 names only what it adds to them. Without that, §7 would either duplicate the pipeline nine times or describe it nowhere.

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
| 5 | Model asks the user questions — built-in `ask_user` tool, pause and resume | **Partly built** — a prompt convention only; tool settled 2026-10-10, see §1.3 | nexus-ai |
| 6 | New topic button; summarize when prompt gets long | **Remaining** | both |
| 7 | Self-hosted / custom endpoints | **Built** — `api_base` → `base_url` | both |
| 8 | Logfire inside nexus-ai only | Not audited | nexus-ai |
| 9 | Persona call rights | **Built** — `persona.mention` + `persona.approve_run` | nucleus |
| 10 | Per-user rate limits on persona calls | **Remaining** — one precedent, hooks only | nucleus |
| 11 | Per-model rate limits | **Remaining** — `WrapperModel` is the seam | nexus-ai |
| 12 | Multiple models per persona | **Built** — own retry, not `FallbackModel` | both |
| 13 | Model choice by query depth | **Settled** — nothing exists | nexus-ai |
| 14 | Fixed budget per project | **Remaining** — blocked: no cost data anywhere | nucleus |
| 15 | Prompt / model caching | Not audited — constraints settled, see §4 | nexus-ai |
| 16 | Tool loop and context limits | **Settled** — tiers right, budget wrong | nexus-ai |
| 17 | Connectors | Not audited | both |
| 18 | Claude Agent SDK runtime | Not audited | nexus-ai |
| 19 | Tool activity visibility | **Built** — `tool_activity` / `_end` | both |
| 20 | Swarm — automatic persona handoff | **Dropped** — replaced by sub-agents | — |
| 21 | Usage recording | **Partly built** — 3 of 9 fields recorded | both |
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
| 35 | Bundled capability MCPs | **Partly built** — `is_internal` exists; rest not audited | both |
| 36 | Object storage for attachments | **Remaining** | both |
| 37 | Run cancellation | **Built** — but registered too late, see §4 | both |
| 38 | Concurrent runs in one topic | **Settled** | both |
| 39 | Provisioning MCP — agentic project setup | **Proposed** | both |
| 40 | Credential verification — Test button, fingerprinted | **Partly built** — only persistence missing | both |
| 41 | Terminal pane (`/terminal/ws`) | **Dropped** — removed from nexus-ai, see §1.1 | — |
| 42 | Browser pane (`/browser/ws`) | **Dropped** — removed from nexus-ai, see §1.1 | — |
| 43 | Message search for people (`/search/messages/`) | **Moved to nucleus** — plain DB search, see §1.1 | nucleus |
| 44 | Chat-message embeddings for the persona | **Remaining** — Layer 3, see §1.1 | nexus-ai |
| 45 | Persona chain under a supervisor persona (team workflow) | **Proposed** 2026-10-10 — Layer 6, see §1.3 | both |
| 46 | Delegation as tools: `escalate` (to the persona's deeper model) and `call_persona` (to another persona), with a `Handover` package | **Settled** 2026-10-10 (design) — see §1.3 | nexus-ai |
| 47 | Topic usage in the status bar: total tokens in and out per topic, live | **Settled** 2026-10-10 — Layer 0, see §1.3 | both |

**Real remaining work:** 1, 6, 10, 11, 13, 14, 16, 26, 32, 33, 34, 36, 39 — plus item 40's persistence, item 5's everything-but-the-convention, and Appendix A's defects.

**Still unaudited against 0.8.0 — six items:** 8, 15, 17, 18, 31, and the unverified half of 35. Audit before designing; several may already exist, as 2, 9, 25, 27 and 37 did.

### 1.1 Out of nexus-ai scope (settled 2026-10-09)

nexus-ai runs personas. Anything that does not is out. Whether terminal and browser come back at all, and where, is a later decision — not part of this rebuild.

- **41 Terminal, 42 Browser.** Neither touches a model, persona or the run pipeline: their only imports are config and ticket auth. The agent's own `Shell` capability is unrelated to the terminal pane, and the agent never drives the browser pane. The `"terminal"` output type (`output_types/types.py:250`) is a render type and stays. Removed from nexus-ai: `routers/terminal.py`, `routers/browser.py`, `managers/terminal.py`, `managers/browser.py`, `managers/tickets.py`, `tests/test_terminal.py`, `tests/test_browser.py`, `main.py:6,12-13`, `core/config.py:76-94`, `playwright` (`docker/dev/requirements.txt:27`). **Not yet read:** the nucleus side that issues tickets and offers the panes, the web-app panes, and the image's Chromium install step (`BROWSER=1`).
- **43 Message search, 44 Chat-message embeddings — revised 2026-10-10.** Chat is held two ways, for two different users:
  - **Text — nucleus.** Chat history stays as text in nucleus's database; only nucleus accesses that database. nexus-ai requests history from nucleus when it needs it (`GET /internal/topics/{id}/history/`, `NU/internal/api.py:469-513`).
  - **People searching (43) — nucleus, from the database.** The app's search box searches chat **text** in nucleus's DB, not chat vectors. `POST /search/messages/` leaves nexus-ai. Whether people search ever uses vectors is a later decision.
  - **The persona (44) — nexus-ai, chat vectors.** A vector copy of chat messages is kept by nexus-ai, in its own vector store (pgvector), for the persona's context. **Basic rule: the persona retrieves only from the topic it is answering in** — everyone in that topic can already see those messages, so nothing leaks across topics. Designed in Layer 3 with item 24. Still to settle there: who triggers embedding of each new message (today nucleus calls `embed_message_async`, `NU/chat/services.py:342`, posting to `/embed/message/` at `:390`); keeping vectors in step with edits, deletes and remove-from-context; purging secrets typed into chat; whether chit-chat is embedded at all.
  - Unchanged: nexus-ai's knowledge vectors — attached documents/files (`POST /embed/`, `DELETE /embed/context-source/{id}`) and recall (`POST /embed/recall/`, `DELETE /embed/recall/{id}`). `GET /directives/` (`routers/embed.py:28`) not yet read.

### 1.2 Build layers (agreed 2026-10-09)

Items are designed in **dependency order, not by number**. Each layer needs only the layers below it. Layer 0 is the core; each later layer adds classes to what already exists. Layers are discussed one at a time, in order; an item's placement can still move during that discussion.

**Seven layers, 0–6.** Layer 6 (Team Workflows) was added 2026-10-10 for persona chains (item 45). More layers only if new requirements fit none of these.

**Method per item:** design first, from the requirement — classes and sequence, without reference to 0.8.0. Then a short list of *copy candidates* from 0.8.0 (`file:line`), each accepted or rejected. Then the item is written here. nucleus may change where it matters; each item lists its nucleus changes separately.

The file columns below are **reference only** — where the requirement touches 0.8.0 today — not a commitment to reuse. `NA/` = `modules/nexus-ai/apps/`, `NU/` = `modules/nexus-nucleus/`. *(not read)* = cited elsewhere in this doc, not opened during the 2026-10-09 review.

#### Layer 0 — Core Turn
*A persona answers a plain text message, with no tools.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 25 | Event contract | `NA/schemas/trigger.py:261-428` · `NA/routers/trigger.py` · `NA/implementations/agents/stream_merge.py` · `NU/chat/services.py:847-1204` (relay) |
| 7 | Self-hosted / custom endpoints | `NA/implementations/agents/pydantic_ai_runner.py:77-82, 310-321` · `NA/managers/nucleus_client.py:52-62` · `NU/internal/api.py:98-122, 239-253` |
| 26 | History selection | `NA/managers/nucleus_client.py:179-241` · `NU/internal/api.py:469-513` · `NA/core/config.py:62` |
| 15 | Prompt / model caching | `NA/managers/prompt_builder.py:80-183` · `NA/implementations/agents/pydantic_ai_runner.py:240-250` |
| 37 | Run cancellation | none in nexus-ai · `NU/chat/services.py:993-1009, 1020, 1102-1113, 1752` · `NU/chat/stop_signals.py` *(not read)* |
| 21 | Usage recording — exact billing rules (§1.3) | `NA/implementations/agents/pydantic_ai_runner.py:214-227` · `NA/managers/model_info.py` · `NU/chat/services.py:519, 818-828` · `NU/internal/api.py:196-209, 435-466` |
| 47 | Topic usage in the status bar (tokens in / out, admins) | none |

#### Layer 1 — Tools
*The persona can use tools, safely.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 1 | Tool matching and the permitted set | `NA/implementations/agents/pydantic_ai_runner.py:253-302` |
| 3 | Persona tool / MCP list | `NU/internal/api.py:36-90, 290-376` · `NA/managers/nucleus_client.py:80-139` · `NA/schemas/trigger.py:213-220` |
| 4 | MCP scope: project / channel / topic | `NU/internal/api.py:349` · project-scope models *(not read)* |
| 2 | Tool permission before use | `NA/managers/approvals.py` · `NU/chat/services.py:599-799` · `NU/internal/api.py:393-400` |
| 19 | Tool activity visibility | `NA/implementations/agents/tool_events.py` · `NA/implementations/agents/pydantic_ai_runner.py:174-201` · `NU/chat/services.py:800-815, 1030-1044` |
| 22 | Execution sandboxing | `NA/schemas/trigger.py:90-177` · project bind-mount *(not read)* |
| 35 | Bundled capability MCPs | `NU/internal/api.py:36-59` · `NA/implementations/agents/pydantic_ai_runner.py:84-105` (unused registry) |

#### Layer 2 — Limits & Model Choice
*Which model answers, and how much it may spend.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 16 | Context budget and tool loop | `NA/implementations/agents/pydantic_ai_runner.py:257-273` · `NA/managers/model_info.py` |
| 12 | Multiple models per persona / fallback | `NA/managers/fallbacks.py` · `NU/internal/api.py:174` |
| 13 | Model choice by query depth | none · utility model only: `NU/internal/api.py:169, 371` · `NA/managers/nucleus_client.py:65-67` |
| 11 | Per-model rate limits | none |
| 10 | Per-user rate limits | none · `NU/scheduling/hooks.py:199` *(not read)* |
| 40 | Credential verification | `NA/managers/model_check.py` · `NA/routers/models.py` · `NU/intelligence/api.py:218` *(not read)* |
| 14 | Fixed budget per project | none |
| 46 | Delegation as tools — `escalate` here; `call_persona` used by Layer 6 | none |

#### Layer 3 — Knowledge & Data
*What the persona can look up besides the conversation.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 24 | Context retrieval / RAG | `NA/managers/prompt_builder.py:104-119` · `NA/factories/context_source.py` · `NA/interfaces/context_source.py` · `NA/implementations/context_sources/document/` |
| 31 | Vector store — pgvector | `NA/implementations/vectorstore/pgvector_store.py` · `NA/implementations/vectorstore/chroma_store.py` · `NA/factories/vectorstore.py` · `NA/core/config.py:35` |
| 33 | Content-type routing | `NA/factories/adapter.py` · `NA/implementations/adapters/code_adapter.py` · `NA/implementations/adapters/doc_adapter.py` |
| 28 | Attachments and vision | `NU/chat/services.py:1616-1661` · `NA/routers/embed.py:34` |
| 36 | Object storage for attachments | none |
| 32 | Code graph | none |
| 34 | Large CSV / data files — DuckDB | none |
| 44 | Chat-message embeddings for the persona (same-topic only) | `NU/chat/services.py:342-403` · `NA/routers/embed.py:53, 87` · `NA/implementations/context_sources/chat/` |

#### Layer 4 — Conversation Features
*How a conversation behaves over time.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 5 | Model asks the user questions — built-in `ask_user` tool; needs 27 for pause/resume | `NA/managers/prompt_builder.py:55-78` (prompt convention only) |
| 6 | New topic / summary | none |
| 23 | Output types and rendering | `NA/output_types/` (6 files) · `NA/managers/agentic_manager.py:86, 123-131` |
| 38 | Concurrent runs in one topic | none |
| 27 | Conversation state persistence | `NA/implementations/agents/pydantic_ai_runner.py:223-227` · `NA/managers/agentic_manager.py:116-119` |
| 29 | Scheduled runs | `NU/scheduling/` *(not read)* |

#### Layer 5 — Extensions
*Additions on top of a working product.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 17 | Connectors | none read |
| 18 | Claude Agent SDK runtime | none |
| 39 | Provisioning MCP | none |
| 8 | Telemetry | none · logging only: `NA/core/logging_config.py` |
| 9 | Persona call rights | `NU/authn/permissions/rights.py` *(not read)* — enforced in nucleus; nexus-ai only respects it |

#### Layer 6 — Team Workflows
*Several personas work on one task under a supervisor persona. Needs Layers 1, 2 and 4.*

| # | Requirement | Current files (reference) |
|---|---|---|
| 45 | Persona chain under a supervisor (e.g. requirements → architecture → classes → code → GitHub) | none · related: runbooks `NA/managers/runbooks.py` (unplaced) |

Candidates to place here when decided: **runbooks** and **preflight** (two of the five unplaced features).

#### Not in a layer

**Not yet placed — decide whether they are in the rebuild at all.** If they stay, they change the persona and the prompt before the model runs, which touches Layer 0's shape. The trigger payload already carries their fields (`preflight`, `approved_plan`, `interactive`, `routine_id`, `step_context` — `NU/chat/services.py:966-975`), so until decided nexus-ai must at least accept them.

| Feature | Current files (reference) |
|---|---|
| Preflight (plan before acting) | `NA/managers/preflight.py` |
| Routines | `NA/managers/routines.py` |
| Runbooks | `NA/managers/runbooks.py` |
| Recall | `NA/managers/recall.py` · `NA/implementations/context_sources/recall/` |
| Nudges | `NA/managers/nudges.py` |

**Dropped.**

| # | Item | Current files (reference) |
|---|---|---|
| 20 | Swarm | `NA/managers/agentic_manager.py:273-725` · `NA/routers/trigger.py:77-126` |
| 30 | Migration of existing data | none — DB is reset |
| 41–42 | Terminal, browser | §1.1 |
| 43 | Message search for people — moved to nucleus, not dropped | §1.1 |

**Item 0** (defects the rebuild must not inherit) is not a layer: each defect is checked against the item it belongs to.

### 1.3 Architecture and framework decisions (2026-10-09/10)

Decided in discussion. Anything marked *open* is not decided.

#### Approach

- **New module, final name from day one** (decided 2026-10-10). nexus-ai is rebuilt as a **new FastAPI project**:
  1. Tag the current code in git first (e.g. `nexus-ai-legacy-0.8.0`) — git history is the real backup.
  2. Rename the old folder to **`modules/nexus-ai-legacy/`**. It stays only as reference for copy candidates and as the running service until the new one is ready.
  3. Create the new code at **`modules/nexus-ai/`**.
  4. Docker Compose runs two services during the build: **`nexus-ai`** (built from `modules/nexus-ai-legacy/` for now — what nucleus talks to, so the product keeps working) and **`nexus-ai-dev`** (built from the new `modules/nexus-ai/`, for building and testing; nucleus can be pointed at it to test).
  5. **Switch-over** = change the `nexus-ai` service's build path to the new folder. nucleus does not change (it still calls `nexus-ai`). Rollback is the same one-line change back.
  6. When the new one is verified, the legacy folder is deleted.
  - Code is copied from the legacy module only when accepted as a copy candidate; it then belongs to the new module, with its tests. The new module never imports from the legacy one.
- **Network.** nucleus and nexus-ai run on the **same Docker network with fixed settings**. nexus-ai has **no public port** — no request from outside is accepted. The internal key check stays as a second lock.
- **Own architecture first, old code second.** Per item: design from the requirement → short list of copy candidates from 0.8.0 (`file:line`), each accepted or rejected → written here. Old code is reference, never the starting point.
- **nucleus may change.** The focus is nexus-ai, but nucleus is changed where it matters. Every item lists its nucleus changes separately.
- **Implementation handoff.** The architecture — classes, fields, method signatures with docstrings, sequence diagrams and acceptance tests — is designed here and reviewed by the owner. Claude Fable writes the method bodies against it. Handed over one layer (or one item) at a time, each reviewed before the next. A rules file in the new module tells the coding model: no files or classes outside the agreed structure, no signature changes without asking, no imports from the old module, pinned library versions only. Library versions are pinned before any code is written — **done 2026-10-10**, see §1.5 "Trial results and pinned versions" (0.8.0 pins nothing at all: `modules/nexus-ai/docker/dev/requirements.txt` and `docker/production/requirements.txt` have no version numbers).

#### Structure

- **The class diagram is independent of the web framework** (FastAPI or Django).
- **`ai_engine/pydantic_ai_system/`** — every pydantic-ai class lives here, **including the tools** (decided 2026-10-10: the simple option — the parts of tools that are not pydantic-specific move out only when a second AI system arrives). It knows nothing about FastAPI or Django. The name leaves room for a second system beside it later (e.g. item 18, Claude Agent SDK).
- **`ai_engine/context/`, `ai_engine/prompts/`, `ai_engine/vector_db/`** sit **beside** `pydantic_ai_system/` — they do not depend on pydantic-ai, so a later AI system can use them unchanged.
- **`fastapi_app/`** — the web side:
  - `contracts/` — plain data classes (pydantic models): `TriggerJob` in, `AgentEvent` out, and other request/response shapes. Framework-neutral; Django could use them too.
  - `routers/` — endpoints; each calls the AI system (`ai_engine/core`).
  - `factories/` — only if needed, for building/choosing engine classes.
- **`ai_engine` imports `fastapi_app/contracts`.** That dependency is accepted; the AI system yields `AgentEvent` directly, no conversion layer.
- **Separate modules** for **vector DB**, **prompts**, **context management** — placed as above.

#### Frameworks and tools

| Area | Decision | Notes |
|---|---|---|
| Model runtime / agent loop | **pydantic-ai** (MIT) | The only agent framework. No second one (LangChain, LlamaIndex, Letta, txtai agents/pipelines) |
| In-run context shrinking | **pydantic-ai-harness compaction** — `TieredCompaction` with `DeduplicateFileReads`, `ClearToolResults`, `ClampOversizedMessages`, `SummarizingCompaction`; `pin` to protect user-attached files; `WarnNearLimits` / `ReportContextUsage` | Model-agnostic, so it works for self-hosted models; provider-native compaction (`OpenAICompaction`, `AnthropicCompaction`) is single-provider. Pin a version that has these classes. A compaction lasts for the run only; carrying a summary to the next turn is ours (items 6, 26) |
| Context selection — what goes into the prompt | **Our own code** | History rules, summary anchor, budget fitting, cache order are product behaviour; no library fits a shared multi-persona chat |
| History ranking (item 26) | **Our own:** always keep the recent turns; label each message once on arrival (chit-chat vs substantive) and drop chit-chat from older history; never reorder | Label-once keeps the prompt prefix stable, so provider caching still hits (item 15). Similarity ranking against the current message only later, only on the older part. Layer 0 starts with recent turns + filters; ranking added after |
| Long-term memory | **Later**, with the Recall decision | Mem0 (Apache 2.0, supports pgvector) is the candidate if needed. Letta (competing runtime) and Zep/Graphiti (needs a graph DB) rejected |
| Vector store | **pgvector** | Postgres already runs; no extra service for self-hosters; tenant filtering is a SQL `WHERE` |
| Search on top of pgvector | **txtai** (Apache 2.0) — **decided 2026-10-10** (owner's decision), replacing the own-SQL option | Used *inside `ai_engine/vector_db/` only*, as `TxtaiVectorStore` behind our own `VectorStore` interface (`index` / `search` / `delete`): pgvector backend, `pgtext` keyword scoring, hybrid search, and later image/video embedding. Its LLM pipelines, workflows and agents are not used. **Setup checks** (to confirm, not to decide): tenant filtering by company/project/topic; all index state in Postgres (no local files, several workers share it); concurrent writes from several workers; image size (default install pulls PyTorch with CUDA; CPU-only build or `txtai_minimal` exist); **the per-company embedder drives txtai** — txtai either uses the company's `Embedder` or accepts vectors we produce (*unverified* that txtai accepts external vectors) |
| Billing source (item 21) | **pydantic-ai per-request usage (`RequestUsage`) + our own dated price table + our own `UsageRecord` ledger** — decided 2026-10-10 | `RequestUsage` gives per call: `input_tokens`, `cache_write_tokens`, `cache_read_tokens`, `output_tokens`, audio tokens, provider `details`, and a best-effort `cost`. **genai-prices** (Pydantic, MIT — the price data behind that `cost`) is used **only to pre-fill** our price table: it says its prices "will not be 100% accurate" and keeps no price history. It works offline from a bundled snapshot; it downloads updates **only if its updater is started** (`genai_prices.UpdatePrices`, or `pydantic_ai.prices.update_in_background()`, interval 3600 s) — we never start it (verified 2026-10-10). pydantic-ai's own `cost` is never the bill |
| Observability (item 8) | **OpenTelemetry tracing — not billing.** OpenLLMetry (Traceloop, Apache 2.0) considered 2026-10-10 | OpenLLMetry instruments the provider SDKs underneath pydantic-ai, while pydantic-ai already emits OTel traces itself — using both gives two traces per call, so pick one. Traces are sampled and droppable, so they never feed billing (Appendix B). Choice of tracer: *open*, decided with item 8 |
| GPU | **Not required.** CPU is the default | Search runs on CPU in Postgres; text embedding runs on CPU. A GPU is an optional speed-up, mainly for future image/video embedding |
| Prompts | **Jinja2** templates as files in the prompts module + **our own prompt layout** | Layout gives each section a priority and drops lowest-priority sections first when the budget is short (the idea from Cursor's Priompt, which is TypeScript-only). POML, BAML rejected |
| Prompt tuning | **Ourselves.** DSPy rejected | promptfoo (prompt regression tests) is a later option |
| Code context (item 32) | **CodeGraphContext** + filesystem grep/read + a repo-map-style outline (the Aider idea) | Serena only if its GPL-3.0 licence is acceptable for a shipped product. No code embeddings |

#### Embedder — configurable per company, local by default

- **Default: local.** Embeddings are computed inside the deployment on CPU (today fastembed with `nomic-ai/nomic-embed-text-v1.5`, `modules/nexus-ai/apps/core/config.py:29-30`), so nothing leaves the network.
- **A company can change the embedder in its company settings** — e.g. a remote provider or a self-hosted endpoint. nucleus already models this per company: `AIConfigInternal` carries `embedding_provider`, `embedding_model`, `embedding_base_url` (`NU/internal/api.py:211-215`), served at `GET /internal/companies/{id}/ai-config/` (`:516-536`).
- **Consequences the design must handle:**
  - **Vectors from different models do not mix.** A query must be embedded with the same model that produced the stored vectors. Every stored vector records the embedding model (and its dimension).
  - **Changing the embedder means re-embedding** that company's stored content. Until re-embedding finishes, search must keep using the old model's vectors (or say it is unavailable) — never compare across models.
  - **Dimensions differ by model,** so the pgvector schema must allow per-model dimensions (e.g. one table or column per model).
  - **A remote embedder sends text off-box** — the settings UI should say so; and its API key is a secret, stored encrypted like model keys.
  - *Open:* where the re-embedding job runs and how progress is shown.

#### Entry point and request flow

- **The router stays thin.** It asks **`AISystemFactory.create(kind)`** for the AI system and calls one method on it. **`AISystem`** is the interface (or interfaces) exposing what the whole AI system offers; **`PydanticAISystem`** is the only implementation today. A later system (e.g. Claude Agent SDK, item 18) implements the same interface. *Open:* one `AISystem` interface, or several small ones (e.g. answer a message, check a model, embed).
- **`PydanticAISystem`** runs the steps of a reply: load the persona, gather context, hand over to the engine, record usage in its cleanup on every ending.
- **Stream guard on the web side** (decided): `EventStream` in `fastapi_app` makes three promises about every reply stream — a keepalive after 30 s of silence so nucleus does not give up; **exactly one final event** (done or error); a crash becomes a clean `message_error`, never a dropped connection. It wraps whatever stream the AI system returns, so every AI system gets them.
- **Names decided:** **`ReplyGenerator`** (was `TurnRunner`), **`ReplyRequest`** (was `TurnRequest`), **`HistoryMessage`** (was `Turn`).
- **The five unplaced features in Layer 0:** nexus-ai **accepts** their trigger fields (`preflight`, `approved_plan`, `interactive`, `routine_id`, `step_context`) **and ignores them**. Whether each feature returns is decided later.
- **nucleus changes needed for Layer 0** (agreed): (1) a **new usage endpoint** with all fields (item 21) and topic totals (item 47); (2) a **status field** in the history endpoint so failed/pending rows can be filtered; (3) **model roles** — until nucleus has roles (Layer 2), the persona's main model maps to `STANDARD` and its fallback models to `FALLBACK`.
- **The persona is unfolded fully from day one.** `PersonaSpec` holds **all** the persona's models, each with a role (router/cheap, standard, deep/costly, fallback…), and its tools with their permission levels — even though Layer 0 uses one model. This avoids redesigning `PersonaSpec` in Layer 2.
- **Full request flow** (Layer 0 is the simple-path spine; later layers add branches at fixed points):
  1. Load the persona and unfold it (all models with roles; tools and levels).
  2. Gather context: chat history from nucleus; vector DB search (documents, recall, same-topic chat vectors).
  3. Tool pre-check before any model call, from cache or keywords.
  4. The router (cheap) model handles the query:
     - simple, no tools → the router answers;
     - needs tools → read tools run if already permitted or cached in the topic, otherwise ask once; **write tools always ask**;
     - complex → the router calls the `escalate` tool and the deep model takes over (decided *while trying*, not by pre-classification). An event tells nucleus that a deeper model is taking over, and the deep model's answer **streams straight to nucleus**.

#### Everything beyond text is a tool

The model does anything other than write text **through a tool**. That gives one permission system, one activity trail (item 19), one usage record (item 21) and one set of limits (item 16) for all of it.

| Tool | Called by | Does | Result |
|---|---|---|---|
| `escalate` (item 46) | the router model | hands the question to the persona's **own** deeper model, with a `Handover` | **Hand over** (decided): an event announces the deeper model, then its answer streams straight to nucleus; the router stops. Written once, so cheaper |
| `call_persona` (item 46) | a supervisor persona | runs **another persona** on a sub-task, with a `Handover` | always **returns** — the supervisor must review it |
| `ask_user` (item 5) | any persona, interactive runs only | asks the person 1–4 questions (2–4 options each, multi-select, free-text "Other") | the person's answer, as the tool result |

**`Handover` — the context passed to a delegated model or persona** (a small data class, never the whole history): `task`, `summary` (what is known so far, written by the caller), `references` (files / documents / message ids to read), `constraints`, `expected_output`. In a persona chain the references are the previous stage's files.

**Rules for delegation:** inner runs act with the **caller's** rights, and their write tools still ask; inner usage is added to the parent run and recorded per persona and model; **depth limit** — supervisor → worker, workers do not call further personas (or at most one level deeper); limits on number of calls and budget. Switching to another model loses the provider cache, so the `Handover` is kept small. pydantic-ai supports an agent calling another agent from inside a tool, with usage counted into the outer run — confirm the API against the pinned version.

**`ask_user` rules:** only the person who started the run answers; others see the card read-only. Never asks for secrets (keys and passwords go through settings / connection screens). Not offered in scheduled or unattended runs — the persona states its assumption instead. Inside a chain, a question from a worker goes up to the user and the whole chain pauses. Questions expire (e.g. 24 h); the run then ends with what it has. Today only a prompt convention exists (`<<<OUTPUT:choice>>>`) — no tool, no pause, no answer path.

**Pause and resume, not an open connection.** `ask_user`, long approvals and chains **save the run's state and end the stream**, then **resume from where they stopped** when the answer arrives. This makes **item 27 (state persistence) a dependency of items 5 and 45**. pydantic-ai's deferred-tool feature (`DeferredToolRequests`, `DeferredToolResults`, `CallDeferred`) is the likely mechanism — the names exist in the pinned 2.55.0 (verified 2026-10-10; behaviour not yet tried). The pinned harness 0.55.0 also ships a ready-made ask-user capability (`pydantic_ai_harness.ask_user`: `AskUser`, `AskUserToolset`, tool name `ask_user_question`) — a candidate for item 5, decided in Layer 4.

#### Billing — exact usage recording (item 21, Layer 0)

Billing must be exact. Rules:

- **Record per model call, not per reply.** One reply can include several calls (router, escalation, tool loops, sub-personas); each is recorded with its own model and role.
- **Every token type, priced separately:** uncached input; cache read; cache write 5-minute; cache write 1-hour (Anthropic prices the two writes differently); output. Reasoning/thinking tokens are recorded but are **already inside output** — priced once, as output, never added on top.
- **How pydantic-ai counts (verified in the trial, 2026-10-10 — this decides the formula):**
  - `input_tokens` is the **whole** input, **including** cache read and cache write. Anthropic reply with 200 new + 500 cache-write + 1000 cache-read → `input_tokens=1700`; OpenAI reply with 1200 prompt tokens of which 1000 cached → `input_tokens=1200`, `cache_read_tokens=1000`.
  - `output_tokens` **includes** reasoning (OpenAI 300 completion tokens of which 120 reasoning → `output_tokens=300`).
  - So: **uncached input = `input_tokens` − `cache_read_tokens` − `cache_write_tokens`**; **cache write 1h** = `cache_write_1h_tokens` (Anthropic) and **cache write 5m** = `cache_write_tokens` − 1h. Pricing `input_tokens` at the input rate would overcharge every cached call.
  - `cache_write_1h_tokens` and `output_reasoning_tokens` are **not declared fields** of `RequestUsage`: the provider code sets them only when the provider reports them. Read them as "absent means 0", with the raw numbers in `details` (`ephemeral_1h_input_tokens`, `reasoning_tokens`) as the cross-check.
- **The provider's own counts** from its response are the source — never an estimate when the provider reports a number.
- **Stopped and cut replies (verified 2026-10-10):** a cut stream raises **no error** in pydantic-ai. OpenAI-shaped: the reply looks finished (`finish_reason` reads `stop`) but every count is 0. Anthropic-shaped: `finish_reason` is empty and `output_tokens=1` (the provisional count from the stream's first event); input counts are real. A client disconnect cancels the run (`CancelledError`) and pydantic-ai has no final usage at all. **Rule:** a call's usage is **estimated** when the run was cancelled, or `finish_reason` is empty, or input and output are both 0. Then: keep any input/cache counts the provider did send; estimate output from the text actually received; estimate input from the request when the provider sent none; set `estimated = true`.
- **Tiered prices.** A model's price can depend on prompt size (genai-prices prices Claude Sonnet 4.5 at $6 / $22.50 per million instead of $3 / $15 above 200k input tokens). The price table must allow a price per size tier.
- **Prices:** each model has a price per token type; a price change is a new dated entry; the cost is **calculated and frozen at the time of the call**, together with the prices used, so old bills never change.
- **Exact money arithmetic** — decimals, never floating point.
- **Everything that costs money is recorded,** each with a kind: chat reply, router call, escalation, sub-persona, summary, model check, remote embedder.
- **Local models** are recorded with their tokens at price 0.
- **Every record carries:** company, project, topic, persona, user, message, model, role, kind, estimated flag.
- **Tests with known numbers:** a fixed usage and a fixed price give an exact expected cost.
- **Where the numbers come from (decided 2026-10-10):** token counts from pydantic-ai's per-request `RequestUsage` (one per model call, not the run total); prices from **our own** dated price table, pre-filled from genai-prices and editable by admins; cost computed by us. Not from OpenLLMetry or any tracing, and not from pydantic-ai's best-effort `cost`.
- *Open:* where the price table is stored (nucleus owns the database) and how admins edit it.

#### Topic usage in the status bar (item 47, Layer 0)

- **Shown per topic:** **tokens in** = sum of `input_tokens` (already includes cache read and cache write) and **tokens out** = sum of `output_tokens` (already includes reasoning) — corrected 2026-10-10 after the trial; adding cache or reasoning on top would double-count. **Tokens only** for now; cost can be added later without redesign, since cost is recorded with every call.
- **Who sees it:** admins only (project admins and company admins/owners, using nucleus's existing roles).
- **Budget:** **one budget per project** (item 14) — no topic budgets. The topic bar shows usage only.
- **How:** nexus-ai records every call with its `topic_id` (everything rolls up to its topic: replies, router, escalations, sub-personas, summaries, tool loops, parallel runs); nucleus adds each record to the topic's running totals and pushes the new totals on the topic's live channel after each reply; for long runs (chains, long tool loops) nexus-ai also sends usage **during** the run, so the bar grows live.

#### Persona chains under a supervisor (item 45, Layer 6)

- **Example team:** supervisor; requirements & documentation; architecture; classes; code; GitHub repository & push. Result: a whole project foundation.
- **A fixed sequence of stages, the supervisor as gatekeeper.** The supervisor reviews each stage's output against criteria: approve, send back with notes, or ask the user (`ask_user`). It does not invent the order on the fly.
- **Documents, not conversations, between stages.** Each persona writes its output as files in the project folder (`requirements.md`, `architecture.md`, class stubs, code); the next persona reads them via `Handover.references`.
- **Bounded review loops** (e.g. at most 2–3 revisions per stage, then the supervisor must ask the user).
- **A long-running background job, not a chat reply,** with a checkpoint per stage so a failure restarts from that stage. Each finished stage posts into the topic.
- **Writes always ask** — creating the repository and pushing code need user approval (item 2) and the user's own credentials (item 17).
- **Cost visible and capped** for the whole chain (items 14, 16, 21); supervisor can use a deep model, workers a standard one.
- **Why this is not the dropped swarm (item 20):** the supervisor is in charge; the user picks the team; context passes as documents; every step acts with the caller's rights.

#### Chat history

- **Text in nucleus.** Chat history stays as text in nucleus's database; only nucleus accesses it. nexus-ai requests it (`GET /internal/topics/{id}/history/`).
- **People search (43) is nucleus's**, over the text in its DB — not chat vectors (may be revisited later).
- **Persona chat vectors (44) are nexus-ai's**, in its vector store. Basic rule: **same topic only.** Designed in Layer 3.

### 1.4 APIs between nucleus and nexus-ai (read from code 2026-10-10)

Both directions as they exist at 0.8.0, with what each becomes under the decisions above. Paths without a prefix: nexus-ai files are under `modules/nexus-ai/apps/`, nucleus files under `modules/nexus-nucleus/`.

#### nucleus → nexus-ai

All calls go to one setting, `NEXUS_AI_URL` (`core/settings.py:167`), with header `X-Internal-Key`.

| # | Endpoint (nexus-ai) | Defined at | Called from (nucleus) | Purpose | Fate |
|---|---|---|---|---|---|
| 1 | `POST /api/v1/trigger/` | `routers/trigger.py:95` | `chat/services.py:1000` (`trigger_ai_response_async`) | A persona replies; SSE stream back | **Keep** — the core (Layer 0) |
| 2 | `POST /api/v1/trigger/swarm/` | `routers/trigger.py:114` | `chat/services.py:1339` (swarm relay) | Swarm run | **Drop** with item 20 — needs a nucleus change |
| 3 | `POST /api/v1/models/check/` | `routers/models.py:22` | `intelligence/services.py:146` (`check_model_config`) | Test a model key before saving | **Keep** — item 40 (Layer 2) |
| 4 | `POST /api/v1/embed/` | `routers/embed.py:34` | `context/services.py:219` (`_embed`) | Embed an attached file / web source | **Keep** — knowledge vectors (Layer 3) |
| 5 | `DELETE /api/v1/embed/context-source/{collection_id}/` | `routers/embed.py:43` | `context/services.py:247` (`_delete_collection`) | Remove a detached source's vectors | **Keep** (Layer 3) |
| 6 | `POST /api/v1/embed/recall/` | `routers/embed.py:74` | `intelligence/recall.py:148` (`_embed_now`) | Embed a recall entry | **Keep if Recall stays** (unplaced) |
| 7 | `DELETE /api/v1/embed/recall/{entry_id}/` | `routers/embed.py:80` | `intelligence/recall.py:168` (`_delete_now`) | Remove a recall entry's vector | **Keep if Recall stays** |
| 8 | `POST /api/v1/embed/message/` | `routers/embed.py:87` | `chat/services.py:390` (`embed_message_async`), started from `chat/services.py:1191` (AI reply), `:1437` (swarm reply), `chat/api.py:223` (human message) | Embed a chat message | **Keep, reshaped** — persona chat vectors, same topic only (item 44, Layer 3) |
| 9 | `DELETE /api/v1/embed/message/{message_id}/` | `routers/embed.py:53` | `context/panel_providers.py:178` (`_delete_message_vector`) | Remove a message's vector (remove-from-context) | **Keep** with item 44 |
| 10 | `POST /api/v1/search/messages/` | `routers/search.py:44` | `chat/search.py:83` (`semantic_ids`) | People's message search | **Move to nucleus** as a DB search (item 43) |
| 11 | `GET /api/v1/directives/` | `routers/embed.py:28` | `context/api.py:71` (`list_directives`) | List `@directives` with help text | **Undecided** — not yet discussed |
| 12 | `WS /api/v1/terminal/ws` | `routers/terminal.py:38` | not nucleus — the web app connects directly with a ticket signed by nucleus (`workspace/services.py:81-130`) | Terminal pane | **Drop** (item 41) |
| 13 | `WS /api/v1/browser/ws` | `routers/browser.py:42` | not nucleus — web app, ticket from `workspace/services.py:133-167` | Browser pane | **Drop** (item 42) |

#### nexus-ai → nucleus

All calls go to `NEXUS_NUCLEUS_URL` (nexus-ai `core/config.py:55`), with header `X-Internal-API-Key`. Endpoints are defined in nucleus `internal/api.py`.

| # | Endpoint (nucleus) | Defined at | Called from (nexus-ai) | Purpose | Fate |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/internal/personas/{id}/` | `internal/api.py:290` | `managers/nucleus_client.py:43` | Persona setup: prompt, models, tools, levels, fallbacks | **Keep, extend** — all models with roles (Layer 0 shape, used from Layer 2) |
| 2 | `GET /api/v1/internal/topics/{id}/history/` | `internal/api.py:469` | `managers/nucleus_client.py:194` | Recent chat history | **Keep** — item 26 (Layer 0); needs a status field for the filters |
| 3 | `GET /api/v1/internal/messages/{id}/approvals/{call_id}/` | `internal/api.py:393` | `managers/approvals.py:178` | Poll a tool-approval decision | **Keep, rework** — item 2 (Layer 1); pause and resume instead of polling |
| 4 | `GET /api/v1/internal/messages/{id}/nudges/` | `internal/api.py:403` | `managers/nudges.py:29` | Collect notes added to a running reply | **Keep if Nudges stays** (unplaced) |
| 5 | `GET /api/v1/internal/routines/{id}/` | `internal/api.py:379` | `managers/nucleus_client.py:160` | Load a routine | **Keep if Routines stays** (unplaced) |
| 6 | `POST /api/v1/internal/recall/` | `internal/api.py:550` | `managers/nucleus_client.py:169` | Save what a reply learned | **Keep if Recall stays** (unplaced) |
| 7 | `POST /api/v1/internal/ai-request-logs/` | `internal/api.py:435` | `implementations/agents/litellm_runner.py:505` **only** — a dead path | Usage log | **Replace** — new usage endpoint for item 21 (Layer 0) |

**Offered by nucleus, never called by nexus-ai today:**

| Endpoint | Defined at | Note |
|---|---|---|
| `GET /api/v1/internal/topics/{id}/contexts/` | `internal/api.py:410` | Unused — nucleus pushes context sources inside the trigger job instead (`chat/services.py:949-962`) |
| `GET /api/v1/internal/companies/{id}/ai-config/` | `internal/api.py:516` | Unused today; **needed** for the per-company embedder setting |

#### New endpoints the design already implies (not built)

| Direction | Purpose | Item |
|---|---|---|
| nexus-ai → nucleus | Record usage with all fields (replaces `ai-request-logs`) | 21 |
| nexus-ai → nucleus | Save and load paused run state (for `ask_user`, approvals, chains) | 27 (for 5, 45) |
| nucleus → nexus-ai | Resume a paused run with the user's answer | 5, 27 |
| nexus-ai → nucleus | Company settings incl. the embedder choice (the existing `ai-config` may cover it) | embedder decision |

**Note:** the two directions use different header names for the same internal key (`X-Internal-Key` vs `X-Internal-API-Key`) — harmless, worth unifying when nucleus is changed anyway.

### 1.5 Architecture reference — the new nexus-ai (2026-10-10)

The target structure. Anything marked *open* or *proposed* is not decided. Layer tags (L0–L6) say when a class arrives (§1.2).

#### Basis

- **A separate AI system behind an interface.** nucleus starts a request for a persona (by persona id). The web layer does not know how the AI works: it asks **`AISystemFactory`** for an **`AISystem`** and calls it. **`PydanticAISystem`** is the only implementation today; a later one (e.g. Claude Agent SDK, item 18) implements the same interface, and the factory chooses. *Open:* one `AISystem` interface or several small ones (answer a message, check a model, embed).
- **Framework-independent engine.** Everything under `ai_engine/` is plain Python: no FastAPI, no Django. The class diagram is drawn without reference to the web framework.
- **Thin web layer.** `fastapi_app/` only receives requests, calls the AI system, and returns results. Contracts are plain pydantic data classes that any framework could use.
- **Everything the model does beyond text is a tool** (§1.3).

#### Folder structure

```
modules/nexus-ai/                  (old code: modules/nexus-ai-legacy/)
  fastapi_app/
    routers/        TriggerRouter (+ model check, embed routers)
    contracts/      TriggerJob, AgentEvent and other request/response data classes
    stream/         EventStream — the stream guard
    factories/      only if needed
  ai_engine/
    core/           AISystemFactory, AISystem (interface), PydanticAISystem, NucleusClient
    context/        ContextBuilder, HistoryPolicy, HistoryLabeler, Retriever, BudgetFitter
    prompts/        PromptLayout, PromptTemplates (+ Jinja2 template files), PromptPlan, PromptSection
    vector_db/      VectorStore, TxtaiVectorStore, Embedder, LocalEmbedder,
                    RemoteEmbedder, EmbedderFactory, SearchQuery
    pydantic_ai_system/
                    ReplyGenerator, AgentBuilder, ModelFactory, MessageConverter,
                    EventMapper, UsageReader
      tools/        ToolRegistry, EscalateTool, CallPersonaTool, AskUserTool, Handover
```

#### Dependency rules

1. `fastapi_app` imports `ai_engine`. `ai_engine` imports only `fastapi_app/contracts` (accepted) — never FastAPI or Django.
2. **Only `ai_engine/pydantic_ai_system/` (including its `tools/`) imports pydantic-ai or pydantic-ai-harness.**
3. **Only `NucleusClient` calls nucleus.**
4. **Only `vector_db/` touches pgvector or txtai.** Everything else uses the `VectorStore` and `Embedder` interfaces.
5. **The router makes one call** into the AI system; the steps of a reply live in `PydanticAISystem`.
6. Nothing imports from `modules/nexus-ai-legacy/`.

#### Class catalog

| Class | Module | Layer | Responsibility | Key methods |
|---|---|---|---|---|
| `TriggerRouter` | fastapi_app/routers | L0 | Receive the trigger job, get the AI system, return the stream | `trigger(job)` |
| `EventStream` | fastapi_app/stream | L0 | Guard every stream: keepalive on silence, **exactly one final event**, unexpected errors become one `message_error` *(proposed: on the web side, so every AI system gets it)* | `wrap(events)` |
| `AISystemFactory` | ai_engine/core | L0 | Return the AI system to use | `create(kind)` |
| `AISystem` | ai_engine/core | L0 | Interface: what the AI system offers | `respond(job) → stream of AgentEvent` |
| `PydanticAISystem` | ai_engine/core | L0 | Runs one reply: load persona, gather context, build the prompt, hand over to the engine, record usage in its cleanup on every ending | `respond(job)` |
| `NucleusClient` | ai_engine/core | L0 | Every call to nucleus | `get_persona`, `get_history`, `get_company_settings`, `record_usage` |
| `ContextBuilder` | ai_engine/context | L0, grows L3 | Gather everything a reply needs: history (L0), retrieval (L3) | `gather(job, persona) → ContextBundle` |
| `HistoryPolicy` | ai_engine/context | L0 | Choose which history messages go into the prompt (filters, recent window, attribution) | `select(rows) → list of HistoryMessage` |
| `HistoryLabeler` | ai_engine/context | later | Label each message once on arrival: chit-chat or substantive | `label(message)` |
| `Retriever` | ai_engine/context | L3 | Search knowledge (documents, recall) and same-topic chat vectors | `documents(...)`, `topic_chat(...)` |
| `BudgetFitter` | ai_engine/context | L2 | Trim a prompt plan to the model's budget, dropping lowest-priority sections first | `fit(plan, budget)` |
| `PromptLayout` | ai_engine/prompts | L0 | Build the prompt as ordered sections: stable first (cache-friendly), system prompt once | `build(persona, bundle, message) → PromptPlan` |
| `PromptTemplates` | ai_engine/prompts | L0 | Render Jinja2 template files | `render(name, values)` |
| `VectorStore` | ai_engine/vector_db | L3 | Interface: index, search, delete vectors | `index`, `search(SearchQuery)`, `delete` |
| `TxtaiVectorStore` | ai_engine/vector_db | L3 | The vector store (decided 2026-10-10): txtai on pgvector — similarity + `pgtext` keyword, hybrid, filtered by company/project/topic; uses the company's embedder (§1.3) | `index`, `search`, `delete` |
| `Embedder` | ai_engine/vector_db | L3 | Interface: text → vectors; reports its model id | `embed(texts)`, `model_id()` |
| `LocalEmbedder` / `RemoteEmbedder` | ai_engine/vector_db | L3 | Local (default) or a company-chosen remote embedder | — |
| `EmbedderFactory` | ai_engine/vector_db | L3 | Pick the embedder from company settings | `for_company(settings)` |
| `ToolRegistry` | ai_engine/pydantic_ai_system/tools | L1 | Decide which tools a persona gets for this run, with their permission levels | `tools_for(persona, job)` |
| `EscalateTool` | ai_engine/pydantic_ai_system/tools | L2 | Hand the question to the persona's deeper model; its answer streams straight to nucleus (item 46) | — |
| `AskUserTool` | ai_engine/pydantic_ai_system/tools | L4 | Ask the person questions; pause and resume (item 5) | — |
| `CallPersonaTool` | ai_engine/pydantic_ai_system/tools | L6 | Run another persona on a sub-task for a supervisor (item 46) | — |
| `ReplyGenerator` | ai_engine/pydantic_ai_system | L0 | Produce one reply with pydantic-ai: build agent, convert messages, stream, collect usage | `generate(request)`, `usage_records()`, `full_text()` |
| `AgentBuilder` | ai_engine/pydantic_ai_system | L0 | Build the pydantic-ai agent for a persona and model role (system prompt through **`instructions=`, never `system_prompt=`** — see trial results; temperature, output limit; tools from L1) | `build(persona, role, instructions)` (L1 adds tools) |
| `ModelFactory` | ai_engine/pydantic_ai_system | L0 | Model config → pydantic-ai model; every provider gets its endpoint | `build(spec)` |
| `MessageConverter` | ai_engine/pydantic_ai_system | L0 | Prompt plan → pydantic-ai messages and the single instructions string (decides nothing) | `to_messages(history)`, `instructions(plan)` |
| `EventMapper` | ai_engine/pydantic_ai_system | L0 | pydantic-ai stream events → `AgentEvent`, text in small batches | `map(event)`, `flush()`, `text()` |
| `UsageReader` | ai_engine/pydantic_ai_system | L0 | Read every usage figure **per model call** from pydantic-ai's `RequestUsage` (not the run total, not its `cost`), split into the priced token types and flagged estimated by the rule in §1.3 Billing; prices and cost are applied by our price table | `read(response, request_messages, received_text, cancelled, base)` |

#### Data classes

| Class | Holds |
|---|---|
| `TriggerJob` (contract) | What nucleus sends: job id, message id, persona id, topic id, the message being answered, text, and the fields of unplaced features |
| `AgentEvent` (contract) | What goes back: start, text delta, tool activity, done (with full text and `UsageRecord`), error |
| `PersonaSpec` | Persona as nexus-ai uses it: id, name, system prompt (with project brief), temperature, output limit, **all models with roles**, tools with levels; `model_for(role)`. Every field nucleus sends has a place |
| `ModelSpec` | One model: role, provider, model id, endpoint, key, **context window** (kept separate from the persona's output limit) |
| `ModelRole` | `ROUTER`, `STANDARD`, `DEEP`, `FALLBACK` |
| `ToolSpec` | Tool id and permission level (`auto`, `ask`, `off`) |
| `HistoryRow` | One raw history row as nucleus sends it |
| `HistoryMessage` | One selected history message: role, author, text |
| `ReplyRequest` | Everything one reply needs: persona, history, new message |
| `ContextBundle` | What `ContextBuilder` gathered |
| `PromptPlan` / `PromptSection` | The prompt as ordered sections; each has kind, priority, stable flag, text |
| `SearchQuery` / `SearchHit` | A vector search with company, project, topic, sources, top_k; and one result |
| `Handover` | Context passed to a delegated model or persona: task, summary, references, constraints, expected output |
| `UsageRecord` | One model call's usage: who/where (company, project, topic, persona, user, message), model and role, kind; token counts (input total, uncached input, cache read, cache write 5m, cache write 1h, output total, of which reasoning); finish reason; estimated flag; cost frozen with the prices used. Field list: §1.5 Layer 0 spec |

#### Layer 0 — one plain reply, step by step

1. nucleus saves the message, creates the empty reply (PENDING) and calls `POST /api/v1/trigger/` with a `TriggerJob`.
2. `TriggerRouter` asks `AISystemFactory` for the AI system and calls `respond(job)`; `EventStream` guards the stream.
3. `PydanticAISystem` sends `message_start`.
4. `NucleusClient.get_persona` → `PersonaSpec` (all models with roles; Layer 0 uses `STANDARD`).
5. `ContextBuilder` → `NucleusClient.get_history` → `HistoryPolicy.select` → list of `HistoryMessage`.
6. `PromptLayout.build` → `PromptPlan` (stable sections first, system prompt once).
7. `ReplyGenerator.generate`: `AgentBuilder` (with `ModelFactory`) builds the agent; `MessageConverter` turns the plan into messages; the agent streams from the LLM; `EventMapper` turns chunks into batched `message_delta` events.
8. `UsageReader` reads every usage figure into a `UsageRecord`.
9. In its cleanup (runs on every ending): `PydanticAISystem` records usage through `NucleusClient`, then sends `message_done` with the full text and usage.
10. nucleus saves the reply and marks it COMPLETED.

- **Stop:** nucleus closes the connection; everything is cancelled; the cleanup still records partial usage; nucleus keeps the partial text as stopped.
- **Failure:** the cleanup records whatever usage happened; exactly one `message_error` is sent; nucleus marks the reply FAILED.

#### Trial results and pinned versions (2026-10-10)

A throwaway trial ran the libraries against a fake model server that answers exactly like OpenAI's and Anthropic's streaming APIs and records every request body. No product code; nothing in the repo. Findings are written into the sections they affect (§1.3 Billing, status bar, class catalog, invariants).

| # | Check | Result |
|---|---|---|
| A1 | All packages install together | **Pass** — `pip check` clean |
| A2 | Provider classes | **Pass** — `OpenAIChatModel`, `OpenAIResponsesModel`, `AnthropicModel`, `GoogleModel`, `OllamaModel`; a custom `base_url` works (Ollama-style endpoint served the call) |
| A3 | Stream events, in order | `PartStartEvent` → `FinalResultEvent` → `PartDeltaEvent` ×n → `PartEndEvent` → `AgentRunResultEvent`. `run_stream_events(...)` is an **async context manager** in 2.55 (`async with agent.run_stream_events(...) as run:`); `run.usage` is a **property**, not a method |
| A4 | Usage per model call | **Pass** — each `ModelResponse.usage` is that call's `RequestUsage`; `RunUsage` is the run total. Counting semantics: see §1.3 Billing |
| A5 | Cut stream | **No error raised.** OpenAI-shaped: counts all 0, `finish_reason` reads `stop`. Anthropic-shaped: `finish_reason` empty, `output_tokens=1`, input counts real. Rule in §1.3 Billing |
| A6 | System prompt sent once | **`system_prompt=` is NOT sent when message history is passed** (0 times in the request body, OpenAI and Anthropic). **`instructions=` is sent exactly once.** → always `instructions=` |
| A7 | Temperature and output limit reach the request | **Pass** (`temperature`, `max_tokens`; OpenAI streaming also gets `stream_options.include_usage=true`) |
| A8 | Harness compaction classes | **Pass** — all present in `pydantic_ai_harness.compaction`: `TieredCompaction`, `DeduplicateFileReads`, `ClearToolResults`, `ClampOversizedMessages`, `SummarizingCompaction`, `pin`, `WarnNearLimits`, `ReportContextUsage` (also `estimate_token_count`). Some older harness module names are deprecated (`experimental.*`, `context` → `repo_context`) — use the new names |
| A9 | Deferred tools / ask-user | **Names present:** `DeferredToolRequests`, `DeferredToolResults`, `CallDeferred`, `ApprovalRequired`, `ToolApproved`, `ToolDenied`; harness `ask_user`. Behaviour not tried yet (Layer 1/4) |
| A10 | genai-prices offline | **Pass** — `calc_price` works offline, returns `Decimal`; unknown model raises `LookupError` (so local models need our own price-0 entries); no download unless its updater is started |
| B11 | Client disconnect cancels the run | **Pass** — FastAPI streaming response; client left after 1 s; the run stopped with `CancelledError` after 0.93 s and the upstream model stream stopped after 10 of 360 words |
| C | txtai on pgvector | **Not run** — Layer 3; checks stay listed in §1.3 |

**Pinned versions** (the new module's `requirements.txt`; Python 3.13):

```
pydantic-ai-slim[openai,anthropic,google,mcp]==2.55.0
pydantic-ai-harness==0.55.0
pydantic==2.14.0
fastapi[standard]==0.143.0
starlette==1.7.0
uvicorn==0.54.0
httpx==0.28.1
genai-prices==0.1.10
Jinja2                 # pin the version pip resolves when the module is created
pytest / pytest-asyncio # test only; pin likewise
# Layer 3 (not before): txtai==9.14.0, fastembed==0.9.0 — after the txtai setup checks
```

The provider SDKs come in through the extras; the trial resolved `openai==3.28.0`, `anthropic==1.13.0`, `google-genai==2.29.0`, `mcp==2.3.0`. Freeze the full resolved set (`pip freeze`) into a lock file when the module is created. Note: the Anthropic provider in this version takes an **`httpx2`** client (`AnthropicProvider(http_client: httpx2.AsyncClient)`), not `httpx`.

#### Layer 0 spec — the handoff to the implementer (draft 2026-10-10, for owner review)

Layer 0 = items 25, 7, 26, 15, 37, 21, 47: **one plain text reply**, streamed, with exact usage. No tools, no routing, no retrieval, no compaction. Built against the pinned versions above.

**Out of Layer 0:** tools and approvals (L1), router / escalation / fallback models / budgets (L2), retrieval and vectors (L3), summaries and ask-user (L4), everything else.

**Decisions this spec needs before handoff** (everything else below follows from settled items):

| # | Question | Why it blocks | Proposal |
|---|---|---|---|
| O1 | Where are prices stored and cost computed? | `UsageRecord` carries cost | nucleus owns the price table (it owns the DB); nexus-ai sends token counts; **nucleus prices each record on arrival** with the price in force at the call time and stores the cost and the prices used. The formula below is the same wherever it runs |
| O2 | `TriggerJob` has no `company_id`, `project_id` or `user_id` (`NA/schemas/trigger.py:261-298`) | every `UsageRecord` must carry them | nucleus adds the three to the job payload (`NU/chat/services.py:955-975`) — a 4th nucleus change for L0 |
| O3 | History window | item 26 says 5–10 messages; 0.8.0 uses 20 (`NA/core/config.py:62`) | **Decided 2026-10-10:** history starts at the topic's **last compaction** (its latest summary), or at the **topic start** if it was never compacted, and is **capped** by the setting `HISTORY_DEPTH` (default **10**), keeping the newest. In Layer 0 nothing compacts yet (item 6, Layer 4), so it is "topic start, capped" |
| O4 | One `AISystem` interface or several | signature of `AISystem` | **one** for now (`respond`); split when a second method arrives |
| O5 | Internal key header name | `NucleusClient` and the router | one name both ways: **`X-Internal-Key`** |

**Contracts (`fastapi_app/contracts/`)** — the wire with nucleus. Field names are kept exactly as 0.8.0 sends and reads them, so nucleus keeps working.

- `TriggerJob` — all 0.8.0 fields (`NA/schemas/trigger.py:271-298`): `job_id`, `msg_id`, `persona_id`, `topic_id`, `user_message_id`, `message`, `context_sources`, `output_type`, `preflight`, `approved_plan`, `interactive`, `routine_id`, `step_context`; **plus** `company_id`, `project_id`, `user_id` (O2). Layer 0 uses `job_id`, `msg_id`, `persona_id`, `topic_id`, `user_message_id`, `message` and the three new ids; the rest are accepted and ignored.
- `AgentEvent` — Layer 0 sends five types: `message_start`, `message_delta`, `keepalive`, `message_done`, `message_error` (names from `NA/schemas/trigger.py:356-370`). Fields the single-persona relay reads (`NU/chat/services.py:1028-1090`, `:519`): `type`, `delta`; on done: `content` (full text), `output_type` (`"text"`), `render_as` (`"text"`), `answered_by_model`, and the three usage fields `prompt_tokens` (= `input_tokens` total), `output_tokens`, `context_window`; on error: `error`, `error_code`. Also sent on every event, as 0.8.0 does: `id` (= `msg_id`), `persona_id`, `persona_name`, `created_at` (the single-persona relay does not read them; only the swarm relay did, `:1367-1372`).

**Data classes (`ai_engine`, plain Python):**

```
class ModelRole(Enum): ROUTER, STANDARD, DEEP, FALLBACK

@dataclass(frozen=True)
class ModelSpec:
    role: ModelRole
    config_id: str            # ModelInternal.id
    name: str
    provider: str             # openai | anthropic | google | ollama | openai_compatible
    model_id: str             # bare name
    base_url: str | None
    api_key: str | None
    context_window: int       # never the same field as the persona's output limit
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool

@dataclass(frozen=True)
class PersonaSpec:
    id: str
    name: str
    company_id: str
    project_id: str
    system_prompt: str        # PromptInternal.system_prompt
    project_brief: str | None # goes ahead of the persona prompt
    output_type: str          # PromptInternal.output_type (kept, unused in L0)
    context_scope: list | None  # kept, unused in L0
    temperature: float
    max_output_tokens: int    # PersonaInternal.max_tokens
    max_steps: int            # kept, unused in L0
    models: tuple[ModelSpec, ...]   # model → STANDARD; fallback_models → FALLBACK, in order
    advisor_model: ModelSpec | None # kept, unused in L0
    utility_model: ModelSpec | None # kept, unused in L0
    tool_levels: dict[str, str]     # kept, unused in L0
    mcp_servers: tuple[dict, ...]   # kept raw, unused in L0
    capabilities: tuple[dict, ...]  # kept raw, unused in L0
    recall_enabled: bool            # kept, unused in L0
    def model_for(self, role: ModelRole) -> ModelSpec   # raises if the persona has none

@dataclass(frozen=True)
class HistoryRow:             # HistoryMessageInternal as nucleus sends it (NU/internal/api.py:218-236)
    id: str; sender_type: str; sender_name: str | None; content: str
    render_as: str; output_type: str; stopped: bool; sequence: int
    status: str | None        # new field from nucleus change (2); None from an older nucleus

@dataclass(frozen=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    author: str | None
    text: str                 # already attributed (see HistoryPolicy)

@dataclass(frozen=True)
class ContextBundle:
    history: tuple[HistoryMessage, ...]   # L3 adds retrieval fields

@dataclass(frozen=True)
class PromptSection:
    kind: str                 # "project_brief" | "persona_prompt" | ...
    priority: int             # higher = dropped last (L2 BudgetFitter)
    stable: bool              # True = same every turn → goes first (cache)
    text: str

@dataclass(frozen=True)
class PromptPlan:
    instructions: tuple[PromptSection, ...]  # joined into the single instructions= string
    history: tuple[HistoryMessage, ...]
    message: str

@dataclass(frozen=True)
class ReplyRequest:
    job: TriggerJob
    persona: PersonaSpec
    role: ModelRole           # STANDARD in L0
    plan: PromptPlan

@dataclass(frozen=True)
class UsageRecord:
    # who / where
    company_id: str; project_id: str; topic_id: str; persona_id: str
    user_id: str; message_id: str; job_id: str
    # what
    kind: str                 # "chat_reply" in L0 (later: router, escalation, sub_persona, summary, model_check, embed)
    model_config_id: str; provider: str; model_id: str; role: str
    provider_response_id: str | None
    # counts — pydantic-ai semantics (§1.3 Billing)
    input_tokens: int         # total, incl. cache read + write
    uncached_input_tokens: int
    cache_read_tokens: int
    cache_write_5m_tokens: int
    cache_write_1h_tokens: int
    output_tokens: int        # total, incl. reasoning
    reasoning_tokens: int     # part of output_tokens, never added
    finish_reason: str | None
    estimated: bool
    called_at: datetime       # UTC; the price in force at this moment applies
    # cost — filled where prices live (O1); Decimal, never float
    cost: Decimal | None = None
    prices_used: dict | None = None
```

**Classes and signatures (Layer 0):**

```
# fastapi_app/routers/trigger.py
POST /api/v1/trigger/   body: TriggerJob   → text/event-stream of AgentEvent
    checks the internal key; return EventStream.wrap(AISystemFactory.create("pydantic_ai").respond(job))

# fastapi_app/stream/event_stream.py
class EventStream:
    def __init__(self, keepalive_seconds: float = 30.0)
    async def wrap(self, events: AsyncIterator[AgentEvent], job: TriggerJob) -> AsyncIterator[bytes]
        # keepalive after silence; exactly one final event (done or error);
        # an unexpected exception → one message_error; never re-raises into the response

# ai_engine/core
class AISystem(Protocol):
    def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]
class AISystemFactory:
    @staticmethod
    def create(kind: str) -> AISystem          # "pydantic_ai" only in L0
class PydanticAISystem(AISystem):
    def __init__(self, nucleus: NucleusClient, context: ContextBuilder,
                 layout: PromptLayout, generator: ReplyGenerator)
    async def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]
        # message_start → persona → context → plan → generator deltas →
        # finally: record usage (also on cancel / error) → message_done
class NucleusClient:
    def __init__(self, base_url: str, internal_key: str, timeout_seconds: float = 10.0)
    async def get_persona(self, persona_id: str, company_id: str, project_id: str) -> PersonaSpec
    async def get_history(self, topic_id: str, limit: int, exclude_message_id: str) -> list[HistoryRow]
    async def record_usage(self, records: list[UsageRecord]) -> None   # new endpoint, nucleus change (1)

# ai_engine/context
class HistoryPolicy:
    def __init__(self, depth: int)             # O3
    def select(self, rows: list[HistoryRow], persona: PersonaSpec) -> list[HistoryMessage]
class ContextBuilder:
    def __init__(self, nucleus: NucleusClient, policy: HistoryPolicy)
    async def gather(self, job: TriggerJob, persona: PersonaSpec) -> ContextBundle

# ai_engine/prompts
class PromptTemplates:
    def __init__(self, template_dir: Path)
    def render(self, name: str, values: dict) -> str
class PromptLayout:
    def __init__(self, templates: PromptTemplates)
    def build(self, persona: PersonaSpec, bundle: ContextBundle, message: str) -> PromptPlan

# ai_engine/pydantic_ai_system
class ModelFactory:
    def build(self, spec: ModelSpec) -> pydantic_ai.models.Model   # every provider gets base_url + key
class AgentBuilder:
    def __init__(self, models: ModelFactory)
    def build(self, persona: PersonaSpec, role: ModelRole, instructions: str) -> pydantic_ai.Agent
        # Agent(model, instructions=..., model_settings={"temperature", "max_tokens"}); never system_prompt=
class MessageConverter:
    def to_messages(self, history: Sequence[HistoryMessage]) -> list[ModelMessage]
    def instructions(self, plan: PromptPlan) -> str     # sections joined, stable first
class EventMapper:
    def __init__(self, msg_id: str, persona: PersonaSpec, batch_chars: int = 40, batch_ms: int = 50)
    def map(self, event: AgentStreamEvent) -> list[AgentEvent]   # text → batched message_delta
    def flush(self) -> list[AgentEvent]
    def text(self) -> str                                        # everything sent so far
class UsageReader:
    def read(self, response: ModelResponse | None, request_messages: list[ModelMessage],
             received_text: str, cancelled: bool, base: UsageRecord) -> UsageRecord
class ReplyGenerator:
    def __init__(self, agents: AgentBuilder, converter: MessageConverter, usage: UsageReader)
    async def generate(self, request: ReplyRequest) -> AsyncIterator[AgentEvent]
    def usage_records(self) -> list[UsageRecord]   # one per model call; available after any ending
    def full_text(self) -> str
```

**Behaviour rules the bodies must follow:**

- **History (`HistoryPolicy.select`)**, applied to rows already excluding `user_message_id`: drop rows whose `status` is FAILED, CANCELLED, PENDING or STREAMING (when nucleus sends `status`); drop `stopped` rows; drop `sender_type == "system"`; drop empty content; `human` → `user`, `persona` → `assistant`; drop an assistant row with `render_as == "html"` that does not look like HTML, and a visual `output_type` rendered as text (0.8.0 behaviour, `NA/managers/nucleus_client.py:213-232`); an assistant row written by **another** persona is prefixed `[Another Agent: <name>]` (0.8.0 behaviour, `NA/managers/prompt_builder.py:170-176`); only rows after the topic's last compaction (or from the topic start) — nucleus applies this boundary, see nucleus change (2); of those, keep the newest `depth` rows, oldest first; never reorder (O3). Putting the summary itself at the head of the history, and `is_deleted_from_context`, come with item 6 / Layer 4.
- **Prompt (`PromptLayout`)**: instructions = project brief (if any) then persona prompt, both stable; history; then the new message as the last user turn. The system prompt text appears **once** in the request.
- **Usage (`UsageReader`)**: counts from `response.usage` with the §1.3 formula; `cache_write_1h_tokens` / `output_reasoning_tokens` read with default 0; estimated by the §1.3 rule; estimates use `pydantic_ai_harness.compaction.estimate_token_count(messages)` — it takes a **list of pydantic-ai messages**, not a string (verified; ~4 characters per token unless a tokenizer is passed): output estimate from a `ModelResponse` holding the received text, input estimate from the request's messages when the provider sent none. So `UsageReader.read` takes `request_messages`, and wraps `received_text` in a `ModelResponse` for the output estimate.
- **Endings**: done → record usage, then `message_done` with full text and usage fields; client disconnect → the run is cancelled, usage recorded (estimated), no event can be sent; error → usage recorded, exactly one `message_error`. `record_usage` failure is logged and never turns a good reply into an error.

**Cost formula** (wherever O1 puts it), all `Decimal`, prices per million tokens:

```
cost = ( uncached_input_tokens * price.input
       + cache_read_tokens     * price.cache_read
       + cache_write_5m_tokens * price.cache_write_5m
       + cache_write_1h_tokens * price.cache_write_1h
       + output_tokens         * price.output ) / 1_000_000
```

**Acceptance tests (write first; "done" = all pass).** Model calls go to a fake server that answers like OpenAI / Anthropic streaming (as in the trial); nucleus is a fake too. Prices below are **test fixtures, not real prices**.

| # | Test | Expected |
|---|---|---|
| T1 | Plain reply | events: `message_start`, ≥1 `message_delta`, exactly one `message_done`; `done.content` == concatenated deltas == model text |
| T2 | System prompt once, with 2 history messages | the persona prompt appears **exactly once** in the captured request body (OpenAI and Anthropic shapes); project brief precedes it |
| T3 | Settings reach the model | request body has the persona's `temperature` and `max_tokens` |
| T4 | Anthropic usage | provider reports input 200, cache write 500 (1h 200), cache read 1000, output 300 → `UsageRecord`: input 1700, uncached 200, cache read 1000, write 5m 300, write 1h 200, output 300, reasoning 0, estimated false |
| T5 | OpenAI usage | provider reports prompt 1200 (cached 1000), completion 300 (reasoning 120) → input 1200, uncached 200, cache read 1000, writes 0, output 300, reasoning 120, estimated false |
| T6 | Cut stream, OpenAI shape | no error event from the model side; record `estimated=true`, output > 0 (estimated from received text) |
| T7 | Cut stream, Anthropic shape | `estimated=true`; input 1700 / cache counts kept as reported; output estimated (not 1) |
| T8 | Client disconnects after 1 s | run cancelled; fake model stops streaming; `record_usage` called once with `estimated=true` |
| T9 | Model returns HTTP 500 | exactly one `message_error`, no `message_done`; `record_usage` called |
| T10 | Silence longer than the keepalive (set to 0.2 s in the test) | a `keepalive` event is sent; still exactly one final event |
| T11 | Cost, T4 numbers, fixture prices input 3.00 / cache read 0.30 / write 5m 3.75 / write 1h 6.00 / output 15.00 | **0.007725** exactly (`Decimal`) |
| T12 | Cost, T5 numbers, fixture prices input 2.50 / cache read 1.25 / output 10.00 | **0.00475** exactly |
| T13 | History rules | given rows covering each rule above → exactly the expected `HistoryMessage` list, order kept |
| T14 | Unplaced fields | a job with `preflight=true`, `approved_plan`, `routine_id`, `step_context` set → normal plain reply, no error |
| T15 | `record_usage` fails | reply still ends with `message_done`; failure logged |
| T16 | Dependency rules | static check: nothing under `ai_engine/` imports `fastapi` or `django`; only `ai_engine/pydantic_ai_system/` imports `pydantic_ai` / `pydantic_ai_harness`; nothing imports `modules/nexus-ai-legacy` |

**nucleus changes for Layer 0** (separate small handoff): (1) new usage endpoint taking a list of `UsageRecord` (and pricing it, if O1 is accepted), adding to topic totals and pushing them on the topic channel (item 47); (2) the history endpoint returns `status` on each row and returns only rows **after the topic's last compaction** (from the topic start when there is none), newest `limit` of them (O3); (3) model roles mapping (persona model → `STANDARD`, fallbacks → `FALLBACK`) — done on the nexus-ai side in `NucleusClient.get_persona` until nucleus has roles; (4) `company_id`, `project_id`, `user_id` in the trigger payload (O2); (5) header name (O5).

#### Rules for whoever implements this (human or model)

- Work **one layer (or one item) at a time**; each is reviewed before the next.
- **Do not add files or classes outside this structure. Do not change a signature without asking.**
- **No imports from the old `modules/nexus-ai/`.** Code may be copied only when accepted as a copy candidate, and then belongs to the new module.
- **Pin library versions before writing code**; confirm every pydantic-ai / harness name used here against the pinned version.
- **Write the acceptance tests first;** "done" means they pass.
- Invariants that must always hold: every field nucleus sends has a place; the system prompt is sent once — **through `instructions=`, never `system_prompt=`** (pydantic-ai drops `system_prompt` whenever message history is passed; verified); `context_window` and the output limit are never the same field; usage is recorded on every ending, including stop and failure; cached tokens are never priced at the input rate and reasoning is never added on top of output; every stream ends with exactly one final event; write tools always ask.
- Set `PYDANTIC_AI_NO_BANNER=1` in the service environment (pydantic-ai 2.55 prints a startup banner otherwise).

#### Diagrams

Rendered diagrams were produced on 2026-10-10 (full architecture, Layer 0 classes, Layer 0 sequence). The class catalog above is the source of truth; diagrams are regenerated from it.

---

## 2. What 0.8.0 already provides — do not rebuild these from scratch

- **Tool approval, item 2.** `Persona.tool_levels` (JSON: `"auto" | "ask" | "off"`, keyed by capability id or `"<capability>/<tool>"`). Worker-side `ToolApprovalGate` is a **harness `AbstractCapability`**, not pydantic-ai deferred tools: `prepare_tools` drops `off`, `before_tool_execute` awaits a decision on `ask`. Defaults when unset: MCP tools with `readOnlyHint` → `auto`, acting tools → `ask`, else `auto`. "Always allow" clears the key for the run. Unattended runs refuse rather than hang. Events: `approval_requested` out, `POST …/approvals/{call_id}/` in, nucleus-held state read by a worker poll.
- **Persona call rights, item 9.** Two rights, both `ObjectType.PERSONA` at `ScopeType.TOPIC`: `persona.mention` (`authn/permissions/rights.py:114`) and `persona.approve_run` (`:176`). Enforced on the send path at `chat/api.py:259` and `:338`, and on both approval paths at `chat/services.py:638` and `:773`. Default role grants at `rights.py:215, 221, 243`; the deny path is covered by test UC10 (`authn/permissions/tests.py:235-247`). A company-wide Viewer is the one default role without `persona.mention`. Persona *management* is a separate right (`intelligence/api.py:440`). **This is load-bearing for §3:** because the tool set is a property of the persona rather than the caller, `persona.mention` is the gate that decides who can reach those tools.
- **Cancellation, item 37.** `POST …/messages/{id}/stop/` → Redis key `nx:stop:{msg_id}` (TTL 600s) → the relay polls every 0.15s wrapping **both** the connection open and the line iteration, so a stop lands while the model is silent. Partial content is kept; the row goes to `COMPLETED` with `metadata.stopped = True` (never `Status.CANCELLED`).
- **Run pause without decoupling, item 27.** The run parks *inside* the existing stream — the worker emits `keepalive` every 30s so the 120s read timeout never fires. **This corrects an earlier conclusion in this document that item 2 forced a transport change. It does not.**
- **Fallback models, item 12.** `PersonaFallbackModel` through-model, ordered, max 3. Worker retries the whole stream per candidate (`FallbackRun`), suppressed once any token has reached the reader. pydantic-ai's `FallbackModel` is **not** used but is available.
- **Event contract, item 25.** 11 worker event types, 15 nucleus types, channel `topic-{topic_id}`.
- **Usage, item 21.** Only `prompt_tokens`, `output_tokens` and `context_window`, on `ChatMessage.metadata["usage"]`, end to end — three of the nine fields `RunUsage` computes. See §4 for what to record.
- **Compaction, item 16.** `TieredCompaction` with `DeduplicateFileReads` → `ClearToolResults` → `SummarizingCompaction`, wired unconditionally. *(But see Appendix A — its target is miscomputed.)*
- **Model check, item 40.** A full end-to-end verification path already exists; only persistence is missing. See §4.
- **Beyond the list.** Routines (per-turn capability intersection, `/name` token), runbooks, recall entries, inbound hooks, deliverables, plan-first preflight, nudges, browser and terminal routers, message search.

---

## 3. The run pipeline

> **Superseded as the target structure by §1.5 (2026-10-10).** The two-pass reasoning, budget arithmetic and eligibility-vs-inclusion split below still hold as design input; the class names and placement do not. Use §1.5 for classes, modules and folders.

Where the cross-cutting classes live. One persona request, start to finish. Everything here is **Settled** — none of it exists at 0.8.0, whose runner assembles inline.

### 3.1 Two passes, and why it cannot be one

The obvious shape is a straight line: unfold the persona, get its models and router, get the project's MCPs, fetch history, check for files, check whether the code graph applies, build the prompt. That shape has a circular dependency in it.

How much history to include depends on `input_budget`, which is `context_window − max_output_tokens − loop_headroom`, and `context_window` is a property of **the model the router has not picked yet**. But routing wants to know what the request looks like. Let the router see the assembled history and you have paid assembly cost before deciding, and assembled to a budget that depends on the decision.

The break: **the router sees metadata only** — query text, attachment type and size, which tool ids are eligible, whether the project has a code graph. Never the assembled history. That splits the request in two.

**Pass 1 — resolve.** Cheap. No content assembly. Ends with one routing decision.

1. load persona, project and requester identity from `TriggerJob`
2. **register the stop signal** — before anything else (§4, item 37)
3. decrypt model configs, check verification fingerprints → candidate `ModelSpec` list (item 40)
4. resolve tool **eligibility**: project MCPs ∩ persona declaration (item 1)
5. **route** → one `RoutingDecision` struct (item 13)

**Pass 2 — plan, execute, run.**

6. `RunPlanner.plan()` → a `RunPlan`. Every inclusion decision, made at once, touching nothing.
7. the fetchers carry the plan out — history, retrieval, file staging
8. `MessageAssembler` lays the message list out in cache order (item 15)
9. `UsageRecorder.open()` — the row exists before the run does (item 21)
10. blue zone: `Provider` → `Model` → wrappers → `Agent` → `run_stream_events`
11. `UsageRecorder.close()` with all nine `RunUsage` fields

### 3.2 The classes

| Pass | Class | Owns | Item |
|---|---|---|---|
| — | `TriggerJob` / `AgentEvent` | the wire contract with nucleus. Unchanged. | 25 |
| 1 | `StopRegistry` | `nx:stop:{id}`, registered first | 37 |
| 1 | `ModelResolver` | decrypt + fingerprint → `ModelSpec` | 40 |
| 1 | `ToolEligibility` | project ∩ persona. A **permission** question. | 1, 9 |
| 1 | `Router` | one struct out, setting-driven, falls through on failure | 13 |
| 2 | **`RunPlanner`** | every inclusion decision → `RunPlan` | 1, 16, 24, 26, 28, 33, 34 |
| 2 | `HistoryStore` | rows since the summary anchor | 26 |
| 2 | `Retriever` | code graph or vector, as the plan says | 24, 31, 32 |
| 2 | `FileStager` | inline reads, path staging | 28, 36 |
| 2 | `MessageAssembler` | cache order | 15, 26 |
| 2 | `ModelBuilder` | `ModelSpec` → wrapped pydantic-ai `Model` | 7, 11, 12 |
| 2 | `ToolsetBuilder` | `plan.tools_*` → harness objects | 1, 2, 16, 17, 32, 34 |
| 2 | `UsageRecorder` | row open before, closed after | 21 |
| — | `PersonaRun` | sequences all of the above | — |

Only `ModelBuilder` and `ToolsetBuilder` reach into pydantic-ai or the harness. Everything else is ours and library-free, which is what makes it testable and what keeps a framework upgrade from reaching the whole module.

### 3.3 `RunPlanner` decides; it does not fetch

One class owns every "what goes in" question. But it takes no connections, no sessions, no clients — only resolved state and a token-counting callable:

```python
def plan(self, *, job, routing, eligible, cache) -> RunPlan
```

That signature is the design. A class that both decides and fetches ends up knowing Postgres, pgvector, the code-graph MCP, the file store, the summarizer and the tokenizer, and it rots. Four things the split buys:

- **Testable with no infrastructure.** Hand it a synthetic state, assert the plan. If it fetched, every test would need Postgres, pgvector and an MCP subprocess running.
- **`RunPlan.evicted` is a durable artifact.** A list of `(what, why)` pairs, stored on the usage row. When a user says "it forgot my file", the answer is read, not guessed. This is the single most useful debugging output in the system and it costs a column.
- **Budget arithmetic lives in one place.** Item 16's eviction order is a pure function over the plan. Spread across fetchers it cannot be verified.
- **The cache prefix is decided once.** Otherwise it drifts turn to turn and nobody notices until the bill arrives.

`RunPlan` carries: the chosen `ModelSpec`; `tools_loaded` and `tools_catalogued`; `history_from` (a message id) and `history_limit`; `inline_files`, `tool_files`, `data_files`; `retrieval` (`code_graph` | `vector` | `none`); `evicted`; `budget`; and `cache_invalidated`.

### 3.4 Eligibility is not inclusion

Two different questions, deliberately answered by two different classes at two different times.

| | Question | Decided by | When |
|---|---|---|---|
| **Eligibility** | may this persona in this project use this tool at all? | `ToolEligibility` | Pass 1, before any content exists |
| **Inclusion** | does it go in the prompt this turn? | `RunPlanner` | Pass 2, against the budget |

Eligibility is **project MCPs ∩ persona declaration**. Two filters, not three: **the requester does not narrow it.** A persona with `shell` configured runs shell for anyone who can mention it.

That is a real transfer of authority, made knowingly. The gate moves to **who may configure the persona** and **who may mention it** — `persona.mention`, TOPIC-scoped, which item 9 confirms is already built and enforced. Deciding it per-requester instead would mean the tool set changes by caller, which makes it uncacheable and scatters the permission decision across the run.

One thing stays per-requester on a different axis: the `ask` approval level pauses and asks *someone*. Which someone is item 2's open question (§4), independent of which tools exist.

### 3.5 The three numbers currently hardcoded

Named here so they are not quietly inherited as constants:

| Value | Used for | Needs |
|---|---|---|
| 32 KB | inline-vs-path boundary for a text attachment | a setting; depends on typical model size |
| `eligible[:4]` | fallback when the router returns no tool hints | a setting, or a better fallback |
| 8,000 | `loop_headroom` in the budget formula | a setting; should scale with tool count |

### 3.6 Open

- Does `RunPlan` get versioned? It is stored on the usage row, so a shape change makes old rows unreadable unless it carries a version.
- Where does the router setting live — instance, company, project or persona? Item 13 settles the mechanism, not the scope.
- `PersonaRun` is a generator yielding `AgentEvent`. Does the stop check belong in the loop (as now) or in a wrapper, so the same check guards assembly and run alike?

---

## 4. What is settled but not built

- **1 — Permitted set.** Permitted ≠ sent. Eligibility and inclusion are split as in §3.4: eligibility is project ∩ persona, resolved in Pass 1; inclusion is `RunPlanner`'s, against the budget. A per-**topic** cache holds the admitted set — topic-wise because the provider's cached prefix is per-conversation, since the history is.

  **The tool list is itself a cache-prefix problem.** On the Anthropic API the tool list is a top-level parameter sitting *ahead* of system and messages in the cache order, so **changing it invalidates everything behind it** — `[?] confirm against current provider docs before building`. That rules out the intuitive design of re-narrowing the loaded set per turn on query relevance: every turn differs, so every turn is a full cache miss, and when the narrowing guesses wrong the model is silently incapable and cannot say why.

  So: **narrow once at topic start, then hold.** The prompt carries the full *catalog* (names plus one line each — cheap, stable, decided once) and *loaded schemas* for the subset the router picked. `ToolSearch` stays available as the escape hatch, so a wrong guess costs one round trip instead of a failed task. The planner only accepts a new loaded tool when the model asked for it through `ToolSearch` — never speculatively, because that is a deliberate cache miss.

  0.8.0 has `tool_levels` at **persona** scope only, no tool tags, no semantic matching (`ToolSearch(strategy=None)` — selection explicitly disabled), and no modelled distinction between permitted and sent.

- **2 — Open: who gets asked.** The `ask` level blocks on a decision. Whether that goes to the triggering user, the project owner, or anyone holding `persona.approve_run` at the topic is undecided. 0.8.0 checks `persona.approve_run` (`chat/services.py:638`), which answers *who may decide* but not *who is notified*. Matters most for a run parked overnight.

- **5 — Questions to the user.** Partly built, and only barely: a prompt convention (`CHOICE_EXCEPTION` plus a `<<<OUTPUT:choice>>>` marker) with no tool, no event, no endpoint, no pause and no renderer. **It therefore does not serve item 39** — provisioning needs real question cards with a response path, and a prompt convention is not one. An earlier version of this document named 39 as item 5's first consumer; that remains true as a dependency and false as a claim that anything reusable exists.

- **6 — Summarize / new topic.** `SUMMARY` added to `MessageType`; last-N history stops at the barrier; a button copies setup and archives the topic. Nothing exists: `SUMMARY` appears nowhere in 0.8.0.

- **10 — Per-user rate limits.** Nothing limits persona calls per user. The only rate limiter in the repo is `within_rate_limit(hook)` (`scheduling/hooks.py:199`), which is per inbound **hook** — a usable precedent, wrong subject. `chat/api.py:158` notes a client-side throttle in `MessageInput.tsx`, which is not enforcement. Everything else matching `rate_limit` is *reading provider 429s* (`chat/reasons.py:20`, `apps/managers/fallbacks.py:42,46`) — error classification, not limiting. Must live **outside** the run in shared Redis, per item 38, or concurrent runs each claim the full allowance.

- **11 — Per-model rate limits.** Nothing built; the mechanism is settled. A custom `WrapperModel` subclass wrapping the provider model, acquiring from a shared Redis bucket before `super().request()` and charging `response.usage.total_tokens` after. `ConcurrencyLimitedModel` caps concurrent requests, not token rate, so it is not a substitute. Built in `ModelBuilder` (§3.2), outermost in the wrapper chain so it sees the true cost.

- **13 — Depth routing.** One step, not two. Which model performs the routing is a **UI setting**: a local model reached through `OpenAIProvider(base_url=…)` and a configured remote model are two implementations of the same step, and `off` must be a valid value — a self-hosted install with no local model should not pay a remote call per request just to pick a model.

  **It returns a struct, not a model id:** chosen model, `is_code`, tool hints. "Is this about code" is a router *output*, not a separate test — same call, no second pass. This is the one place in the system where pydantic-ai's `output_type=` earns its keep, because a validated struct is wanted rather than prose; `retries={"output": 3}` already covers a model that ignores the schema. Everywhere else the output streams to a human and `output_type` gets in the way.

  **Three properties it must have:** its tokens are recorded like any others (item 21 — a routing call per request is not free and the number should be visible); its timeout is its own, because a hung router stalls a request that has not started; and **any failure falls through to the persona's default model**, recorded as `source="router_failed"`. Routing is an optimisation, never a dependency.

  0.8.0 has nothing: `CompanyAIConfig.utility_model` is a fixed company-level small-pass model with one caller (recall). Zero hits for `escalat`, `complexity`, `depth`, `tier`.

- **14 — Project budget. Blocked, not merely remaining.** There is no cost data anywhere to budget against: no `cost` column, and `ModelUsageLog` with its `cost_usd` was dropped in migration 0008 having never had a writer. `BudgetExceededError` in `apps/managers/fallbacks.py:34` is an exception name in the failure classifier, not a budget. Item 21 has to land first.

- **15 — Prompt caching. Constraints settled; 0.8.0 behaviour still unaudited.** Caching is not a feature to add later — it dictates the message layout, so it constrains §3 now.

  **The layout is forced.** Stable first and byte-identical across turns, volatile last:

  1. system — persona prompt + project brief + tool policy
  2. the summary (changes only when a new one is written)
  3. recent turns (grows by two each turn)
  4. this turn — retrieved context, then inlined files, then the query

  Put an inlined file above the persona prompt and the prefix breaks for the whole conversation, every turn. This is `MessageAssembler`'s entire contract.

  `cache_hit_ratio` (item 21) is how this gets proven rather than assumed. `model_settings` is currently passed as nothing at all (Appendix A), so no cache control reaches any provider today.

- **16 — see §4.1 below.**

- **20 — Swarm.** Automatic handoff **dropped**: it broke item 2's permission model (A gets approval, B inherits the run), left nobody in charge of the chain, lost context per hop, and billed personas the user never chose. Replaced by user-driven @mention (a separate run) and model-driven `SubAgents` (parent keeps its identity). Repoint `swarm_transition` at sub-agent delegation rather than deleting it.

  **The replacement currently cannot work.** `SubAgents` is registered in `_CAPABILITY_REGISTRY`, and that registry has **zero readers** — see Appendix A. So the agreed substitute is imported, registered and unreachable, along with `SpendLimits`, `Memory`, `Planning` and `Skills`. Wiring the registry is a prerequisite for this decision, not a detail of it.

- **21 — Usage recording. Record every field `RunUsage` reports — nothing is dropped**, so later cost and efficiency figures are exact rather than reconstructed. That is `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cache_audio_read_tokens`, `total_tokens`, `cache_hit_ratio`, `requests`, `tool_calls`, and **`cost` frozen at run time** (recomputing later from current prices silently rewrites historical spend). 0.8.0 reads only three of these — plumbing nobody finished, not a decision. The omissions matter: cache reads price at roughly a tenth of input, so without them cost is badly wrong on any cached workload, and `cache_hit_ratio` is how item 15 gets proven rather than assumed. Written to **our own Postgres** (Supabase stays identity-only — usage must join to project/topic/persona/model, which exist only here), as a row at run **start** updated at **end**, so a run that dies or parks leaves a reconcilable orphan rather than silence.

  **Two additions from §3:** the row also carries the `RunPlan` — `evicted` especially, which is what makes "why did it forget that" answerable. And the **router's own usage** is recorded against the same message (item 13), or per-request routing cost stays invisible.

  **Central phone-home telemetry is a separate, deliberately tiny thing:** instance count keyed by the existing `NEURALOPS_INSTALL_TOKEN`, and total tokens — nothing else, documented and disableable by one env var.

- **22 — Sandboxing.** Stays as-is: project folder bind-mounted, filesystem and shell allow-lists. No container-per-run, no microVM.

- **26 — History selection.** Last 5–10 messages, back to the most recent `SUMMARY`; filter out `FAILED`/`CANCELLED`/`PENDING`/`STREAMING`; honour `is_deleted_from_context`. 0.8.0 does none of the three.

  **Anchor at the summary, always.** The summary *replaces* what sits behind it, so taking both double-counts. `n` is a DB `LIMIT` and nothing more — tokens are the real control, and tokens are not known until the model is, which is why this sits in Pass 2.

- **28 — Attachments.** Bytes as now, plus an embedded **one-line description** per attachment for discovery (works for code, where embedding source would not), plus chunks in pgvector for prose only. Needed because attachments go unreachable once 26's barrier passes them. Pasted source files are offered a home in the project folder instead.

  **Three fates, decided by size and type, before budget accounting** — because inlining spends the budget:

  | Attachment | Fate |
  |---|---|
  | small text (under the §3.5 boundary) | inlined into the volatile tail. Spends budget. |
  | large or binary | **not** inlined — a `FileSystem` path the model may read |
  | `.csv` `.parquet` `.xlsx` | DuckDB (34). Never inlined. |

  Protected from compaction in all three cases (item 16): compacting an attached file silently corrupts the task.

- **30 — Migration.** Dropped; DB reset, migrations for new data only.

- **37 — Cancellation: register earlier.** 0.8.0 wraps both the connection open and the line iteration, which is right for the stream — but the signal is registered when the stream starts. Assembly happens first and is not instant: history, retrieval, file staging, a routing call. A stop pressed during assembly must land. **Register in Pass 1 step 2**, before any of it. Also unresolved: `Status.CANCELLED` has no writer (§5).

- **38 — Concurrent runs.** Independent and separately cancellable. Consequences: each message must persist **what it replied to** (`TriggerJob` already carries `user_message_id` in flight — land it as `in_reply_to`), or transcript order stops matching causality; the rate limiter must live **outside** the run (shared Redis) or concurrent runs each claim the full TPM allowance; `sequence` needs safe concurrent allocation; and the permitted set is read at run start, so concurrent runs legitimately differ — correct, not a bug.

### 4.1 — 16 — Context budget, compaction and the tool loop

**The trigger is a budget, not a constant.** The prompt must leave room for the model's own output and for the loop to grow mid-run:

```
input_budget = context_window − max_output_tokens − loop_headroom
```

`context_window_for(model)` already exists and returns the real window; it is simply not used for this. Two numbers, not one: a **target** (what compaction compacts down to, ~70% of budget) and a **trigger** (~90%). Firing at the target means re-compacting constantly; the gap is what lets the loop grow between compactions.

**Keep the two token numbers structurally apart.** `ModelSpec` (§3.2) carries `context_window` and `max_output_tokens` as separate fields, because reading the second as the first is exactly the live defect: `max_output_tokens` is the **output** cap, default 4096; `context_window` is the input ceiling; they are unrelated. The fix at the far end is one line — `TieredCompaction(target_tokens=plan.budget.target)` where 0.8.0 computes a target from `max_tokens`. Keeping them as one field anywhere on the path re-opens the bug.

**Selection and compaction are different mechanisms.** Conflating them is how the budget got wrong in the first place.

| | What | Mechanism |
|---|---|---|
| Before the run | history window (26), retrieved chunks (24), attached files, tool schemas (1) | **selection** — do not put it in if it will not fit |
| During the run | tool results accumulating | **compaction** — unforeseeable, so it must be cleaned up |

Items 26 and 1 are selection, and they belong to `RunPlanner`. Compaction exists for growth that cannot be predicted, not to clean up after a carelessly assembled prompt.

**Where it applies, in order — and only one layer is ever summarized:**

1. **Duplicate tool results** — same file read twice, keep the last. Lossless, free, drop first.
2. **Old tool results** — search hits, graph queries, greps, DuckDB output. **Evicted, not summarized.** Summarizing a grep is pointless: it was fetched for one turn, is stale after it, and is re-runnable if needed. This is the bulk of the saving in a tool-heavy run.
3. **Old history** — the only layer where summarizing makes sense, because conversation is narrative and compresses well.
4. **Never touched:** the current user message, the system prompt, and **user-attached files**. Compacting an attached file silently corrupts the task — "fix the typos in this file" against a summary of the file.

So, by source: history → summarize (last resort); search and graph output → evict; attached files → protect. Every eviction writes a `(what, why)` pair into `RunPlan.evicted`.

**0.8.0's tier order is already correct** — `DeduplicateFileReads` → `ClearToolResults` → `SummarizingCompaction` is exactly 1 → 2 → 3. Only the target number is wrong (see Appendix A). But `ClearToolResults(max_fraction=0.9, keep_pairs=5)` and `DeduplicateFileReads`'s `read_file`-only key both need revisiting once graph (32) and DuckDB (34) results flow through, since neither is keyed for them.

**Limits still absent:** `UsageLimits` is unused and `max_steps` is dropped on the wire, so nothing caps agent rounds. Tool results have no size cap before entering the transcript.

**The escape valve.** Content that can neither be compacted (authoritative) nor fitted is not a compaction problem — it becomes a *retrievable source* instead of inline content. Same rule as item 28: **indexing answers "too big to send."** That is what 33 and 34 are for.

### 4.2 — 32 — Code graph

CodeGraphContext (MIT) — integrated, not built. An **internal** MCP (`is_internal`), never in the Add-MCP form. **One shared HTTP service**, always running; not a container per project (that needs the Docker socket = root on host). **One named graph per project** (`p_<uuid>`) — deliberately unlike 31's shared table, because traversal is recursive and a missing filter walks into another tenant's subgraph. FalkorDB server mode likely, on an instance **separate from Celery's Redis**. Project folders mounted **read-only**; graph volume separate and writable. Activation: auto above a file-count threshold, prompt below; one click, and the click is the onboarding; **maintenance automatic** on checksum change. **Three-layer ignore:** repo `.gitignore` → our vendored/generated defaults (`vendor/`, `*.gen.ts`, `*_pb2.py`) → `.nexusignore`, written on first build so it explains itself; real `pathspec` semantics so `!negation` works. Language allow-list is **system** config, separate from the ignore deny-list. **Model-driven, not pre-injected**, with three scaffolds: a line in `instructions=`, rewritten tool descriptions, and 13 escalating code-modification queries away from the cheap model. **Hard dependency on the filesystem MCP** — traversal needs an entry point. Graph retained on soft delete, dropped on hard delete.

Reached through `RunPlan.retrieval == "code_graph"`, set when the router returns `is_code` (item 13) — not by a second classification pass.

**Open:** does CodeGraphContext support per-request graph targeting? If it is one-server-one-repo, the shared service collapses into a process per project. Second: language quality beyond Python and TypeScript.

### 4.3 — 33 — Content-type routing

| Content | Graph | pgvector | Reached by |
|---|---|---|---|
| `.py` `.ts` `.tsx` `.go` `.rs` … | ✓ | ✗ | graph + grep/read |
| `.md` `.rst` `.txt` `.pdf` `.docx` | ✗ | ✓ | semantic search |
| `.csv` `.xlsx` `.parquet` | ✗ | ✗ | query engine (34) |
| `.yaml` `.json` `.toml`, lock files, images | ✗ | ✗ | grep/read on demand |

**No code embeddings anywhere** — identifiers are poor semantic targets; grep plus the file tree does that job better and never goes stale. No file in two stores. The router is ours.

### 4.4 — 34 — Large CSV and data files

Tabular data is a third retrieval mode: **computational**. **DuckDB** over files in place from the project mount — no ingestion, handles larger-than-RAM, infers schema, reads CSV/Parquet/JSON/Excel, joins two files in one query, a library not a service. **Schema before rows**: store columns, types, row count, nulls and ~5 samples (~200 tokens) on upload. **Cap the result and say it was capped.** **Read-only.** **Two tiers behind one interface** — bundled DuckDB, or a remote HTTP MCP the user supplies (DuckDB+MinIO, ClickHouse, BigQuery) — same tool shape (`describe_schema`, `query`), so the backend swaps with no other change. Results render as tables and charts, which is why 23 matters.

### 4.5 — 39 — Provisioning MCP (agentic project setup)

An **internal** MCP (item 35's category) reached through a reserved channel, where the agent interviews an admin and then *performs* the setup: what kind of project, who to invite, what scope, what each AI team member's role is, which models to use. It is the first item whose tools **write** to nucleus — everything else on the list reads.

**Tools:** `create_project`, `invite_member`, `create_persona`, `assign_role`, `set_permission`, `configure_mcp`, `set_budget`, `create_model_config`. Read-side: `list_available_models`, `list_members`.

**Access:** project owner / project admin / company owner / company admin only — a new `Right` code at PROJECT and COMPANY scope plus a `row_rules.visible_channels` exclusion. Note this is a new pattern: today channels are visible by *membership*, not by role. The reserved channel name also needs protecting, or a user creates their own and shadows it.

**The non-negotiable: it acts as the caller, never as itself.** If the MCP holds a privileged credential of its own, anyone who can reach the channel gains admin-equivalent power through the agent. Every tool call carries the caller's identity through `PermissionChecker.can()` — same check, same scope chain. This is invariant I2 made concrete: a run parked overnight on an approval must **re-check rights on resume**, because the person's role may have been revoked while it waited.

**Two anti-escalation rules:** no self-elevation (the agent cannot grant the caller a right the caller does not hold — otherwise "make me company owner" is a working prompt), and no granting beyond the caller's own grant. `PermissionChecker` may not express these today, since granting rights is normally a UI-only action.

**Secrets never enter a message.** A key typed into chat is already in `ChatMessage.content`, broadcast over Centrifugo, embedded into pgvector by `embed_message_async`, replayed into the next prompt by `fetch_history`, and **sent to the model provider** — the last two being unrecoverable. So: **the agent creates the row with the secret left `null`**, never a placeholder string (a fake key is indistinguishable from a real one by inspection, and fails as an opaque provider 401). The user supplies it through the normal UI. Same pattern for MCP auth tokens. This means item 5's question cards stay simple — radio, checkbox, multi-select — with no secret-input variant and no second response path.

**Setup therefore ends with a punch list, not a completion:** "3 personas and 2 models created; these 2 need keys before anyone can use them." Item 40 lets that list clear itself.

**Scope bounds for v1:** no deletes — create and invite only, destructive operations stay in the UI. And bound it explicitly to provisioning: "set up a project" grows naturally into "manage everything", and a general-purpose admin agent is a far larger security surface.

**Depends on:** 2 (every tool here is an acting tool → `"ask"` by default, which `ACTING_TOOLS` already expresses), 5 (**which has nothing reusable yet** — a prompt convention is not a question card), 9 (the new right; the existing two are TOPIC-scoped, this one is not), 35 (bundled internal MCP), 40 (verification), 13/21 (model suggestion needs cost data, which does not exist — no `cost` column anywhere, and item 14 is blocked on the same gap).

**Open:** company scope, project scope or both; whether it can reconfigure an existing project or only create; whether a half-finished setup rolls back or leaves partial state (invariant I5, and worse here — a double-resumed run that invites five people twice is visible to five people).

**Audit gap this exposes.** Every tool here changes who can do what, or what gets spent — which needs a durable record of who approved what. But `AgentRun` and `AgentApproval` were **deleted** upstream (migrations 0006/0007), and approval decisions currently live in Redis with a 600s TTL. Either provisioning writes its own audit rows, or approval decisions become persistent for acting tools. Decide before building.

### 4.6 — 40 — Credential verification (Test button)

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

`ModelResolver` (§3.2) compares the fingerprint in Pass 1 and drops any config that fails, so a stale key fails with a clear message before assembly rather than as an opaque provider 401 mid-stream.

**Save policy:** enable Save on pass, **allow save-anyway**. An unverified row is harmless because `is_verified` reads false, and a briefly-down provider should not trap someone in a dialog. Surface it instead — "Not verified" on the model, a warning on personas pointing at it.

**Also:** expose `is_verified` and `verified_at` on `ModelConfigOut` so the UI needs no second call. **Rate-limit `/model-configs/check/` per company** — it makes outbound paid calls on user-supplied input, so uncapped it is an amplification vector.

**Generalises to `MCPServer`:** fingerprint over url + auth_type + `secrets_encrypted`, verified by "connect and list tools".

### 4.7 — 35 / 36

- **35.** Filesystem, code graph and data query are *bundled capability MCPs*: internal, activated by content type, model-driven, shipped with the product. 0.8.0 already has `is_internal` (migration 0017). **But see item 20 and Appendix A: the capability registry that would reach them has no readers**, so "bundled" is currently aspirational for everything except the five hardcoded natives. Open: an admin **egress allow-list** for external MCP hosts at company scope, and visible indication when a project sends data off-box.
- **36.** `MEDIA_ROOT` is container-local disk — caps the product at one node and loses files on container replacement. An S3-compatible store (MinIO) for attachments, data files and exports also lets 34's two tiers read from the same place.

---

## 5. Blocking the list

1. **Six items are unaudited against 0.8.0** — 8, 15, 17, 18, 31, and the unverified half of 35. Several may already exist, as 2, 9, 25, 27 and 37 did. Audit before designing.
2. **`_CAPABILITY_REGISTRY` has no readers.** This blocks item 20's agreed replacement (`SubAgents`), item 35's whole premise, and the per-persona compaction route. It is one wiring job that unblocks three items — probably the highest-leverage single fix on the list.
3. **Item 32's blocker:** per-request graph targeting in CodeGraphContext. Decides one service vs one process per project.
4. **Item 14 is blocked on item 21.** There is no cost data anywhere to budget against. 21 lands first or 14 cannot start.
5. **Four defects are silent failures** (Appendix A: compaction target, dropped generation settings, no step cap, FAILED messages in history). Undecided whether they become constraints with tests or stay a defect list. Two of the four cannot be noticed without a test.
6. **`Status.CANCELLED` has no writer** — stopped runs land on `COMPLETED` with `metadata.stopped`. Decide whether the rebuild uses the status or keeps the flag.
7. **Confirm the provider cache ordering** (§4, item 1): if the tool list does *not* sit ahead of system and messages in the cached prefix, the narrow-once-and-hold decision can be relaxed to per-turn narrowing.

**The items that decide the class structure:** 1, 13, 15, 16, 26, 33 — all of which now meet in §3. Items 2, 9, 25 and 27 are answered by 0.8.0's shapes; 5 and 12 are answered badly enough that 5 counts as new work.

---

## Appendix A — defects at 0.8.0 (verified 2026-10-07)

**Severe — silent quality loss**

- **Compaction squeezes every transcript to 3,686 tokens.** `token_target = max(max_tokens - 20_000, int(0.9 * max_tokens))` where `max_tokens` is `persona.model.max_tokens` — the **output** cap, default 4096. So `max(-15904, 3686)` = 3686, on every model regardless of a 200k window. `context_window_for()` exists and is used for the event payload but not here. Fix is §4.1's two separate fields plus `target_tokens=plan.budget.target`. [16]
- **`temperature` and `max_tokens` are dropped.** Nucleus deliberately moved them onto the persona (`internal/api.py:109` says so) but `model_from` still reads them off the model dict → always 0.7 / 4096. This is the cause of the line above. Temperature never reaches the model at all: `build_agent` passes no `model_settings` — which also means no provider cache control reaches anything. [12, 15, 16]
- **`max_steps` is dropped** by `persona_from`; `PersonaConfig` has no such field. `UsageLimits` appears zero times. **Nothing caps agent rounds** — `retries={"tools": 3, "output": 3}` is the only bound. [16]
- **FAILED messages re-enter the prompt as the model's own words.** `fail_ai_message` writes the user-facing sentence into `content`, and the history query filters no status — so the model reads *"The model provider rate-limited this request. Try again in a moment."* as something it said. [26]

**The capability registry is dead**

- **`_CAPABILITY_REGISTRY` has exactly one reference — its own definition.** Zero readers. `_resolve_capabilities` instead hardcodes five natives (shell, thinking, web_search, web_fetch, filesystem). So **`SubAgents`, `SpendLimits`, `Memory`, `Planning` and `Skills` are imported, registered and unreachable**, and the per-persona `COMPACTION` route with them. Consequences: item 20's agreed replacement for swarm does not work; item 35's "bundled capability MCP" category has no delivery mechanism; item 14 loses the `SpendLimits` seam it would otherwise use. One wiring job blocks three items. [1, 3, 14, 16, 20, 35]

**Dropped on the wire**

- `advisor_model` is sent and discarded — `PersonaConfig` has no field; the `Advisor` capability is reachable only through an opaque `capability_config`. [12]
- `supports_vision` is sent and discarded. [28]
- Only `capabilities[0]` is read, with bracket access that raises `KeyError` rather than degrading. A persona with two internal capability rows keeps one. [1, 3, 4, 17]
- `qualified_id` is composed server-side and unused; `build_model` re-derives it.

**History**

- `is_deleted_from_context` has a **writer** (`context/panel_providers.py:156`) and no reader in the history query — so remove-from-context has no effect on the prompt. [26]
- No status filter: all five statuses are admitted. `PENDING` rows are skipped only incidentally, by empty content. [26]
- `limit` has no server-side ceiling, unlike `list_messages` (`le=200`). [26]
- No `SUMMARY` type anywhere; `SummarizingCompaction` output is never persisted back — so there is no anchor for §4's "always anchor at the summary". [6, 26]

**Usage / tenancy**

- `AIRequestLog` has **zero live writers** — `_post_ai_request_log` exists only in `litellm_runner.py`, which `AgentFactory` cannot reach. The endpoint's docstring still claims it is "called by nexus-ai after every model completion". [21]
- A **stopped run loses its usage**: published as three `None`s, because usage only arrives on `message_done`, which a stopped run never reaches. Cancelled runs' tokens go uncounted. Fixed by §3's row-at-start. [21, 37]
- `internal/api.py:443` picks the company with `Company.objects.filter(is_active=True).first()` rather than deriving it from the job — a single-tenant assumption in a multi-tenant product. Same pattern in eight other service modules. [21]
- No `cost` column; `ModelUsageLog` and its `cost_usd` were dropped in migration 0008 having never had a writer. This is what blocks item 14. [14, 21]

**Rate limiting**

- **No per-user or per-model rate limiting exists.** The only limiter is `within_rate_limit(hook)` (`scheduling/hooks.py:199`), per inbound hook. `chat/api.py:158` documents a client-side throttle in `MessageInput.tsx`, which is not enforcement. Matches for `rate_limit` elsewhere (`chat/reasons.py:20`, `apps/managers/fallbacks.py:42,46`) are 429 *classification*, not limiting. [10, 11]

**Contract / dead code**

- `message_type` is never carried on `message_done`. AI rows stay `message_type="text"` permanently even when resolved as `chart` or `code`. [23, 25]
- `keepalive` is emitted by the worker and matched by no branch in the nucleus relay. `persist_internal_state` never reaches nucleus — the manager `continue`s past it. [25]
- `chat/tasks.py` is unreferenced dead code using a **different** channel (`topic:{id}`, colon) and vocabulary (`token`/`done`/`error`), and is the only writer of `Status.STREAMING`. [25]
- `Status.CANCELLED` has no writer. [37]
- Tool results have no size cap before entering the transcript — the 600-char cap is only the preview sent to nucleus, and the 50k cap is shell-only. `ClearToolResults` is the only backstop and fires after the fact. [16]
- `DeduplicateFileReads` keys only on `read_file`. [16]
- `_MODEL_REGISTRY` has four providers; no `ollama`, no `google`. `openai_compatible` + `api_base` covers Ollama/vLLM/LM Studio, so this may be deliberate — but item 13's local router depends on it, so confirm rather than assume. [7, 13]
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
| `output_type=` | construction | **13 only** — the router wants a validated struct, not prose; `retries={"output": 3}` covers a model that ignores the schema. Everywhere else output streams to a human and this gets in the way. |
| `model_settings=` | construction | 12, 15 — **currently passed as nothing at all** |
| `deps_type=` | construction | caller / topic / permitted set into tools |
| `retries=` | construction | the only loop bound today |
| `run_stream_events(message_history=…)` | run | 25 |
| model override on the run call | run | 13 — escalation needs no second Agent |
| `UsageLimits` | run | 16 — unused |
| `message_history: list[ModelMessage]` | run | 15, 24, 26 — no prompt builder exists; we construct these, in the cache order §4 item 15 fixes |

**Mid-run pause is a capability hook, not deferred tools.** 0.8.0's `ToolApprovalGate` implements `prepare_tools` and `before_tool_execute` on a harness `AbstractCapability`, and awaits an HTTP poll of nucleus-held state. The pydantic-ai primitives `requires_approval`, `DeferredToolRequests`, `DeferredToolResults`, `ToolApproved`, `ToolDenied`, `CallDeferred` and `HandleDeferredToolCalls` appear **zero times** in the repo; `DECISIONS.md` records the substitution as deliberate. Earlier versions of this document assumed the deferred-tool route — that was wrong about the code, though the primitives remain available if the rebuild prefers them.

`before_tool_execute` returns `args`, which is what makes it the general seam: it can block (await a decision), refuse (`raise SkipToolExecution`), **or silently rewrite the arguments** before the tool runs. Three behaviours from one return type.

**`WrapperModel` exists** — `InstrumentedModel` and `ConcurrencyLimitedModel` are both instances of it. A `WrapperModel` *is* a `Model` and *holds* a `Model`, so wrapping nests and `Agent` cannot tell how deep it goes. A custom subclass is the mechanism for item 11's tokens-per-minute enforcement: acquire from a shared bucket, `await super().request(...)`, charge `response.usage.total_tokens`. `ConcurrencyLimitedModel(model, limiter=N)` caps concurrent requests, not token rate. `[?] WrapperModel.__init__` / `.request` signatures are inferred from `InstrumentedModel` being one, not read from the base class — confirm with `inspect.signature` before building item 11.

**Usage is already modelled by the framework.** `UsageBase` carries `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cache_audio_read_tokens`, `details`, `total_tokens`, **`cost`** and **`cache_hit_ratio`**, plus `opentelemetry_attributes()`. `RunUsage` adds `requests` and `tool_calls`. Read off the stream object as a property after it drains. 0.8.0 reads only `input_tokens` and `output_tokens` — cache fields and cost are available and unused, and `cache_hit_ratio` would let 15 prove caching works rather than assuming it.

**Telemetry is not the billing source.** `InstrumentedModel` belongs to **pydantic-ai, not logfire** — they meet at OpenTelemetry, which is why any OTel backend works and item 8 is not locked to Logfire's cloud. `logfire.configure()` installs itself as the global `TracerProvider` once at process start, and pydantic-ai finds it with no wiring. But spans are sampled and droppable, so they are observability, never the usage record. Central telemetry is deliberately **only two numbers** — instance count keyed by the existing `NEURALOPS_INSTALL_TOKEN`, and total tokens — documented and disableable by one env var, since the product is sold on nothing leaving the network. Per-project budgets (14) are a customer-side feature and separate.

**Stays ours (no framework equivalent).** pydantic-ai has no retrieval abstraction and no prompt builder: `EmbeddingModel`, `VectorStore`, `ContextAdapter`, `ContextSource` and their factories; the content-type router (33); the whole of §3's pipeline (`RunPlanner`, `MessageAssembler`, `ToolEligibility`, `Router`, `UsageRecorder`); `AgentEvent` / `TriggerJob` / `PersonaConfig` (the wire contract with nucleus); the `output_types` registry; `AgentRunner`.

---

## Appendix C — starting prompt

Paste this into a fresh session. It is written to be standalone: a new session has none of the context that produced this document.

> **Updated 2026-10-10:** nexus-ai is now rebuilt as a **new module** with the architecture in §1.3–§1.5, designed layer by layer (§1.2). The "FIRST WORK" list below (wiring `_CAPABILITY_REGISTRY`, patching 0.8.0 code) predates that decision: in the rebuild those defects become requirements on the new classes, not patches to old code. The working rules ("HOW I WORK") still apply.

```
I own NeuralOps Nexus, a self-hosted multi-tenant AI chat product. I am rebuilding
the `nexus-ai` module. `nexus-nucleus` schema and API are largely kept.

REPO
  /data/code/neuralops-forked  (device: node3-neuralops-forked)
  Baseline: upstream/dev @ 939af00 = server 0.8.0. The fork was merged up to this
  on 2026-10-08. Verify against `upstream/dev`, never `upstream/main`.

READ FIRST, IN THIS ORDER
  docs/NEXUS-AI-REVAMP.md
    §1          the list — 48 items (0–47), with status against 0.8.0; §1.1 scope, §1.2 layers, §1.3 architecture decisions
    §3          the run pipeline — the two passes and the cross-cutting classes
    §4          what is settled but not built, per item
    §5          what is blocking
    Appendix A  defects at 0.8.0 the rebuild must not inherit
    Appendix B  pydantic-ai / harness seams, with what is verified and what is not
  docs/nexus-ai-run-example.py
    The worked example for §3 — not runnable, it pins the shapes and the order.
    Every line is marked [V] verified at 0.8.0, [?] unverified library signature,
    or [NEW] our design. Where it disagrees with §3, §3 wins.
  Do not restate either back to me. Tell me what you think is wrong in them.

HOW I WORK — THIS MATTERS MORE THAN SPEED
  1. We settle an item in discussion first. Then it gets written into the doc.
     Never write a document ahead of the discussion.
  2. Do not predefine architecture. The new design comes out of the settled items.
  3. When I ask you to explain one thing, explain that one thing. Do not expand
     scope, do not volunteer adjacent work, do not launch subagents unless I ask.
  4. If I ask for a command, give me the command. Do not run an investigation
     instead.
  5. Never infer an item's status from a filename. `git grep` it against
     upstream/dev and quote file:line. Four earlier status calls in this document
     were wrong because they were inferred rather than read.
  6. Mark anything unverified as unverified. I would rather have a gap than a
     confident guess.

THREE FIXED CONTRACTS — everything inside them is free to change
  TriggerJob in · AgentEvent out · the /internal/* back-calls to nucleus

VERIFY BEFORE WRITING ANY CODE — three unknowns are load-bearing
  1. WrapperModel's real signature. Item 11 (per-model rate limits) depends on it.
     Appendix B infers it from InstrumentedModel rather than reading the base class.
       docker compose -f docker-compose.neuralops.yaml exec nexus-ai python -c \
         "import inspect; from pydantic_ai.models.wrapper import WrapperModel; \
          print(inspect.signature(WrapperModel.__init__)); \
          print(inspect.signature(WrapperModel.request))"
  2. Provider prompt-cache ordering. If the tool list does NOT sit ahead of system
     and messages in the cached prefix, §4 item 1's narrow-once-and-hold decision
     can be relaxed to per-turn narrowing. Check current provider docs.
  3. Does CodeGraphContext support per-request graph targeting? Decides whether
     item 32 is one shared service or one process per project.

FIRST WORK, IN THIS ORDER, AND WHY
  1. Wire `_CAPABILITY_REGISTRY`. It has exactly one reference — its own
     definition. Zero readers. That single gap blocks item 20's agreed swarm
     replacement (SubAgents), item 35's entire bundled-MCP premise, and item 14's
     SpendLimits seam. One wiring job, three items unblocked. Highest leverage
     thing on the list.
  2. Split `context_window` from `max_output_tokens` everywhere on the path
     (§3.2 ModelSpec, §4.1). Then `TieredCompaction(target_tokens=...)`. This is
     the live defect that squeezes every transcript to 3,686 tokens on every
     model regardless of window size. Write the test first — it is invisible
     without one.
  3. Land item 21 (usage recording, all nine RunUsage fields, row at start).
     Item 14 is blocked on it: there is no cost data anywhere in the product.
  4. Audit the six remaining unverified items: 8, 15, 17, 18, 31, and the
     unverified half of 35. Several may already exist — 2, 9, 25, 27 and 37 all
     turned out to be built. Audit before designing.

WHAT I WANT NEXT FROM YOU
  Per list item: the inheritance sketch (what inherits from what) and the
  sequence from the nucleus API call through to nexus-ai, connected across items
  so they compose into one class diagram. I will verify, query and change the
  design. Start with the item I name — do not work ahead through the list.
```

