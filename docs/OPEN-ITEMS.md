# Open Items — deferred during the docs/repo reorg pass

Running notes on things flagged mid-cleanup but deliberately not fixed yet,
so they don't get lost. Add to this rather than fixing inline unless you say
otherwise.

---

## Dev nginx.conf doesn't block `/api/v1/internal/`

**Where:** root-level `nginx.conf` (dev profile, used by `docker-compose.yaml`'s
`dev` profile).

**What's different from production:** `neuralops/nginx.conf` (the unified-image
production config) explicitly returns 403 on `/api/v1/internal/`:

```
location /api/v1/internal/ {
    return 403;
}
```

The dev config has no equivalent block. `/api/v1/internal/` is meant to be
called only container-to-container (nexus-ai → nucleus) and, per the
production config's own comment, its endpoints return real secrets —
decrypted AI-model API keys, raw chat history. In the dev config, a request
to that path just falls through to the generic `/api/` location and gets
proxied straight to `nucleus-dev:8000`, protected only by the
`X-Internal-API-Key` header check on the Django side, not by a network-level
block the way production has it.

**Decision needed:** is this an acceptable gap for a local/dev-only setup, or
should the same `return 403` block be ported into the dev nginx.conf too?

---

## Centrifugo runs fully insecure — in production, not just dev

**Where:** two separate places, both currently insecure, in different ways:

- Root `centrifugo.json` (old dev profile): `"client_insecure": true`,
  `"allowed_origins": ["*"]`.
- `neuralops/entrypoint.sh`'s `centrifugo` mode (the CURRENT production /
  unified-image flow — this is what self-hosters actually run today):

  ```
  nexus-transport --admin.enabled --admin.insecure --client.insecure --http_api.insecure
  ```

This is baked directly into `entrypoint.sh`, not read from any JSON file —
`centrifugo.json` isn't used by the new Docker setup at all, only by the old
dev-profile `docker-compose.yaml`.

**Why it matters more than the earlier framing suggested:** this isn't just
the client-channel-isolation gap noted in `TASKS.md`'s gotchas
(`--client.insecure` — no per-channel JWT, channel isolation relies on
clients only subscribing to topics they were legitimately given). Production
also runs `--admin.insecure` (Centrifugo's admin panel, no auth) and
`--http_api.insecure` (the HTTP control API, no auth) wide open, by default,
on every current self-hosted deployment. nginx currently only proxies
`/connection/websocket` and `/connection/sse` — so the admin/HTTP API
surfaces aren't directly internet-reachable through nginx today, but they
are reachable to anything else that can reach the `centrifugo`/`realtime`
container directly (another container on the same network, or the host
itself if the port's published) — worth explicitly confirming that no
compose file publishes that port before treating this as low-risk.

**Decision needed:** whether to move to token-based client auth (the
"backlog task on adding a post-connect token endpoint" mentioned in
`neuralops/nginx.conf`'s own comment) and drop all three insecure flags
before this gets more real-world usage, and whether it's P0 or P1 —
`--client.insecure` requires a client to deliberately misbehave to matter,
but `--admin.insecure`/`--http_api.insecure` don't require misbehavior, just
network reachability.

---

## Rename `neuralops/` folder to `docker/`

**Where:** the `neuralops/` folder at repo root (`Dockerfile`, `entrypoint.sh`,
`infra.env.example`, `app.env.example`, `nginx.conf`, `nginx.dev.conf`) — the
unified-image build context for the current production self-host flow.

**Status:** deliberately deferred — decided not to do this now, revisit later.

**What the rename touches, so this doesn't get done half-way later:**

- The folder's own files move as a unit — no internal changes needed.
- `docker-compose.neuralops.yaml` (root) — build context/Dockerfile path and
  both env-file paths (`infra.env.example`, `app.env.example`) currently
  point at `neuralops/...` and would need updating.
- `neuralops/entrypoint.sh` — header comments reference the folder name
  (cosmetic, won't break anything, but will read wrong post-rename).
- `docs/SELF-HOST.md` — likely has setup instructions pointing at
  `neuralops/` for env files.
- `docs/DECISIONS.md` — §20's discussion of the unified-image flow likely
  names the folder.
- `readme.md` — if it walks through unified-image setup or links to files
  inside the folder.

**Decision needed when this is picked back up:** whether to just move the
folder and leave references broken for a later pass (same approach used for
the `docs/` consolidation), or move it and fix every reference in the same
pass. Also worth a quick grep for the literal string `neuralops/` across the
repo first, rather than relying on this list, since it wasn't exhaustively
searched.

---

## Shared default Postgres/Redis credentials, both exposed on host ports

**Where:** `docker-compose.neuralops.yaml`'s `postgres` and `redis` service
blocks (production profile), plus `neuralops/infra.env.example`.

**What's wrong:** `infra.env.example` ships literal example values —
`POSTGRES_DB=neuralops`, `POSTGRES_USER=neuralops`,
`POSTGRES_PASSWORD=change-me` — and unlike `FIELD_ENCRYPTION_KEY` /
`INTERNAL_API_KEY` / `CENTRIFUGO_API_KEY` / `CENTRIFUGO_HMAC_SECRET` (which
get a dedicated `init-secrets` generator producing a fresh random value per
deployment), there is no equivalent generator or forced-change mechanism for
the Postgres credentials. A self-hoster who copies the example file and
doesn't specifically go edit `POSTGRES_PASSWORD` ends up running Postgres
with the literal password `change-me` — confirmed this repo's own
`neuralops/infra.env` still has it unchanged.

Redis has the same shape of gap but worse: no `REDIS_PASSWORD` / Redis
`--requirepass` is set anywhere in the compose file or example env — Redis
runs with **zero authentication** at all, not even a shared default one.

**Why it's more than cosmetic:** both services publish host ports in the
`postgres`/`redis` blocks — `${POSTGRES_HOST_PORT:-5495}:5432` and
`${REDIS_HOST_PORT:-6395}:6379` — meaning they're not internal-network-only.
If a self-hoster's firewall, cloud security group, or tunnel/funnel config is
more permissive than intended, these ports are reachable from outside the
host. Combined with a widely-known shared default password (or no password
at all, for Redis), that turns "misconfigured firewall" into "anyone can
connect directly to the database or cache with `psql`/`redis-cli`,
bypassing the app layer and RBAC entirely."

**Decision needed:** whether Postgres credentials should get the same
per-deployment `init-secrets`-style generation treatment the other four
secrets already have; whether Redis should require a password by default;
and whether `postgres`/`redis` need their host `ports:` mappings published
at all in the production profile, versus staying reachable only over
`neuralops-network` internally (nothing outside the stack currently seems to
need direct host access to either).

---

## neuralops-react-app: 8 remaining eslint warnings

**Where:** `modules/neuralops-react-app` (`npm run lint`).

Left in place during the 2026-09 UI/build-fix pass because fixing them
changes behavior, not just style:

- 2× `react-hooks/exhaustive-deps` — `AddPersonaForm.tsx:87` (missing
  `projectId`), `useChat.ts:448` (missing `channelId`/`projectId`). Adding
  the deps re-runs those effects on channel/project switches; that needs a
  deliberate review of the intended reset semantics, not a mechanical fix.
- 6× `react-refresh/only-export-components` — shadcn/ui files exporting
  variants/helpers alongside components (`badge`, `button`, `form`,
  `navigation-menu`, `sidebar`, `toggle`). Standard shadcn layout; fixing
  means splitting files and touching many imports for dev-only HMR benefit.

---

## neuralops-web-app: Escape during an in-flight create still completes it

**Where:** `modules/neuralops-web-app` — all intelligence create dialogs.

Pre-existing semantics (predates the create-flow rework, which only widened
the window with the attach-first step): once submit fires, closing the dialog
does not abort the mutation — the entity is still created and toasts. If
cancel-on-close is ever wanted, it needs AbortSignal plumbing through the
mutations; today the toast at least announces the outcome.

## Backend docs still describe AIAgent / AIModel after PR #99

**Where:** `docs/CONCEPTS-AND-ROLES.md` (the "Agent — AIAgent" section, the
`ai_model.*` / `agent.*` rights tables, `visible_agents`), `docs/ARCHITECTURE.md`
(`AIModel`, LiteLLM `provider/model` ids, "attach it to an agent"), and the
`readme.md` feature list.

PR #99 collapsed `AIAgent` into `Persona` (one model + optional advisor + 0..5
MCP servers), renamed `AIModel` → `ModelConfig` (`/model-configs/`, bare
`model_id` + `provider`, `qualified_id` in pydantic-ai `provider:model` form),
renamed the rights to `model_config.*` (plus a new `model_config.update`), and
deleted `agent.*`. None of those docs were updated in the PR. DECISIONS.md §18
was rewritten with the web-app follow-up; the rest is the backend's to fix.

**Decision needed:** whether the backend maintainer updates them in one pass or
the sections get a "superseded by PR #99" banner until then.

---

## `NEURALOPS_VERSION` not bumped for the PR #99 API break

**Where:** `neuralops/Dockerfile` (`NEURALOPS_VERSION="0.1.2"`), consumed by the
web-app's `COMPATIBLE_SERVER_VERSION` drift check in `src/lib/version.ts`.

PR #99 is a breaking API change for clients (`/ai-models/` → `/model-configs/`,
`/agents/` gone, persona payloads reshaped), but the image version stayed 0.1.2
(the dev profile reports `dev`, which the check ignores). The web-app was
adapted to the new contract and its `COMPATIBLE_SERVER_VERSION` deliberately
left at 0.1.2: bumping it alone would flag every 0.1.2 production server as
"breaking" even though 0.1.2 images built from the current `dev` DO speak the
new contract. When the image version is bumped (0.2.0 would be right under the
"MINOR drift is breaking while MAJOR is 0" rule), move the frontend constant in
the same change.

**Decision needed:** release owner's call — when and to what.

---

## Backend fields the AI worker never reads (do not build UI for these yet)

**Where:** `modules/nexus-nucleus/internal/api.py` (`ModelInternal`, `PromptInternal`,
`MCPServerInternal`) vs `modules/nexus-ai/apps/managers/nucleus_client.py` /
`apps/schemas/trigger.py`.

While aligning every web-app dialog with the backend input schemas (2026-09-06),
these accepted-and-stored fields turned out to have no consumer at runtime, so
the web app deliberately does NOT expose them (a control that changes nothing
is worse than none):

- `ModelConfig.config` (provider-specific JSON): not in `ModelInternal`, so
  nexus-ai never sees it.
- `MCPServer.server_type` beyond local/remote, `docker_image`, `docker_command`,
  `kubernetes_service`: not in `MCPServerInternal`; the runner only knows
  transport + url/command.
- `MCPServer.timeout_seconds` / `max_retries`: nexus-ai's `MCPServerConfig` has
  a `timeout_seconds` slot, but nucleus's `MCPServerInternal` does not forward
  either field — the web app now lets admins set them (the API accepts them),
  and they will take effect once nucleus forwards them.
- `Prompt.context_scope` (`['chat', 'doc']`): forwarded in `PromptInternal` but
  nothing in nexus-ai reads it.
- `Prompt.template_id` (DB `PromptTemplate`): no list endpoint is mounted
  (`list_prompt_templates` exists in services only; `/prompt-templates` serves
  files), so a client cannot offer a choice.
- `CompanyAIConfig` (`GET/PUT /ai-config/`): nucleus exposes it internally at
  `/companies/{id}/ai-config/`, but nexus-ai never calls it — it reads
  `EMBEDDING_MODEL` etc. from env (`apps/core/config.py`). Also note the public
  `PUT /ai-config/` has no permission check.

**Decision needed:** which of these the backend intends to honor (forward in the
internal payload / read in nexus-ai), and which should be dropped from the
schemas. The web app will follow once they are real.

---

## Migrations 0009/0010 stop on legacy dev data (orphan and duplicate soft-deleted MCP rows)

**Where:** `modules/nexus-nucleus/nucleus/migrations/0009_mcpserver_project_data.py`,
`0010_mcpserver_project_finalize.py`.

Seen migrating a long-lived dev database to the #99 schema (2026-09-06):

- 0009 refuses when any `MCPServer` has no project in the old M2M — on this
  database six inactive "Legacy MCP Test Flow" rows left behind by the old
  nested `/ai-models/{id}/mcp-servers/` path. Fixed by deleting exactly those
  six (after nulling the `AIAgent.mcp_server` FKs of the test agents that
  referenced them).
- 0010 then fails to build `uniq_mcp_server_name_per_project` because
  soft-deleted rows keep their names: five inactive "Search MCP Test Flow v2"
  copies in one project and an inactive "GitHub" beside the live one. Fixed by
  renaming the inactive duplicates `name_deleted_<8-char id>` — the same scheme
  `delete_persona()` uses to free a name.

**Decision needed:** whether 0009/0010 should do this themselves (skip or
mangle soft-deleted rows, drop project-less inactive rows) so a self-hoster's
upgrade does not stop with a traceback, and whether `delete_mcp_server_standalone`
should mangle the name on soft delete like `delete_persona` does.

---

## After upstream #101/#102: what the pydantic-ai runner does with a persona's composition

**Where:** `modules/nexus-ai/apps/implementations/agents/pydantic_ai_runner.py`,
`apps/managers/agentic_manager.py` (`NewImprovedAgenticManager`),
`apps/managers/prompt_builder.py` (`NewImprovedPromptBuilder`), `apps/routers/trigger.py`,
`apps/factories/agent.py`, `apps/managers/nucleus_client.py` (`resolve_persona`).

#101 ("Switched to pydantic AI for model response streaming") and #102 (50 ms delta
buffering) rewired the single-persona trigger path. The Centrifugo events nucleus
publishes keep their shape (`chat/services.py` is untouched), so the web app needs
no contract change — but several things the web app lets an admin configure do not
reach the model on that path. Verified against the merged code on 2026-09-07, with
each gap attributed to the PR that opened it (the pre-#101 runner at `a52cac4` is the
baseline):

Introduced by #101:

- **MCP servers are no longer mounted.** The old runner opened every
  `persona.mcp_servers` entry and raised `MCPReauthRequiredError` for one flagged
  `needs_reauth`; `PydanticAIRunner._resolve_capabilities` now returns
  `_DEFAULT_CAPABILITY_REGISTRY` (WebSearch, WebFetch, Shell, FileSystem, Thinking,
  Planning) for every persona and never references `persona.mcp_servers`. So the
  servers attached in the persona dialog do nothing, the OAuth reconnect prompt can
  no longer be triggered (`trigger.py` now imports `MCPReauthRequiredError` from
  `litellm_runner.py`, which `AgentFactory` never instantiates), and `supports_tools`
  gates nothing at runtime (nucleus still enforces it on attach).
- **Providers.** The old runner handed LiteLLM the model id and let it route;
  `_MODEL_REGISTRY` now resolves only `openai` and `anthropic`. A persona on a
  `google`, `ollama` or `openai_compatible` config raises `KeyError` in
  `_resolve_model`, surfaced as the generic `message_error` copy. The web app still
  offers the five providers nucleus accepts (`_reject_unknown_provider`).
- **Output directives.** The old manager resolved `job.output_type` (the
  `@chart`/`@table`… directive nucleus extracts from the message, else the
  classifier) and injected the registry's instruction text. `NewImprovedPromptBuilder`
  ignores `job.output_type` and appends the classifier's type *name* ("chart") as the
  "OUTPUT FORMAT INSTRUCTION". Rich output now depends on the model emitting markers
  unprompted. `NewImprovedAgenticManager` also omits `output_type` from `message_done`,
  so nucleus stores `"text"` beside a marker-derived `render_as` (e.g. `html`); the web
  app renders by `render_as`, so charts still frame (regression tests:
  `message-store.test.ts`, `message-render.test.tsx`).
- **Swarm hand-offs.** `AgenticSwarmManager` is unchanged: it still passes
  `PromptBuilder`'s `list[dict]` messages and the handoff/delegate/continue `tools`
  to `run_stream`, which the new runner types as pydantic-ai `ModelMessage`s and whose
  `tools` argument it never reads. The old runner merged `injected_tools` into the
  call; multi-persona hand-offs cannot be triggered by the model on this runner.
- **Errors.** Every runner exception becomes `message_error` with
  `error_code="sorry"`; nucleus maps anything but `mcp_reauth_required` to the
  generic copy, so users get no hint that, e.g., their provider is unsupported.
- **Tool activity is invisible.** The runner emits `tool_call_start` for the built-in
  tools, but nucleus's single-persona relay only handles `message_delta`/
  `message_done`/`message_error` (it never relayed tool events; now every persona has
  tools, so the silence is routine): the browser shows the in-bubble "Thinking…" cue,
  then the 90 s stall notice. `persist_internal_state` is consumed by the manager and
  its payload discarded (`internal_model_state` assigned, never used).
- **DECISIONS.md §19** ("DO NOT use pydantic-ai Agent for LLM calls. Use
  `FastMCPClient` + `litellm` directly.") is contradicted by the new runner, which
  builds `pydantic_ai.Agent` directly and adds `pydantic-ai[all,…]` +
  `pydantic-ai-harness` to the image.
- **Dev compose:** the new `web-app-dev` service `env_file`s
  `modules/neuralops-web-app/.env.local`; compose refuses to start the dev profile
  until that file exists (`cp .env.example .env.local` per the module README).

Already unread before #101 — a `resolve_persona` mapping gap left by #99:

- **Generation settings.** `nucleus_client.resolve_persona` reads `max_tokens` and
  `temperature` off the `model` sub-object, but since #99 nucleus sends them on the
  persona (`PersonaInternal.temperature/max_tokens/max_steps`), so the worker has
  used 4096 / 0.7 regardless of the persona dialog. `max_steps` and `advisor_model`
  are not mapped at all (`PersonaConfig` has no such fields), and neither is
  `api_base`, so `openai_compatible` could not have worked on the old runner either.
- **Persona output type.** `PromptInternal.output_type` (the dialog's "Output type"
  select, shown as "answers as …" on the card) is forwarded but not mapped either;
  the job's `output_type` comes only from the `@chart`-style directive in the
  message (`extract_output_type`), so the persona setting has no runtime effect.
  The persona dialog still edits all of these because nucleus stores and returns them.

**Decision needed:** which of these are transitional (the PR body says tool
configuration "needs to be passed to the backend" and `PersonaCapabilities` is marked
under construction) and which the web app should reflect now — in particular whether
to hide the three unsupported providers and the MCP/advisor/generation controls until
the runner reads them, or keep the nucleus contract as the source of truth (current
choice).
