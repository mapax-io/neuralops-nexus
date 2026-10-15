# NeuralOps Nexus — the API reference

**Document version: 1.0 (2026-10-15, at the close of Step 7).** Compiled by
reading every live router, not from memory.

| Version | Date | What changed |
|---|---|---|
| 1.0 | 2026-10-15 | First full reference — every nucleus + engine endpoint |

**The rule:** an endpoint added, changed or removed lands here in the same
change, with a version bump.

---

## 0. Calling it (Postman and friends)

**Base URLs (dev stack):** nucleus `http://<server>:8000/api/v1/`
(behind nginx in production), engine `http://nexus-ai:8001/api/v1/`
(container-to-container only).

**Live, always-current schemas — import these into Postman instead of typing
paths by hand:**
- Nucleus (django-ninja): `GET /api/v1/openapi.json` · browsable docs at
  `GET /api/v1/docs`
- Engine (FastAPI): `GET /openapi.json` · docs at `/docs` (internal network
  only)

**The four auth styles:**

| Style | Header | Used by |
|---|---|---|
| User token | `Authorization: Bearer <token>` — a Supabase JWT, OR a local HS256 token from `/auth/local/signin/` (the server picks the check by the token's alg header) | every user-facing endpoint |
| Gateway token | `Authorization: Bearer nxg_…` | `POST /api/v1/mcp/` only |
| Nucleus-internal key | `X-Internal-API-Key: <INTERNAL_API_KEY>` | `/api/v1/internal/*` — engine→nucleus. **nginx answers 403 for /internal/ from outside**; reachable only on the Docker network |
| Engine key | `X-Internal-Key: <INTERNAL_API_KEY>` | every engine endpoint — nucleus→engine. (Note the two header NAMES differ — historical, kept for 0.8.0 compatibility.) The gateway's inside road also uses `X-Internal-Key` + `X-NeuralOps-User: <user_id>` |

Errors are `{"detail": "<plain words>"}` with the usual codes; the detail is
written to be shown verbatim to a person.

---

## 1. Public — no auth at all

| Method + path | What it does |
|---|---|
| GET `/auth/config/` | Server URL + per-module versions (frontend's pre-connect peek) |
| POST `/auth/signin` *(no trailing slash)* | Supabase access token → session user payload; 401 bad token |
| GET `/auth/invite-preview/?token=` | Invite details for the portal invite page; 404 used/invalid, 410 expired |
| GET `/auth/setup/status/` | `{needs_owner, local_login_enabled, portal_url}` — fresh-install check |
| POST `/auth/setup/start/` | Hands out the claim code `{code, request_id, portal_url, expires_in}`; 409 already owned; 502 dead portal (names create_owner) |
| POST `/auth/setup/poll/` `{request_id, workspace_name?}` | `{status: pending}` or `{status: claimed, email, workspace, access_token}`; first VERIFIED claim wins (second → 409) |
| POST `/auth/local/signin/` `{email, password}` | Offline login → `{access_token, token_type, expires_hours, user}`; 401 one message for every cause; 403 switched off; 429 after 10 tries/5min |
| POST `/hooks/{token}/` `{text, data?}` | Inbound hook (W12): the hook's persona answers in its topic AS the hook's creator. 404 flat for unknown tokens; 409/413/429 vocabulary; `Retry-After` on 429 |
| GET `/mcp-servers/oauth/callback/?code&state` | The OAuth bounce target — verifies the signed state, exchanges the code (PKCE), stores tokens, answers a self-closing postMessage page |
| GET `/media/<path>` | Avatars/uploads, served always (not only under DEBUG) |

GET `/auth/verify/` takes a Bearer Supabase token but no prior session: it
verifies, auto-accepts a pending invitation, 403 if not allowed on this server.

---

## 2. User API (Bearer token) — nucleus `/api/v1/`

### Auth / me / roles
| Method + path | Right | What |
|---|---|---|
| POST `/auth/change-username/` `{new_name, topic_id}` | signed in | Rename self; announces in the topic; 409 taken |
| POST `/auth/local/set-password/` `{password}` | signed in | Your own offline password (Django validators → 400) |
| POST `/auth/local/reset-password/` `{user_id, password}` | company.local_password | Reset someone else's; personas refused |
| GET `/me/permissions/` | signed in | Every right the caller holds, resolved per object — the frontend gates controls on this |
| POST / DELETE `/me/avatar/` | signed in | Upload (re-encoded server-side) / clear profile photo |
| GET `/roles/` | role.update (Owner) | The rights registry + what each role grants |
| PATCH `/roles/{role_id}/rights/` `{rights: [...]}` | role.update | Replace a role's whole right set — effective immediately for every holder |

### Workspace `/projects/`
| Method + path | Right | What |
|---|---|---|
| GET `/projects/?include_archived=` | row visibility | The projects this person can see |
| POST `/projects/` `{name, description?}` | project.create | Create + provision (folder, capabilities row, 4 routines, configure topic, template chain) |
| GET / PATCH / DELETE `/projects/{id}/` | view / project.update / project.archive | Read (with brief) / edit brief+description / archive |
| GET / PUT `/projects/{id}/embedder/` | view / project.embedder | The embedder spec; PUT `{embedder: {provider, model_id, api_base?, api_key?} | null}` locks + rebuilds; 409 while building |
| GET `/projects/{id}/files/?path=` | project road | Folder entries, folders first |
| GET `/projects/{id}/files/content/?path=[&as=html]` | project road | Download (streamed) or sandboxed HTML view; 400/404/409/413/415 vocabulary |
| POST `/projects/{id}/terminal/session/` | project.terminal | 60s ticket for the worker's shell WebSocket |
| POST `/projects/{id}/browser/session/` `{width, height, url?}` | project.browser | Ticket for the server-side Chromium |
| GET `/projects/{id}/deliverables/?latest=&title=` + GET/POST/DELETE one | view / deliverable.manage | Kept outputs; same title = new version |
| GET / POST `/projects/{id}/channels/` + POST `…/channels/{cid}/archive/` | view / channel.create / channel.archive | Channels |
| GET / POST `/projects/{id}/channels/{cid}/topics/` | view / topic.create | Topics (list carries unread counts) |
| PATCH / `…archive/` / `…read/` on a topic | topic.update / topic.archive / topic.mark_read | Rename / archive / mark read |
| GET `/projects/{id}/team/` + POST (add) + POST `invite/` + GET `available-users/`/`available-personas/` + DELETE `{user_id}/` | view / project.archive for managing | The project team |
| DELETE `/projects/server/members/{user_id}/` | company.remove_member | Remove from the whole server |

### Members `/members/`
POST `/members/invite/` (grants: whole project or topic-scoped), GET `/members/`,
GET/PUT `/members/{user_id}/access/` (company.invite_member), DELETE `/members/{user_id}/`.

### Chat `/projects/{pid}/channels/{cid}/topics/{tid}/…`
| Method + path | What |
|---|---|
| GET `messages/?limit=&before_sequence=` | History, oldest first, paged backwards |
| POST `messages/` `{content}` | Save + broadcast + embed; parses @mentions/@session//routine; triggers personas (right: persona.mention, refused list in the answer; "reindexing" refusal while rebuilding) |
| POST `typing/` | Fire-and-forget typing indicator |
| POST `messages/{mid}/preflight/` `{decision, note?}` | Approve/deny a gated persona's PLAN (persona.approve_run) |
| POST `messages/{mid}/approvals/{call_id}/` `{decision, always?}` | Allow/deny one held tool call; all decided → the run resumes |
| POST `messages/{mid}/questions/{call_id}/` `{text}` | Answer a paused persona's question |
| POST `messages/{mid}/stop/` | Stop a streaming reply (the caller's to stop) |
| POST `messages/{mid}/nudge/` `{text}` | Add to a running reply; leftovers post after it ends |
| GET `usage/` | The topic's token/cost totals (visible to whoever sees the topic; "estimated" label) |

**Search (not under a project):** GET `/search/messages/?q=&limit=` — semantic
ranking through the engine, filtered to what the caller may see, literal
fallback.

### Context `/projects/{pid}/topics/{tid}/…`
GET `context-sources/` · POST `context-sources/file/` (multipart) · POST
`context-sources/web/` `{url, name}` · DELETE `context-sources/{sid}/` ·
GET `context-panel/` (the grouped tree) · DELETE `context-panel/items/`
`{items: [{directive, id}]}`.

### Intelligence (mounted at root)
| Method + path | Right | What |
|---|---|---|
| GET / POST `/model-configs/` + PATCH / DELETE `/model-configs/{id}/` | model_config.list/create/update/delete | Models; key write-only; delete refused while personas use it |
| POST `/model-configs/check/` | create or update | Verify with the provider through the engine; categorised plain-words reasons |
| POST / DELETE `/model-configs/{id}/utility/` | model_config.update | Set/clear the server's utility model |
| POST / DELETE `/projects/{pid}/model-configs/{cid}/attach/` | model_config.attach | Project visibility of a config |
| GET / POST `/mcp-servers/` + PATCH / DELETE `/mcp-servers/{id}/` | mcp_server.list/create/update/delete | Tool servers; tool list fetched best-effort on create/patch |
| POST `/mcp-servers/{id}/tools/refresh/` | mcp_server.update | Re-dial through the engine; 200 `{tools}` or 502 with the dial's reason verbatim |
| GET `/mcp-servers/{id}/oauth/authorize/?frontend_origin=` | mcp_server.update | The Connect click: auto-registers (dynamic registration) when nothing pasted; → `{authorize_url}` (PKCE) or 502 with what to do |
| GET / POST `/personas/?project_id=` + PATCH / DELETE `/personas/{id}/` | persona.list/create/update/delete | Personas (model, advisor, fallbacks, MCP servers, tool_levels, gate) |
| GET / POST `/projects/{pid}/routines/` + PATCH / DELETE `…/{rid}/` | topic.list / routine.manage | Team `/` methods; built-ins editable, never deletable (409) |
| GET `/projects/{pid}/recall/?kind=&q=` + PATCH / DELETE `…/{eid}/` | topic.list / recall.manage | What personas recorded |
| GET / PUT `/ai-config/` | — / model_config.update | Embedding provider + default/utility models |
| GET `/ai-request-logs/` | signed in | Last 200 engine call logs |
| GET `/mcp-catalog/` · `/persona-catalog/` · `/output-types/` | mcp_server.list / persona.list / signed in | The hand-kept catalogs + output type list |
| GET `/prompt-templates` + GET `/prompt-templates/{id}` | signed in | Bundled prompt files |
| GET `/projects/{pid}/usage/` | usage.view_project | Project rollup (per persona, per model) |
| GET `/usage/company/` | usage.view_company | The whole install's bill (full detail stays local) |

### Scheduling `/projects/…`
| Method + path | Right | What |
|---|---|---|
| GET / POST `…/topics/{tid}/schedules/` + PATCH / DELETE `…/{sid}/` | schedule.create (+persona.mention; runbook.run for chain schedules) / creator-or-schedule.manage | Timed fires; persona XOR runbook; checkpoint chains refused (400 "run it by hand") |
| GET / POST `/{pid}/runbooks/` + PATCH / DELETE `…/{rid}/` | topic.list / runbook.manage | Chains: steps (persona|checkpoint), supervisor_id, redo_limit, clear_supervisor; has_checkpoint in the answer |
| POST `/{pid}/runbooks/{rid}/run/` `{topic_id | channel_id, title?}` | runbook.run + persona.mention | Start now (step-less template → 400 "add its steps first") |
| GET `/{pid}/runbooks/runs/?runbook_id=&topic_id=&active=` | topic.list | Run history/live (status incl. `waiting`, step_results, checkpoint) |
| POST `/{pid}/runbooks/runs/{run_id}/checkpoint/` `{answer}` | starter or project.update | Answer a waiting chain; 403/409 vocabulary |
| POST `/{pid}/runbooks/runs/{run_id}/stop/` | runbook.run | Stop (works while waiting too) |
| GET / POST `…/topics/{tid}/hooks/` + PATCH / DELETE | hook.manage (+persona.mention to create) | Define inbound hooks; the fire URL is public (§1) |

---

## 3. The MCP gateway (Step 6)

**POST `/api/v1/mcp/`** — stateless MCP streamable-HTTP JSON-RPC. Auth:
`Bearer nxg_…` OR `X-Internal-Key` + `X-NeuralOps-User`. Methods:
`initialize`, `tools/list`, `tools/call`, `ping`; notifications → 202; batch
refused; GET → 405; `GATEWAY_ENABLED=false` → 403. The eight tools (each runs
AS the token's person, with their rights): `list_projects`, `list_topics`,
`post_message`, `ask_persona` (waits ≤180s then "still working"),
`search_memory`, `list_chains`, `run_chain`, `chain_status`.

**Tokens:** POST `/gateway/tokens/` `{name, user_id?}` → the token value
ONCE (right: gateway.token — the four roles; company-level may mint FOR
someone) · GET `/gateway/tokens/` (own; company-level sees all) · DELETE
`/gateway/tokens/{id}/` (revoke).

Postman tip: body `{"jsonrpc":"2.0","id":1,"method":"tools/call",
"params":{"name":"list_projects","arguments":{}}}`.

---

## 4. Internal API — engine → nucleus (`/api/v1/internal/`, X-Internal-API-Key)

nginx 403s this prefix from outside; call it only on the Docker network.

| Method + path | What |
|---|---|
| GET `/internal/personas/{id}/` | The WHOLE persona config, decrypted: prompt, model(+key), advisor/router(resolved)/deep seats, flags, mcp_servers (secrets; needs_reauth), capabilities, tool_levels, fallbacks, project brief, utility model |
| GET `/internal/routines/{id}/` | One routine ready to apply (instructions, narrowing, model+key) |
| POST `/internal/messages/{mid}/pause/` | The engine parks a run BEFORE message_paused: `{job_id, topic_id, persona_id, state, catalog_hash, pending[], role}` |
| GET `/internal/messages/{mid}/nudges/` | Take-once nudges for a running reply |
| GET `/internal/topics/{tid}/history/?limit=&exclude_message_id=` | Raw history rows (with status; engine filters) |
| GET `/internal/topics/{tid}/contexts/` | Active context sources |
| GET `/internal/companies/{cid}/ai-config/` | Embedding provider/model, default LLM |
| POST `/internal/recall/` | The remember pass: `{project_id, persona_id, message_id?, entries[]}` → created/skipped |
| POST `/internal/usage/` | The usage batch → priced rows + live `usage_totals` push |
| POST `/internal/ai-request-logs/` | One log row per model completion |

---

## 5. Engine API — nucleus → engine (X-Internal-Key)

| Method + path | What |
|---|---|
| POST `/api/v1/trigger/` | THE run: TriggerJob in (see CHANGE-PROMPT §5 for every field; a resume is the same job + `resume` block) → SSE stream of AgentEvents |
| POST `/api/v1/models/check/` | `{provider, model_id, api_key?, api_base?}` → ok/reason/latency |
| POST `/api/v1/embed/` | Ingest one context source (chunks) → `{collection_id, chunks_count}`; `type:"code"` refused |
| DELETE `/api/v1/embed/context-source/{collection_id}/` | Drop a source ("{project_id}:{source_id}") |
| POST `/api/v1/embed/message/` | Embed one chat message (used_tools metadata) |
| DELETE `/api/v1/embed/message/{mid}/?company_id=&project_id=` | Drop a message's vector AND its tool memory |
| POST `/api/v1/embed/recall/` + DELETE `/api/v1/embed/recall/{eid}/?company_id=` | Recall vectors (same id upserts) |
| POST `/api/v1/embed/reindex/` | Rebuild a project with a new embedder → 202 building / 409 busy |
| GET `/api/v1/embed/reindex/{pid}/status/` | building / active / failed |
| POST `/api/v1/search/messages/` | `{company_id, query, top_k, project_ids}` → `{hits:[{message_id, score}]}` — ranks only, NUCLEUS filters visibility |
| POST `/api/v1/mcp/tools/` | `{url, bearer_token?}` → `{tools:[{name, one_line, read_only}]}`; any dial failure = 502 + reason |

Embed/vector endpoints answer 503 when `NEXUS_VECTOR_DB_URL` is unset.
