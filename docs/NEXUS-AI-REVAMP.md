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
| 8 | Telemetry | **Resolved** 2026-10-14 — Layer 5 decision 6: no tracing; one-value (total tokens) phone-home, nucleus-side, always on | nucleus |
| 9 | Persona call rights | **Built** — `persona.mention` + `persona.approve_run` | nucleus |
| 10 | Per-user rate limits on persona calls | **Remaining** — one precedent, hooks only | nucleus |
| 11 | Per-model rate limits | **Remaining** — `WrapperModel` is the seam | nexus-ai |
| 12 | Multiple models per persona | **Built** — own retry, not `FallbackModel` | both |
| 13 | Model choice by query depth | **Settled** — nothing exists | nexus-ai |
| 14 | Fixed budget per project | **Remaining** — blocked: no cost data anywhere | nucleus |
| 15 | Prompt / model caching | Not audited — constraints settled, see §4 | nexus-ai |
| 16 | Tool loop and context limits | **Settled** — tiers right, budget wrong | nexus-ai |
| 17 | Connectors | **Settled** 2026-10-14 — Layer 5 decision 3: bundled MCPs + the NeuralOps MCP gateway; MCP/nucleus track, zero engine code | both |
| 18 | Claude Agent SDK runtime | **Deferred** 2026-10-14 — Layer 5 decision 1; the AISystem seam is built and tested | nexus-ai |
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
| 39 | Provisioning MCP — agentic project setup | **Settled** 2026-10-14 — Layer 5 decision 4: a bundled connector, fenced to the "configure" topic (4 roles); own project on the MCP track | both |
| 40 | Credential verification — Test button, fingerprinted | **Partly built** — only persistence missing | both |
| 41 | Terminal pane (`/terminal/ws`) | **Dropped** — removed from nexus-ai, see §1.1 | — |
| 42 | Browser pane (`/browser/ws`) | **Dropped** — removed from nexus-ai, see §1.1 | — |
| 43 | Message search for people (`/search/messages/`) | **Moved to nucleus** — plain DB search, see §1.1 | nucleus |
| 44 | Chat-message embeddings for the persona | **Remaining** — Layer 3, see §1.1 | nexus-ai |
| 45 | Persona chain under a supervisor persona (team workflow) | **Settled** 2026-10-14 — Layer 6 decisions 1–2: nucleus orchestrates, workflow MCP drives; engine hooks built (turn_rules, call_persona) | both |
| 46 | Delegation as tools: `escalate` (to the persona's deeper model) and `call_persona` (to another persona), with a `Handover` package | **Built** — escalate 2026-10-13 (Layer 2), call_persona 2026-10-14 (Layer 6, trial I) | nexus-ai |
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

#### Layer 1 — decisions before design (settled 2026-10-12)

Settled in discussion ahead of the Layer 1 item designs (items 3, 1, 2, 19, 22, 35; order inside the layer: 3 → 1 → 2 → 19 → 22 → 35, item 4 decided alongside 3).

1. **Approvals pause and resume via pydantic-ai deferred tools** (items 2, 27). A run that hits an `ask` saves its state, ends its stream cleanly (one final event, as ever), and resumes when the decision arrives — no run parks under keepalive for hours. Consequence: item 27's save/resume machinery moves into Layer 1 — the two nucleus endpoints already implied in §1.4 (save/load paused run state; resume a paused run with the decision) arrive now. **Behaviour trial required before item 2's class design:** trial A9 verified only that the names exist in the pinned 2.55 (`DeferredToolRequests`, `DeferredToolResults`, `ApprovalRequired`, `ToolApproved`, `ToolDenied`); a throwaway trial must pause a run on an approval, serialize its state, and resume it in a FRESH process. If that fails, the fallback is 0.8.0's park-in-stream gate (§2, item 2) — chosen knowingly, not by surprise.
2. **The approver is configurable: `approval_scope: topic | requester_only`, default `topic`** — anyone holding `persona.approve_run` at that topic may decide (reuses item 9's existing right and its enforcement on the approval path; a company-wide Viewer is already excluded). Where the setting lives (persona vs project): decided with item 2's design.
3. **The tool set is fixed per topic** — §4 item 1's narrow-once-and-hold stands, forced by the provider cache order (tools → system → messages: the definitions sit at the FRONT of the cacheable prefix, so they must be stable; tool calls and results are ordinary messages at the back and never break the prefix). The router picks the initial loaded set; everything else eligible stays in the prompt as a one-line catalog.
**Deferred-tools behaviour trial (run 2026-10-12, pinned 2.55.0 — decision 1 CONFIRMED):** same instrument as the 2026-10-10 trial (fake OpenAI-shaped server, no product code). Results: (D1) a tool declared `requires_approval=True` pauses the run — it ends cleanly with `DeferredToolRequests` carrying `tool_call_id`, tool name and args, and the stream emits a `DeferredToolRequestsEvent` (the natural hook for the `approval_requested` AgentEvent); the tool does NOT execute. (D2) the whole resume state is `result.all_messages()` serialized with `ModelMessagesTypeAdapter.dump_json` (≈1.5 KB for a one-call run). (D3) a FRESH process rebuilt the agent, passed `message_history=` + `deferred_tool_results=DeferredToolResults(approvals={call_id: ToolApproved()})` — the tool executed there with the original args and the reply finished. (D4) `ToolDenied("…")` — the tool never ran; the denial text reached the model as the tool result and the model answered on. (D5) the paused call's `RequestUsage` is readable at pause time, so billing per call survives the pause. One requirement this places on the design: the resuming process must rebuild the agent with the SAME tools — given tools are built from `PersonaSpec` per run, that holds by construction. Mark: `output_type=[str, DeferredToolRequests]` is required on the agent for the pause to surface.

4. **A ToolSearch addition asks the user — once per tool per topic.** When the model requests an unloaded tool, the user is asked whether to add it to the topic's set; approved → the schema joins the fixed set (one deliberate cache miss) and is never asked about again in that topic. RUNNING the tool is governed separately by item 2's `auto/ask/off` gate, and write tools always ask — loading and executing are two different permissions. The ask-to-load prompt is itself a paused-run case, served by the same deferred-tool mechanism as approvals: one pause machinery, both uses. This also retires §4 item 1's "silent incapability" worry: a wrong router guess now costs one visible question, not a mystery failure.

**Item 2 — decisions before design (settled 2026-10-12):**

5. **`approval_scope` lives on the persona** (ships in `PersonaInternal`, lands in `PersonaSpec`) — each agent carries its own trust rule. Enforcement stays nucleus's: whoever decides must hold `persona.approve_run` at that topic (admins have it through their role); `requester_only` additionally requires being the message's sender. nexus-ai never checks who decided; it only receives the decision.
6. **"Always allow" is narrowed, not general** (stricter than 0.8.0, which cleared a tool for the rest of the run): read tools run automatically and never ask; **write tools ask every time — no always-allow escape, per-topic or otherwise**; the only "always allow" left is for an MCP tool with no `readOnlyHint` (default ask) — a yes means "treat this tool as a read in this topic", stored next to `topic_tools` (nucleus change 8), never asked again in that topic. Writes stay outside it entirely.
7. **The approval card carries 0.8.0's 300-char `args_preview` only**; the full args already travel inside the pause state nucleus stores, so an expand view is nucleus-side UI work with nothing new on the wire.

**Capability-tools trial (trial E, run 2026-10-12, pinned 2.55.0 — the gate design CONFIRMED):** same instrument as D1–D5 (fake OpenAI-shaped server, throwaway code, no product code). Question: D1–D5 proved the pause only for a plain `@agent.tool_plain(requires_approval=True)` tool — do CAPABILITY tools (natives, MCP) pause too? Results: (E0) `requires_approval` is sugar for `ToolDefinition.kind='unapproved'`; a separate gate capability's `prepare_tools` hook receives EVERY capability's tool definitions (harness FileSystem's eight tools included) and may rewrite `kind` — so one gate capability can gate all sources, exactly 0.8.0's `ToolApprovalGate` shape ported. (E1) harness `FileSystem.write_file` flipped to `unapproved` paused the run with `DeferredToolRequests` (and `DeferredToolRequestsEvent` on the stream); the file was NOT written. (E2) pause state ≈1.6 KB; the paused call's usage readable at pause (billing holds). (E3) a FRESH process + `ToolApproved()` → the file was written there; `ToolDenied("…")` → no file, the denial text reached the model as the tool result. (E4) the MCP shape — the capability wrapped in `PrefixTools` — pauses the same way, keyed on the prefixed name. **Two bugs found in shipped Layer 1 code:** (a) pinned `PrefixTools` joins names as `{prefix}_{name}`, so `ToolsetBuilder` must pass `"{slug}_"` to get the catalog's `{slug}__{tool}` — **fixed 2026-10-12**, 36/36 tests green; (b) harness `FileSystem`/`Shell` REQUIRE a workspace capability on the run (`LocalWorkspace(...)`; `UserError` without one) — ToolsetBuilder ships none, so a persona with filesystem/shell currently fails at the first model call that uses them. **OPEN — fixed in item 2/22's pass:** where the workspace root (the project folder) comes from is item 22's sandbox-config question.

#### Item 3 — persona tool/MCP list (settled 2026-10-12, with item 4)

1. **Problem.** Before anything can be narrowed (item 1) or gated (item 2), nexus-ai must know every tool a persona could use — by NAME, with a one-line description and a read-only hint — not just the servers. The prompt catalog, ToolSearch and `tool_levels` all key on tool names; 0.8.0 knows an MCP server's tool names only after dialing it.
2. **Decision.** **Hybrid: stored catalog + live at connection + drift sync.** (a) nucleus stores, per MCP server, `tools: [{name, description, read_only}]` — captured by extending item 40's verify to MCPServer exactly as §4.6 proposes ("connect and list tools") — and ships it inside `MCPServerInternal`. (b) At run time, any server in the topic's LOADED set is dialed for the run anyway; its **live** tool list is the truth for execution. (c) When the live list differs from the stored one, nexus-ai posts the fresh list back to nucleus (drift sync) — the catalog heals on the next reply that used the server, not only on the next admin Test. **Rejected:** runtime-dial-only — every topic's first reply pays N dials, a dead server stalls the whole catalog, and the cache has no home (nexus-ai owns no store); stored-only without drift sync — rots silently. **Namespacing (settled):** catalog/levels id = `mcp:<server_id>/<tool>` for external tools, `<capability>` or `<capability>/<tool>` for natives (the keying 0.8.0's levels already support); the MODEL-facing tool name is prefixed with the server's slug (`github__search`, `monday__search`) so two servers' same-named tools never collide — `ToolRegistry` owns the mapping back to the right server. **Item 4 / eligibility formula (amended 2026-10-12):** eligibility is one intersection with two independent axes — `eligible(persona, topic) = available(servers in this scope) ∩ allowed(this persona)`. The SERVER axis (where a server is available: project today; channel/topic later) is item 4 — stays PROJECT-scoped in Layer 1, deferred as a nucleus data-model change; when it lands, only nucleus's `available()` changes, nexus-ai is untouched. The PERSONA axis is new (nucleus change 7): **`Persona.tool_access: selected | all_project`, default `selected`** — `selected` = exactly the persona's attached servers (today's M2M), `all_project` = every project MCP, current and future (an explicit admin choice, never the default, because it widens the persona silently whenever a project MCP is added). Resolved in nucleus inside the persona endpoint; `ToolRegistry` just reads what arrives. Division of labour stays clean: `tool_access` decides what is ELIGIBLE, the router/cap decides what is LOADED, item 2's gate decides what may RUN.
3. **Mechanism.** `MCPServerInternal` gains the `tools` list (nucleus change 6); `PersonaSpec` already carries both source lists raw since Layer 0; `ToolRegistry` (ai_engine/pydantic_ai_system/tools/) builds the catalog; native capabilities' names and one-liners come from a small static table keyed on `capability_config`.
4. **At 0.8.0.** The internal/external split already arrives as two lists (`NU/internal/api.py` get_persona_internal); `tool_levels` keys `"<capability>/<tool>"` are already honoured by the approvals defaults; MCP tool names exist nowhere until dial time (`MCP(defer_loading=True)` in the runner); `_resolve_capabilities` hardcodes five natives (Appendix A — becomes a requirement on ToolRegistry, not a patch).
5. **Open.** Does the pinned harness 0.55 `MCP` capability already namespace tool names? (check before coding; reuse its scheme if so). Exact drift-sync endpoint shape — folded into the Layer 1 nucleus handoff.
6. **Acceptance (sketch).** Two servers exposing a same-named tool → two distinct catalog ids AND two distinct model-facing names; the catalog builds with ZERO network calls when nucleus sends tool lists; a live list differing from the stored one → exactly one drift POST with the fresh list; natives catalogued from `capability_config` with read-only hints; a persona with no tools → empty catalog, plain Layer 0 reply.
7. **Classes and methods.** `ToolCatalogEntry` (frozen): `tool_id`, `model_name`, `source_id`, `source_kind: native|mcp`, `one_line`, `read_only: bool|None`. `ToolRegistry`: `catalog_for(persona) -> list[ToolCatalogEntry]` (pure, no I/O — testable like HistoryPolicy); the loaded-set side (`tools_for`) arrives with item 1.
8. **API.** Nucleus change (6): `MCPServerInternal` += `tools` (filled at save/verify, §4.6's generalisation); new drift-sync endpoint nexus-ai → nucleus (shape with the Layer 1 nucleus handoff).
9. **Sequence.** `get_persona` → `ToolRegistry.catalog_for()` → three consumers: prompt catalog section, ToolSearch searchable set, item 1's loaded-set decision. At run: loaded servers dialed → live lists are the execution truth → drift detected → one POST back to nucleus.

#### Item 1 — tool matching and the permitted set (settled 2026-10-12)

1. **Problem.** The catalog says what a persona COULD use; the model must get a small, STABLE set of full schemas (the cache prefix demands stability — §1.3 Layer 1 decision 3) plus a cheap view of the rest. Something must decide that loaded set once per topic and remember it — and nexus-ai deliberately owns no store.
2. **Decision.** The topic's loaded set is **stored by nucleus on the topic** and shipped in `TriggerJob.topic_tools` (nucleus change 8). First reply in a topic, Layer 1 (no router yet): **all eligible tools, capped by the setting `MAX_LOADED_TOOLS`** (default 12), rest catalog-only; Layer 2 replaces exactly this seam with the router's `tool_hints` — one method body. Additions only via ToolSearch's ask-on-first-load (§1.3 Layer 1 decision 4); an approved addition returns to nucleus WITH the approval decision, so storage and approval travel one path. **Rejected:** a Redis for nexus-ai (new infrastructure for one key); per-turn re-narrowing (a cache miss every turn — §4 item 1).
3. **Mechanism.** `ToolRegistry.tools_for(persona, job) → LoadedSet` (uses `job.topic_tools` when present, else the capped default); `ToolsetBuilder` turns the loaded entries into harness objects (natives from `capability_config`, `MCP(...)` per loaded server, ToolSearch over the catalog minus loaded); `PromptLayout` gains a STABLE `tool_catalog` section (one line per eligible tool); `TriggerJob` accepts `topic_tools` (absent from today's nucleus → first-reply rule applies — works unchanged, like O2's ids).
4. **At 0.8.0.** No modelled distinction between permitted and sent; the set is assembled per run from the persona alone and persisted nowhere; `ToolSearch(strategy=None)` — selection explicitly disabled; no catalog.
5. **Open.** `MAX_LOADED_TOOLS` default (12 proposed); whether the catalog section also lists loaded tools or only the unloaded rest (decided in review of the prompt text).
6. **Acceptance (sketch).** `topic_tools` present → exactly those schemas in the request, regardless of eligibility count; absent → all eligible capped at the setting; the catalog section is byte-identical across turns of a topic; loaded schemas appear in the provider request body and unloaded ones do NOT; two same-named tools from different servers both loadable and distinct in the request.
7. **Classes and methods.** `LoadedSet` (frozen): `tool_ids`, `catalog_hash`. `ToolRegistry.tools_for(persona, job) -> LoadedSet`. `ToolsetBuilder.build(loaded, catalog, persona) -> list` (the only class here that touches harness objects, per dependency rule 2).
8. **API.** Nucleus change (8): topic record stores the loaded tool set; `TriggerJob` += `topic_tools`; an approved ask-to-load updates the topic record on the approval path. (Change 7, `tool_access`, is item 3/4's.)
9. **Sequence.** trigger (`job.topic_tools`) → `catalog_for` → `tools_for` → `ToolsetBuilder` → `AgentBuilder` (gains a toolsets argument — the L1 addition §1.5's catalog already reserves) → run; ToolSearch request → pause (item 2's machinery) → approved → nucleus updates the topic set → resume.

#### Item 2 — tool permission before use (settled and built 2026-10-13)

1. **Problem.** Tools that change something need a person's yes before they run. 0.8.0 held the reply stream open and POLLED nucleus for the decision (`NA/managers/approvals.py` NucleusApprovals) — a long wait holds a connection for hours and dies with a restart; timeouts had to exist just to cap the damage.
2. **Decision.** **Pause and resume via deferred tools** (§1.3 decision 1, trials D1–D5 + E confirmed): a run that hits an `ask` tool ends cleanly, its state goes to nucleus, and the decision later resumes it — in a different process if need be. The POLICY is 0.8.0's `level_for`, ported and narrowed by decision 6: reads auto, writes ask EVERY time, an unlabeled MCP tool asks unless the topic cleared it as a read (`topic_tool_clearances` — the only "always allow" left). Explicit persona `tool_levels` still win over all defaults (an admin's deliberate setting is a different lever than the card's button); `off` now removes the tool from the CATALOG, not just the run. `approval_scope: topic | requester_only` lives ON THE PERSONA (decision 5), enforced by nucleus under `persona.approve_run`. The card carries only the 300-char `args_preview` (decision 7). Unattended runs (`interactive=false`) never pause: the ask-tool is refused with 0.8.0's "nobody can approve" text and the model answers on. **Rejected:** 0.8.0's park-in-stream gate — kept only as the named fallback, a pause costs nothing and survives restarts; a general "always allow" — a write asks every time, per decision 6; a separate resume endpoint — the resume is the SAME `/trigger` with a `resume` block, so the whole reply path stays one road.
3. **Mechanism.** `ApprovalPolicy` (pure: `runtime_level`, `catalog_level`, `args_preview`, the ported texts) + `ApprovalGate(AbstractCapability)`: `prepare_tools` sees EVERY capability's tool defs (trial E0), drops `off`, flips `ask` to `kind='unapproved'` (the pause mechanism, E1), and records name→capability_id for the cards; `before_tool_execute` refuses ask-tools in unattended runs via `SkipToolExecution`. A run ending in `DeferredToolRequests` sets `ReplyGenerator.pause_info()` (state = `all_messages()` JSON + pending calls + catalog hash); `PydanticAISystem` then records usage (the paused call's numbers are real — D5/E2), POSTs the state to nucleus, and closes with the new final event `message_paused` — state FIRST, so a decision can never race an unsaved pause; a failed save is a real error. `EventMapper` turns `DeferredToolRequestsEvent` into `approval_requested` events in 0.8.0's exact `ApprovalRequestData` shape. Resume: `TriggerJob.resume = {state, approvals: {call_id: {decision, reason?}}}` — the same agent is rebuilt (same persona → same tools, by construction), `message_history=` the stored state, `deferred_tool_results=` the decisions (`ToolDenied` carries 0.8.0's denial text when no reason is given), and the reply streams to `message_done`. `EventStream` counts `message_paused` as a final event. `AgentBuilder` sets `output_type=[str, DeferredToolRequests]` (required for the pause to surface — trial D mark).
4. **At 0.8.0.** The whole gate exists as park-in-stream: `ToolApprovalGate` (prepare_tools filters off, before_tool_execute asks), `NucleusApprovals` announcing `approval_requested` and polling `GET /internal/messages/{msg_id}/approvals/{call_id}/`, decisions stored on the reply row under `persona.approve_run`, "always allow" clearing one tool for the rest of the RUN. Event name, `ApprovalRequestData` fields and the did-not-run texts are kept verbatim so nucleus's relay and card UI carry over; only the WAITING changes.
5. **Open.** (a) **RESOLVED 2026-10-13** — ToolSearch is wired (trial F below, tests/test_discovery.py). One deliberate reframe of decision 4: discovery itself is SILENT (portable across providers — the load mechanism differs per provider and cannot be intercepted uniformly); the ASK moved from load time to the tool's **first use** — one approval card both runs that call and adds the tool to `topic_tools` (change 8), so it stays once-per-tool-per-topic for reads, and writes keep asking every time. Loading a schema alone never asks, which also means a wrong discovery costs nothing. (b) **RESOLVED 2026-10-13** — the workspace root comes from `capability_config` `root_dir`/`cwd`; nucleus's project provisioning writes the project folder there (`/nexus/projects/<slug>` — CapabilityInternal docstring), and an unrooted config falls back to `"."` exactly as 0.8.0's FileSystem default did (item 22 "stays as-is"); the louder refusal built on 2026-10-12 was replaced with this parity. (c) **RESOLVED 2026-10-13** — the e2e dial test (tests/test_mcp_dial.py) proves a live server's `readOnlyHint` annotation survives the pinned MCP capability into `ToolDefinition.metadata`: an unlabeled-catalog read tool ran without asking on the annotation alone. (d) A resume emits a second `message_start` on the same msg_id — nucleus's relay must treat it as the stream reopening (handoff note). (e) Pause expiry is nucleus's job (e.g. a 24h cron that resumes-with-deny); nexus-ai holds nothing while paused.
6. **Acceptance (built, tests/test_approvals.py).** A write tool pauses the run (approval_requested + message_paused, state POSTed BEFORE the final event, file not written, paused call billed); an approved resume executes the tool in the resumed process and finishes (both halves billed); a denied resume never runs the tool and the model sees the denial text; a read tool runs silently; `off` removes catalog + tools + section; an unattended run refuses instead of pausing. Policy units: native read/write defaults; explicit levels win; unlabeled-MCP ask / clearance / known-write-never-cleared / stored-read silent.
7. **Classes and methods.** `ApprovalPolicy` + `ToolSource` (tools/approval_policy.py); `ApprovalGate` with `tool_capability_ids` (tools/approval_gate.py); `PendingApproval`, `PauseInfo` (core/specs.py); `PersonaSpec.approval_scope`; `ReplyGenerator.generate(request, capabilities, resume, catalog_hash)` + `pause_info()`; `NucleusClient.save_pause`; contracts: `ResumeBlock`, `ApprovalDecisionIn`, `ApprovalRequestData`, `AgentEventType.APPROVAL_REQUESTED/PAUSED`, `TriggerJob.topic_tool_clearances/resume`; `ToolsetBuilder.build(..., interactive=, clearances=)` now also assigns explicit capability ids and the `LocalWorkspace`.
8. **API.** Nucleus change (9): `POST /api/v1/internal/messages/{msg_id}/pause/` ← `{job_id, topic_id, persona_id, state, catalog_hash, pending: [{call_id, tool, capability_id, args_preview}]}`; the resume is the SAME trigger endpoint with the stored `state` back in `resume`. Change (8) extended: the topic also stores the clearance list, shipped as `topic_tool_clearances`. The persona endpoint ships `approval_scope` (with change 7's `tool_access`). Nucleus owns: the card UI (it already has it), WHO may decide (`persona.approve_run` + `approval_scope`), firing the resume, and expiring stale pauses.
9. **Sequence.** trigger → gate flips ask-tools → model calls one → run pauses → `approval_requested` event(s) → usage recorded → pause POST → `message_paused` → a person decides (nucleus checks the right and the scope) → nucleus resends the trigger with `resume` → same build, history = state, decisions in → tool executes (or the denial text goes to the model) → normal stream → `message_done` (or the next ask pauses again, same machinery).

**ToolSearch trial (trial F, run 2026-10-13, pinned 2.55.0 — decision 4's mechanism CONFIRMED):** same throwaway instrument. (F0) a gate capability's `prepare_tools` can set `defer_loading=True` AND `kind='unapproved'` on another capability's tool defs in one pass. (F1) deferred tools are absent from the provider request; `ToolSearch(strategy="keywords")` exposes one model-facing tool named **`search_tools`**; after the model calls it, the discovered tool's schema appears in the NEXT request (`{"discovered_tools":[…]}` as the tool result). (F2) the discovered tool's first CALL pauses the run with `DeferredToolRequests` — the same pause machinery as approvals, one road. As built: `ToolsetBuilder` now builds ALL eligible capabilities (not only loaded); the gate hides tools outside `topic_tools` and arms their first use; `ToolSearch(strategy="keywords")` is appended only when something is hidden (zero overhead otherwise — and a toolless or fully-loaded persona keeps the exact Layer 0/1 request shape, byte for byte).

#### Item 19 — tool activity visibility (ported 2026-10-13)

1. **Problem.** A reader must see what a tool did — name, outcome, duration, a glimpse of the result — without the raw object, so a run can be audited from the chat.
2. **Decision.** Port 0.8.0 verbatim: events `tool_call_start` (`ToolCallData: name, args`) and `tool_call_end` (`ToolResultData: name, ok, duration_ms, preview ≤600 chars, error ≤300, url`), the web-url rule included (web_fetch's url; a search's results page). One deliberate simplification: 0.8.0 subtracted approval WAIT from the duration (`ToolApprovalGate.waits`) — with pause/resume the wait happens BETWEEN runs, so a resumed call's duration counts from the resume and the subtraction bookkeeping is gone. **Rejected:** new event shapes — the relay already speaks these.
3. **Mechanism.** `EventMapper` maps `FunctionToolCallEvent` → start (records t0 per call id) and `FunctionToolResultEvent` → end (`RetryPromptPart` = failed call); buffered text is flushed before each tool event so wire order mirrors what happened.
4. **At 0.8.0.** `NA/implementations/agents/tool_events.py` + runner 174-201; nucleus relays and stores the trail (`NU/chat/services.py:800-815`).
5. **Open.** None.
6. **Acceptance (built).** tests/test_discovery.py::test_i19 — start before end, name+args on start, ok/duration/preview on end; the MCP dial test asserts the same for a real MCP tool.
7. **Classes and methods.** contracts: `ToolCallData`, `ToolResultData`, `AgentEventType.TOOL_CALL_START/END`, `AgentEvent.tool_call/tool_result`; `EventMapper`: the two branches + `preview_of`, `url_of`, `_args_dict`.
8. **API.** None — stream events only, 0.8.0 shapes unchanged.
9. **Sequence.** model calls tool → `tool_call_start` → tool executes → `tool_call_end` → text resumes.

#### Item 22 — execution sandboxing (reviewed 2026-10-13; stays as-is)

1. **Problem.** Filesystem and shell tools must act inside the project's folder, under the patterns and command lists admins configured.
2. **Decision.** **Stays as-is**, confirmed against the legacy config (`NA/schemas/trigger.py:90-177`): FileSystem's `root_dir`/`allowed_patterns`/`denied_patterns`/`protected_patterns` and Shell's `cwd`/`allowed_commands`/`denied_commands`/timeouts travel verbatim in `capability_config`; `_accepted_kwargs` passes exactly what the pinned harness accepts (pinned FileSystem takes BOTH `protected_patterns` and its newer `read_only_patterns` — verified from the 0.55 signature, nothing is dropped). NEW requirement from trial E: the pinned harness demands a workspace on the run — `LocalWorkspace(root)` is added, rooted per item 2 Open (b). **Rejected:** refusing to build without a configured root (the 2026-10-12 interim) — 0.8.0's default was `"."`, and parity wins until real isolation work.
3. **Mechanism.** `ToolsetBuilder`: root = filesystem `root_dir` → shell `cwd` → `"."` (logged); `LocalWorkspace` inserted first.
4. **At 0.8.0.** The config models above; nucleus provisioning writes `/nexus/projects/<slug>` into the config (CapabilityInternal docstring); the project bind-mount itself is deploy config (still not read — unchanged claim).
5. **Open.** Real isolation (container/user separation) beyond path scoping — future, outside Layer 1.
6. **Acceptance.** Every filesystem test runs inside a tmp root and never escapes it; the T-L1/approval suites all pass through this path.
7. **Classes and methods.** None new.
8. **API.** None.
9. **Sequence.** `capability_config` → `ToolsetBuilder` → `LocalWorkspace` + capabilities, per run.

#### Item 35 — bundled capability MCPs (audited 2026-10-13)

1. **Problem.** The product wants first-party MCP servers available out of the box.
2. **Decision.** **nexus-ai needs no special path** — a bundled server is an ordinary `MCPServerInternal` row: catalog, namespacing, gate, billing and the e2e dial path apply unchanged; `is_first_party` is carried and deliberately unused in the engine. 0.8.0's `_CAPABILITY_REGISTRY` (runner 84-105, 21 names → harness classes, never called) is NOT ported: `_NATIVE_BUILDERS` keeps exactly the five natives, and a new native is one added row when it is actually wired, not a pre-registered promise. **Rejected:** porting the full registry — dead code that implies support that doesn't exist.
3. **Mechanism.** None here.
4. **At 0.8.0.** `is_internal`/first-party flag exists (NU internal/api.py:36-59, the Capability/MCPServer split); the registry was unused.
5. **Open.** WHICH servers ship bundled, and their provisioning — nucleus/product work, folded into the nucleus handoff.
6. **Acceptance.** tests/test_mcp_dial.py doubles as the bundled-server path (same row shape, real dial).
7. **Classes and methods.** None.
8. **API.** None new.
9. **Sequence.** N/A — same as any MCP server.

#### Requirement → test traceability (Layer 1, added 2026-10-13)

Same convention as the Layer 0 matrix (§1.5): every test's docstring is its report row; `python -m pytest` regenerates `tests/REPORT.md` (now 70 tests).

| Requirement (doc) | Tests (tests/test_tools.py, tests/test_approvals.py) |
|---|---|
| Item 3 — catalog: namespacing, zero-network, server-without-list, natives, empty | `test_l1_catalog_namespaces_same_named_tools` · `test_l1_catalog_builds_without_network` · `test_l1_catalog_server_without_stored_tools_is_one_entry` · `test_l1_catalog_natives_from_capability_config` · `test_l1_catalog_empty_persona` |
| Item 1 — loaded set: topic_tools verbatim, first-reply cap, unknown ids dropped | `test_l1_topic_tools_pin_the_loaded_set` · `test_l1_first_reply_loads_all_eligible_capped` · `test_l1_unknown_topic_tool_ids_are_dropped` |
| Items 3+1 — through the service: schemas in the request, stable section, toolless untouched | `test_l1_loaded_native_schema_reaches_the_request` · `test_l1_catalog_section_is_stable_across_turns` · `test_l1_toolless_persona_is_plain_layer0` |
| Item 2 — policy: defaults, explicit levels, decision 6's MCP rules | `test_a_policy_native_defaults` · `test_a_policy_explicit_levels_win` · `test_a_policy_mcp_unknown_asks_clearance_clears` |
| Item 2 — pause/resume: pause on write, approve executes, deny never runs | `test_a1_write_tool_pauses_the_run` · `test_a2_resume_approved_runs_the_tool` · `test_a3_resume_denied_never_runs_the_tool` |
| Item 2 — the quiet paths: reads silent, off invisible, unattended refusal | `test_a4_read_tool_runs_without_asking` · `test_a5_off_tool_is_invisible` · `test_a6_unattended_run_refuses_instead_of_pausing` |
| Item 2 decision 4 — ToolSearch: hidden until discovered, ask on first use, unattended refusal (tests/test_discovery.py) | `test_f1_unloaded_tools_hidden_until_discovered` · `test_f2_approved_first_use_executes_and_finishes` · `test_f3_unattended_discovery_is_refused_not_paused` |
| Item 19 — activity trail: start/end order, shapes, preview | `test_i19_tool_activity_events` · the dial test's end-event assert |
| E2E MCP dial — real server over streamable HTTP: prefixed names, stored read runs / stored write pauses, live `readOnlyHint` passthrough (tests/test_mcp_dial.py) | `test_mcp_read_tool_executes_against_the_real_server` · `test_mcp_unlabeled_write_pauses` · `test_mcp_annotation_passthrough_without_stored_list` |
| Items 13+46 — router/escalation (tests/test_router.py, Layer 2): simple answered by router, hand-over announced + billed apart, hints become the set, fall-through, standard-as-router, no seats untouched | `test_r1_router_answers_simple_questions` · `test_r2_escalation_hands_over_announced_and_billed_apart` · `test_r3_tool_hints_become_the_topic_set` · `test_r4_router_failure_falls_through_to_standard` · `test_r5_standard_escalates_when_no_router_seat` · `test_r6_no_seats_means_yesterdays_behaviour` |
| Item 16 — budget/selection/limits (tests/test_budget.py, Layer 2): formula, untouched-under-target, oldest-first, protected list, small-window trim, max_steps cap | `test_b_budget_formula_keeps_the_two_numbers_apart` · `test_b_fitter_under_target_is_untouched` · `test_b_fitter_drops_oldest_history_first` · `test_b_fitter_drops_catalog_before_touching_protected` · `test_b_small_window_trims_history_before_the_run` · `test_b_max_steps_caps_the_tool_loop` |
| Item 12 — fallbacks (tests/test_fallbacks.py, Layer 2): labelled fallback answer, all-dead one error, default unchanged | `test_fb1_fallback_answers_and_is_labelled` · `test_fb2_all_candidates_dead_is_one_clean_error` · `test_fb3_no_fallbacks_fails_clean_unchanged` |
| Item 40 — model check (tests/test_model_check.py, Layer 2): ok+latency, unsupported provider, dead endpoint never a 500 | `test_mc1_working_model_checks_ok` · `test_mc2_unsupported_provider_is_named` · `test_mc3_dead_endpoint_is_a_model_failure` |
| Known gaps (Layer 1, closing state 2026-10-13) | stdio MCP refused loudly pending `MCP(local=…)` verification; drift-sync endpoint shape — nucleus handoff; resume's second `message_start` — relay handoff note |

#### Layer 2 — decisions before design (settled 2026-10-13)

Settled in discussion ahead of the Layer 2 item designs (items 16, 12, 13, 11, 10, 40, 14, 46). Item 16 was already fully settled (§4.1) and needs no new decision.

1. **Fallback models (item 12) are OPT-IN per persona, with 0.8.0's own retry ported.** A persona with no `fallback_models` configured (the default) fails cleanly: one `message_error`, the run stops — Layer 0's T9, unchanged. Only where an admin deliberately configured fallbacks does the retry run: each candidate tried with a whole fresh stream, **never switching after the first token reached the reader**, and the reply labelled "answered by X (fallback)". **Rejected:** pydantic-ai's `FallbackModel` — its retry semantics are the library's, and `answered_by_model` + the no-switch-mid-stream rule would have to be dug back out of it; dropping the feature entirely — an admin who configured a backup asked for it to work.
2. **The ROUTER seat lives on the persona** (the `PersonaSpec.models` role slot built for it on day one). No router model on the persona = `off` — the query goes straight to STANDARD. A company-level default may fill the empty seat; resolved in NUCLEUS inside the persona endpoint (same pattern as `tool_access`, change 7).
3. **Rate limits (items 11 + 10) are enforced by NUCLEUS, before the trigger fires** — nexus-ai writes zero code. Unit: **requests or tokens**; window: **per hour or per day** (admin settings); computed from the usage records nexus-ai already posts per call (change 1). Scope: per user, and per model (concurrency / volume). Mid-run token precision (per-second/minute TPM) is EXPLICITLY out of scope: enforcement happens at trigger time and a run's tokens land as its calls finish; the `WrapperModel` seam stays reserved in the design so that, if fine-grained gating is ever truly needed, it is one class plus a store — not a redesign. **Rejected:** a Redis for nexus-ai — same reasoning as item 1 (new infrastructure for one feature), now twice.
4. **Escalation (item 46) needs NO custom plumbing — trial G below retired the flagged risk.** `Escalate` is a structured OUTPUT TYPE on the router's agent (`output_type=[str, Escalate]`), exactly the struct item 13 promised: the model "calling escalate" is the model calling the `final_result` output tool, which ends the router's run cleanly with the `Handover` fields. The deep answer is then a SECOND ordinary streaming run inside the same ReplyGenerator — no in-tool stream splicing, no run termination tricks, both halves billed separately by the machinery Layer 0 already has.

**Escalate/hand-over trial (trial G, run 2026-10-13, pinned 2.55.0 — decision 4 CONFIRMED):** same throwaway instrument (fake OpenAI-shaped server, no product code). (G0) with `output_type=[str, Escalate]` the model sees ONE extra tool named `final_result` carrying Escalate's fields, `tool_choice=auto` — so the router can still answer plain text (verified both paths). (G1) the router's run ends cleanly with `result.output == Escalate(task=…, summary=…, expected_output=…)`. (G2) the deep model's answer streams token by token to the caller as an ordinary second run. (G3) BOTH runs' usage is readable separately (`ModelResponse.usage` per run) — router billed role=ROUTER, deep as the reply; nothing lost at the seam. (G4) the deep run received ONLY the `Handover` content, not the router's history — "Handover kept small" holds by construction (and switching models loses the provider cache anyway, §1.3).

#### Items 13 + 46 — router and escalation (settled and built 2026-10-13)

1. **Problem.** Every question costs the standard model's price even when a cheap model could answer it; and a persona has no way to bring MORE capability to a genuinely hard question. One decision point — made while trying, not by pre-classification — should route between cheap, standard and deep.
2. **Decision.** The persona's model bench decides everything — **there is no separate on/off setting**: ROUTER seat filled → the cheap model screens first; no ROUTER but a DEEP seat → **STANDARD plays the router role** (it answers normally, at today's cost, and may hand over on a hard question — the user's amendment, 2026-10-13); neither seat → Layer 0/1 behaviour, untouched (verified: no Escalate tool on the wire). The hand-over is trial G's mechanism: `Escalate` (task, summary, expected_output, **tool_hints**) as a structured output type; the deep answer is a second ordinary run. The ROUTING run gets **no tools** (it hints, it does not act — a deliberate narrowing of §1.3's "read tools run if permitted"; running tools in the router returns with its own pass later if wanted). **Router text streams LIVE** (settled: speed is the router's point); if the model misbehaves and talks before escalating, **the form wins** — the stray words flicker on the live stream only, because `message_done.content` is the deep run's text alone. On a topic's FIRST reply the router's `tool_hints` (∩ eligible) become the loaded set — item 1's reserved seam filled. The resume of a paused run rebuilds on the SAME seat (`ResumeBlock.role`, from the pause POST). **Rejected:** a separate escalate tool with in-tool stream splicing — trial G made it unnecessary; a project/company router switch — seats on the persona already express it per agent; holding router text until the run ends — every simple question would lose streaming to cosmetically fix a rare case.
3. **Mechanism.** `escalation.py`: the `Escalate` model, `ROUTER_INSTRUCTIONS` (stable: "answer OR escalate, never both"), `handover_suffix()` (the deep run keeps topic history + the user's message — same persona, same conversation; cross-persona hand-overs in Layer 6 travel alone). `AgentBuilder.build(escalate=)` adds Escalate to the output union. `ReplyGenerator`: records ACCUMULATE across runs; `escalation()`, `used_tools()`, `set_source_on_last_run()`; router records carry `kind="router"`, `role=ROUTER`. `PydanticAISystem.respond`: the routing stage (case A router / case B standard-as-router), `asyncio.timeout(ROUTER_TIMEOUT_SECONDS)` + any failure → fall through to STANDARD with `source="router_failed"` on the router's record (a broken router never blocks a reply; a client disconnect is NOT a router failure); on escalation a `deep_escalation` event (`escalated_to`) precedes the deep run; `message_done` carries `answered_by_model`, **`loaded_tools`** (None when no tool-bearing run happened, so a router-answered first reply leaves the topic's set deliberately undecided) and **`used_tools`** (what actually executed — the Layer 3 bridge: stored on the message row, later vector metadata so retrieval returns "text + what solved it", and a future router hint).
4. **At 0.8.0.** Nothing — no router, no escalation; every reply paid the persona's one model.
5. **Open.** (a) The router runs toolless — letting it run READ tools (§1.3's fuller flow) is a later pass on the same seams. (b) The company-level default for an empty ROUTER seat is nucleus-side resolution (change 3) — nexus-ai just reads the seats. (c) `is_code`/output-type hints in the router struct (§4's sketch) — deferred until the output-type work (item M7 territory) needs them.
6. **Acceptance (built, tests/test_router.py).** Router answers simple questions itself (one call, streamed, role=ROUTER/kind=router); escalation announced + billed apart (ROUTER then DEEP records, deep text is the content, answered_by_model set); tool_hints become the set (deep request carries the hinted schema; done carries loaded_tools; the router request carries none); a dead router endpoint falls through (done, no error, source=router_failed on the router record only); STANDARD escalates when no router seat; a persona with no seats is byte-for-byte yesterday's behaviour.
7. **Classes and methods.** `escalation.Escalate/ROUTER_INSTRUCTIONS/handover_suffix`; `PersonaSpec.model_for_or_none`; `UsageRecord.source`; `EngineSettings.router_timeout_seconds`; contracts: `AgentEventType.ESCALATION`, `AgentEvent.escalated_to/loaded_tools/used_tools`, `ResumeBlock.role`; `EventMapper.used_tools`; `ReplyGenerator.escalation/used_tools/set_source_on_last_run`; the routing stage in `PydanticAISystem.respond`.
8. **API.** Nucleus change (3), concrete shape: `PersonaInternal` += optional `router_model` / `deep_model` (ModelInternal-shaped; a company default fills the empty router seat nucleus-side). Change (8) carried by events: nucleus stores `message_done/message_paused.loaded_tools` as `topic_tools` on the topic's first reply, and `used_tools` on the message row (Layer 3 reads it into vector metadata, item 44). Change (9) extended: the pause POST and `ResumeBlock` carry `role`. The usage endpoint's records gain `kind="router"` and `source`.
9. **Sequence.** trigger → seats read → (router run, toolless, timed → text = done | Escalate | failure → fall through) → on Escalate: `deep_escalation` event → hints∩eligible become the set (first reply) → deep run with handover suffix + full tools → done with answered_by_model + loaded_tools + used_tools; every run's usage posted with its own role.

#### Item 16 — context budget, selection and the tool loop (built 2026-10-13; design was already settled, §4.1)

1. **Problem.** §4.1 — the budget was computed from the wrong number (`max_output_tokens` read as the window), nothing capped agent rounds, and selection and compaction were conflated.
2. **Decision.** §4.1 verbatim — nothing was re-decided; this entry records the BUILD. `input_budget = context_window − max_output_tokens − loop_headroom`; target ≈70% / trigger ≈90%; selection before the run, compaction during it; eviction order 1→2→3, only history ever summarized; protected: the current message, the persona prompt/brief, attached files. The three hardcoded numbers became settings (`BUDGET_LOOP_HEADROOM`=8192, `BUDGET_TARGET_PCT`=70, `BUDGET_TRIGGER_PCT`=90).
3. **Mechanism.** `ai_engine/context/budget.py`: `Budget`, `budget_for(spec, …)` (window from the MODEL, output cap from the PERSONA — two fields, never one), `BudgetFitter.fit(plan, budget)` — pure, estimator injected (`usage_reader.estimate_tokens`, the harness estimator wrapped, so context/ stays framework-free). Fit runs in `ReplyGenerator.generate` before anything is sent (never on a resume). Over target: history oldest-first, then sections below the persona prompt's priority (the tool catalog); protected content over target is sent anyway with a warning — §4.1's escape valve (indexing, 33/34) is the real answer, never truncation. Compaction: `ToolsetBuilder` appends `TieredCompaction(tiers=[DeduplicateFileReads(read_file key), ClearToolResults(max_fraction=0.9, keep_pairs=5), SummarizingCompaction(max_fraction=0.9)], target_tokens=run budget target)` whenever tools are built — 0.8.0's tier order kept, the target finally right, per-run per-model. Limits: `persona.max_steps` → `UsageLimits(request_limit=…)` on every run — agent rounds finally capped; the limit error is one clean `message_error` and the spent rounds still bill.
4. **At 0.8.0.** The tiers existed in the right order with the wrong target (Appendix A); `UsageLimits` unused; `max_steps` dropped on the wire.
5. **Open.** Tier 1's dedup key is still read_file-only and tier 2's knobs are 0.8.0's — both flagged in §4.1 for revisiting when graph (32) / DuckDB (34) results flow through; tool-result size caps before entering the transcript remain future work.
6. **Acceptance (built, tests/test_budget.py).** The budget formula with the two numbers apart; a plan under target passes byte-identical; oldest history drops first, newest survives, message/persona never dropped; the catalog drops before protected content, which is sent anyway; through the service: a small window trims history before the run; max_steps=3 stops an endless scripted tool loop with one error, ≤4 provider calls, usage still recorded.
7. **Classes and methods.** `Budget`, `budget_for`, `BudgetFitter` (context/budget.py); `estimate_tokens` (usage_reader.py); `EngineSettings.budget_*`; `ToolsetBuilder.build(compaction_target=)`; `_read_file_key`; UsageLimits wiring in `ReplyGenerator.generate`.
8. **API.** None — engine-internal.
9. **Sequence.** plan built → fit to the run model's budget (selection) → run with UsageLimits + compaction tiers armed at the same budget's target → growth mid-run handled by tiers 1→2→3.

#### Item 12 — fallback models (built 2026-10-13; decision 1 of the Layer 2 block)

1. **Problem.** A provider outage took the persona down even when the admin had configured backup models.
2. **Decision.** Layer 2 decision 1, built as settled: OPT-IN per persona; candidates tried in order with a whole fresh stream each; **never a switch after the first token reached the reader** (the mapper's received text is the witness); the reply labelled "answered by X (fallback)"; no fallbacks configured → Layer 0's clean single error, byte-for-byte.
3. **Mechanism.** The candidate loop in `ReplyGenerator.generate`: `[seat's model] + persona FALLBACK specs`; each failed attempt bills (estimated, under the failed model's own ids — T9's rule per candidate); retry only while `mapper.text() == ""`; `fallback_used()` → `message_done.answered_by_model = "<name> (fallback)"`. `AgentBuilder.build(spec=)` override builds a candidate for the same seat. The loop wraps EVERY run — router, standard and deep alike.
4. **At 0.8.0.** `apps/managers/fallbacks.py` — the same user-visible behaviour; re-implemented on the rebuilt generator rather than ported line by line.
5. **Open.** None.
6. **Acceptance (built, tests/test_fallbacks.py).** Dead primary → fallback answers, labelled, two records (estimated dead + real fallback); both dead → exactly one message_error, both billed estimated; no fallbacks → one error, one record — unchanged default.
7. **Classes and methods.** the candidate loop + `fallback_used()` (reply_generator.py); `AgentBuilder.build(spec=)`.
8. **API.** None new — `fallback_models` already arrives in PersonaInternal.
9. **Sequence.** run candidate 1 → fails before any token → bill it estimated → candidate 2 fresh stream → answers → done labelled "(fallback)".

#### Item 40 — model check endpoint (nexus-ai half ported 2026-10-13)

1. **Problem.** Nucleus's Register/Edit model dialogs verify a model+key before saving; the endpoint lived in the old module and had to come across.
2. **Decision.** Ported with 0.8.0's path and answer shape unchanged (`POST /api/v1/models/check/` → `{ok, latency_ms}` or `{ok:false, error_code, error, status_code}`); the check now BUILDS the model with the rebuild's own `ModelFactory` and STREAMS the tiny call — so passing means "a persona on this model will run", the same code path. The §4.6 fingerprint-persistence half (verify once, store the fingerprint, re-verify on drift) is NUCLEUS work — handoff. **Rejected:** a new response shape — nucleus's dialogs already word these codes.
3. **Mechanism.** `pydantic_ai_system/model_check.py` (`check_model`, `SUPPORTED_PROVIDERS`, `_is_model_failure`); `fastapi_app/routers/models.py` behind the same `X-Internal-Key` check as the trigger.
4. **At 0.8.0.** `routers/models.py` + `managers/model_check.py` — same contract, non-streaming call.
5. **Open.** Fingerprint persistence + MCPServer verify-and-store-tools (change 6) — nucleus handoff; a future check could also return the live tool list for MCP rows (item 3's capture point).
6. **Acceptance (built, tests/test_model_check.py).** Reachable model → ok + latency; unknown provider → `unsupported_provider`, no call attempted; dead endpoint → HTTP 200 with ok=false + `model_failure` — a broken model never breaks the endpoint that tests models.
7. **Classes and methods.** `check_model` et al. above.
8. **API.** `POST /api/v1/models/check/` — kept verbatim.
9. **Sequence.** nucleus dialog → POST config → one streamed 5-token call → worded dict back.

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

#### Layer 3 — decisions before design (settled 2026-10-13)

Scope: items 31 (vector store), 44 (persona chat vectors), 24 (RAG), 33 (content
routing) are designed and built now; item 32 (code graph) was settled in §4.2 and
is reached through the router, not through embeddings; items 28 (vision), 36
(object storage) and 34 (DuckDB) stay deferred until these land.

1. **Quarantine.** txtai and pgvector are touched only inside
   `ai_engine/vector_db/`, behind the `VectorStore` interface and its factory —
   the same rule that confines pydantic-ai to `pydantic_ai_system/`. Nothing
   outside that folder imports txtai, sqlalchemy-for-vectors, or pgvector.
2. **One database.** A separate `nexus_vectors` database on the SAME Postgres
   instance nucleus uses — no second DB server. The dev stack's `postgres-dev`
   image was swapped to `pgvector/pgvector:0.8.7-pg17` on 2026-10-13 (same PG 17,
   same data volume; one-time REINDEX for the musl→glibc collation change). The
   production `postgres` service gets the same one-line swap when next touched.
3. **Embedder is a project setting.** Each project's settings name its embedder
   (owner's words: "The embedder will be given in project settings, and can be
   changed later"). Default: local fastembed `nomic-ai/nomic-embed-text-v1.5`.
   A remote embedder is billed under kind=remote_embedder. Open (a) RESOLVED
   2026-10-13: NO company default — a project with no embedder set uses the
   system default (the local one) directly. Nucleus's ai-config is per-project
   only.
4. **Embedder change ⇒ full re-embed.** Changing a project's embedder rebuilds
   ALL of that project's embeddings — nothing is silently dropped. Raw text is
   stored beside every vector so the rebuild never re-fetches sources. While the
   rebuild runs, search keeps answering from the OLD model's vectors and flips
   only when the new set is complete — vectors are never compared across models
   (per-model tables, per-model dimensions). Where the rebuild job runs and how
   progress is reported = a design point in item 31's entry.
5. **Code files are never embedded.** A code file attached to a prompt rides the
   prompt only. Deep code inspection is the code-graph MCP's job (item 32, §4.2
   — CodeGraphContext + FalkorDB); no code embeddings, confirmed.
6. **used_tools is vector metadata.** Every answer row carries the tools/MCPs
   that produced it (Layer 2, nucleus change 8); item 44's search returns the
   chat text with that list as metadata, so retrieval can say which MCPs were
   in play when the remembered answer was written.
7. **One index per PROJECT** (settled 2026-10-13) — follows from the
   per-project embedder. Each index lives in its own pg schema,
   `vx_p{project_id}_{model_slug}` (trial C rule i). Chat vectors (item 44) and
   document vectors (item 24) share the project's index, distinguished by
   `kind` metadata (message | context_source) plus topic, source, used_tools.
   A registry table in the public schema — `vx_indexes(project_id, model_id,
   schema_name, status active|building)` — says which schema answers searches.
8. **ReembedJob runs inside nexus-ai** (settled 2026-10-13) — vectors are
   nexus-ai's property. Nucleus triggers `POST /api/v1/embed/reindex/`
   (internal key) and polls a status endpoint; nucleus makes the project
   INACCESSIBLE to users until the rebuild completes (owner's decision). The
   job builds the NEW model's schema from the old schema's stored raw text,
   flips the registry row only when complete, then drops the old schema — so a
   crash mid-rebuild loses nothing (the old index stays active underneath the
   lock). A reindex while one is building → 409. Changing a project's embedder
   — and therefore triggering reindex — is restricted to the company
   owner/admin, enforced by NUCLEUS at the project-settings endpoint; nexus-ai
   trusts the internal key.
9. **Retrieval trigger, v1 (item 33; settled 2026-10-13).** Every reply ALWAYS
   searches the project's active index with the user's message (hybrid,
   filters: company+project for documents, company+project+topic for chat
   memory — decision in item 44's entry). Hits above the similarity threshold
   become a RETRIEVED section in the ContextPlan (priority < 90, governed by
   item 16's BudgetFitter); below-threshold or empty → nothing attached, the
   reply proceeds as if the index were empty. Owner's words: "it will find and
   if found something its ok, otherwise db is empty for it." The search is
   local-embedder cheap; a router-decides upgrade can replace the
   always-search rule later on the same seam.
10. **Retrieval shows itself in events** (owner's call, settled 2026-10-13:
    "i think we should include all such things in events"). A new
    `context_retrieved` event is emitted after the search, before the model
    run, ONLY when something was attached: `{retrieved: [{id, kind:
    message|context_source|recall, label, score, topic_id?}], count}` —
    references and scores only, never the chunk text. `message_done` carries
    the same list as `retrieved_sources` beside `used_tools`, and nucleus
    stores it on the message row (change 8 pattern) — so an answer's vector
    metadata says which tools ran AND which memories were used.
11. **Recall endpoints ported now** (settled 2026-10-13): `POST
    /api/v1/embed/recall/` and `DELETE /api/v1/embed/recall/{entry_id}/` —
    legacy W5 contract kept (entry_id is the doc id, edit = upsert); recall
    entries are rows in the project index with kind=recall. `type="code"` on
    POST /embed/ is REFUSED with a clear error — enforcement of decision 5;
    the nucleus handoff notes to stop sending it. `GET /api/v1/directives/`
    is NOT ported (legacy plugin machinery) — known gap, flagged in the
    handoff for nucleus to confirm nothing calls it.
12. **Items 32, 34 and 36 are ADD-ON MCPs, not engine code** (settled
    2026-10-13). They formally leave nexus-ai's backlog and become their own
    MCP-server projects — item 35's audit already proved the engine needs NO
    special path for first-party servers (ordinary MCPServerInternal rows:
    catalog, namespacing, approval gate, billing and the e2e dial all apply
    unchanged, test-proven). Concretely:
    - **One combined DATA MCP for items 34 + 36**: a server running MinIO
      (object storage) + DuckDB (SQL over large CSV/Parquet) together —
      DuckDB's httpfs speaks the S3 API, so it queries MinIO's files
      directly. One toolset (≈ upload_file, list_files, describe_table,
      query_sql); the TOOL NAMES ARE THE CONTRACT — the query engine behind
      query_sql can be swapped for Spark later without touching personas,
      topics or this doc. Multi-tenancy lives IN the MCP: bucket per project,
      DuckDB confined to that project's bucket.
    - **Item 32 (code graph) stays its OWN MCP** — CodeGraphContext +
      FalkorDB per §4.2; different data and lifecycle, never merged into the
      data MCP.
    - **Item 28 (vision) is NOT an MCP** — images in the prompt are model
      input capability, engine-side work; it stays deferred as the one
      remaining Layer 3 ENGINE item.

Legacy contract verification (2026-10-13, read from
`modules/nexus-ai-legacy/apps/routers/embed.py` + `apps/schemas/embed.py`):
POST /api/v1/embed/ takes EmbedRequest{source_id, type "file"|"code", label,
content, language?, topic_id?, channel_id?, project_id?, company_id?} and
answers EmbedResponse{source_id, collection_id, chunks_count} — nucleus stores
collection_id back, so the port returns an equivalent key.
DELETE /embed/context-source/{collection_id}/ → {ok}. POST /embed/message/
takes MessageEmbedRequest{message_id, company_id, sequence, topic_id,
channel_id, project_id, sender_id, sender_name, sender_type, content,
created_at} → MessageEmbedResponse{message_id, collection, embedding_model,
ok}; the port ADDS optional used_tools (decision 6 / nucleus change 8).
DELETE /embed/message/{message_id}/?company_id= → {ok}. Also present in
legacy, NOT yet ruled on: GET /api/v1/directives/, POST /embed/recall/ and
DELETE /embed/recall/{entry_id}/ (W5 Recall entries) — owner to decide port
now vs defer; and type="code" ingestion, which decision 5 forbids — proposed:
the port refuses type="code" with a clear error and nucleus stops sending it.

Trial C — RESULT 7/7 PASSED (2026-10-13, run by the owner in nexus-ai-debug
against the real `nexus_vectors` DB on `pgvector/pgvector:0.8.7-pg17`; script
was `modules/nexus-ai/trial-c/trial_c.py`, throwaway, delete after):

| Claim | Result |
|---|---|
| C1 semantic search on pgvector, EXTERNAL embedder (our code calls the embedder; txtai only receives vectors via `method="external", transform=fn`) | PASS (top=m4) |
| C2 company+project+topic as parameterized SQL WHERE on content storage | PASS |
| C2b cross-company isolation — c2's filter never sees c1 rows | PASS |
| C3 hybrid: pgvector similarity + pgtext keyword finds an exact term | PASS (`scoring={"method":"pgtext"}, hybrid=True`) |
| C5 delete by source: SQL select ids → `delete(ids)` → gone | PASS |
| C6 reconnect from a fresh process | PASS — the ONE working strategy: `emb.save(dir)` once, then `Embeddings().load(dir, config={**config, "transform": fn})` — the transform callable is ALWAYS injected in code; txtai refuses to resolve an external transform from a saved config (`ALLOW_RESOLVE_TRANSFORM` guard). `load(config=)` alone and lazy-connect both FAIL. |
| C4 two embedding dimensions in one DB | PASS — but ONLY with ONE SCHEMA PER INDEX. txtai indexes use fixed content/scoring table names: a second index in the same schema blocks forever on the first one's open transaction (the first trial run hung exactly there) and would clobber its content tables. Second index in its own schema (`schema=` top-level + in the pgvector dict): 384-dim index worked AND the 768-dim original stayed intact. |

Confirmed pins: `txtai==9.14.0`, `fastembed==0.9.0` (embedder
`nomic-ai/nomic-embed-text-v1.5`, 768 dims), plus what pip resolved with them:
`sqlalchemy 2.1.4`, `psycopg2-binary 2.9.13`, `pgvector 0.5.1` (python client —
txtai's own ceiling), server extension pgvector 0.8.7. Docker/image note:
install CPU torch FIRST (`pip install torch --index-url
https://download.pytorch.org/whl/cpu`) or txtai pulls ~6 GB of CUDA wheels.
Infra one-timers done during the trial: dev postgres image swapped (entry 2
above), cluster password re-aligned to secrets.env (`ALTER USER` — the volume
predated the generated secrets), nexus-ai's container must be on
`neuralops-network` to resolve the postgres host.

Design rules the trial adds: (i) one Postgres DATABASE, one SCHEMA per txtai
index; (ii) the Embeddings object is constructed fresh each process start with
the transform injected in code — nothing executable is ever loaded from saved
config; (iii) the saved-config dir is tiny and regenerable — treat it as cache,
the truth lives in Postgres.

#### Items 31 + 44 + 24 + 33 — vector store, chat memory, document RAG, retrieval (designed 2026-10-13)

1. **Problem.** A persona must remember: documents attached to a project (24), the project's own chat beyond the context window (44, SAME TOPIC ONLY), and short recall entries (W5) — searchable semantically, strictly inside the tenant, and visible when used. Item 31 is the store itself; item 33 decides when a reply searches it.
2. **Decision.** pgvector + txtai 9.14.0 behind `VectorStore` in `ai_engine/vector_db/` — Layer 3 decisions 1–11 plus trial C's rules: one `nexus_vectors` DATABASE, ONE SCHEMA PER INDEX, ONE INDEX PER PROJECT (schema `vx_p{project_id}_{model_slug}`); EXTERNAL embedder (our code embeds, txtai receives vectors); kinds `message | context_source | recall` in the one project index; always-search v1 with a score threshold; retrieval announced in events. **Rejected:** Chroma (legacy — a second store when pg already holds everything); code embeddings (decision 5); a per-company index (the embedder is per-project); self-embedding replies inside respond() (one writer path: nucleus calls POST /embed/message/ for every stored message, answers included).
3. **Mechanism.** `EmbedderFactory` → `LocalEmbedder` (fastembed, process-cached per model) or `RemoteEmbedder` (OpenAI-compatible `/v1/embeddings` via httpx; billed kind=remote_embedder). `TxtaiVectorStore` keeps a registry table `public.vx_indexes(project_id, model_id, schema_name, status active|building, updated_at)`; opening a project reads the ACTIVE row and constructs the txtai Embeddings FRESH — saved-config-dir cache + `load(path, config={**cfg, "transform": embedder})` (trial C6's one working strategy; nothing executable ever loads from disk). `index()` upserts (ids: message_id / `{source_id}:{n}` per chunk / entry_id), raw text always stored (content=URL). `search(SearchQuery)` is hybrid SQL with parameterized filters. Chunker: paragraph-pack to ~1000 chars with one-paragraph overlap. `ReembedJob.start(project, embedder)`: registry row (new schema, status=building) → stream old schema's raw text → embed+index with the new model → flip active → drop the old schema; a second start while building → 409; the status endpoint reads the registry. Retrieval in `PydanticAISystem.respond()` right after the plan is built: active index exists → search (documents: company+project; chat memory + recall: company+project+topic) → hits ≥ RETRIEVAL_MIN_SCORE up to RETRIEVAL_TOP_K → one `retrieved` PromptSection (priority 50, unstable — item 16's BudgetFitter governs it) + `context_retrieved` event + the refs ride to message_done as `retrieved_sources`.
4. **At 0.8.0.** ChromaDB collections per company (`company_{id}_chat` …), fastembed default, endpoints in NA/routers/embed.py + schemas/embed.py (shapes quoted in the verification block above); retrieval lived in the chat/document/recall context-source managers.
5. **Open.** (a) `GET /api/v1/directives/` not ported — handoff asks nucleus to confirm nothing calls it. (b) threshold/top_k are settings — tune after real use. (c) router-decides retrieval — later, same seam (decision 9). (d) `collection_id` returned by POST /embed/ is `{project_id}:{source_id}` — the delete endpoint carries no other scope, so the key must locate the project index on its own.
6. **Acceptance** (tests/test_vector_db.py, test_embed_endpoints.py, test_retrieval.py; fake deterministic embedder, real pgvector pg via NEXUS_VECTOR_DB_URL). Store: scoped index+search, cross-company isolation, hybrid exact-term, delete by source, two models' schemas coexist with the first intact (trial C re-asserted as regression tests); reembed: build→flip→old dropped, searches answer OLD vectors until the flip, second start → 409. Endpoints: POST /embed/ chunks and answers collection_id + chunks_count; type="code" refused 422; context-source delete empties the source; message embed stores used_tools; recall upsert-on-same-id + delete; every endpoint 401 without the key; 503 when NEXUS_VECTOR_DB_URL is unset. Retrieval e2e (harness): topic with indexed rows → context_retrieved with refs+scores, a retrieved section reaches the model's instructions, retrieved_sources lands on message_done; empty index → no event, no section; another topic's chat memory is never retrieved (same-topic rule); below-threshold hits attach nothing.
7. **Classes and methods.** vector_db/: `VectorStore` (index / search / delete_source / delete_ids / active_model), `TxtaiVectorStore`, `Embedder` + `LocalEmbedder` + `RemoteEmbedder` + `EmbedderFactory`, `ReembedJob`, `chunk_text`; specs: `VectorItem(id, kind, text, label, source, topic_id?, used_tools?)`, `SearchQuery(company_id, project_id, text, topic_id?, kinds?, top_k, min_score)`, `SearchHit(id, kind, label, score, text, topic_id?, used_tools?)`; contracts: `AgentEventType.CONTEXT_RETRIEVED("context_retrieved")`, `AgentEvent.retrieved / retrieved_sources`; config: `vector_db_url (NEXUS_VECTOR_DB_URL, empty = feature off)`, `retrieval_top_k (RETRIEVAL_TOP_K, 6)`, `retrieval_min_score (RETRIEVAL_MIN_SCORE, 0.30)`, `vector_config_dir (VECTOR_CONFIG_DIR)`.
8. **API.** Ported verbatim paths (contracts in the verification block): `POST /api/v1/embed/` (+ optional `embedder` block — nucleus sends the project's embedder spec, omitted = system default; `type="code"` refused 422), `DELETE /api/v1/embed/context-source/{collection_id}/`, `POST /api/v1/embed/message/` (+ optional `used_tools`), `DELETE /api/v1/embed/message/{message_id}/?company_id=`, `POST /api/v1/embed/recall/`, `DELETE /api/v1/embed/recall/{entry_id}/`. New: `POST /api/v1/embed/reindex/` {company_id, project_id, embedder} → 202 | 409, `GET /api/v1/embed/reindex/{project_id}/status/` → {status, done, total}. Nucleus handoff additions: per-project embedder setting with owner/admin-only change; lock the project while reindex runs and poll status; store `retrieved_sources` from message_done beside used_tools; keep calling the embed/delete endpoints exactly as 0.8.0 did; stop sending type="code"; confirm /directives/ is unused.
9. **Sequence.** Reply: trigger → plan → active index? → search → `context_retrieved` + retrieved section → routing stage (items 13/46, unchanged) → run → message_done{used_tools, retrieved_sources}. Ingest: nucleus → POST /embed/* → chunk → embed with the index's model → upsert into the active schema. Reindex: admin changes the embedder → nucleus locks the project → POST reindex → new schema builds → flip → drop old → nucleus unlocks.

#### Requirement → test traceability (Layer 3, added 2026-10-13; built, suite now 86 tests, supersedes the earlier 70-test count)

| Requirement | Test |
|---|---|
| Scoped search + tenant isolation (decisions 1/7, item 44 topic rule at store level) | test_vector_db.py::test_tv1 |
| Hybrid vector+keyword (trial C3) | test_tv2 |
| Delete by source (trial C5) | test_tv3 |
| Per-model dimensions, schema-per-index, no clobber (trial C4) | test_tv4 |
| Fresh-process reconnect from the registry alone (trial C6 + rule iii) | test_tv5 |
| Re-embed: build → serve-old → flip → drop; 409 on double start (decisions 4+8) | test_tv6, test_embed_endpoints.py::test_te7 |
| POST /embed/ 0.8.0 contract, chunking, collection_id (item 24) | test_te1 |
| type="code" refused (decisions 5/11) | test_te2 |
| Context-source delete by collection key | test_te3 |
| Message embed + used_tools metadata + M6 delete (item 44 / decision 6) | test_te4 |
| Recall upsert-on-id + delete (W5, decision 11) | test_te5 |
| Internal-key lock + 503 when unconfigured | test_te6 |
| Retrieval e2e: event + section + retrieved_sources, same-topic rule (decisions 9+10) | test_retrieval.py::test_tr1 |
| Empty project → byte-same pre-Layer-3 stream | test_tr2 |
| Below-threshold → nothing attached, no event | test_tr3 |

Known gaps carried: /directives/ not ported (Open a); requirements.lock not yet
regenerated with the Layer 3 pins (regenerate in the Docker build with CPU
torch first); retrieval thresholds are defaults pending real-use tuning;
router-decides retrieval deferred (decision 9).

**The nucleus side of everything above is compiled in
`docs/NUCLEUS-HANDOFF.md` (written 2026-10-13)** — changes 1–9 from Layers
0–2, the rate-limit decisions (items 10/11), and Layer 3's change 10
(embedder setting, reindex flow, embed-endpoint call points, event relay).
That document is the prompt for the nucleus work, as this one is for nexus-ai.

#### Layer 4 — decisions before design (settled 2026-10-13)

1. **Item 5 (ask_user) is a REAL pausing tool** — a built-in `ask_user` tool
   that pauses the run on item 2's road (deferred tools → state to nucleus →
   message_paused); the user's ANSWER rides the resume as the tool result.
   One road for approvals, discovery and questions — no new machinery.
   Legacy had only a prompt convention (NA/managers/prompt_builder.py:55-78).
2. **Item 23 (output types): auto = the model decides, the user always wins.**
   `TriggerJob.output_type` already travels (default "auto"): auto → the model
   decides the render type; an explicit value → the engine obeys without
   second-guessing. The declared type is VALIDATED before `render_as` claims
   it (a broken "html" falls back to text — T13's instinct, applied at
   output). How much of legacy's output_types/ package ports — after the
   verification read.
3. **Nudges (W8) is PLACED: Layer 4, in the rebuild.** What it is: the user
   types while the reply runs; the engine polls nucleus after EACH tool call
   and injects waiting nudges into that tool's result ("[The reader adds
   while you work: …]"), emits nudge_taken; a toolless run can't take one,
   nucleus posts it as a message after the reply. Ports as a capability
   beside ApprovalGate — PENDING verification that the pinned harness
   (0.55.0) offers after_tool_execute with the legacy signature
   (NA/managers/nudges.py:46).
4. **Item 6 (new topic / summary) is NUCLEUS-side, zero engine code**: a
   "continue in new topic" action — nucleus sends an ordinary trigger asking
   the persona for a handover summary, opens the new topic with that summary
   as its first message. Compaction (item 16) keeps handling the invisible
   mechanics; this is the visible, correctable cut. Note: chat memory (item
   44) is same-topic-only, so the summary IS the carryover — deliberate.
5. **Item 38 (concurrency): parallel across topics, QUEUE per topic.** The
   engine is stateless-per-run and fully async — cross-topic parallelism
   already works, nothing to build. Inside one topic nucleus serializes
   triggers (per-topic lock/chain): replies in order, no topic_tools race.
   Deliberate in-topic parallelism arrives with Layer 6's supervisor.
6. **Unplaced features placed** (owner + assistant, 2026-10-13): preflight →
   Layer 6; runbooks → Layer 6; routines → with item 29 (nucleus-side
   scheduling); recall front-half (entry CRUD/UI) → nucleus — its vector
   half shipped in Layer 3 (decision 11); nudges → Layer 4 (decision 3
   above). The trigger keeps accepting their fields meanwhile.
7. **Items 27 and 29 are VERIFY-FIRST**: 27 (state persistence) is checked
   against legacy (NA pydantic_ai_runner.py:223-227) — likely already
   covered by stateless-rebuild + item 2's pause state, but proven, not
   assumed; 29 (scheduled runs) is checked for anything beyond
   interactive=false, which the engine already honors (tested).
8. **Item 27 RESOLVED (settled 2026-10-13): the MEMORY PASS — tool outputs
   become vector memory, the model decides what deserves it.** Verified
   first: legacy persisted the run's INTERNAL model state across turns
   (pydantic_ai_runner.py, the PERSIST event carrying events.new_messages())
   — that road is deliberately NOT ported (version-fragile JSON, unbounded
   growth, incompatible with item 16's text-based budget machinery).
   Instead, owner's design: after any reply that ran tools, ONE cheap model
   call — seat chain UTILITY → ROUTER → STANDARD (owner: "there must be
   some utility, otherwise router or standard will be utility") — reviews
   the run's tool outputs (previews, not megabytes) and rules per output:
   `raw` (exact data worth keeping → text chunked into the project index,
   kind=tool_result), `summary` (a verbal note WITH exact key figures and
   provenance → one small row), or `skip` (re-runnable / worthless →
   nothing). Guidance in the pass's prompt: local project files are
   re-readable → usually skip; remote/ephemeral sources (the lost-CSV case)
   → usually save — but the model may override either way. Every saved row
   carries {tool, command/args, message_id, topic_id, created_at};
   source="toolres:{message_id}" so a message delete drops its memory;
   SAME-TOPIC retrieval rule applies (like chat memory); the retrieved
   section labels it "(memory from <date>, via <command> — may be outdated,
   re-run to confirm)". nexus-ai indexes these itself right after the run —
   a deliberate, documented exception to nucleus-as-writer (which is about
   messages). The pass is billed as its own usage record under its seat's
   role, kind="memory". Ephemeral data the USER will need as a durable file
   still belongs in the data MCP (decision 12), not in memory rows.

Trial H — RESULT 3/3 PASSED (2026-10-13, pinned 2.55.0; throwaway script):
the ask_user road. (H1) a `kind='external'` tool (via
`ExternalToolset([ToolDefinition(...)])`) called by the model ends the run
with `DeferredToolRequests.calls` — NOT `.approvals` — the same pause shape
as item 2. (H2) a second run with `message_history` +
`DeferredToolResults(calls={tool_call_id: "the user's answer"})` hands the
ANSWER to the model as the tool result and the run finishes on it. (H3) both
runs' usage is separate (trial G's rule holds). Design consequence: item 5
needs no new machinery — one ExternalToolset beside the gate, a
`question_asked` event, and `ResumeBlock.answers` beside `approvals`.

Verification notes for the other Layer 4 engine items (2026-10-13): the
nudges hook `after_tool_execute(ctx, *, call, tool_def, args, result)` EXISTS
at pinned 2.55.0 (inspected) — legacy's NudgeGate signature carries over.
Legacy output_types verified by reading all six files: ten types (text, html,
chart, table, diagram, form, terminal, code explicit-only, preflight,
choice); resolution = explicit non-auto → cosine-centroid classifier over
example_prompts (+0.05 over text to win) → text; markers tolerant of mangled
closers; recovery files an unmarked whole-object chart/choice reply as its
type, strictly. Item 27's legacy PERSIST event verified (internal state
across turns) and deliberately not ported — decision 8 replaces it.

#### Items 23 + 5 + W8 + 27 — output types, ask_user, nudges, the memory pass (built 2026-10-14)

1. **Problem.** A reply is not always prose: the caller (or the model) may want a chart, an HTML page, a table (23). Mid-run, the model sometimes needs the person's answer before it can continue (5). The person types while a reply runs and that text should reach the working model, not wait (W8). And a run's tool outputs vanish with the run — the lost-CSV case (27).
2. **Decision.** Layer 4 decisions 1–3 + 8 above, plus three build-time calls: (i) a TYPED turn skips the router screen — the type's contract needs a capable model, the cheap screen is for plain text only; (ii) a taken nudge's event rides out with the next mapped flush — no side-channel merge into the stream; (iii) memory-pass failure is logged and never surfaced — the reply is already done. ask_user availability: `allow_ask AND job.interactive` — every interactive run carries the schema (four Layer 1/2 tests updated to this truth), the router's screening run passes allow_ask=False, an unattended run never gets the tool.
3. **Mechanism.** *Output types* — `ai_engine/output_types/` ports legacy's ten specs verbatim: `resolve_output_spec(job.output_type, message, history)` = explicit non-auto → cosine-centroid classifier over example_prompts (injectable embedder, `CLASSIFIER_EMBEDDER`, +0.05 over text to win; request-behind-pick reads `HistoryMessage.output_type`) → text; the chosen contract rides as an `output_format` PromptSection (priority 85, unstable) wrapped "--- OUTPUT FORMAT INSTRUCTION ---" with the CHOICE_EXCEPTION appended for every type except preflight/choice. At END, `finalise_reply(raw, resolved_type)`: `parse_output_markers` (tolerant of mangled closers; MCP markers override; EMBED/CONTEXT block → embed_description) → recovery files an UNMARKED whole-object chart/choice only when the resolver asked for that type → `_holds` validation (chart/choice/preflight must be one JSON object, html must start `<!doctype`/`<html`; a broken claim downgrades to text/text) → message_done carries clean content + output_type + render_as + embed_description, with a byte-parity guard so an untouched plain reply equals its streamed deltas exactly (T1 kept). *ask_user* — `tools/ask_user.py`: one `ToolDefinition(kind="external")` in an `ExternalToolset(id="ask-user")`, passed as `toolsets=` when ask is on (trial H); the run ends in `DeferredToolRequests.calls` → mapper emits `question_asked` (call_id, question, options), pause pending rows get kind="question", and the resume's `answers={call_id: text}` becomes `DeferredToolResults(calls=...)` — the answer IS the tool result. *Nudges* — `tools/nudge_gate.py`: a NudgeGate capability whose `after_tool_execute` (verified at 0.55.0) polls `GET /internal/messages/{msg_id}/nudges/` (consume-on-GET), appends "[The reader adds while you work: …]" to that tool's result and queues `nudge_taken` events, drained after each flush; built only when job.interactive and attached only when capabilities exist (a toolless run can't take one). *Memory pass* — `memory_pass.py`, fired as `asyncio.create_task` AFTER message_done: skips (zero cost) when the project has no ACTIVE index — the pass never guesses an embedder; otherwise one structured-output call (MemoryRulings) on the UTILITY → ROUTER → STANDARD seat, streamed like every other call; rulings → rows id `{msg_id}:tr{i}(:{n})`, kind=tool_result, label="{tool} {args_preview}", source=`toolres:{msg_id}`, topic_id, created_at (summary = one row; raw = chunked, capped 4000 chars); billed kind="memory" under the seat; EventMapper collects each ok tool output capped at 20k chars for the pass's previews (1500 chars each in its prompt).
4. **At 0.8.0.** output_types was a six-file package under the legacy app root (all read); ask_user existed only as a prompt convention (prompt_builder.py:55-78); nudges lived in NA/managers/nudges.py with the same poll-after-tool shape; item 27 was the PERSIST internal-state event — deliberately not ported (decision 8 replaces it).
5. **Open.** (a) The nucleus half — nudge storage + endpoint + leftovers-posted-after-done, the question card + `answers` on resume, `pending[].kind`, storing embed_description and output_type — is handoff change 11. (b) The retrieved-section label for memory rows ("memory from <date>, via <command>") rides the existing section via created_at — wording tuned with real use. (c) Classifier centroids are computed per process on first use; the production default (fastembed) downloads its model once — fine now, revisit if types multiply. (d) Item 29 is PARKED WITH THE NUCLEUS PROJECT (owner, 2026-10-14): the verify-first read of 0.8.0's scheduling code and everything it may imply live in `docs/NUCLEUS-HANDOFF.md` change 12; the engine side — interactive=false honored (refuse, never pause; no ask_user) — is already built and tested (a6/f3/q3), and nothing more is planned engine-side. With that, LAYER 4 IS CLOSED ON NEXUS-AI.
6. **Acceptance** (tests/test_output_types.py, test_ask_user.py, test_nudges_memory.py; four existing tests updated to the always-ask_user truth). Markers parse and survive mangled closers; recovery only on the resolved type; broken claims fall to text while a good html holds; explicit chart e2e — contract (with choice exception) in the request, validated typed done out with embed_description; a plain auto turn stays byte-identical to its deltas; a typed turn produces no kind=router record on a router-seated persona. ask_user pauses with question_asked and pending kind=question; the answer resumes, reaches the model as the tool result, and both halves bill; interactive=false carries no ask_user schema. A waiting nudge rides the next tool result, is announced and consumed exactly once; a toolless run leaves it untouched. The memory pass saves a summary ruling with full provenance into the project index and bills kind="memory" on the utility seat; a skip ruling saves nothing but still bills; the pass runs after done.
7. **Classes and methods.** `ai_engine/output_types/`: registry (OutputTypeSpec, TYPES_WITHOUT_CHOICE), types (ten specs), markers (`parse_output_markers`), classifier (centroids, `set_embedder`), resolver (`resolve_output_spec`), recovery (`finalise_reply`, `_holds`), prompting (`output_instruction_block`, CHOICE_EXCEPTION); `tools/ask_user.py` (`ask_user_toolset`, ASK_USER_CAPABILITY_ID), `tools/nudge_gate.py` (`NudgeGate`, NUDGE_NOTE), `memory_pass.py` (`MemoryRuling(s)`, `memory_seat`, `run_memory_pass`). Contracts: `AgentEventType.QUESTION("question_asked")` / `NUDGE_TAKEN("nudge_taken")`, `QuestionData{call_id, question, options}`, `AgentEvent.question / nudge / embed_description`, `ResumeBlock.answers`, `PendingApproval.kind("approval"|"question")`, `HistoryMessage.output_type`, `VectorItem.created_at` / `SearchHit.created_at`, `PersonaSpec.utility_model`, `EngineSettings.classifier_embedder (CLASSIFIER_EMBEDDER, default fastembed nomic-embed-text-v1.5; "hash" in tests)`, `NucleusClient.get_nudges`.
8. **API.** message_done gains `output_type`, `render_as`, `embed_description`; new events `question_asked` and `nudge_taken`; the pause payload's pending rows gain `kind`; the resume block gains `answers`; nexus-ai calls `GET /api/v1/internal/messages/{msg_id}/nudges/` (nucleus consumes on GET); usage records gain kind="memory". TriggerJob is unchanged — output_type already travelled.
9. **Sequence.** Typed turn: trigger → resolve type → contract section → router SKIPPED → run → finalise → done{output_type, render_as, embed_description} → memory pass if tools ran. Question: run → ask_user → calls-pause → state to nucleus (pending kind=question) → question_asked + message_paused → person answers → resume{answers} → answer as tool result → done. Nudge: person types mid-run → nucleus stores → engine polls after the next tool → injected into that result + nudge_taken → leftovers posted by nucleus after done.

#### Requirement → test traceability (Layer 4, added 2026-10-14; built, suite now 99 tests, supersedes the 86-test count)

| Requirement | Test |
|---|---|
| Markers parse; mangled/missing closers tolerated; EMBED extracted | test_output_types.py::test_ot1 |
| Recovery files an unmarked chart ONLY on a chart turn | test_ot2 |
| Broken claimed type → text; valid html holds (decision 2) | test_ot3 |
| Explicit type: contract (+ choice exception) in, validated done out | test_ot4 |
| Plain auto turn byte-identical to deltas (T1 kept through parsing) | test_ot5 |
| Typed turn skips the router (build call i) | test_ot6 |
| ask_user pauses: question_asked + pending kind=question + usage (decision 1, trial H1) | test_ask_user.py::test_q1 |
| Answer rides the resume as the tool result; both halves billed (H2/H3) | test_q2 |
| Unattended run never offered ask_user | test_q3 |
| Interactive runs ALWAYS carry ask_user (updated claims) | test_approvals.py::test_a5, test_router.py::test_r6, test_tools.py::test_l1, test_discovery.py::test_f1 |
| Nudge rides the next tool result; announced; consumed once (decision 3) | test_nudges_memory.py::test_n1 |
| Toolless run takes no nudge — nucleus keeps it | test_n2 |
| Memory pass saves the ruling with provenance; billed kind=memory on the UTILITY seat (decision 8) | test_m1 |
| Skip ruling saves nothing, still bills; pass runs after done | test_m2 |

Known gaps carried: the memory pass skips projects without an active index
(deliberate — it never creates one); the production classifier embedder
downloads its model on first use (tests pin "hash"); item 29 is parked with
the nucleus project (handoff change 12); the nucleus half of everything
above is handoff change 11 in `docs/NUCLEUS-HANDOFF.md`. Verified by the
owner 2026-10-14: 99 passed, 0 skipped, against the dev pgvector stack.

#### Layer 5 — decisions before design (settled 2026-10-14)

1. **Item 18 (Claude Agent SDK runtime) is DEFERRED** (owner, 2026-10-14).
   Deferring costs nothing: the seam is already built and tested —
   `AISystemFactory.create(kind)` + the `AISystem` interface, and T16 keeps
   pydantic-ai quarantined in `ai_engine/pydantic_ai_system/` so a second
   system can arrive beside it later without touching the rest. Revisit after
   switch-over.
2. **Item 9 (persona call rights): zero engine work.** Already **Built** in
   nucleus (`persona.mention` + `persona.approve_run`), enforced PRE-trigger;
   a job that reaches nexus-ai is by definition allowed. Nothing to build or
   test engine-side.
3. **Item 17 (connectors) SETTLED — two simple halves, zero engine code.**
   Owner's rule: "don't make things too difficult — I just wanted our app API
   to behave like an MCP as well, which can be accessed internally and
   externally."
   Three tiers, ranked by the owner (2026-10-14):
   **Tier 1 — the NeuralOps MCP GATEWAY is the FIRST-CLASS CITIZEN**: one MCP
   server exposing nucleus's EXISTING APIs, available BY DEFAULT — internally
   (personas use the product itself as a tool) and externally (any
   MCP-speaking client: Claude Desktop/Code, Cursor): ask_persona (→ the
   normal trigger road), search_memory (→ the embed/search endpoints),
   list_projects / list_topics, post_message. Auth is a PER-USER token
   created in the UI; every call acts AS THE CALLER through
   `PermissionChecker` — the caller sees exactly what they see in the web UI;
   no shared master key, ever. A thin front-door over existing endpoints — no
   new business logic.
   **Tier 2 — the other bundled MCPs are ONE CLICK away**: MCP servers that
   ship in the product's own code (item 35's mechanism; 0.8.0's `is_internal`
   flag) — the data MCP (34+36), the code-graph MCP (32), the provisioning
   MCP (39). They appear on every new project, OFF until the admin's one
   click turns them on.
   **Tier 3 — internal native tools are ON BY DEFAULT**: the native
   capabilities (filesystem, web search, shell, …) stay capabilities, not
   MCPs, available as today.
   All of it lives on the MCP/nucleus track (handoff change 13). Engine
   impact: none — personas already dial MCPs (Layer 1), including these.
4. **Item 39 (provisioning MCP) — one of the bundled connectors, with a
   fence** (owner, 2026-10-14): it is available ONLY in a reserved
   per-project topic named **"configure"**, accessible to exactly four roles
   — Project Admin, Project Owner, Company Admin, Company Owner. §4.5's
   design stands (acts as the caller, no self-elevation, secrets never in
   chat); its old blocker is GONE — item 5's real question cards were built
   in Layer 4, so the interview flow exists. Built as its own project on the
   MCP track, like the data and code-graph MCPs (decision 12's pattern).
5. **Connector deployment (settled 2026-10-14): both approaches, split by
   weight — and location-flexible.** Rule: *owns data or heavy libraries →
   its own container; just calls nucleus → rides one shared thin service.*
   HEAVY connectors — the data MCP (+ MinIO) and the code-graph MCP
   (+ FalkorDB) — are pre-defined services in `docker-compose.neuralops.yaml`
   (behind a compose profile); THIN connectors — the gateway and the
   provisioning MCP — share one lightweight "neuralops-mcp" service. NOTHING
   downloads or installs at click time: the admin's one click only flips
   availability in nucleus (self-hosted installs may be offline, and runtime
   docker control would hand nucleus the docker socket — refused). Because
   personas reach every MCP by URL, a heavy connector's container can run
   BESIDE THE STACK (default, the compose service's URL) or REMOTELY on
   rented compute — Amazon, RunPod — as the owner requires: same container
   image, the admin repoints the server URL in nucleus. This generalizes
   §4.4's "two tiers behind one interface" to all heavy connectors. Open:
   auth between the stack and a remote connector (per-server secret, like
   every stored MCP server's auth today).
6. **Item 8 (telemetry) RESOLVED (owner, 2026-10-14): no tracing — only the
   token phone-home, and it lives in nucleus.** The owner wants exactly ONE
   value reported: **total tokens**, sent home identified by the install
   (`NEURALOPS_INSTALL_TOKEN` names who owns the server), running from app
   start, NOT switchable by the customer. This supersedes Appendix B's
   earlier "disableable by one env var" note. Full request traces NEVER
   leave the customer's server — no OTel/logfire wiring ships in the rebuild
   (plain logs stay; tracing can return later as an opt-in if debugging
   demands it). Engineering note recorded with the ruling: the sender must
   FAIL SILENTLY when offline, so air-gapped installs work unharmed. Where it
   lives: NUCLEUS — the install token is there and nucleus already aggregates
   every usage record (change 1), so the phone-home is one sum + POST **at
   application open and close** (owner's cadence); handoff change 13.6. The
   full, detailed usage values stay recorded LOCALLY for the customer — that
   is item 21, already built — so users watch their own budget on their own
   box, and only the single total ever leaves. **Engine work: ZERO.**

**With decision 6, LAYER 5 IS CLOSED ON NEXUS-AI (2026-10-14): every Layer 5
item resolved to deferral (18), nucleus (8, 9), or the MCP track (17, 39) —
no engine code, no new tests; the suite stays at 99.**

#### Layer 6 — decisions before design (settled 2026-10-14)

1. **Item 45 (persona chains): NUCLEUS ORCHESTRATES; every stage is an
   ordinary trigger.** The §1.3 design (fixed stages, supervisor as
   gatekeeper, documents between stages, bounded review loops, checkpoints,
   writes ask, cost capped) stands — the settled question was WHERE it runs.
   Owner's pick: each worker stage AND each supervisor review is an ordinary
   `POST /api/v1/trigger/` run; nucleus holds the chain state and checkpoints
   and fires the next stage on each verdict. Rationale: everything already
   built then applies PER STAGE for free — item 2 pauses, ask_user, nudges,
   the memory pass, usage records, queue-per-topic — and a crash restarts
   from the checkpoint. Rejected: running the whole chain inside one engine
   run (a worker's pause has no stored shape inside another run's state; one
   chat reply cannot carry an hours-long job).
2. **The chain is driven through a bundled WORKFLOW MCP** (a Tier-2 connector,
   decision pattern of 39): tools ≈ `define_chain(stages, personas,
   criteria)`, `start_stage(n, handover)` (returns immediately — nucleus
   fires the stage; the supervisor's run ends and nucleus re-triggers it with
   "stage n done, review"), `approve_stage(n)`, `send_back(n, notes)` (bounded
   2–3 per stage, then ask the user), `get_stage_output(n)`. Acts as the
   caller; own project on the MCP track. An off-the-shelf "serial tasks" MCP
   was considered and rejected: it can store a step list but cannot RUN a
   persona with its own permissions, pauses and billing — only nucleus can.
3. **Runbooks RESOLVED — verified first** (legacy
   `apps/managers/runbooks.py`, read 2026-10-14, 26 lines): legacy W6 is
   ALREADY nucleus-sequenced — nucleus puts the previous reply on the job as
   `TriggerJob.step_context`, and the engine's whole job is
   `apply_step_context()`: append "Previous step's output — this step builds
   on it:" + the text, clipped to `RUNBOOK_STEP_CONTEXT_MAX`, to the persona
   prompt. Decision: (a) a runbook in the rebuild = A SAVED CHAIN DEFINITION
   (team + stages + criteria + per-stage model seats) — nucleus data,
   rerunnable, the workflow MCP's `define_chain` output; (b) the engine PORTS
   the step_context block (one prompt section, clip kept) so the 0.8.0 wire
   contract keeps working — Layer 6 engine piece 1.
4. **Preflight RESOLVED — verified first** (legacy
   `apps/managers/preflight.py`, read 2026-10-14, 37 lines): nucleus flags
   `preflight=True` when the persona is gated and no plan approved; the
   ENGINE owns the acts-at-all judgement (`acts_with_tools`: any mcp_servers,
   or shell/filesystem capability) and `plan_turn()`: a preflight turn that
   would act runs ONE TURN WITH NO TOOLS resolved as the `preflight` output
   type (already shipped in Layer 4's ten); `approved_plan` rides ahead of
   the persona prompt under "Approved plan — carry out these steps and
   nothing beyond them:" with tools restored. Decision: PORT both transforms
   — Layer 6 engine piece 2. The trigger fields already travel (T14).
5. **Item 46's `call_persona`: the engine's one-shot delegation tool —
   VERIFY-FIRST (trial I).** Scope: a persona (typically the supervisor)
   runs ANOTHER persona on a sub-task with a `Handover`; it ALWAYS RETURNS
   (never hands over the stream); the inner run gets NO ask/approval pauses
   — an inner ask-tool is refused exactly like an unattended run, and the
   result says so, so the outer persona (or the chain) decides; depth limit
   1 (a called persona cannot call further); inner usage recorded under the
   CALLEE's persona/model ids on the same message. Trial I must verify at
   pinned 2.55.0: an agent run INSIDE a tool function, usage accumulation
   into the outer run (the documented `usage=ctx.usage` pattern), and
   streaming constraints. Layer 6 engine piece 3 — built only after the
   trial passes.
6. **Model strategy (owner + assistant, 2026-10-14): both options are pure
   configuration; the shipped default is opinionated.** Personas already
   carry per-seat models (item 13), so "many personas → one model" and
   "many personas → many models" both work with zero new design. Default
   chain template: every worker on the project's main model, the SUPERVISOR
   on the deep seat (the reviewer should be the smartest in the room),
   utility seats cheap. The product's moat is not model mixing — it is
   documents-as-contract between stages + review gates + project memory +
   per-role billing.

Trial I — RESULT 3/3 PASSED (2026-10-14, pinned 2.55.0; throwaway script):
the call_persona road. (I1) an EXECUTING async tool in a
`FunctionToolset([...])` passed via `toolsets=` runs inside
`run_stream_events` and its return value reaches the model as the tool
result. (I2) INSIDE that tool, a second agent runs its own full stream loop
to completion — no event-loop deadlock; FunctionToolCallEvent/ResultEvent
appear for the outer tool as usual. (I3) the inner run's usage is its own
(1 request) and the outer run's does not absorb it (2 requests) — so billing
the inner run through its own respond() records is exactly right. Design
consequence: call_persona nests THE ENGINE (a fresh AISystemFactory graph
per inner run), not pydantic-ai agents — the `usage=ctx.usage` pattern was
not needed.

#### Items 45 + 46 + W6 + preflight — Layer 6: delegation and the turn rules (built 2026-10-14)

1. **Problem.** Chains need three engine hooks: a supervisor must be able to
   run a worker persona on one sub-task (46); a runbook step must see the
   previous step's output (W6); a gated persona must propose before acting
   (preflight). The chain itself is nucleus's (decision 1).
2. **Decision.** Layer 6 decisions 1–6 above. Build-time calls: the inner
   call_persona run is THE ENGINE CALLING ITSELF — a fresh factory graph and
   an ordinary respond() per inner job (trial I's consequence) — so pauses,
   retrieval, usage and the memory pass all apply to the callee for free;
   inner events are drained silently (item 19's tool_call_start/end is the
   outer trail); inner msg/job ids are `{outer}:cp{n}` — traceable, never
   colliding (vector row ids included); the plan block is PROTECTED
   (priority 91) while step_context is droppable (86); both ride as volatile
   sections — the cache rule beats legacy's splice order, headings verbatim.
3. **Mechanism.** *turn_rules.py*: `acts_with_tools(catalog)` (any MCP entry
   or shell/filesystem native), `step_context_section` (STEP_HEADING + head
   of the text, clipped at RUNBOOK_STEP_CONTEXT_MAX=12000 with CLIP_NOTE),
   `approved_plan_section` (PLAN_HEADING). respond(): `preflight_turn =
   preflight AND no approved_plan AND acts_with_tools` → catalog/loaded
   emptied (no capability tools, no catalog section; ask_user stays — the
   Layer 4 invariant holds) and the resolver is bypassed: the turn IS the
   preflight type (its contract rides; TYPES_WITHOUT_CHOICE keeps the choice
   exception off). *call_persona.py*: `call_persona_toolset(job, settings)`
   — one FunctionToolset per reply, closure-counted `delegation_max_calls`
   (3), `delegation_timeout_seconds` (600) via asyncio.timeout; args are the
   Handover (task, summary, references, constraints, expected_output),
   rendered small; inner TriggerJob: same company/project/topic/user,
   interactive=False, delegation_depth=1; errors/timeouts/empties return as
   WORDED TOOL RESULTS, never exceptions — a broken callee is the caller's
   information. Attached in respond() only when `persona.delegation_enabled
   AND delegation_depth == 0 AND not preflight_turn`; rides generate()'s
   toolsets beside ask_user. The gate ignores it by design (unknown
   capability_id → auto, loaded).
4. **At 0.8.0.** runbooks.py (26 lines) and preflight.py (37 lines) quoted in
   decisions 3–4 — both ported with contracts kept; call_persona had no
   legacy (swarm was the dropped non-answer, item 20).
5. **Open.** (a) Handover.references are plain strings v1 — the chain's
   stage files; a typed reference (message id vs file) can come later.
   (b) delegation across PROJECTS is refused by construction (ids pinned to
   the outer job) — revisit only with a real case. (c) The callee's
   context_window guard for a huge Handover rides item 16 as usual.
6. **Acceptance** (tests/test_turn_rules.py, test_delegation.py; T14's claim
   updated — three of the five "unplaced" fields are now LIVE). step_context
   reaches the prompt clipped to its head with the legacy heading; a
   preflight turn strips every capability tool (ask_user only), carries the
   preflight contract, answers as output_type=preflight; approved_plan
   restores the tools and rides under the legacy plan heading; a toolless
   persona passes through untouched. call_persona runs the CALLEE's own
   prompt on the rendered Handover, returns its reply as the tool result,
   bills the inner run under the callee's persona id on `{msg}:cp0`; the
   callee gets NO tools at depth 1 (no call_persona, no ask_user); personas
   without the flag never see the tool.
7. **Classes and methods.** `ai_engine/core/turn_rules.py` (acts_with_tools,
   step_context_section, approved_plan_section, STEP_HEADING, CLIP_NOTE,
   PLAN_HEADING); `pydantic_ai_system/tools/call_persona.py`
   (call_persona_toolset, DELEGATION_TOOLSET_ID, _handover_message);
   contracts: `TriggerJob.delegation_depth` (int, 0);
   `PersonaSpec.delegation_enabled` (bool, False — parsed from
   PersonaInternal); settings: `runbook_step_context_max
   (RUNBOOK_STEP_CONTEXT_MAX, 12000)`, `delegation_max_calls
   (DELEGATION_MAX_CALLS, 3)`, `delegation_timeout_seconds
   (DELEGATION_TIMEOUT_SECONDS, 600)`; ReplyGenerator.generate gains
   `delegate=`.
8. **API.** TriggerJob gains `delegation_depth` (additive; nucleus never
   sends it — only the engine's inner jobs carry 1). PersonaInternal gains
   `delegation_enabled` (handoff change 14). Usage records may carry
   message_id `{msg_id}:cp{n}` with the CALLEE's persona/model ids. No new
   endpoints.
9. **Sequence.** Delegation: outer run → call_persona(args) → fresh engine
   graph → inner trigger (unattended, depth 1) → inner done → content =
   tool result → outer continues → outer done; inner usage posted by the
   inner run itself. Preflight: trigger{preflight} → acts? → toolless
   preflight turn → plan to the user → trigger{approved_plan} → plan block
   + tools → acting run. Runbook step: nucleus sends step_context → block
   in prompt → reply → nucleus carries it to the next step.

#### Requirement → test traceability (Layer 6, added 2026-10-14; built, suite now 106 tests, supersedes the 99-test count)

| Requirement | Test |
|---|---|
| step_context block, legacy heading, clipped to its head (W6) | test_turn_rules.py::test_w1 |
| Preflight turn: no capability tools, preflight contract + type (decision 4) | test_p1 |
| approved_plan: tools restored, protected plan block, no contract | test_p2 |
| Preflight on a persona that cannot act passes through (legacy branch 3) | test_p3 |
| call_persona: callee runs as itself, reply = tool result, billed under callee on {msg}:cp0 (decision 5, trial I) | test_delegation.py::test_d1 |
| Depth limit + unattended inner run: no tools at depth 1 | test_d2 |
| Delegation is opt-in: no flag, no tool | test_d3 |
| The loaded 0.8.0 payload still replies clean (claim updated: 3 fields now live) | test_acceptance.py::test_t14 |

Known gaps carried: the chain itself (orchestration, workflow MCP, runbook
storage, default template) is nucleus/MCP-track work — handoff change 14;
delegation needs nucleus's `delegation_enabled` flag before any persona can
use it in production.

**With this entry, LAYER 6 IS CLOSED ON NEXUS-AI (2026-10-14) — and with it
the layered build of the engine: Layers 0–6 all closed, suite at 106.
VERIFIED BY THE OWNER 2026-10-14: 106 passed, 0 skipped, in nexus-ai-debug
against the dev pgvector stack. Remaining on nexus-ai: item 28 (vision,
deferred Layer 3 engine item), the stdio-MCP gap (Layer 1),
requirements.lock regeneration, and the switch-over. Everything else lives
in the nucleus project and the MCP track.**

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

#### Running the acceptance tests — the test report (added 2026-10-12)

**Layer 0 is built** at `modules/nexus-ai/` (2026-10-11) and all acceptance tests pass — T1–T16 as 25 pytest cases (T2/T3 run once per provider shape, plus three extra guards: internal-key auth, Decimal-never-float arithmetic, and a status-less row from today's nucleus being kept). O1 resolved as proposed (nucleus prices; the formula is pinned in `ai_engine/core/billing.py`); O2–O5 as written, with the three ids defaulting to `""` until nucleus sends them.

**Run after every change** — "done" still means all pass:

- venv: `cd modules/nexus-ai && pip install -r requirements-dev.txt && python -m pytest`
- Docker: `docker build -t nexus-ai:new-dev -f modules/nexus-ai/docker/Dockerfile modules/nexus-ai`, then `docker run --rm -u root nexus-ai:new-dev sh -c "pip install -r requirements-dev.txt && python -m pytest"`

**The suite is self-documenting.** Every test's docstring is its registry entry: the first line is the title (with its T-number), the rest the falsifiable claim it verifies. Every run prints the full report — title, purpose, result, duration per test — and rewrites `modules/nexus-ai/tests/REPORT.md` (hook in `tests/conftest.py`). Commit REPORT.md at milestones: its diff is the regression record. A new test joins the report by carrying the same two-part docstring — there is no separate list to maintain.

**The fakes are the harness.** `tests/fake_provider.py` answers exactly like OpenAI's and Anthropic's streaming APIs and records every request body (the same instrument as the 2026-10-10 trial); `tests/fake_nucleus.py` serves persona/history and records what lands on the usage endpoint; the module itself runs under real uvicorn in the test process, so disconnects (T8) and keepalives (T10) are real behaviour. No real model, no network, fully deterministic — and the dependency rules are themselves tests (`tests/test_dependencies.py`, T16), so a structural violation anywhere fails the suite naming the file.

#### Requirement → test traceability (Layer 0, added 2026-10-12)

Every Layer 0 requirement and the test that proves it. Gaps — true but not
proven by a test — are listed at the end, so it is visible where trust runs out.

**Item 25 — Event contract**

| Requirement | Covered by |
|---|---|
| Stream shape: `message_start` → `message_delta`(s) → exactly one `message_done`; done carries the full text == joined deltas == model text | T1 |
| `message_done` carries `output_type`/`render_as` "text", `prompt_tokens`, `output_tokens`, `context_window` (the fields the nucleus relay reads) | T4 (asserts 1700 / 300 / 200 000 on the done event) |
| Errors end as exactly one clean `message_error`, never a dropped connection | T9 |
| `keepalive` emitted on silence; still exactly one final event | T10 |
| 0.8.0's `TriggerJob` validates unchanged — unplaced-feature fields accepted and ignored | T14 |
| Only the right internal key gets in | auth test (`test_internal_key_required`) |

**Item 7 — Self-hosted / custom endpoints**

| Requirement | Covered by |
|---|---|
| `base_url` reaches the provider client — a custom endpoint actually serves the call | every acceptance test, implicitly: the fake provider IS a custom `api_base`, for both OpenAI and Anthropic shapes — including Anthropic, which 0.8.0 silently ignored (Appendix A) |

**Item 26 — History selection**

| Requirement | Covered by |
|---|---|
| Drop FAILED / CANCELLED / PENDING / STREAMING (when nucleus sends `status`) | T13 (`test_t13_history_rules`) |
| Drop stopped, system, empty, fake-HTML, visual-rendered-as-text rows | T13 |
| Another persona's reply prefixed `[Another Agent: …]`; own rows untouched | T13 |
| Rows without `status` (today's nucleus) pass — works pre-nucleus-change | T13 (`test_t13_status_none_is_kept`) |
| Newest `HISTORY_DEPTH` kept, oldest first, never reordered (O3) | T13 (`test_t13_depth_caps_keeping_newest_in_order`) |
| Selected history actually reaches the model request | T2 ("earlier question/answer" in the captured body) |

**Item 15 — Prompt caching (its Layer 0 form: the prompt layout)**

| Requirement | Covered by |
|---|---|
| System prompt in the request exactly once, via `instructions=` (never `system_prompt=`, which pydantic-ai drops with history) | T2, both provider shapes |
| Project brief ahead of the persona prompt; stable sections first | T2 (index comparison) |
| Persona's `temperature` and output cap reach the request (`model_settings` — the Appendix A drop) | T3, both shapes |

**Item 37 — Cancellation**

| Requirement | Covered by |
|---|---|
| Client disconnect cancels the run and stops the upstream model stream | T8 (the fake provider confirms the stream was cut; one request only) |
| A stopped run still records its (estimated) usage — never silent | T8 |

**Item 21 — Usage recording (exact billing)**

| Requirement | Covered by |
|---|---|
| One record per model call; counts per pydantic-ai semantics: input includes cache read+write, output includes reasoning | T4 (Anthropic), T5 (OpenAI) |
| Split into priced types: uncached = input − read − write; 5m = write − 1h; reasoning never added on top | T4, T5 |
| Record carries who/where/what: company, project, topic, persona, user, message, model, role, kind | T4 (asserts the ids, kind="chat_reply", role="STANDARD") |
| Cut stream, OpenAI shape → estimated; output from received text, input from the request | T6 |
| Cut stream, Anthropic shape → estimated; provider's input/cache counts kept, output re-estimated (never the provisional 1) | T7 |
| A failed model call (HTTP 500) still records | T9 |
| A cancelled run still records, once | T8 |
| `record_usage` failure never breaks a good reply | T15 |
| Cost formula exact, Decimal, per token type — 0.007725 and 0.00475 to the digit | T11, T12, + the Decimal guard |

**Item 47 — Topic usage feed**

| Requirement | Covered by |
|---|---|
| Every call recorded with its `topic_id`, so nucleus can roll it up to the topic bar | T4 (`topic_id == "t1"` on the record) — the roll-up and live push are nucleus's side, tested there when nucleus change (1) lands |

**Architecture rules (§1.5 dependency rules)**

| Requirement | Covered by |
|---|---|
| `ai_engine` framework-free; only imports `fastapi_app.contracts`; pydantic-ai quarantined in `pydantic_ai_system/`; no legacy imports; `fastapi_app/__init__.py` import-free | T16 ×4 (`tests/test_dependencies.py`) |

**Gaps — true but NOT proven by a test:**

1. Item 7, partially: only OpenAI and Anthropic shapes are exercised. The `google` and `ollama` branches of `ModelFactory` are written and import-checked but never called by a test — no google-shaped fake exists yet.
2. Item 15's actual cache HITS cannot be tested against a fake — only the layout is proven. Whether providers cache the prefix is measured later via `cache_read_tokens` in production. *Open:* the HISTORY_DEPTH sliding window vs. byte-identical prefix tension — once a topic passes `HISTORY_DEPTH` messages, the window slides every turn and the cached prefix misses until summaries (item 6, Layer 4) provide an anchor; undecided whether L0 accepts this or anchors the window in chunks.
3. EventMapper's batch sizes (40 chars / 50 ms) are not asserted — T1 only proves no text is lost, not the batching rhythm.
4. O3's "start at the topic's last compaction" is nucleus's half of the history contract — untestable here until nucleus change (2).
5. The Docker image build — verified by hand, not by the suite.

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

  **Central phone-home telemetry is a separate, deliberately tiny thing:** instance count keyed by the existing `NEURALOPS_INSTALL_TOKEN`, and total tokens — nothing else. *(Superseded 2026-10-14, Layer 5 decision 6: always on, not customer-disableable, fails silently offline, nucleus-side.)*

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

