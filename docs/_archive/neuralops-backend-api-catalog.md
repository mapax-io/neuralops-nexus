# NeuralOps Backend API Catalog

Compiled directly from source (`nexus-nucleus`, `nexus-ai`) on the `staging` branch — every router actually mounted in `core/urls.py` (nucleus) and `apps/main.py` (nexus-ai), with full request/response fields and the Django models behind each one. `workspace/members_api.py` and `workspace/team_api.py` exist on disk but are **not imported anywhere** — dead code, not a live API surface — so they're excluded below.

- **nexus-nucleus** (Django Ninja) — base path `/api/v1/` — staging: `http://192.168.1.90:8081/api/v1/`
- **nexus-ai** (FastAPI, internal only — never called by the frontend) — staging: `http://192.168.1.90:8002/`

Auth column: `Bearer` = Supabase JWT (`SupabaseBearer`, `Authorization: Bearer <token>`), `Internal Key` = `X-Internal-API-Key` (nucleus) / `X-Internal-Key` (nexus-ai) header, `None` = public/no auth.

---

## 0. Django models — quick reference

Every model lives under `nucleus/models/` (one Django app, `nucleus`, split across files by rough topic — the `db_table` prefix is the real domain grouping, not the filename). All inherit from one of the abstract bases in `base.py`: `BaseModel` (UUID pk + `created_at`/`updated_at` + soft-delete `is_active`/`deleted_at`), `TenantBaseModel` (adds `company` FK), `ProjectBaseModel` (adds `project` FK too), or the `*OperationModel` variants (same, plus Django `invite`/`remove`/`archive`/`join` permissions auto-created per model).

| File | Models | What they're for |
|---|---|---|
| `account.py` | `User` (custom `AbstractUser`, UUID pk, `user_type`: human\|persona), `Human` | Identity. Every human *and* every persona has a `User` row — personas via a "shadow user" (see `Persona.identity_user`). `Human` is the private profile (email, timezone, locale) for real people only. |
| `governance.py` | `Company`, `CompanyAccess` | `Company` = the single tenant this server serves (one server = one company, by design — see `STORY.md`). `CompanyAccess` is the user↔company membership + role (owner/admin/member/viewer). |
| `workspace.py` | `Project`, `Channel`, `ChatTopic`, `KnowledgeBase`, `KnowledgeFile`, `ChatMessage`, `ChatReadMarker`, `ChatReaction`, `ChatSession`, `ChatAttachment` | The actual workspace hierarchy: `Company → Project → Channel → ChatTopic → ChatMessage`. `ChatSession` backs `@session`. `KnowledgeBase`/`KnowledgeFile` are a broader (currently under-used) alternative to per-topic `ContextSource`. |
| `intelligence.py` | `CompanyAIConfig`, `AIModel`, `AIAgent`, `AIRequestLog`, `Persona`, `MCPServer` | The AI configuration layer — see §5 below. `Persona` is what appears in chat; it wraps exactly one `AIModel` (direct) or one `AIAgent` (model + MCP tools). |
| `context.py` | `ContextSource` | A file or web URL attached to a `ChatTopic` — the more actively-used, simpler counterpart to `KnowledgeBase`. |
| `prompt.py` | `PromptTemplate`, `Prompt` | `PromptTemplate` is a company-wide curated library; `Prompt` is the actual live system prompt attached 1:1 to a `Persona` (optionally derived from a template). |
| `scheduling.py` | `PersonaSchedule` | "Run this persona on a schedule in this topic" — the business-data half; timing math is delegated to `django_celery_beat`'s own `PeriodicTask`/`IntervalSchedule`/`CrontabSchedule`/`ClockedSchedule` models, one of which `PersonaSchedule.periodic_task` points at. |
| `extended.py` | `Invitation`, `ProjectMember`, `TopicParticipant`, `Upload`, `UploadPart`, `AgentRun`, `KnowledgeChunk`, `EmbeddingJob`, `VectorDocument`, `ProjectContext`, `TopicContext`, `AuditEvent`, `Notification`, `UserSession`, `ModelUsageLog`, `AgentApproval`, `SavedSearch`, `SearchLog` | A grab-bag file, not one domain — despite the shared filename these span governance (`Invitation`, `AuditEvent`, `Notification`), workspace (`ProjectMember`, `TopicParticipant`, `ProjectContext`, `TopicContext`), storage (`Upload`, `UploadPart`), intelligence (`AgentRun`, `KnowledgeChunk`, `EmbeddingJob`, `VectorDocument`, `ModelUsageLog`, `AgentApproval`), search (`SavedSearch`, `SearchLog`), and accounts (`UserSession`). Several of these (`AgentRun`, `AgentApproval`, `KnowledgeChunk`, `EmbeddingJob`, `VectorDocument`, `SavedSearch`, `SearchLog`) have **no API endpoints anywhere in the routers below** — modeled but not yet wired to anything callable. |

The permission system itself (`Role`, `Right`, `RoleRight`, `RoleAssignment`) lives in `authn/permissions/models.py`, re-exported through `authn/models.py` — see `DECISIONS.md` and `story/operation-permissions-story.md` for how that's designed.

---

## 1. AI/LLM model configuration

Separate from the Django models above — this is *which AI provider/model* actually answers a chat message, not a database table. Nothing is hardcoded; defaults live in `nexus-ai/apps/core/config.py` and are mirrored in the `CompanyAIConfig` Django model so both sides agree out of the box.

| Layer | Default | How it's chosen | Notes |
|---|---|---|---|
| **LLM (chat/agent replies)** | `anthropic/claude-haiku-4-5-20251001` via LiteLLM | `AIModel.model_id` (per model, set via `/ai-models/`) or `CompanyAIConfig.default_llm_model` (server-wide fallback) | Every provider LiteLLM supports works by just changing the prefix: `openai/gpt-4o`, `azure/gpt-4`, `ollama/llama3` (+ `api_base`/`OLLAMA_BASE_URL`), etc. `provider="local"` exists as a reserved value for a future direct ONNX/llama.cpp runtime — selecting it today raises `NotImplementedError`. |
| **Agent backend** | `pydantic_ai` (`AGENT_BACKEND` env var) | `AgentFactory.get()` in `nexus-ai/apps/factories/agent.py` | `langgraph` and `agno` are declared as valid switch cases but their runner files don't exist in this checkout — selecting either would fail at import. |
| **Embedding** | `fastembed` / `nomic-ai/nomic-embed-text-v1.5` (768-dim, local ONNX, no network or GPU) | `EMBEDDING_PROVIDER` env var / `CompanyAIConfig.embedding_provider` | Alternative: `litellm`, routing to any remote embedding endpoint via the same prefix format. |
| **Vector store** | `pgvector` (reuses nucleus's own Postgres) | `VECTOR_STORE` env var | `chroma` is still a valid switch case but `chromadb` was removed from `requirements.txt`; `qdrant` is declared but has no implementation file at all. |

**Heads up:** the main `readme.md`'s "Architecture at a glance" table still lists `chromadb` as *the* vector store — stale against the above (`pgvector` is the real default, matching `Fat-Docker/bootstrap.py`). Flagged, not fixed — say the word if you want it changed.

---

## 2. Authentication & Onboarding

Router: `authn/api.py`, mounted at `/auth/`. **Models:** `User`, `Human` (`account.py`), `Company`, `CompanyAccess`, `Invitation` (governance).

| Method & URL | Auth | Request | Response | What it does |
|---|---|---|---|---|
| `GET /api/v1/auth/config/` | None | — | `{server_url, server_version, nucleus_version, nexus_ai_version, nexus_transport_version}` | Public server info — frontend uses this to show your server's version before you even connect. |
| `POST /api/v1/auth/signin` | None | `{access_token}` | `{user: {id, email, username, is_new_user}, external_identity: {provider, provider_user_id, email, email_verified}}` | Verifies a Supabase access token, syncs/creates the local `User`. |
| `GET /api/v1/auth/verify/` | Bearer | — | `{ok, email, user_id, is_new_user, company_exists, is_owner, role?, company_name?, server_version?, ...}` | The real "connect to this server" call. Verifies the JWT, checks server access via `CompanyAccess`, **auto-accepts any pending `Invitation`** for this email. |
| `GET /api/v1/auth/invite-preview/?token=` | None | query: `token` | `{company_name, inviter_name, email, expires_at?}` | Public preview shown on the portal invite page before login — reads `Invitation`. |
| `POST /api/v1/auth/change-username/` | Bearer | `{new_name, topic_id}` | `{ok, display_name}` | Changes `User.display_name` (2–30 chars, `[a-zA-Z0-9_]`), posts a `ChatMessage` system message into the given topic announcing the change. |

## 3. Server Members

Router: `workspace/api.py` → `members_router`, mounted at `/members/`. **Models:** `CompanyAccess`, `Invitation`.

| Method & URL | Auth | Request | Response | What it does |
|---|---|---|---|---|
| `POST /api/v1/members/invite/` | Bearer + `nucleus.add_invitation` perm | `{email, role="member"}` | `{ok, message, email, role, expires_at?}` | Invite a new member to the server (not a specific project) — creates an `Invitation`. |
| `GET /api/v1/members/` | Bearer | — | `[{user_id, email, role, invited_by?, joined_at, avatar?}]` | List all `CompanyAccess` rows. |
| `DELETE /api/v1/members/{user_id}/` | Bearer + `nucleus.remove_invitation` perm | — | `{ok, message}` | Remove a member from the server entirely. |

## 4. Workspace — Projects, Channels, Topics, Team

Router: `workspace/api.py` → `router`, mounted at `/projects/`. **Models:** `Project`, `Channel`, `ChatTopic` (`workspace.py`), `ProjectMember`, `TopicParticipant` (`extended.py`), `Persona` (for team listing).

Archiving replaces the old irreversible delete: it's a reversible soft-delete (`is_active=False`, inherited from `BaseModel`). `project.archive` / `channel.archive` / `topic.archive` are all reachable by that project's own Project Admin, not just a company-wide Owner/Admin. Every list endpoint below accepts `?include_archived=true`.

| Method & URL | Auth | Request | Response | What it does |
|---|---|---|---|---|
| `GET /api/v1/projects/` | Bearer | query: `include_archived=false` | `[ProjectOut]` | List `Project` rows. `ProjectOut = {id, name, slug, description?, channels: [{id, name, slug, description?}]}`. |
| `POST /api/v1/projects/` | Bearer + `project.create` | `{name, description?}` | `ProjectOut` | Create a `Project`. |
| `GET /api/v1/projects/{project_id}/` | Bearer | — | `ProjectOut` | Get one project. |
| `DELETE /api/v1/projects/{project_id}/` | Bearer + `project.archive` | — | `{ok, message}` | Archive (soft-delete) a project. |
| `GET /api/v1/projects/{project_id}/channels/` | Bearer | query: `include_archived=false` | `[{id, name, slug, description?}]` | List `Channel` rows. |
| `POST /api/v1/projects/{project_id}/channels/` | Bearer + `channel.create` | `{name, description?}` | `{id, name, slug, description?}` | Create a `Channel`. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/archive/` | Bearer + `channel.archive` | — | `{ok, message}` | Archive a channel. |
| `GET /api/v1/projects/{project_id}/channels/{channel_id}/topics/` | Bearer | query: `include_archived=false` | `[{id, title, slug, channel_id, project_id, has_unread}]` | List `ChatTopic` rows, with per-user unread flag from `ChatReadMarker`. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/` | Bearer + `topic.create` | `{title}` | `{id, title, slug, channel_id, project_id}` | Create a `ChatTopic` (this is the actual conversation thread). |
| `PATCH /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/` | Bearer + `topic.update` | `{title}` | same as above | Rename a topic. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/archive/` | Bearer + `topic.archive` | — | `{ok, message}` | Archive a topic. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/read/` | Bearer + `topic.mark_read` | — | `{ok}` | Upsert a `ChatReadMarker` for the current user. |
| `GET /api/v1/projects/{project_id}/team/` | Bearer | — | `[{id, user_id, name, email, role, member_type, avatar?}]` | List a project's team (`ProjectMember` rows, humans + personas). |
| `POST /api/v1/projects/{project_id}/team/` | Bearer | `{user_id, role="member"}` | `TeamMemberOut` | Add an existing user/persona to a project — creates a `ProjectMember`. |
| `POST /api/v1/projects/{project_id}/team/invite/` | Bearer | `{email?, persona_name?, scope="topic", topic_id?, role="member"}` | `{ok, is_new_user, email, scope, message, server_url?, invite_url?}` | The `/invite` slash command — either a human email (`Invitation`) or an `@PersonaName` (`ProjectMember`). |
| `GET /api/v1/projects/{project_id}/team/available-users/?search=` | Bearer | query: `search?` | `[{user_id, name, email, avatar?}]` | Users not yet on the project (add-member picker). |
| `GET /api/v1/projects/{project_id}/team/available-personas/` | Bearer | — | `[{persona_id, user_id, name, source_type, avatar?}]` | Personas not yet on the project. |
| `DELETE /api/v1/projects/{project_id}/team/{user_id}/` | Bearer | — | — | Remove a `ProjectMember` (not from the server). |
| `DELETE /api/v1/projects/server/members/{user_id}/` | Bearer | — | — | Owner action — deactivates `CompanyAccess` + every `ProjectMember` for this user. Cannot remove yourself or the owner. |

## 5. Chat Messaging

Router: `chat/api.py`, also mounted at `/projects/`. **Models:** `ChatMessage`, `ChatSession` (`workspace.py`), reads `Persona` (`intelligence.py`) to resolve `@mentions`.

| Method & URL | Auth | Request | Response | What it does |
|---|---|---|---|---|
| `GET /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/` | Bearer | query: `limit=100` (max 200), `before_sequence?` | `[MessageOut]` | Load `ChatMessage` history, oldest first. `MessageOut = {id, type, message_type?, content, render_as, output_type, sender_name?, sender_id?, sender_avatar?, sender_type, persona_id?, sequence, created_at}`. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/typing/` | Bearer | — | `{ok}` | Fire-and-forget typing indicator broadcast over Centrifugo — no DB write. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/` | Bearer | `{content}` (1–4000 chars, validated/stripped) | `{message: MessageOut, channel}` | The core send path: saves a `ChatMessage`, fires an async embed to nexus-ai, publishes to Centrifugo, resolves `@mentions` → `Persona` rows, opens/closes a `ChatSession` as directed, and routes to AI per the session priority rules (`@session close` / `@mentions+@session` / `@mentions` / active session / plain message) — see the docstring at the top of `chat/api.py`. Returns immediately; the AI reply streams back over Centrifugo. |

## 6. AI Intelligence — Models, MCP Servers, Agents, Personas

Router: `intelligence/api.py`, mounted at the API root (`/`). **Models:** `AIModel`, `AIAgent`, `MCPServer`, `Persona`, `AIRequestLog`, `CompanyAIConfig` (`intelligence.py`), `PromptTemplate`, `Prompt` (`prompt.py`). All endpoints require Bearer auth and are company-scoped; specific rights noted per endpoint.

**AI Models** — backs `AIModel`. `AIModelIn = {name, provider="litellm"|"local", model_id, api_key?, api_base?, secret_ref?, description?, licence_accepted=false, temperature=0.7, max_tokens=4096, context_window=8192, supports_tools=false, supports_streaming=true, supports_vision=false, supports_audio=false, config={}}`. `licence_accepted` must be `true` to create; `api_key` is Fernet-encrypted into `api_key_encrypted`, never returned (`AIModelOut` exposes `has_api_key: bool` instead).

| Method & URL | Rights | Request | Response |
|---|---|---|---|
| `GET /api/v1/ai-models/` | — | — | `[AIModelOut]` |
| `POST /api/v1/ai-models/` | `ai_model.create` | `AIModelIn` | `AIModelOut` |
| `DELETE /api/v1/ai-models/{model_id}/` | `ai_model.delete` | — | 204 |
| `POST /api/v1/projects/{project_id}/ai-models/{model_id}/attach/` | `ai_model.attach` (project-scope) | — | `{ok}` |
| `DELETE /api/v1/projects/{project_id}/ai-models/{model_id}/attach/` | `ai_model.attach` | — | `{ok}` |

A newly-created `AIModel` is invisible to every project until explicitly attached to `AIModel.projects` (M2M) — company-wide `ai_model.list` holders see everything regardless.

**MCP Servers** — backs `MCPServer`. `MCPServerIn = {name, description?, project_id, server_type="remote", transport="http", url?, command?, docker_image?, docker_command?, kubernetes_service?, config={}, secret_ref?, timeout_seconds=60, max_retries=3, is_first_party=false, embed_output=false}`.

| Method & URL | Rights | Request | Response |
|---|---|---|---|
| `GET /api/v1/mcp-servers/` | `mcp_server.list` (company, via row-visibility) | — | `[MCPServerOut]` |
| `POST /api/v1/mcp-servers/` | `mcp_server.create` (project) | `MCPServerIn` | `MCPServerOut` |
| `PATCH /api/v1/mcp-servers/{server_id}/` | `mcp_server.update` | `MCPServerPatchIn` | `MCPServerOut` |
| `DELETE /api/v1/mcp-servers/{server_id}/` | `mcp_server.delete` | — | 204 |
| `GET /api/v1/ai-models/{model_id}/mcp-servers/` (legacy, nested) | `mcp_server.list` | — | `[MCPServerOut]` |
| `POST /api/v1/ai-models/{model_id}/mcp-servers/` (legacy) | `mcp_server.create` | `MCPServerIn` | `MCPServerOut` |
| `DELETE /api/v1/ai-models/{model_id}/mcp-servers/{server_id}/` (legacy) | `mcp_server.delete` | — | 204 |

No attach/detach — `MCPServer.projects` (M2M) is restricted to exactly one entry by application code at creation, unlike `AIModel`.

**AI Agents** — backs `AIAgent`, pairs a model + optional MCP server. `AIAgentIn = {name, description?, project_id, model_id, mcp_server_id?, agent_type="internal", safety_mode=true, max_steps=5}`.

| Method & URL | Rights | Request | Response |
|---|---|---|---|
| `GET /api/v1/agents/` | — | — | `[AIAgentOut]` |
| `POST /api/v1/agents/` | `agent.create` (project) | `AIAgentIn` | `AIAgentOut` |
| `PATCH /api/v1/agents/{agent_id}/` | `agent.update` | `AIAgentPatchIn` | `AIAgentOut` |
| `DELETE /api/v1/agents/{agent_id}/` | `agent.delete` | — | 204 |

**Personas** — backs `Persona` + its 1:1 `Prompt`. `PersonaIn = {name, description?, project_id, source_type: "model"|"agent", model_id?, agent_id?, prompt: {system_prompt, output_type="text", context_scope?, template_id?}}`. DB `CheckConstraint` enforces exactly one of `model`/`agent` set, matching `source_type`.

| Method & URL | Rights | Request | Response |
|---|---|---|---|
| `GET /api/v1/personas/?project_id=` | — | query: `project_id` (required) | `[PersonaOut]` |
| `POST /api/v1/personas/` | `persona.create` | `PersonaIn` | `PersonaOut` |
| `PATCH /api/v1/personas/{persona_id}/` | `persona.update` | `PersonaPatchIn {name?, description?, prompt?}` | `PersonaOut` |
| `DELETE /api/v1/personas/{persona_id}/` | `persona.delete` | — | 204 |

**Prompt templates, AI config, logs, output types**

| Method & URL | Request | Response |
|---|---|---|
| `GET /api/v1/prompt-templates` | — | `{prompts: {base64_id: relative_path}}` — every file under `intelligence/prompts/` (this is a filesystem directory read, **not** the `PromptTemplate` model, despite the name) |
| `GET /api/v1/prompt-templates/{id}` | path id = base64-encoded relative path | `{content}` |
| `GET /api/v1/ai-config/` | — | `{embedding_provider, embedding_model, embedding_base_url, default_llm_model}` — reads `CompanyAIConfig`, see §1 for defaults |
| `PUT /api/v1/ai-config/` | same 4 fields | same shape — updates `CompanyAIConfig` |
| `GET /api/v1/ai-request-logs/` | — | `[AIRequestLogOut]` — last 200 `AIRequestLog` rows, newest first, full prompt/response/tokens/latency |
| `GET /api/v1/output-types/` | — | Static list of 8 output types: `text, code, chart, table, diagram, form, html, terminal` — not a DB table, matches `nexus-ai/apps/output_types/types.py` |

## 7. Context Sources & Context Panel

Router: `context/api.py`, mounted at `/projects/`. **Models:** `ContextSource` (`context.py`).

| Method & URL | Auth | Request | Response | What it does |
|---|---|---|---|---|
| `GET /api/v1/projects/context-sources/directives/` | Bearer | — | `[dict]` | Proxies to nexus-ai's `GET /api/v1/directives/` — all registered `@directive`s with help text. |
| `GET /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/` | Bearer | — | `[ContextSourceOut]` | List `ContextSource` rows for a topic. |
| `POST /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/file/` | Bearer | multipart file upload | 201 `ContextSourceOut` | Creates a `ContextSource(type=file)`, embedded via nexus-ai. Posts a `ChatMessage` system message either way. |
| `POST /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/web/` | Bearer | `{url, name?}` | 201 `ContextSourceOut` | Creates a `ContextSource(type=web)`. |
| `DELETE /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/{source_id}/` | Bearer | — | `{ok}` / 404 | Deletes the `ContextSource`, posts a system message. |
| `GET /api/v1/projects/{project_id}/topics/{topic_id}/context-panel/` | Bearer | — | `[dict]` | Full context panel tree (Files, Chat History, ...) — generic, provider-registry driven. |
| `DELETE /api/v1/projects/{project_id}/topics/{topic_id}/context-panel/items/` | Bearer | `{items: [{directive, id}]}` | `{ok, deleted: [id]}` | Bulk-remove across providers — `file` deletes a `ContextSource`, `chat` sets `ChatMessage.is_deleted_from_context=True`. |

## 8. Scheduling — Automated Personas

Router: `scheduling/api.py`, mounted at `/projects/`. **Models:** `PersonaSchedule` (`scheduling.py`), plus `django_celery_beat`'s own `PeriodicTask`/`IntervalSchedule`/`CrontabSchedule`/`ClockedSchedule` (third-party app, not in `nucleus/models/`).

`ScheduleCreateIn = {persona_id, query_text, label="", schedule_kind: "interval"|"crontab"|"clocked", interval_every?, interval_period?, crontab_minute="0", crontab_hour="*", crontab_day_of_week="*", crontab_day_of_month="*", crontab_month_of_year="*", clocked_time?, timezone="UTC", trigger_visible=true, catch_up_missed=true}`.

| Method & URL | Rights | Request | Response | What it does |
|---|---|---|---|---|
| `GET /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/` | (topic visibility) | — | `[ScheduleOut]` | List `PersonaSchedule` rows for a topic. |
| `POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/` | `schedule.create` | `ScheduleCreateIn` | `ScheduleOut` | Creates a `PersonaSchedule` + its paired `PeriodicTask`; announces it in-chat. |
| `PATCH .../schedules/{schedule_id}/` | creator, or `schedule.manage` | `ScheduleUpdateIn {query_text?, label?, is_paused?}` | `ScheduleOut` | Pause/resume/edit; keeps `PeriodicTask.enabled` in sync; announces pause/resume in-chat. |
| `DELETE .../schedules/{schedule_id}/` | creator, or `schedule.manage` | — | `{ok}` | Deletes the schedule; announces in-chat. |

`ScheduleOut` includes `schedule_summary` (human-readable, e.g. "Daily at 09:00 UTC"), `last_run_at`, `last_status`, `last_error`.

## 9. Internal API — nexus-ai → nexus-nucleus only

Router: `internal/api.py`, mounted at `/internal/`. Auth is `X-Internal-API-Key` header (`INTERNAL_API_KEY` env var) — **never** exposed to the frontend. This is how nexus-ai reads every model above that it needs to actually run a persona.

| Method & URL | Response | What it does |
|---|---|---|
| `GET /api/v1/internal/personas/{persona_id}/` | `PersonaInternal {id, name, source_type, prompt: {...}, model?: ModelInternal, mcp_servers: [MCPServerInternal]}` | Reads `Persona` + `Prompt` + `AIModel`/`AIAgent` + `MCPServer` — **includes the decrypted `AIModel.api_key`** and decrypted `MCPServer` secrets. Only ever sent over the internal network. |
| `GET /api/v1/internal/topics/{topic_id}/contexts/` | `[{id, type: "doc"\|"code", label, collection_id}]` | Reads `TopicContext` for building the AI prompt. |
| `POST /api/v1/internal/ai-request-logs/` | 201 `{ok}` | Writes an `AIRequestLog` row after every model completion. |
| `GET /api/v1/internal/topics/{topic_id}/history/?limit=20&exclude_message_id=` | `[HistoryMessageInternal {...}]` | Reads recent `ChatMessage` rows, oldest-excluded-message dropped so the triggering message isn't duplicated. |
| `GET /api/v1/internal/companies/{company_id}/ai-config/` | `AIConfigInternal {embedding_provider, embedding_model, embedding_base_url, default_llm_model}` | Reads `CompanyAIConfig` — nexus-ai fetches this itself rather than trusting a value nucleus pushes. |

## 10. nexus-ai — the AI worker's own HTTP surface

FastAPI app (`apps/main.py`), base path `/api/v1/`, auth is `X-Internal-Key` header — this service is **never** called directly by the frontend, only by nucleus, and has no Django models of its own (it's stateless — everything it needs comes from §9). Its entire HTTP surface is two routers:

**Embed** (`apps/routers/embed.py`)

| Method & URL | Request | Response | What it does |
|---|---|---|---|
| `GET /api/v1/directives/` | — | `[dict]` | All registered `@directive`s (proxied by nucleus's `context/api.py`). |
| `POST /api/v1/embed/` | `EmbedRequest {source_id, type: "file"\|"code", label, content, language?, topic_id?, channel_id?, project_id?, company_id?}` | `EmbedResponse {source_id, collection_id, chunks_count}` | Chunk + embed + store a document/code context source (result written back to `ContextSource.collection_id` by nucleus). |
| `DELETE /api/v1/embed/context-source/{collection_id}/` | — | `{ok}` | Delete all vectors for a context-source collection. |
| `DELETE /api/v1/embed/message/{message_id}/?company_id=` | — | `{ok}` | Delete a single chat-message vector (called when a `ChatMessage` is excluded from context). |
| `POST /api/v1/embed/message/` | `MessageEmbedRequest {message_id, company_id, sequence, topic_id, channel_id, project_id, sender_id, sender_name, sender_type, content, created_at}` | `MessageEmbedResponse {message_id, collection, embedding_model, ok}` | Embed a `ChatMessage` into the company's chat collection (fired fire-and-forget after every `send_message`). |

**Trigger** (`apps/routers/trigger.py`)

| Method & URL | Request | Response | What it does |
|---|---|---|---|
| `POST /api/v1/trigger/` | `TriggerJob {job_id, msg_id, persona_id, topic_id, user_message_id, message, context_sources: [ContextSourceRef], output_type="auto"}` | SSE stream of `AgentEvent` (`text/event-stream`) | The actual AI call. `TriggerJob` is deliberately minimal — persona config and history are resolved server-side from `persona_id`/`topic_id` via the Internal API (§9), not pushed by nucleus. Streams `message_start` → `message_delta`(×N) → `message_done` (or `message_error`). `message_done` carries the resolved `output_type`/`render_as` and, for html/form/terminal renders, an `embed_description` extracted from an `<<<EMBED>>>...<<<END_EMBED>>>` block in the model's own output. |

---

> **Branch notice:** compiled against `dev`/`staging` — verify against source if `main`/`master` has diverged.
