# NeuralOps Nexus — Nexus-AI Revamp Spec

**Version:** 2 (design closed; remaining decisions in §14)
**Repo:** `neuralops-forked` @ `/data/code/neuralops-forked` (node3)
**Builds on:** `neuralops-persona-refactor-spec.md` v2 (Persona = 1 ModelConfig + 0..1 advisor + 0..N MCPServer) and `docs/OPEN-ITEMS.md` § "After upstream #101/#102"
**Date:** 2026-10-03

---

## 0. Changelog from v1

| Item | v1 | v2 |
|---|---|---|
| Model slots | FAST / STANDARD / DEEP / FALLBACK / ADVISOR / UTILITY, plus a proposed ROUTER | **ROUTER folded into FAST**, STANDARD retained as the default answerer. The FAST model *is* the router |
| Routing | Rules → scorer → optional LLM judge → tier | **Rules decide tools; the gatherer decides depth after seeing results.** `escalate()` replaces the pre-emptive judge |
| Two-model turns | "gather → answer", parked as a complex later phase | **Default mechanism**, falls out of escalation. Promoted to Phase 3 |
| Tool mounting | Mount only what the query needs | **Stable per-topic active set**, monotonic growth. Dynamic mounting broke the cached prefix |
| Tool ownership | Persona owns `mcp_servers` | **Three axes**: availability (project/channel/topic), default-on (persona ticks), permission (effect tier) |
| Tool permission | Not specified | **Reads ask once per topic; writes ask every call**; plan-level approval for multi-step. "Strict" policy for ask-always |
| Model → human questions | Not specified | **F15 question cards**, shared pause/resume with approval cards |
| Eval pipeline | Absent | **F14**, three suites, operator-runnable. Auto-routing is gated on it |
| Tool-calling capability | Trusted `supports_tools` flag | **Probe at registration** decides slot eligibility |
| Router LLM / hosted router | Open question | **Rejected** — see §13 |
| Abstraction layer | — | **LangChain/LlamaIndex rejected** — pydantic-ai + `ModelConfig` rows already are it. See §13 |
| D8 (judge default) | Open | **Resolved** — no judge model; evidence gate instead |

---

## 1. Scope

This spec revamps how a persona call travels through NeuralOps, from the moment a user types `@Persona` to the moment a cost is recorded.

| # | Feature | Lives in |
|---|---|---|
| F1 | Persona call rights (who may call which persona) | nucleus |
| F2 | Persona rate limits per user | nucleus |
| F3 | Summarize a topic into a new topic | nucleus + nexus-ai |
| F4 | Multiple models per persona (slots) | nucleus + nexus-ai |
| F5 | Rate limits per model | nucleus (config) + nexus-ai (enforcement) |
| F6 | Fixed budget per project | nucleus (ledger) + nexus-ai (metering) |
| F7 | Depth routing: cheap gatherer → escalation | nexus-ai |
| F8 | Bring-your-own Ollama models + tool-calling probe | nucleus + nexus-ai |
| F9 | Prompt / model caching | nexus-ai |
| F10 | Tool-loop control and context management | nexus-ai |
| F11 | Logfire observability — **inside nexus-ai only** | nexus-ai |
| F12 | Tools: scoping, catalog, index, selection | nucleus + nexus-ai |
| F13 | Claude Agent SDK as a second agent runtime | nexus-ai |
| F14 | Eval pipeline (router, tier sufficiency, tool selection) | nexus-ai + nucleus (admin UI) |
| F15 | Human-in-the-loop cards (approval + questions) | nucleus + nexus-ai |

**Out of scope:** nexus-transport (Centrifugo), the vector store and embedding pipeline, auth/Supabase. Logfire is not added to nucleus; that is deliberate (§6.3).

**Ownership note:** the persona refactor spec marked `pydantic_ai_runner.py` and `apps/schemas/trigger.py` as owned by another team member. This revamp rewrites both. Agree the split before Phase 3 (§14, D1).

---

## 2. Where things stand (verified against source, 2026-10-03)

The single-persona path today:

```
web app ──@Persona──► nucleus chat/api.py:send_message
                        │  MessageDirectives (parse @mentions, @chart, /swarm, @session)
                        │  rights: persona.mention (TOPIC scope, same for every persona)
                        ▼
                      chat/services.py:trigger_ai_response_async
                        │  POST nexus-ai /api/v1/trigger/   (TriggerJob: persona_id, topic_id, message…)
                        ▼
nexus-ai  routers/trigger.py → NewImprovedAgenticManager.run()
                        │  nucleus_client.resolve_persona()   (GET /internal/personas/{id}/)
                        │  nucleus_client.fetch_history()     (GET /internal/topics/{id}/history/)
                        │  NewImprovedPromptBuilder.build()   (system + format hint + RAG + history + msg)
                        │  PydanticAIRunner.run_stream()      (one Agent per call, SSE deltas)
                        ▼
                      SSE ──► nucleus relays to Centrifugo, saves ChatMessage
```

Gaps that feed directly into this revamp:

| Gap | Where | Consequence |
|---|---|---|
| `resolve_persona` reads `temperature`/`max_tokens` off `model`, but nucleus sends them on the persona. `max_steps`, `advisor_model`, `api_base` never mapped | `nexus-ai/apps/managers/nucleus_client.py` | Every persona runs at 4096 tokens / 0.7 with no step cap. F10 depends on fixing this |
| `_MODEL_REGISTRY` covers `openai`, `anthropic`, `deepseek`, `openai_compatible` only. No `ollama`, no `google`, no `api_base` | `pydantic_ai_runner.py` | F8 cannot work until fixed |
| `AIRequestLog` and `POST /internal/ai-request-logs/` exist, but **nothing calls them** on the pydantic-ai path. The endpoint also writes to `Company.objects.first()` | `internal/api.py`, runner | No usage data exists, so budgets (F6) need a real ledger first |
| `persist_internal_state` is read and discarded (`internal_model_state` assigned, never used) | `agentic_manager.py` | Tool calls/results from earlier turns are lost; no cache prefix carries between turns (F9, F10) |
| Output-format instruction is appended to the **system prompt** per message; RAG chunks go **before** history | `prompt_builder.py` | The prefix changes every turn, so provider prompt caching can never hit (F9) |
| `persona.mention` is one TOPIC-scope right | `authn/permissions/rights.py` | Anyone who can mention can call any persona (F1) |
| No `REDIS_URL` in nexus-ai's compose env, though Redis runs for Celery | `docker-compose.neuralops.yaml` | Needed for F2/F5/F6 counters |
| Production `nexus-ai` has no `extra_hosts: host.docker.internal` (dev does) | compose | Host Ollama unreachable in production (F8) |
| `OLLAMA_BASE_URL` defaults to `http://nexus-ollama:11434`, but **no such service exists** in `docker-compose.neuralops.yaml`. `ollama_embedding.py` is marked DEPRECATED | config + compose | F8 needs the service added behind a profile |
| `LLMFactory`'s `"local"` case raises `NotImplementedError` ("placeholder for future ONNX/llama.cpp"); `implementations/llm/litellm_model.py` is dead on the pydantic-ai path | `apps/factories/llm.py` | Delete with the litellm path in Phase 3. Local models arrive as `provider=ollama` through `providers.py`, not through this stub |
| `FastEmbedEmbedding`'s class default is `BAAI/bge-small-en-v1.5` (384 dims) but `EmbeddingFactory` always passes `settings.EMBEDDING_MODEL` = `nomic-ai/nomic-embed-text-v1.5` (768 dims) | `implementations/embedding/fastembed_embedding.py` | Dead default + misleading docstring; a reader sizing the vector store could use the wrong dimension. Fix in Phase 0 |
| Schedules (`scheduling/tasks.py`) and swarm trigger personas with no shared admission check | nucleus | F1/F2/F6 must apply on **every** entry point |

**What already exists and is reused rather than rebuilt:**

- `apps/output_types/classifier.py` — a working cosine classifier over `example_prompts` centroids, using the local fastembed model, with a margin threshold against a `"text"` baseline. F7 and F12 generalize this rather than adding anything new.
- `pydantic-ai` + `pydantic-ai-harness` — the abstraction layer, including `TieredCompaction`, `ToolSearch`, `SpendLimits`, `Advisor`, MCP mounting.
- `ModelConfig` rows — model swaps are already an admin action in the UI, not a code change.

---

## 3. Target architecture

### 3.1 Division of responsibility

**Nucleus decides whether a call may happen. Nexus-AI decides how it runs and reports what it cost.**

```
                ┌───────────────────────────── nucleus ─────────────────────────────┐
 user / schedule│  1. ADMISSION  (new: ai_gateway/admission.py)                      │
 / swarm ──────►│     • F1 call right on this persona?                               │
                │     • F2 per-user rate limit (Redis)                               │
                │     • F6 project budget: remaining > reservation? (Redis + DB)      │
                │     → deny: ephemeral notice to the caller, no AI message created    │
                │     → allow: reservation_id + run limits into the TriggerJob         │
                └───────────────┬────────────────────────────────────────────────────┘
                                │ TriggerJob (+ run_limits, reservation_id, caller, hints)
                ┌───────────────▼──────────────── nexus-ai ──────────────────────────┐
                │  2. RESOLVE   persona + model slots + topic tool set (internal API) │
                │  3. PLAN      rules + cosine → active tool set, skip-fast filters   │
                │  4. CONTEXT   history + persisted run state + RAG, cache-aware      │
                │               layout (F9), compaction (F10)                         │
                │  5. GATHER    FAST model runs with the tool index; permission cards  │
                │               (F15) gate execution; it answers, or escalate()        │
                │  6. ANSWER    on escalation: DEEP model continues from a distilled   │
                │               findings block (F7)                                    │
                │  7. METER     usage + cost per model request → POST /internal/usage/ │
                │               (settles the F6 reservation)                           │
                │  ── Logfire spans wrap 2–7 (F11) ──                                  │
                └────────────────────────────────────────────────────────────────────┘
```

Admission sits in nucleus because nucleus owns users, rights, projects and money, and because denying before `create_ai_message()` means no PENDING bubble is left to fail. Routing and per-model limits sit in Nexus-AI because only it knows which model served each request and how many tokens it used.

### 3.2 Nexus-AI layout after the revamp

```
apps/
  core/            config.py (+ REDIS_URL, LOGFIRE_*, RUNTIME/ROUTING defaults)
  observability/   logfire_setup.py, scrubbing.py                         (F11)
  gateway/         limits.py   (Redis token buckets per model)            (F5)
                   pricing.py  (cost from usage × ModelConfig prices)     (F6)
                   meter.py    (usage events → nucleus ledger)            (F6)
  routing/         planner.py    (rules: tools, skip-fast filters)        (F7/F12)
                   classifier.py (generalized cosine: output type, depth prior,
                                  tool relevance — one embedder, three exemplar sets)
                   slots.py      (slot chain, fallback, cache-adjusted cost) (F4/F5/F9)
                   escalation.py (escalate() tool, distilled handoff)      (F7)
  context/         layout.py      (cache-aware message assembly)          (F9)
                   tool_set.py    (per-topic active set, monotonic)        (F9/F12)
                   state_store.py (persisted run state per topic×persona)  (F10)
                   compaction.py  (TieredCompaction config, summarizer)    (F10/F3)
  interaction/     cards.py       (approval + question cards, pause/resume) (F15)
  runtimes/        base.py        (AgentRuntime protocol, AgentEvent contract)
                   pydantic_ai_runtime.py    (was implementations/agents/pydantic_ai_runner.py)
                   claude_agent_sdk_runtime.py                             (F13)
                   providers.py   (provider → pydantic-ai Model, incl. ollama/google/api_base) (F8)
                   loop_guard.py  (repeat-call detection, tool result caps) (F10)
                   probe.py       (tool-calling smoke test)                (F8)
  connectors/      catalog.py, mount.py (MCP mounting + tool filters)      (F12)
  evals/           suites.py, judge.py, report.py                          (F14)
  managers/        agentic_manager.py (pipeline 2–7), swarm_manager.py, nucleus_client.py
  routers/         trigger.py, embed.py, summarize.py (F3), evals.py (F14)
```

Deleted in Phase 3, once swarm moves onto the new runtime: `implementations/agents/litellm_runner.py`, `implementations/llm/litellm_model.py`, `factories/llm.py`, and the old `PromptBuilder`/`AgenticManager` classes. `litellm` stays **only** for embeddings, as `CompanyAIConfig` already documents.

---

## 4. Governance (nucleus)

### F1 — Persona call rights

**Goal:** a project admin controls who may call each persona. A "Finance Analyst" with a production database connector should not be callable by every project member.

```python
class Persona(TenantBaseModel):
    class Access(models.TextChoices):
        PROJECT    = "project",    "Everyone in the project with persona.mention"   # default, current behavior
        RESTRICTED = "restricted", "Only listed users / roles"
    access = models.CharField(max_length=20, choices=Access.choices, default=Access.PROJECT)

class PersonaGrant(TenantBaseModel):
    """Who may call a RESTRICTED persona. Exactly one of user / role is set."""
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="grants")
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    role    = models.ForeignKey("authn.Role", null=True, blank=True, on_delete=models.CASCADE)
    rate_limit_override = models.ForeignKey("nucleus.RateLimitPolicy", null=True, blank=True, on_delete=models.SET_NULL)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    class Meta:
        constraints = [
            CheckConstraint(name="persona_grant_user_xor_role",
                            condition=(Q(user__isnull=False) & Q(role__isnull=True))
                                    | (Q(user__isnull=True) & Q(role__isnull=False))),
            UniqueConstraint(fields=["persona", "user"], name="uniq_persona_grant_user", condition=Q(user__isnull=False)),
            UniqueConstraint(fields=["persona", "role"], name="uniq_persona_grant_role", condition=Q(role__isnull=False)),
        ]
```

**Check:** `can_call(user, persona, topic)` = existing `persona.mention` on the topic **AND** (`access == PROJECT` **OR** a matching `PersonaGrant`, directly or through one of the user's `RoleAssignment`s in this project).

**New right:** `persona.manage_access` (PROJECT scope), covering `access` and grants. Owner and Admin by default.

**Enforcement:** one `ai_gateway/admission.py:admit()` called from `send_message` (single, session and swarm paths) and from `scheduling/tasks.py`. For swarm, **every** persona in `job.personas` must pass, and personas the caller cannot call are removed from the handoff/delegate tool `enum` so the model cannot route to them.

**Schedules:** rejected at creation if the creator cannot call the persona; re-checked against the creator on each run, since access may have been revoked.

**UX:** an ephemeral notice to the caller only ("You don't have access to @FinanceBot — ask a project admin"). Nothing is posted to the topic, no AI message is created. `available-personas` / `List Team` mark restricted personas; mention autocomplete hides personas the caller cannot call.

### F2 — Persona rate limits per user

```python
class RateLimitPolicy(TenantBaseModel):
    """Reusable limit bundle. Any field null = unlimited on that axis."""
    name = models.CharField(max_length=100)
    calls_per_minute = models.PositiveIntegerField(null=True, blank=True)
    calls_per_hour   = models.PositiveIntegerField(null=True, blank=True)
    calls_per_day    = models.PositiveIntegerField(null=True, blank=True)
    tokens_per_day   = models.PositiveIntegerField(null=True, blank=True)   # settled after the run
    cost_per_day_usd = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    max_concurrent   = models.PositiveSmallIntegerField(null=True, blank=True)  # in-flight per user×persona

class Persona(...):
    user_rate_limit = models.ForeignKey(RateLimitPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

class Project(...):
    default_user_rate_limit = models.ForeignKey(RateLimitPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
```

**Resolution order** (most specific wins): `PersonaGrant.rate_limit_override` → `Persona.user_rate_limit` → `Project.default_user_rate_limit` → unlimited.

**Enforcement:** Redis sliding window in nucleus. Keys `rl:{persona}:{user}:m|h|d` (sorted sets of timestamps) and `rl:{persona}:{user}:inflight` (counter with TTL safety net). `tokens_per_day` and `cost_per_day_usd` are checked at admission against counters the F6 meter increments; a run that starts under the limit is allowed to finish. Swarm hops count against the persona that served them, charged to the original caller. Schedules count against the creator.

**UX:** ephemeral notice with the reset time ("Limit reached for @Nova: 20/hour. Try again in 14 min"). Admins get a per-persona usage view from the F6 ledger, grouped by user.

---

## 5. Models

### F4 — Model slots

**Goal:** a persona is no longer tied to one model. It holds an ordered set of **slots** feeding routing (F7), rate-limit fallover (F5) and outage fallback.

```python
class PersonaModel(TenantBaseModel):
    class Slot(models.TextChoices):
        FAST     = "fast",     "Fast — gatherer and light answerer"
        STANDARD = "standard", "Standard — default answerer"
        DEEP     = "deep",     "Deep — hard reasoning, long tool loops"
        FALLBACK = "fallback", "Fallback — when others are limited or down"
        ADVISOR  = "advisor",  "Advisor capability (second opinion)"
        UTILITY  = "utility",  "Utility — summaries, compaction, distillation, eval judge"
    persona      = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="model_slots")
    model_config = models.ForeignKey(ModelConfig, on_delete=models.PROTECT, related_name="persona_slots")
    slot         = models.CharField(max_length=20, choices=Slot.choices)
    priority     = models.PositiveSmallIntegerField(default=0)   # order inside a slot
    # Optional per-slot generation overrides (null = persona value)
    max_tokens      = models.PositiveIntegerField(null=True, blank=True)
    temperature     = models.FloatField(null=True, blank=True)
    thinking_effort = models.CharField(max_length=10, null=True, blank=True)  # minimal|low|medium|high|xhigh
    class Meta:
        constraints = [UniqueConstraint(fields=["persona", "slot", "model_config"], name="uniq_persona_slot_model")]
```

There is **no ROUTER slot**. The FAST model is the router (F7).

**Migration (two steps, non-breaking):**
1. Add `PersonaModel`. Copy `Persona.model` into a STANDARD slot and `advisor_model` into an ADVISOR slot. Keep both FKs; nucleus writes both while the new UI ships.
2. Once the web app writes slots only, drop `Persona.model` and `Persona.advisor_model`. The `persona_advisor_differs_from_model` constraint becomes a service-layer check: the ADVISOR model ≠ any STANDARD model.

**Rules:**
- At least one STANDARD slot is required. FAST, DEEP, FALLBACK, ADVISOR, UTILITY are optional; a missing slot falls back to STANDARD (UTILITY falls back to the project utility model, then STANDARD).
- Every non-UTILITY slot on a tool-enabled persona must have **passed the tool-calling probe** (F8). `supports_tools` alone is not sufficient evidence.
- Every slot model must be attached to the persona's project (`ModelConfig.projects`).

**Contract:** `PersonaInternal.model`/`advisor_model` are replaced by `model_slots: list[{slot, priority, model: ModelInternal, overrides}]`. Both shapes are sent during migration.

### F5 — Rate limits per model

```python
class ModelConfig(...):
    rpm_limit         = models.PositiveIntegerField(null=True, blank=True)
    tpm_limit         = models.PositiveIntegerField(null=True, blank=True)   # input+output
    max_concurrency   = models.PositiveSmallIntegerField(null=True, blank=True)
    daily_token_limit = models.PositiveIntegerField(null=True, blank=True)

# The auto-generated ModelConfig.projects M2M becomes an explicit through model:
class ProjectModelConfig(BaseModel):
    project      = models.ForeignKey("nucleus.Project", on_delete=models.CASCADE)
    model_config = models.ForeignKey(ModelConfig, on_delete=models.CASCADE)
    rpm_limit    = models.PositiveIntegerField(null=True, blank=True)   # this project's share of the key
    tpm_limit    = models.PositiveIntegerField(null=True, blank=True)
    class Meta:
        constraints = [UniqueConstraint(fields=["project", "model_config"], name="uniq_project_model_config")]
```

Converting an auto M2M to a `through` model needs a `SeparateDatabaseAndState` migration — the table and rows stay, only columns are added.

**Enforcement in Nexus-AI** (`gateway/limits.py`):
- Redis token buckets keyed `ml:{model_config_id}:rpm|tpm|conc` and `ml:{model_config_id}:{project_id}:rpm|tpm`.
- `acquire(model, est_tokens)` runs before each **model request**, not each run — one run can make 20 requests in a tool loop. Implemented as a pydantic-ai `WrapperModel` (`LimitedModel`) so every request inside the agent loop is checked.
- On saturation: if the run has not streamed text yet, move to the next model in the chain (`FallbackModel` semantics). If text has streamed, wait up to `RATE_LIMIT_MAX_WAIT_S` (default 20 s), then fail with `error_code="model_rate_limited"`.
- Provider 429s update the bucket from the `retry-after` header.
- After each response the bucket is corrected with real token counts.
- Limits arrive in the persona payload (`ModelInternal.limits`); Nexus-AI never queries the database.

### F7 — Depth routing: cheap gatherer, then escalation

**Goal:** easy questions are answered cheaply, hard ones get the strong model, and the decision is made with evidence rather than guessed from the question.

**The central principle: tools are decided up front; depth is decided after the tool results exist.** "Why is the build failing?" is light if the log shows a typo and heavy if it shows a race across three services. A pre-emptive classifier commits to a tier with the least information it will ever have.

**Persona setting:** `routing = off | auto`, default `off` (existing personas unchanged). With `off`, STANDARD always answers. `auto` is **gated on F14 evals** — a project cannot enable it until its own eval run shows the FAST tier is sufficient above threshold (§10).

**Flow:**

1. **Plan (`routing/planner.py`, rules + cosine, no LLM).** Decides the active tool set (F12) and whether to skip the FAST attempt entirely. Skip-fast filters: `/deep` typed, vision needed, context above the FAST model's window, write tools required, the topic already escalated, or no FAST slot configured.
2. **Gather.** The FAST model runs with the tool index (F12) and an `escalate(reason)` tool. It is instructed to settle its tool plan **before producing prose**, which gives a clean pause point for the F15 permission card. Tools execute after approval.
3. **Fork.** The FAST model either answers, or calls `escalate(reason)`.
4. **Answer.** On escalation the DEEP model continues from a **distilled findings block** the FAST model writes — it has just read everything, so the summary costs only output tokens, and the strong model receives signal rather than a raw dump. Handles to the full tool results accompany it (F10.3), so the DEEP model can pull specifics.
5. **Stick.** Escalation is sticky for the topic: later turns start at DEEP and cache properly.

**Why this is cheaper.** The tool loop is where requests pile up. Illustrative, 8 calls with context growing to ~20k, cheap model at ~$0.15/Mtok and strong at ~$3/Mtok, input only:

| | Cost |
|---|---|
| Loop on the cheap model | ~$0.01 |
| Loop on the strong model | ~$0.24 |
| Cheap loop + one strong answer pass | ~$0.06 |

≈5× overall, ≈20× on the loop. Verify against live prices before quoting these anywhere.

**Cache-adjusted cost, not sticker price** (`routing/slots.py`). Switching models mid-topic discards the cached prefix. Illustrative, 30k history + 500-token question, strong at $3/Mtok with cache reads at 10%, cheap at $0.80/Mtok, output excluded:

| Choice | Input cost |
|---|---|
| Stay on the strong model, prefix cached | ≈ $0.011 |
| Switch to the cheap model, cold prefix | ≈ $0.024 (≈ $0.031 with a cache write) |

The cheaper model costs 2–3× more on that turn. So the router compares **cache-adjusted** cost using the history size and both models' prices, and prefers tier stability within a topic. Routing decisions therefore concentrate at topic start, where context is small and a wasted FAST attempt is cheap — which is also what makes the gather-first design affordable.

**Escalation bias.** Misroutes are asymmetric: routing down wrongly produces a weak answer, a re-ask, and two runs; routing up wrongly costs cents. The planner is therefore biased toward the stronger option, and the ambiguous middle of the cosine score **defaults to STANDARD** rather than invoking a judge.

**System tasks route by type, not depth.** Summaries (F3), compaction (F10), the distilled handoff, title generation, output-type classification and the F14 judge always use the UTILITY slot regardless of the user's query.

**Routing presets** (project setting):

| Preset | Behavior |
|---|---|
| `cost_first` | Prefer the cheapest adequate slot; escalate only on `escalate()` |
| `balanced` | Default. Cache-adjusted comparison as above |
| `quality_first` | Prefer the strongest slot within budget; skip the FAST attempt for anything but trivial queries |
| `local_first` | Prefer zero-cost self-hosted models (F8); escalate to paid APIs only on `escalate()` or hard filters. Latency over money |

**Transparency:**
- `message_done` carries `model_used`, `tier`, `routing_reason` (`override`, `rule:tools`, `score:0.82`, `escalated`, `budget_downgrade`), and an `escalation` event is emitted on hand-off so the UI shows "moving to a stronger model — multi-step debugging" instead of a stall.
- Every decision becomes a Logfire span attribute (F11) so thresholds are tuned from real data.
- A thumbs-down on a FAST answer is recorded as a labelled example for F14. Exemplars are never added automatically.

**Budget pressure:** at ≥ `downgrade_at_pct` of the project budget (F6), DEEP is capped at STANDARD and STANDARD at FAST, unless the user typed `/deep`.

**Guards:** one escalation per turn; FAST → DEEP only, never a second hop, never DEEP → FAST; if the gathered results exceed the compaction target, compact before hand-off.

### F8 — Ollama models and the tool-calling probe

**Goal:** a self-hoster points NeuralOps at an Ollama server and picks models from a list, and NeuralOps knows empirically which of them can actually call tools.

**Nucleus:**
- `ModelConfig.Provider.OLLAMA` already exists; `api_base` defaults to `http://host.docker.internal:11434`.
- `POST /api/v1/model-configs/ollama/discover/ {api_base}` — calls `GET {api_base}/api/tags`, then `POST {api_base}/api/show` per model for context length, family and reported `capabilities` (`tools`, `vision`, `thinking`) to pre-fill `supports_tools`/`supports_vision`.
- `POST /api/v1/model-configs/ollama/register/ {api_base, models: [...]}` — one `ModelConfig` per selected model. No API key, no licence step, prices 0.
- Right: `model_config.create` (unchanged).
- Health: new `last_health_check_at` / `health_status`, refreshed by a Celery beat task pinging `/api/tags`. Unhealthy models are skipped by routing.

**The probe (`runtimes/probe.py`), run once at registration and re-runnable from the admin UI.** Reported capability flags and third-party benchmark tables are not evidence; small open models vary enormously at tool calling, and that is the binding constraint for any slot touching tools.

The fixture: a two-tool prompt requiring exactly one call, then a deliberately failing tool result to test recovery. Records `tool_call_ok`, `recovers_from_error`, `valid_json`, `latency_ms`. Results decide slot eligibility:

| Probe result | Eligible slots |
|---|---|
| Passes both | Any, including FAST gatherer on tool-enabled personas |
| Calls tools but does not recover | STANDARD/DEEP on tool personas; not the gatherer |
| Fails tool calling | Text-only personas and UTILITY only |

**Nexus-AI** (`runtimes/providers.py`) — one place builds every pydantic-ai model:

```python
match cfg.provider:
    case "anthropic":         AnthropicModel(cfg.model_id, provider=AnthropicProvider(api_key=cfg.api_key, base_url=cfg.api_base))
    case "openai":            OpenAIResponsesModel(cfg.model_id, provider=OpenAIProvider(api_key=cfg.api_key, base_url=cfg.api_base))
    case "google":            GoogleModel(cfg.model_id, provider=GoogleProvider(api_key=cfg.api_key))
    case "deepseek":          OpenAIChatModel(cfg.model_id, provider=DeepSeekProvider(api_key=cfg.api_key))
    case "ollama":            OpenAIChatModel(cfg.model_id, provider=OllamaProvider(base_url=f"{cfg.api_base.rstrip('/')}/v1"))
    case "openai_compatible": OpenAIChatModel(cfg.model_id, provider=OpenAIProvider(api_key=cfg.api_key or "none", base_url=cfg.api_base))
```

Requires `pydantic-ai-slim[google]`; present in dev via `pydantic-ai[all,…]`, **absent from `docker/production/requirements.txt`** — add it there.

**Compose:** add `extra_hosts: ["host.docker.internal:host-gateway"]` to production `nexus-ai`, and add an `ollama` service named **`nexus-ollama`** behind a `local-llm` profile, matching the existing `OLLAMA_BASE_URL` default that currently points at a service which does not exist.

**Where a local model pays.** Not tool selection (the embedder narrows for free, and the FAST model picks as its first action). The two slots worth pointing at a local model are **UTILITY** — summaries, compaction, distillation, eval judging: high volume, low stakes, zero marginal cost — and **FAST**, the gather loop, which is the biggest cost lever and keeps the loop's data inside the deployment. Both work through the registration path above plus the `local_first` preset; no new mechanism.

---

## 6. Runtime

### F6 — Fixed budget per project

**Pricing** on `ModelConfig`, entered by the admin, pre-filled from a bundled advisory price table for known model ids:

```python
input_price_per_mtok        = Decimal(10,6)   # USD per 1M input tokens
output_price_per_mtok       = Decimal(10,6)
cache_read_price_per_mtok   = Decimal(10,6, null=True)   # F9
cache_write_price_per_mtok  = Decimal(10,6, null=True)
```

Ollama and self-hosted endpoints default to 0; an admin may set a notional price so a GPU box appears in reports.

**Ledger.** Extend `AIRequestLog` in place, renaming the class to `UsageRecord` and keeping the table (§14, D4):

```python
class UsageRecord(TenantBaseModel):
    project      = FK(Project, PROTECT)                 # NEW — the budget key
    topic        = FK(ChatTopic, SET_NULL, null)        # NEW
    user         = FK(User, SET_NULL, null)             # NEW — who triggered (F2 counters)
    persona      = FK(Persona, SET_NULL, null)
    model_config = FK(ModelConfig, SET_NULL, null)      # NEW — joinable; model_id/provider strings kept
    job_id, msg_id, model_id, provider                  # existing
    kind         = CharField  # chat | swarm_hop | summary | compaction | distill | probe | eval | schedule
    tier         = CharField(null)                      # F7
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens   # NEW cache fields (F9)
    requests     = PositiveIntegerField(default=1)
    tool_calls   = PositiveIntegerField(default=0)
    cost_usd     = Decimal(12,6)                        # computed in nexus-ai, re-verified in nucleus
    latency_ms, status, error                           # existing
    prompt / response                                   # existing — now OPTIONAL (STORE_PROMPTS, default off)
```

Fix while here: `create_ai_request_log` writes to `Company.objects.first()`. It must take the company from the persona and project.

**Budget:**

```python
class ProjectBudget(TenantBaseModel):
    project       = OneToOneField(Project, CASCADE, related_name="budget")
    amount_usd    = Decimal(12,2)
    period        = CharField  # monthly | fixed | none
    period_anchor = PositiveSmallIntegerField(default=1)
    enforcement   = CharField  # hard (block) | soft (warn only)
    alert_thresholds = JSONField(default=[50, 80, 100])
    downgrade_at_pct = PositiveSmallIntegerField(null=True, default=80)   # F7 budget pressure
    per_run_cap_usd  = Decimal(10,4, null=True)
```

**Reserve → meter → settle**, so parallel runs cannot jointly overspend:

1. **Admission (nucleus).** `spent_this_period` from a Redis counter `budget:{project}:{period}`, rebuilt from the DB on a miss. Reserve `min(per_run_cap, estimate)`, the estimate being the persona's p90 cost over its last 50 runs or a default. If `spent + reserved_open + reservation > amount` and enforcement is hard, deny. Otherwise put `reservation_id` and `budget_remaining_usd` in the TriggerJob.
2. **Run (Nexus-AI).** Remaining budget becomes a hard per-run cost guard. The meter accumulates after each model request; if the next would exceed `run_limits.max_cost_usd`, the loop stops cleanly ("Stopped: this run reached the project's budget limit").
3. **Settle.** `POST /internal/usage/` sends one record per model request, batched at run end plus every 5 s during long runs. Nucleus writes records, increments Redis spend and per-user counters, releases the reservation. Unsettled reservations expire after 15 minutes.
4. **Alerts.** Celery checks thresholds after settle and notifies project admins, idempotent per threshold per period.

**Also metered:** F3 summaries, F10 compaction, F7 distillation, F8 probes, F14 eval runs, scheduled runs.

**UI:** project settings → Budget; a usage dashboard by persona, model, user and day including cache savings; "≈ $0.02 / answer" on persona cards from recent runs.

### F9 — Prompt and model caching

Providers charge far less for input tokens matching a cached prefix, and that only works when the start of the prompt is byte-identical turn to turn. Today it never is (§2).

**The layout (`context/layout.py`):**

```
[1] instructions        persona system prompt + stable persona-level format guidance   ← stable for days
[2] tools               schemas for the topic's ACTIVE SET, sorted deterministically,
                        + a name-only roster of other available servers                ← stable per topic
[3] history             previous turns + persisted run state (F10), compacted           ← append-only
    ── cache breakpoint ──
[4] per-turn context    RAG chunks for THIS message + output-format instruction for THIS message
[5] current user message
```

Changes from today: move the per-message output-format instruction out of the system prompt into [4]; move RAG chunks from before history to after it; sort tools deterministically; never put timestamps, message ids or random values in [1]–[3].

**The per-topic active tool set (`context/tool_set.py`)** — the unit that makes [2] both small and stable:

- **Active set** = basic tools (project-configurable) + the persona's default-on ticks ∩ the topic's attached tools + anything unlocked in this topic. Schemas are mounted only for these.
- **Roster** = the other attached servers, **names only** (~20–30 tokens), so the persona can say "I could check GitHub if you mention `@github`" without carrying 40 schemas.
- **Monotonic:** the active set only grows within a topic, never shrinks. Dropping an unused tool later would be a second prefix invalidation for no gain.
- **Unlock is sticky and whole-server.** Tool definitions sit before history, so unlocking invalidates the history cache for that turn — re-paying full input price on the whole history once (a few cents at 20k history). Hence: pay once per server per topic, and mount a whole server at a time rather than one tool, taking one invalidation instead of several. In practice one or two per topic.
- **Basic set** defaults to project-local reads (read file, grep inside the project folder — no credentials, no egress). Web search and fetch default on but are switchable off per project, because a search query leaves the deployment and that matters to the same self-hosters the Ollama path serves.

**Per provider:**

| Provider | Mechanism | Settings |
|---|---|---|
| Anthropic | Explicit breakpoints | `AnthropicModelSettings(anthropic_cache_instructions=True, anthropic_cache_tool_definitions=True, anthropic_cache_messages=True)`. TTL `'5m'` default; `'1h'` while an `@session` is open or a schedule runs more often than every 5 min. Max 4 breakpoints; pydantic-ai trims extras |
| OpenAI / DeepSeek / OpenAI-compatible | Automatic prefix caching | No settings; the layout is what makes it hit. Pass a stable `prompt_cache_key` = `persona_id` where supported |
| Google Gemini | Implicit caching | Layout only. Explicit `cachedContents` is a later option for very large RAG corpora |
| Ollama | KV cache on prefix match; weights stay resident | Layout plus `keep_alive` (default `30m`, per-model via `config.keep_alive`) |

**Metering:** record `cache_read_tokens`/`cache_write_tokens` from pydantic-ai `usage.details` (including `ephemeral_1h_input_tokens`) and price them separately (F6). The dashboard shows cache hit rate and dollars saved — the evidence that the layout works.

**Persisted agent state** (F10.4) is the second half of this: replaying real `ModelMessage` history, tool calls included, keeps the prefix identical instead of rebuilding a lossy text version each turn.

**Semantic response cache: deferred** (§13).

### F10 — Tool loops and context management

**1. Enforce limits that already exist.** `max_steps` → `UsageLimits(request_limit=max_steps, tool_calls_limit=max_steps * 3)`; `max_tokens` honoured per response; `total_tokens_limit` from the F6 run limits. When a limit trips, end with a closing summary from one final no-tools request, streamed as normal deltas: "I stopped after 10 steps. Done so far: … Say *continue* to keep going."

**2. Loop guard (`runtimes/loop_guard.py`).**
- **Repeat call:** identical `(tool_name, canonical_args)` three times in a run → the third returns a tool error naming the prior result; the fourth stops the run.
- **No progress:** 6 consecutive tool calls with no new text, plan update or file write → one-time "summarize what you've learned and decide" nudge.
- **Swarm:** keep `MAX_HOPS=7` plus a shared run budget (steps, tokens, cost) across all hops, so delegation cannot multiply limits.

**3. Tool result hygiene.** Cap each result at `TOOL_RESULT_MAX_CHARS` (default 20k); larger results are written to `/nexus/projects/<slug>/.nexus/tool-results/<run>/<n>.txt` and replaced with a head/tail preview plus a handle the model can read. Keep the existing `TieredCompaction` order (dedupe file reads → clear old tool results keeping 5 pairs → summarize), running the summarizer on **UTILITY**. Set `target_tokens` from the **routed model's `context_window`** — today it is derived from `max_tokens`, which is the output limit and the wrong number — using ~70% for history and 30% for response, RAG and margin.

**4. Persisted run state (`context/state_store.py`).** New nucleus table `AgentRunState(topic, persona, messages_json, token_count, sdk_session_id, updated_at)`, written through `PUT /internal/run-state/` at run end, storing the compacted `ModelMessage` list via `ModelMessagesTypeAdapter`. The next trigger for the same topic × persona loads it instead of rebuilding from `ChatMessage.content`; intervening human and other-persona messages merge in as user turns, attributed as today. Cleared when the topic is archived, the persona's `config_hash` changes, or a user types `/reset`. Compacted before saving if over target. **This is also the pause/resume substrate for F15.**

**5. Many tools.** Keep `ToolSearch`. Beyond 40 tools in a topic's active set, mount with `defer_loading=True` so only the index is in context — which also keeps [2] small and stable.

**6. Visibility.** New `tool_call_end` event `{name, status: ok|error|truncated, duration_ms}`. Nucleus relays both tool events through the existing `tool_activity_event` helper to show "Searched GitHub ✓ 1.2s".

### F11 — Logfire, inside Nexus-AI only

```python
import logfire
logfire.configure(
    service_name="nexus-ai",
    service_version=settings.VERSION,
    environment=settings.ENVIRONMENT,                 # dev | staging | production
    send_to_logfire="if-token-present",               # no token → nothing leaves the box
    scrubbing=logfire.ScrubbingOptions(extra_patterns=["api_key", "authorization", "secret", "token", "client_secret"]),
    console=False,
)
logfire.instrument_pydantic_ai(include_content=settings.LOGFIRE_INCLUDE_CONTENT)  # default False
logfire.instrument_fastapi(app, excluded_urls="/health")
logfire.instrument_httpx()        # nucleus, Ollama, MCP over HTTP
logfire.instrument_mcp()
logfire.instrument_redis()        # F5 limiter
```

Called first in `main.py`. With no `LOGFIRE_TOKEN`, traces can still go to any OTel collector via `OTEL_EXPORTER_OTLP_ENDPOINT`, or nowhere. Telemetry never leaves unless the operator configures it.

**Root span `nexus.run`** per trigger, with `job_id, msg_id, project_id, topic_id, persona_id, user_id`, `runtime, tier, routing_reason, model_used, escalated`, `steps, tool_calls, input/output/cache tokens, cost_usd, budget_remaining`, and `outcome` (`ok | escalated | limit_steps | limit_budget | rate_limited | awaiting_input | error`). Child spans: `resolve`, `plan`, `context.build`, `compaction`, `gather`, `distill`, `answer`, `meter.flush`, plus automatic spans per model request and tool call.

**Secrets:** `nucleus_client` already avoids logging decrypted MCP secrets. Add a test asserting no span attribute contains values from `ModelInternal.api_key` or `MCPServerInternal.secrets`.

**Nucleus is not instrumented** (decision). Correlation uses `job_id`/`msg_id`, which nucleus already logs.

**Dashboards:** cost per project per day; p50/p95 time-to-first-token per model; tier mix and escalation rate; FAST-tier thumbs-down rate; cache hit rate per provider; tool error rate per connector; runs stopped by limits; approval card response times.

---

## 7. Tools and humans

### F12 — Tool scoping, catalog, index and selection

**Today:** an admin hand-creates an `MCPServer` row and attaches it to a persona. That is powerful but not a product: nobody knows the GitHub MCP URL or its OAuth scopes. And per the OPEN-ITEMS audit, the pydantic-ai runner does not currently mount `persona.mcp_servers` at all, so attached servers do nothing.

**Three independent axes.** These are easy to conflate and the spec keeps them separate:

| Axis | Set by | Decides |
|---|---|---|
| **Availability** | Project / channel / topic attachment | What is in the index at all |
| **Default-on** | Persona ticks | Whether the model may reach for it unprompted, or only on mention |
| **Permission** | Effect tier (read vs write) | Who approves, and how often |

A tick is configuration, not consent: a ticked write tool is still gated on every call.

**Availability — attachment, not persona ownership:**

```python
class ToolAttachment(TenantBaseModel):
    """Where a tool server is available. Exactly one of project/channel/topic is set."""
    mcp_server = models.ForeignKey("nucleus.MCPServer", on_delete=models.CASCADE, related_name="attachments")
    project    = models.ForeignKey("nucleus.Project", null=True, blank=True, on_delete=models.CASCADE)
    channel    = models.ForeignKey("nucleus.Channel", null=True, blank=True, on_delete=models.CASCADE)
    topic      = models.ForeignKey("nucleus.ChatTopic", null=True, blank=True, on_delete=models.CASCADE)
    disabled   = models.BooleanField(default=False)   # topic-level opt-out of an inherited attachment
```

Available in a conversation = project ∪ channel ∪ topic attachments, minus topic-level `disabled`. Rights: admins attach at project and channel level; members may attach or disable at topic level from servers the project already defines, via a new `topic.manage_tools` right (TOPIC scope).

**Default-on — the persona's ticks.** `Persona.mcp_servers` is **reinterpreted, not dropped**: its rows become the default-on selection rather than "the tools it has". Granularity matches the mention syntax — tick a whole server, or expand and tick individual tools; server-level is the UI default. The ticks are a preference matched at runtime against what the topic actually has:

- ticked and attached → default-on
- attached but unticked → in the roster, usable on mention
- ticked but not attached here → absent, and the persona can say so

Two defaults: a new persona has **nothing ticked**, so it needs a mention until configured; and a persona-level **`tools_enabled` master switch** off means an empty index and declined mentions, for writing or policy personas that should not be tool-capable even on request.

**Permission — by effect, not by name:**

| Tier | Policy |
|---|---|
| **Read** (no side effect, no spend, no egress) | Asks once per topic, then runs, every call visible in the activity trail |
| **Write / delete / send / spend** | **Asks every single time**, showing real arguments, never remembered |
| **Admin-blocked** | Never available |

For multi-step work the model presents its **plan** once rather than prompting per call — "read 4 files in `api/`, search the web, list open PRs" → Allow / Edit selection / Deny. One decision per turn instead of eight, and the person sees the whole shape of the work. A **stop button** on the running message plus the live trail and an **approval audit log** (who approved what, when) provide the oversight that per-call prompting is meant to provide, without the fatigue that makes people click through. Every remembered grant is revocable from the topic's tool panel and project settings.

A project-level **`tool_policy = standard | strict`** setting makes even reads ask every time, for regulated deployments.

**Mentions — the fast path, and themselves the permission.** `@github` (server level, the one that matters), `@tools` / `@mcp` (blanket grant for this turn), `@github.list_prs` (single tool, supported but not featured). A mention directs *and* authorizes read use of that server for that turn, so someone who knows what they want sees no card. Mentions are stripped before the prompt, as `@chart` and `@session` already are in `MessageDirectives`. Mentioning a server the topic lacks gets a straight answer plus an offer to attach it if the caller holds the right.

**Mentions are not mandatory.** The commonest case is "why is the build failing?" from someone who does not know GitHub is behind the answer; requiring a mention would make them retype, which is worse than one card.

**Selection — cosine, reusing what exists.** `apps/output_types/classifier.py` is generalized into `routing/classifier.py`: one local fastembed model, three labelled exemplar sets (output type — existing; depth prior; tool relevance). Four details make tool matching work:

- **Embed an augmented document per tool**, not the raw description. Descriptions are written for the model ("Creates an issue in a repository"), not for query matching ("the login button is broken, log it"). Description + trigger phrases, from the catalog YAML or generated once at registration by the UTILITY slot. Vectors are computed at registration and cached by `config_hash`.
- **Include "no tool needed" exemplars** and let them compete, mirroring how `"text"` is today's baseline, rather than using an absolute threshold.
- **Match at server level, cap at two.** Unlock is per-server and monotonic (F9), and a card listing five servers is not a decision anyone makes well. Tool-level scores only rank within `ToolSearch`.
- **Bias toward recall.** A false positive costs one legible permission card; a false negative costs a worse answer and a retyped message.

**Cosine decides what to offer, never what to execute.** Permission gates the call. No LLM is involved in selection: the FAST model is already running with the index and picks as its first action.

**Connector catalog** (versioned in the repo, `modules/nexus-nucleus/intelligence/connectors/*.yaml`):

```yaml
key: github
name: GitHub
icon: github.svg
category: engineering
transport: http
url: https://api.githubcopilot.com/mcp/
auth:
  type: oauth2
  authorize_endpoint: https://github.com/login/oauth/authorize
  token_endpoint: https://github.com/login/oauth/access_token
  scopes: [repo, read:org]
  client_credentials: operator      # operator registers the OAuth app once per deployment
alt_auth:
  type: static_secrets
  fields: [{name: client_secret, label: "Personal access token", secret: true}]
tools:
  default_allow: ["*"]
  deny: ["delete_repository"]
  requires_approval: ["create_*", "update_*", "merge_*"]   # write tier
  trigger_phrases: ["pull request", "PR", "issue", "repo", "commit", "CI", "build failing"]
credential_scope: [user, project]
first_party: false
```

Initial set: GitHub, Google Drive, Slack, Notion, Jira/Confluence, Linear, Postgres (read-only), Filesystem (internal, already provisioned), Web Search/Fetch (internal capability).

```python
class ConnectorInstall(TenantBaseModel):          # one per project per connector
    project         = FK(Project, CASCADE)
    connector_key   = CharField(max_length=64)
    catalog_version = CharField(max_length=20)
    mcp_server      = OneToOneField(MCPServer, CASCADE, related_name="connector_install")
    tool_allow      = JSONField(default=list)
    tool_deny       = JSONField(default=list)

class ConnectorConnection(TenantBaseModel):       # the credential
    install           = FK(ConnectorInstall, CASCADE, related_name="connections")
    owner_type        = CharField  # project | user
    user              = FK(User, null=True, CASCADE)
    secrets_encrypted = TextField  # same Fernet pattern as MCPServer
    oauth_config      = JSONField(null=True)
    needs_reauth      = BooleanField(default=False)
```

**Whose credentials.** A `project` connection is one shared credential (a bot account); anyone who can call the persona acts through it. A `user` connection uses the **caller's own** credential for that run, and an unconnected caller gets `connector_auth_required` with a "Connect GitHub" button, reusing the existing `mcp_reauth_required` flow. Nucleus resolves per call via `GET /internal/personas/{id}/?caller={user_id}`. Default: user-owned for personal-data connectors (Drive, Slack, Gmail), project-owned for team systems (GitHub org bot, Jira).

**Rights:** `connector.install`, `connector.remove` (PROJECT, Admin), `connector.connect_own` (PROJECT, Member), `topic.manage_tools` (TOPIC, Member). Attaching a connector to a persona reuses `persona.update`.

**Runtime:** no new mechanism. `ConnectorInstall.mcp_server` arrives in `mcp_servers` as today, with the resolved credential and tool filter, and the same list feeds the Claude Agent SDK runtime (F13). Filters apply at mount time via the pydantic-ai MCP toolset's `filtered()`.

**UI:** a tool chip row on the topic header — "GitHub · Web search · Files" — with add and remove, making "this topic is using these tools" visible and doubling as the revoke path. Composer autocomplete on `@` lists what is attached here with read/write markers; without it, mentions fail because people cannot type what they do not know exists.

### F15 — Human-in-the-loop cards

**Goal:** one mechanism for the two times a run must stop and wait — it needs permission, or it needs a decision only a person can make.

**Shared substrate.** Both pause the run, persist state via `AgentRunState` (F10.4), end the stream with `outcome="awaiting_input"`, and resume on the answer. The pydantic-ai path uses deferred tool approval; the Agent SDK path uses `canUseTool` with a `PreToolUse` deferral so the process can exit and resume later rather than holding a callback open.

**Approval cards** (F12 permission tiers) carry the plan, per-tool checkboxes, the server being asked for, and **Allow once / Allow for this topic / Deny**. Write-tier calls show real arguments and offer no remembering.

**Question cards** — a built-in `ask_user` tool, matching the shape the Agent SDK already uses so both runtimes behave identically:

- 1–4 questions per card, 2–4 options each, `multiSelect` for checkboxes, a short header per question
- an "Other…" free-text option per question, and a dismiss-and-reply-freely path
- the card names the persona (or tool server) asking
- answers post into the topic as a visible message, then the run resumes

**Rules:**
- **Only the caller answers.** Everyone else in the topic sees the card read-only — NeuralOps is a shared chat, unlike every comparable product's single-user assistant.
- At most one question card per turn by default.
- Cards expire after 24 h; an expired run ends with what it has.
- **Never ask for secrets in a card.** Credentials go through the connector OAuth flow or a URL-mode interaction, never a form field, per the MCP elicitation rule.
- **Schedules cannot ask.** A scheduled run uses only tools pre-authorized at creation (read-only unless the creator named write tools), and states its assumption instead of asking.
- Every approval and answer is written to the audit log.

**New SSE events:** `approval_required`, `question_required`, `tool_call_end`, `escalation`. Nucleus relays them on a **per-user channel** (`user-{id}`, §14 D3) so a card reaches only its intended answerer while the activity trail stays visible to the topic.

---

## 8. Summarize into a new topic (F3)

**Goal:** when a topic gets long or drifts, start a fresh topic carrying a summary of the old one. The new topic starts with clean, cheap context; the old one stays intact and linked.

**Trigger:** `/summarize-new [title]`, the topic menu's "Continue in new topic", or a suggestion chip when the persisted run state crosses 80% of the compaction target.

**Rights:** `topic.create` on the channel plus the ability to call some persona in the project. The summary runs on the project utility model, not a specific persona, so F1 does not block it. It counts toward the project budget (`kind=summary`) and the caller's F2 counters.

**Flow:**
1. Nucleus creates the `ChatTopic` in the same channel with `parent_topic=<old>` (new nullable FK) and title `<given>` or "<old title> (cont.)".
2. `POST nexus-ai /api/v1/summarize/ {source_topic_id, target_topic_id, focus?}` — SSE, so the summary streams in like any AI message.
3. Nexus-AI loads the full history in chunks (map-reduce above the utility model's context) and produces: **Goal / context**, **Decisions made** (with who decided), **Open questions**, **Action items** (owner, status), **Key artifacts** (files, links, code paths), **Persona notes** (who was involved, tool state worth keeping).
4. Saved as the first message of the new topic (`message_type=SUMMARY`, sender = system "Summary", metadata `{source_topic_id, covered_through_sequence}`). The old topic gets "Continued in → #new-topic".
5. `fetch_history` always includes a topic's SUMMARY message even when older than `HISTORY_DEPTH`, and it sits in cache block [3], so it is cached.
6. Optionally copy the old topic's `ContextSource`s and tool attachments (checkbox, default on).

**Model:** the project's `utility_model` (new nullable FK on `Project` to an attached `ModelConfig`); else the FAST slot of the first persona mentioned in the topic; else the company `default_llm_model`.

**Not doing:** splitting topics automatically. Summaries are user-initiated or suggested, never silent.

---

## 9. Claude Agent SDK runtime (F13)

**Goal:** let a persona run on the Claude Agent SDK instead of pydantic-ai, gaining Claude Code's built-in tools, subagents, hooks and session resume. Suited to coding personas working in `/nexus/projects/<slug>`.

**⚠ Authentication constraint — read before building.** Anthropic's documentation states: *"Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead."* (https://code.claude.com/docs/en/agent-sdk/overview, checked 2026-10-02). SDK use is governed by Anthropic's Commercial Terms of Service.

NeuralOps therefore **cannot ship "sign in with your Claude subscription"** unless Anthropic approves it. Pluggable auth:

| `auth_mode` | Source | Status |
|---|---|---|
| `api_key` | The persona's Anthropic `ModelConfig.api_key` → `ANTHROPIC_API_KEY` for the SDK process | **Ship** |
| `bedrock` | `CLAUDE_CODE_USE_BEDROCK=1` + AWS credentials in a ModelConfig | Ship (5b) |
| `vertex` | `CLAUDE_CODE_USE_VERTEX=1` + GCP credentials | Ship (5b) |
| `subscription` | claude.ai login | **Not built.** Only with Anthropic approval (§14, D7) |

**Persona setting:** `runtime = pydantic_ai | claude_agent_sdk`, default `pydantic_ai`. The SDK runtime requires every slot model to be `provider=anthropic` (or Bedrock/Vertex Claude). F7 routing still applies, selecting which Claude model the SDK uses. The ADVISOR slot does not apply — use SDK subagents.

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    model=routed.model_id,
    system_prompt=persona.system_prompt,              # NeuralOps persona prompt, not Claude Code's
    cwd=project_dir,                                  # /nexus/projects/<slug>
    mcp_servers=to_sdk_mcp_config(active_tool_set),   # F12 active set, same credentials and filters
    allowed_tools=persona.sdk_allowed_tools,          # e.g. ["Read","Grep","Glob","Edit","Bash(git *)","mcp__github__*"]
    permission_mode="default",                        # anything outside → F15 approval card
    can_use_tool=cards.handle,                        # F15: approvals + ask_user
    setting_sources=[],                               # never load ~/.claude from the container
    max_turns=persona.max_steps,
    include_partial_messages=True,                    # token streaming → message_delta
    resume=run_state.sdk_session_id,                  # F10.4 continuity per topic×persona
    env=sdk_env(auth_mode, model_config),             # per call, never process-global
)
```

**Event mapping to the existing contract:**

| SDK message | Maps to |
|---|---|
| stream text deltas | `message_delta` (same 50 ms buffering as today) |
| tool use block | `tool_call_start` |
| tool result | `tool_call_end` |
| `canUseTool` for a gated tool | `approval_required` (F15) |
| `canUseTool` for `AskUserQuestion` | `question_required` (F15) |
| `ResultMessage` | `usage` + `cost_usd` (`total_cost_usd`, cross-checked against our pricing) → meter |
| `ResultMessage.session_id` | `AgentRunState.sdk_session_id` |

Budget and loop limits are enforced through `max_turns`, a `PreToolUse` hook checking the run cost guard, and cancelling the client when it trips.

**Isolation:** a separate subprocess per run with its own env; `cwd` pinned to the project folder; `Bash` off unless explicitly allowed; `setting_sources=[]` so no user-level `~/.claude` configuration applies.

**Image:** the SDK drives the Claude Code CLI binary, so the `neuralops` image must include it. Confirm whether the pinned Python SDK bundles it or whether Node plus the CLI must be installed. Add `claude-agent-sdk` to the Nexus-AI requirements.

**Branding:** per Anthropic's guidelines, present it as "Claude Agent" or "{Persona} · Powered by Claude", never "Claude Code".

---

## 10. Eval pipeline (F14)

**Goal:** know whether routing is correct and whether the cheap tier is sufficient, rather than guessing thresholds. **Auto-routing is earned, not assumed:** a project keeps `routing=off` until its own eval run clears the threshold.

The question is not "which model is best" — the operator chose their models. It is three narrower questions, so three suites:

| Suite | Measures | Pass criterion |
|---|---|---|
| **Router accuracy** | Did the planner pick the tier a human would? | ≥ 85% agreement, and **no more than 2% wrong-downgrades** on cases labelled deep |
| **Tier sufficiency** | Could the FAST model actually handle what was routed to it? | ≥ 90% of FAST answers judged "good enough" |
| **Tool selection** | Did cosine pull the right server? | ≥ 90% recall at server level, ≤ 2 servers offered |

**Ground truth comes from production, not only hand-written cases.** After Phase 1 there is real traffic with real costs. Sample real queries, replay each through both the cheap and strong paths, and judge whether the cheap answer sufficed. A thumbs-down on a FAST answer becomes a labelled example. A shipped synthetic seed set covers a fresh install with no history.

**Operator-runnable**, because the model mix is theirs: `manage.py run_evals [--suite] [--sample N]` plus an admin page showing per-suite scores, the tier mix, and which thresholds would change. Results gate `routing=auto` per project.

**The judge** runs on the UTILITY slot (which may be a local model, §F8) and is metered as `kind=eval`. **Evals on real chat content are opt-in and stay on the operator's infrastructure**; the default is the synthetic seed set. Nothing is sent anywhere.

**Escape hatches this unlocks, each gated on its own suite failing:** an LLM tier judge (if the ambiguous band proves large and expensive), a UTILITY-slot tie-breaker for tool selection (if cosine recall is short), and a depth-classifier fine-tune (§13).

---

## 11. Contract changes (nucleus ⇄ Nexus-AI)

### 11.1 `TriggerJob` / `TriggerSwarmJob`

```python
class RunLimits(BaseModel):
    max_cost_usd: Decimal | None        # F6: min(budget remaining, per_run_cap)
    max_total_tokens: int | None        # F2 tokens_per_day remainder

class TriggerJob(BaseModel):
    ...existing fields...
    caller_user_id: str                 # F1/F2/F12/F15
    project_id: str                     # F6 metering key (today inferred)
    reservation_id: str | None          # F6
    run_limits: RunLimits               # F6/F2
    routing_hint: Literal["fast","deep"] | None   # F7 /fast /deep
    mentioned_tools: list[str]          # F12 — server or server.tool keys; grants read use this turn
    trigger_kind: Literal["chat","session","swarm","schedule"]
    resume_token: str | None            # F15 — resuming after a card
```

### 11.2 `PersonaInternal`

Adds `model_slots[]` (each `ModelInternal` carrying `limits`, `pricing`, `probe_result`), `runtime` + `sdk_allowed_tools`, `routing` + `routing_preset`, `tools_enabled`, `default_on_tools[]`, `tool_policy`, and `config_hash`. Removes `model`/`advisor_model` after migration.

New sibling payload `TopicToolsInternal`: the topic's attached servers with `tier` (read/write) per tool, `tool_allow`/`tool_deny`, `requires_approval`, resolved per-caller credentials, and existing topic grants.

### 11.3 New internal endpoints (Nexus-AI → nucleus)

| Endpoint | Purpose |
|---|---|
| `POST /internal/usage/` | Batch usage records; settles the reservation (F6). Replaces `/internal/ai-request-logs/` |
| `GET/PUT /internal/run-state/{topic_id}/{persona_id}/` | Persisted agent state (F10.4, F13 session id, F15 pause) |
| `GET /internal/topics/{id}/tools/?caller={user_id}` | The topic's tool set with per-caller credentials and grants (F12) |
| `POST /internal/tool-grants/` | Record an approval decision + audit entry (F15) |
| `GET /internal/topics/{id}/history/?include_summary=1` | Always include the SUMMARY seed (F3) |
| `POST /internal/probe-results/` | Tool-calling probe outcome (F8) |

### 11.4 SSE events

- `message_done` gains `model_used`, `tier`, `routing_reason`, `escalated`, `usage {input, output, cache_read, cache_write}`, `cost_usd`, `stop_reason` (`end | escalated | limit_steps | limit_budget | limit_tokens | awaiting_input`). It also **restores `output_type`**, an existing regression.
- New: `tool_call_end`, `escalation`, `approval_required`, `question_required`.
- New `error_code` values: `model_rate_limited`, `budget_exhausted`, `connector_auth_required`, `provider_unsupported`, `tool_denied` — replacing today's blanket `"sorry"`.

Admission denials (F1/F2/F6) never reach Nexus-AI. Nucleus publishes them, and F15 cards, on a per-user channel `user-{id}`.

---

## 12. Phasing

Each phase ships on its own and leaves `dev` working.

| Phase | Contents | Depends on | Size |
|---|---|---|---|
| **0 — Repair** | `resolve_persona` mapping (temperature, max_tokens, max_steps, api_base, advisor); `providers.py` with ollama/google/openai_compatible + api_base; restore `output_type` in `message_done`; precise `error_code`s; `REDIS_URL` + `extra_hosts` for nexus-ai; `pydantic-ai-slim[google]` in production requirements; remove the dead `bge-small` default and fix its docstring | — | S |
| **1 — See it** | F11 Logfire; F6 ledger half (UsageRecord fields, `/internal/usage/`, pricing, per-request cost) with no enforcement; usage dashboard v1 | 0 | M |
| **2 — Govern it** | F1 call rights + PersonaGrant; F2 RateLimitPolicy + Redis admission; F6 ProjectBudget + reserve/settle + alerts; one `admit()` used by chat, session, swarm and schedules | 1 | M–L |
| **3 — Choose models** | F4 slots (two-step migration); F5 per-model limits + `LimitedModel` + fallback chain; F8 Ollama discover/register/health + probe + `nexus-ollama` service; F7 planner + gather/escalate + distilled hand-off + presets; **restore MCP mounting with ask-every-call permission as the interim safe default**; F14 suites 1–2; move swarm onto the new runtime and delete the litellm path | 2 | L |
| **4 — Context & control** | F9 cache-aware layout + per-topic active tool set + cache metering; F10 UsageLimits, loop guard, tool-result capping, `AgentRunState`, `tool_call_end`; F3 summarize-new-topic | 3 | M–L |
| **5 — Tools & humans** | F12 attachment scoping, catalog, index + roster, cosine selection, permission tiers, mention syntax, per-caller credentials, Strict policy; F15 approval + question cards (needs Phase 4 run state); F14 suite 3; F13 Agent SDK (`api_key`), then 5b Bedrock/Vertex | 4 | L |

**Note on tool permission order.** Phase 3 restores MCP mounting — currently broken, so there is no regression to protect — with **ask on every call**, the simplest safe default. Phase 5 then adds read-once-per-topic, plan-level approval, and the Strict policy for operators who want to keep ask-always.

**Frontend per phase:** 1 — usage page. 2 — persona Access tab, rate-limit policies, budget settings, per-user notices. 3 — slot editor, Ollama discovery + probe results, "answered by" badge. 4 — "Continue in new topic", tool activity ✓/✗ chips, "stopped after N steps — continue?". 5 — connector gallery, connect-account flow, approval and question cards, topic tool chips, `@` autocomplete, runtime picker.

---

## 13. Rejected options

Recorded so they are not relitigated.

| Option | Why not |
|---|---|
| **LangChain / LlamaIndex / LiteLLM as an abstraction layer** | Already solved twice over. pydantic-ai is the abstraction, and `ModelConfig` rows make a model swap an admin action in the UI rather than a config edit — stronger decoupling than the advice reaches for. A second layer over the first adds indirection and a dependency. LiteLLM stays for embeddings only |
| **A shipped model tier list** (naming specific models per tier) | Dates within a release or two, and it is not ours to decide: a self-hoster assigns their own models. Ship capability requirements per slot, plus an advisory metadata file the operator can override |
| **A dedicated router LLM** | Sits on the happy path, charging latency and cost on 100% of requests to improve the ~10–20% ambiguous ones. Since tools are mounted, the FAST model's first action *is* the tool decision, and `escalate()` makes the depth decision with evidence rather than prediction. Revisit only if F14 suite 1 shows the ambiguous band is large and expensive |
| **A NeuralOps-hosted router (e.g. on RunPod)** | Sends **every user query** out of the customer's network, which inverts the self-hosting and privacy positioning that justifies the Ollama path in the first place; makes NeuralOps an uptime dependency for other people's installations; inverts the cost model (continuous GPU spend so customers save money) to replace a decision an in-process embedder makes free; and conflicts with data-residency requirements. If a hosted product is ever wanted, **hosted inference** for GPU-less self-hosters is the better candidate, as an opt-in paid add-on with a published data policy |
| **Fine-tuning the tool set into model weights** ("a model that already knows my tools") | Models like the Hermes line are trained on the function-calling *format*, not on anyone's tools; definitions still go in context. Baking them in would need retraining on every connector change, per tenant, on infrastructure self-hosters do not have — to save ~70 effective tokens a turn once caching is applied. Worse, it removes the property that the mounted set **is** ground truth, so the model would confidently call detached, removed or unpermitted tools. A depth classifier fine-tune is the one variant that survives, gated on F14 |
| **Mandatory tool mentions** (user must name a tool for any tool use) | The commonest case is someone who does not know which connector backs their question. Requiring a mention makes them retype, which is worse than one approval card. Mentions stay as a fast path and as implicit permission |
| **Ask-every-time for read tools as the shipped default** | An eight-call run means eight prompts; the eighth is clicked, not read, so the full friction is paid for less real oversight. Reads on resources the caller already has access to grant no new privilege. Available as the `strict` tool policy, and it is the Phase 3 interim default before tiering lands |
| **Semantic response cache** (answer repeats without a model call) | Deferred past Phase 4. Only safe with no tools, low temperature and no per-topic RAG, and a stale or misattributed answer in a team chat is worse than paying for the call. Revisit against Phase 4 metrics |
| **Running every slot model per turn** | Multiplies cost and latency and leaves conflicting answers to arbitrate in a shared chat. Exactly one model answers; extras serve defined roles (gather, escalate, advise, fall back). A `/compare` command is the explicit exception if ever wanted |
| **Logfire in nucleus** | Nexus-AI is where models, tools and cost live. Correlation via `job_id`/`msg_id` is sufficient, and nucleus instrumentation would add a dependency and a data-egress surface for little gain |

---

## 14. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| D1 | Who owns the Nexus-AI runtime rewrite (the persona spec assigned `pydantic_ai_runner.py` elsewhere)? | Agree before Phase 3; Phase 0 fixes are small enough to land now |
| D2 | Fold `advisor_model` into an ADVISOR slot, or keep the FK? | Fold it in — one place for every model a persona uses |
| D3 | Per-user notices and cards: a `notice` with `target_user_id` on the topic channel, or a per-user channel? | Per-user channel (`user-{id}`). Needed for F15 cards anyway, and nothing leaks to other subscribers |
| D4 | Rename `AIRequestLog` → `UsageRecord`, or extend in place? | Extend in place, keep the table, rename the class only |
| D5 | Keep prompts/responses in the DB ledger? | Off by default (`STORE_PROMPTS=false`); Logfire `include_content` is the opt-in debugging path |
| D6 | Budget currency | USD only for v1 |
| D7 | Claude subscription auth for the Agent SDK | Do not build. Ship API key / Bedrock / Vertex. Contact Anthropic only if subscription use becomes a hard business requirement |
| D8 | ~~Router LLM judge default~~ | **Resolved:** no judge model. The ambiguous band defaults to STANDARD and `escalate()` corrects it; F14 gates any revisit |
| D9 | Semantic response cache | Deferred; see §13 |
| D10 | Connector credential ownership default | User-owned for personal-data connectors (Drive, Slack, Gmail); project-owned for team systems (GitHub org bot, Jira) |
| D11 | Basic tool set contents | Project-local reads on by default; web search/fetch on but switchable off per project, since a search query leaves the deployment |
| D12 | Who may answer an F15 card in a shared topic | The caller only; others see it read-only |

---

## 15. Test plan (minimum per feature)

- **F1** — a restricted persona rejects an ungranted user on all four entry points (chat, session, swarm, schedule); a role grant works; the swarm tool `enum` excludes personas the caller cannot call.
- **F2** — the 21st call in an hour is denied with the correct reset time; concurrency respects `max_concurrent`; a swarm hop charges the original caller.
- **F4/F5** — migration copies model and advisor into slots; a saturated FAST model falls over before streaming and waits-then-errors after streaming; a provider 429 updates the bucket.
- **F6** — two parallel runs cannot jointly exceed a hard budget (reservation test); a run stops cleanly at `max_cost_usd`; alerts fire once per threshold per period; cached tokens are priced at the cache rate.
- **F7** — `/fast` and `/deep` override; the write-tools rule skips the FAST attempt; `escalate()` hands over a distilled block and the DEEP model can pull a handle; escalation is sticky for the topic; the cache-adjusted comparison keeps a long topic on its cached model; budget pressure downgrades; `routing_reason` appears on the span and in `message_done`; no second hop.
- **F8** — discovery against a stub Ollama returns models and capabilities; the probe fails a non-tool model and restricts its slots; an Ollama persona streams in production compose via host-gateway.
- **F9** — golden test: prefix bytes for turns N and N+1 are byte-identical through block [3]; an Anthropic run reports `cache_read_tokens > 0` on turn 2; unlocking a server invalidates once and the active set never shrinks.
- **F10** — an identical tool call ×3 is intercepted; `max_steps` stops with a closing summary; an oversized tool result is truncated with a working handle; run state round-trips and is invalidated on a `config_hash` change.
- **F11** — no secret values appear in exported spans (scrubbing test); no content is exported with `include_content=False`.
- **F12** — the three axes compose correctly (attached-but-unticked is roster-only; ticked-but-unattached is absent; a tick alone never authorizes a write); a topic-level `disabled` overrides an inherited attachment; a mention authorizes reads for that turn only; cosine offers ≤2 servers and loses to the no-tool baseline on plain conversation; a deny-listed tool is never mounted; a user-owned connection is used only for its own caller.
- **F13** — event-mapping parity with the pydantic-ai runtime (golden SSE transcript); `max_turns` and the cost guard hold; the subprocess gets only per-call env and loads no `~/.claude` settings.
- **F14** — each suite runs offline on the seed set; the judge is metered as `kind=eval`; `routing=auto` cannot be enabled below threshold; real-chat sampling is off unless opted in.
- **F15** — a run pauses, persists and resumes after an approval and after a question; only the caller can answer and others see read-only; a write tool asks on every call even after "allow for this topic"; a card expires at 24 h; a scheduled run never asks and states its assumption; no card field can request a secret; revoking a topic grant re-prompts.
- **F3** — the new topic gets a SUMMARY seed, a back-link and copied context sources; map-reduce engages above the utility model's context; cost is recorded as `kind=summary`.

---

## Sources

- Repo code read 2026-10-02/03: `modules/nexus-ai/apps/{managers/agentic_manager.py, managers/nucleus_client.py, managers/prompt_builder.py, implementations/agents/pydantic_ai_runner.py, implementations/embedding/{fastembed_embedding.py, ollama_embedding.py}, factories/{embedding.py, llm.py}, output_types/{classifier.py, types.py}, schemas/trigger.py, routers/trigger.py, core/config.py, main.py}`, `docker/{dev,production}/requirements.txt`; `modules/nexus-nucleus/{nucleus/models/intelligence.py, nucleus/models/workspace.py, authn/permissions/{models.py, rights.py}, internal/api.py, chat/services.py}`; `docs/OPEN-ITEMS.md`; `docker-compose.neuralops.yaml`.
- Claude Agent SDK overview, auth note and branding guidance: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK, approvals and user input (`canUseTool`, `AskUserQuestion` shape, deferral): https://code.claude.com/docs/en/agent-sdk/user-input
- MCP elicitation (form/URL modes, enum single/multi-select, accept/decline/cancel, no secrets in forms): https://modelcontextprotocol.io/specification/draft/client/elicitation
- OpenAI, developer mode and MCP apps in ChatGPT (reads vs write confirmation, per-message app selection, admin action controls): https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- GitHub, auto model selection routing on task signals: https://github.blog/changelog/2026-05-20-auto-model-selection-now-routes-based-on-your-task-in-vs-code/ and https://github.blog/changelog/2026-07-01-copilot-cli-auto-model-selection-routes-based-on-task/
- VS Code MCP approval scopes and the revoke gap: https://github.com/microsoft/vscode/issues/245329
- pydantic-ai Anthropic prompt-caching settings: https://pydantic.dev/docs/ai/models/anthropic/
