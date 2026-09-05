# NeuralOps — Decisions & Design Rules

This file must be read at the start of every session before touching any code.
It records product decisions, architectural constraints, and things that have
been explicitly decided (and must NOT be changed without the owner's approval).

---

## 1. Personas — Scope & Team Membership

**Decision:** A persona belongs to exactly ONE project team.
Personas are NOT global. They must be explicitly added to a project either via:
- The "Add to Team → Add Persona" dialog
- `/invite @PersonaName` slash command inside a chat topic (adds to that project)

They do NOT auto-join all projects on creation, and new projects do NOT
auto-receive all personas.

**Why decided:** Owner explicitly said:
> "no this is separate project, remember that Personas, until to be called
> in another group, will be tied to one group"

**Files involved:**
- `intelligence/services.py` → `create_persona()` — does NOT add to any project
- `workspace/services.py` → `create_project()` — does NOT add any personas
- `workspace/api.py` → `POST /{project_id}/team/` — manual add only
- `workspace/services.py` → `invite_to_project()` — handles `persona_name` arg

---

## 2. Personas — Shadow User Pattern

Each persona gets a Django `User` record with `user_type="persona"` called a
"shadow user". The `Persona` model has a OneToOne to this via `identity_user`
(related_name `persona_profile`).

**On deletion:** `delete_persona()` must:
1. Rename `persona.name` to `"{name}_deleted_{uuid8}"` (frees unique constraint)
2. Set `identity_user.username = "deleted_{uuid8}"` and `is_active = False`
3. Soft-delete the Persona record

**On creation:** `create_persona()` must generate a unique username with
incremental suffix: `persona_ryan`, `persona_ryan_1`, etc.

**Files:** `intelligence/services.py` → `create_persona()`, `delete_persona()`

---

## 3. Human Display Name

**Decision:** `Human` profile records are NEVER created for device-auth users.
Only the `User` record is created on login.

`_format_member()` in `workspace/services.py` MUST use `user.get_display_name()`
for human members, NOT `user.human_profile.full_name`. The `Human` profile
lookup is a secondary fallback only if the record happens to exist.

`User.get_display_name()` returns `display_name` if set (assigned via
`assign_display_name()` on first login), else derives from email local-part.

**Files:** `workspace/services.py` → `_format_member()`

---

## 4. Team Sidebar — @handle Display

**Decision:** Team members in the sidebar are shown with an `@` prefix:
`@Ryan`, `@noamanfaisal`, etc.

**File:** `neuralops-react-app/src/components/layout/Sidebar.tsx`
The `@` is prepended in JSX: `@{member.name}`

---

## 5. Topic Naming — Auto-Create & Auto-Rename

**Decision:** Users do NOT type topic names. Topics are:
1. **Created** automatically as `chat#N` (N = existing topics count + 1)
2. **Renamed** automatically after the first AI response, using the text of
   the first human message (stripped of @mentions, max 60 chars)

No dialog is shown for topic name input.

**Files:**
- `neuralops-react-app/src/components/chat/TopicList.tsx` → `handleNewTopic()`
- `neuralops-react-app/src/hooks/useChat.ts` → `message_done` handler
- `workspace/services.py` → `update_topic()`
- `workspace/api.py` → `PATCH /{project_id}/channels/{channel_id}/topics/{topic_id}/`

---

## 6. API Routing — Active Routers Only

**The only mounted router for workspace/team is `workspace/api.py`.**
`workspace/team_api.py` and `workspace/team_services.py` exist as reference
files but are NOT mounted in `authn/urls.py` and are NOT active.

When fixing team/workspace bugs, always edit:
- `workspace/services.py` (active service layer)
- `workspace/api.py` (active API layer)

**File:** `authn/urls.py` — source of truth for what is mounted.

---

## 7. Soft-Delete Pattern

All models inherit `BaseModel` which has `soft_delete()` that sets
`is_active = False`. Records are NEVER hard-deleted.

Consequences:
- Unique constraints can be violated when re-creating deleted records
- `delete_persona()` renames the record before soft-deleting to free constraints
- `list_team()` filters `user__is_active=True` to exclude deactivated shadow users

---

## 8. Delete Button — 204 No Content

`DELETE` endpoints return HTTP 204 (no body). The frontend `apiRequest()` helper
must NOT call `.json()` on 204 responses. Fixed in `api-client.ts`:

```ts
if (res.status === 204) return undefined as T;
```

**File:** `neuralops-react-app/src/services/api-client.ts`

---

## 9. Projects — Current State (as of last session)

| Project            | Personas in team                  |
|--------------------|-----------------------------------|
| FilePilot          | @Ryan (Coder), @Alex (DevOps), @Sam (System Designer) |
| Canada Economic Trends | @Marco (SerpAPI), @Diana (model/charts) |
| Research On TVs    | @Sara (SerpAPI)                   |

Personas must be added manually via the team dialog if not yet added.
Use the sync shell command if needed (see below).

---

## 10. One-Time DB Sync Command

To add existing personas to specific project teams (run on node3):

```bash
docker exec nexus-nucleus python manage.py shell -c "
from nucleus.models import Persona, Project, ProjectMember, Company
company = Company.objects.filter(is_active=True).first()
# Add persona to ONE specific project:
persona = Persona.objects.get(company=company, name='Ryan', is_active=True)
project = Project.objects.get(company=company, name='FilePilot', is_active=True)
ProjectMember.objects.get_or_create(
    company=company, project=project, user=persona.identity_user,
    defaults={'role': 'member'},
)
print('Done')
"
```

---

## 11. Docker Container Names (node3)

| Service    | Container name     |
|------------|--------------------|
| Django app | `nexus-nucleus`    |
| PostgreSQL | `nexus-postgres`   |

Backup command (credentials from `.env`):
```bash
cd /data/code/neuralops-backend
source .env 2>/dev/null || export $(cat .env | grep -v ^# | xargs)
docker exec nexus-postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backups/neuralops_$(date +%Y%m%d_%H%M%S).sql
```

Backups live at: `/data/code/neuralops-backend/backups/`

---

## 12. MCP Tool Usage Rules

- **File reads/writes on node3:** use `mcp__node3-neuralops-backend__*` tools
- **Shell commands on node3:** NOT available via MCP — give the user the command to run manually
- **`mcp__MKTV-AMAZON-SHELL__shell_execute`** is for a different server entirely — do NOT use for neuralops/node3
- **`mcp__workspace__bash`** runs in an isolated Linux sandbox — cannot SSH to node3

---

## 13. /invite Slash Command — Persona vs Human

**Decision:** `/invite` detects the argument type automatically:
- `/invite @Ryan` or `/invite Ryan` — persona (no `@` in middle = not an email)
- `/invite email@example.com` — human (has `@` in middle = email)
- `/invite email@example.com project` — human, added to project scope

Persona invite calls `invite_to_project()` with `persona_name` (not `email`).
It adds the persona to the **current project** only (not global).

**Files involved:**
- `workspace/schema.py` → `InviteToProjectRequest` has both `email` and `persona_name` (both optional)
- `workspace/services.py` → `invite_to_project()` — persona branch runs before email branch
- `workspace/api.py` → passes both fields from payload
- `workspace.service.ts` → `inviteToProject()` payload type accepts either field
- `MessageInput.tsx` → `handleInviteCommand()` detects persona vs email

---

## 15. Human Invite Flow — `/invite email@example.com`

**Full flow:**
1. Inviter types `/invite x@x.com` in chat
2. Backend creates `Invitation` record (token_hash, 30-day expiry, project_id in access_payload)
3. Backend returns `invite_url = {PORTAL_URL}/invite?server_url={SERVER_URL}&token={RAW_TOKEN}`
4. Frontend shows toast with **"Copy invite link"** button (30s duration)
5. Inviter copies link and sends it to invitee (email, WhatsApp, etc.)
6. Invitee clicks link → portal page at `/invite?server_url=...&token=...`
7. Portal calls `GET {SERVER_URL}/api/v1/auth/invite-preview/?token={TOKEN}` → gets company name, inviter name, email
8. Portal shows: "You've been invited to join [company] by [inviter]. Sign in to accept."
9. Invitee signs in/up on portal → portal connects to server URL
10. Server calls `auth_verify()` → finds pending invitation by email → auto-accepts → creates CompanyAccess → adds to project

**Key files:**
- `workspace/services.py` → `invite_to_project()` — generates raw token, builds invite_url
- `workspace/schema.py` → `InviteToProjectOut` — includes `invite_url` field
- `authn/api.py` → `GET /auth/invite-preview/` — public, no auth, returns invite details for portal
- `authn/services.py` → `auth_verify()` → `_add_user_to_invited_project()` — auto-accepts on connect
- `MessageInput.tsx` → shows "Copy invite link" toast
- `workspace.service.ts` → `inviteToProject()` return type includes `invite_url`

**Portal contract:**
- Page: `{PORTAL_URL}/invite?server_url={URL}&token={TOKEN}`
- Calls: `GET {server_url}/api/v1/auth/invite-preview/?token={token}`
- After auth: connects to `server_url` → triggers `auth_verify()`

---

## 16. App Version — Changelog

**Single source of truth:** `modules/neuralops-react-app/src/lib/version.ts`

Increment `APP_VERSION` on every meaningful change. Update the log below.

| Version | Date       | Changes                                      |
|---------|------------|----------------------------------------------|
| 0.1     | 2026-07-20 | Initial alpha — About dialog, version system |
| 0.1.1   | 2026-07-26 | Fix pydantic-ai 2.x MCP path — rewrite `_run_with_mcp` using `FastMCPClient` + `litellm.acompletion()` directly |
| 0.1.2   | 2026-07-27 | Session UX (open/close system messages, `@session end`, WARNING logs, content guard); persona edit dialog (PATCH); system message rendering in frontend |
| 0.1.3   | 2026-09-01 | UI/build fixes: restore missing `src/lib/mcpOAuth.ts` (gitignore trap), dialog max-height + scroll, message word-wrap + table scroll, type fixes, prettier pass |

**About dialog:** `src/components/layout/AboutDialog.tsx`
Opened via the `ⓘ` button in the Sidebar footer.

---

## 17. Session UX — Confirmed Behaviour & Rules

**Session open:** `@PersonaName @session` — creates a `ChatSession` in DB and shows a system message:
> *Session with @PersonaName opened (30 min). Plain messages will go to them automatically.*

**Session close:** `@session close` OR `@session end` — both accepted, shows:
> *Session closed.*

**Trigger guard:** When opening a session, personas are only triggered if the message contains
content beyond the @mention(s). A bare `@Sara @session` opens the session without triggering Sara.
Only `@Sara @session hello, how are you?` would trigger Sara.

**Logging:** Session operations log at `WARNING` level so they appear in Docker logs even
without a custom `LOGGING` config in `settings.py` (default Django level is WARNING).

**System messages** are stored in the DB with `sender=None`, `message_type="system"`.
They are published to Centrifugo as a `"message"` event with `sender_type="system"`.
The frontend renders them as a centered separator line (not a chat bubble).

**Files:**
- `chat/services.py` → `_SESSION_RE`, `_SESSION_CLOSE_RE`, `extract_session_directive()`
- `chat/api.py` → Rules 1–5 in `send_message()`, `_save_system_message`
- `neuralops-react-app/src/hooks/useChat.ts` → `toUiMessage()` maps `sender_type="system"` → `type: "system"`
- `neuralops-react-app/src/components/chat/MessageItem.tsx` → system branch renders separator
- `neuralops-react-app/src/components/chat/types.ts` → `MessageSender.type` includes `"system"`

---

## 18. Persona Edit — PATCH Support

**A persona is a composition** (since PR #99 removed `AIAgent`): exactly one `ModelConfig` (`model`),
an optional second `ModelConfig` (`advisor_model` — a second opinion the primary can ask for), and
0..5 `MCPServer`s (`mcp_servers`), plus per-persona generation settings (`temperature`, `max_tokens`,
`max_steps`). "Agent-ness" is emergent: a persona with tool servers acts, one without just answers.

**What can be patched:** everything above plus `name`, `description`, `prompt.system_prompt`,
`prompt.output_type`. **The backing is mutable** — the earlier rule ("cannot be changed after creation —
delete and recreate") died with `AIAgent`. Two PATCH conventions, because handlers apply
`dict(exclude_none=True)`: `clear_advisor: true` is the ONLY way to remove the advisor (a null means
"not sent"), and `mcp_server_ids: []` is a real value that detaches every server.

**Server-side wiring rules** (`_validate_persona_wiring()` in `intelligence/services.py`, 400 on
violation): the model and advisor must be attached to the persona's project; the advisor must differ
from the model; tool servers must belong to the same project, number at most
`MAX_MCP_SERVERS_PER_PERSONA` (5), and require a model with `supports_tools`. A PATCH re-validates the
existing servers against a newly chosen model.

**Backend:** `PATCH /api/v1/personas/{id}/` → `PersonaPatchIn` schema → `patch_persona()` in `intelligence/services.py`.

**Frontend (`neuralops-web-app`):** Pencil button on each persona card in **Intelligence → Personas**.
The edit dialog carries the same composition controls as create — model and advisor pickers (with
attach & use for models not yet attached to the project), the tool-server checklist, generation
settings — and mirrors the wiring rules client-side (advisor excluded from the primary's id and cleared
if the primary takes it; unchecked servers disabled at five; a non-tool model unticks and disables the
servers). Only changed fields are sent. Changes take effect on the next @mention.

**Files:**
- `intelligence/api.py` → `patch_persona()` endpoint
- `intelligence/schema.py` → `PersonaPatchIn`
- `intelligence/services.py` → `patch_persona()`, `_validate_persona_wiring()`
- `neuralops-web-app/src/lib/api/intelligence.ts` → `PersonaPatch`, `patchPersona()`
- `neuralops-web-app/src/components/intelligence/personas-tab.tsx` → `EditPersonaDialog`

---

## 19. pydantic-ai 2.x — MCP Architecture

**DO NOT use pydantic-ai Agent for LLM calls. Use `FastMCPClient` + `litellm` directly.**

In pydantic-ai 2.x:
- `LiteLLMModel` → removed entirely
- `MCPServerStreamableHTTP` / `MCPServerStdio` → replaced by `MCPToolset(FastMCPClient(...))`
- `LiteLLMProvider` → proxy-only (needs a running LiteLLM server; does NOT do in-process routing)
- `AnthropicModel` → needs `pydantic-ai-slim[anthropic]` extra; NOT in our requirements
- Available in `pydantic_ai.mcp`: `FastMCPClient`, `MCPToolset`, `MCPToolsetClient`, `FastMCP`

**The working pattern (MCP path in `pydantic_ai_runner.py`):**

```python
import contextlib, json
from pydantic_ai.mcp import FastMCPClient

async with contextlib.AsyncExitStack() as stack:
    client = await stack.enter_async_context(FastMCPClient(url_or_config))
    tools = await client.list_tools()          # list of MCP tool objects
    result = await client.call_tool(name, args) # call a tool

# LLM calls: use litellm.acompletion() directly — same as fast path.
# litellm handles anthropic/, openai/, local/ routing via model_id prefix.
response = await litellm.acompletion(model="anthropic/claude-...", messages=..., tools=...)
```

**Why this works:** litellm already routes `anthropic/claude-haiku-4-5-20251001` correctly
(the fast path proves it). pydantic-ai is used **only** as an MCP client library.

**Why this broke:** `_run_with_mcp` only fires when a persona has `mcp_servers` configured.
Sara/Marco worked before they were wired to nexus-serp-mcp (fast path only, no pydantic-ai).

**Rule:** Verify any third-party class exists in the installed version before using it.
Do NOT assume API compatibility across major versions without checking.

**Files:** `modules/nexus-ai/apps/implementations/agents/pydantic_ai_runner.py`
**requirements.txt:** `pydantic-ai-slim[openai,mcp,anthropic]` (anthropic extra for future use)

---

## 20. Self-Host Distribution (#170) — Fat Docker Profile + Installer

**Status:** Verified end-to-end (2026-08-08) — `fat` profile in
`docker-compose.yaml`, `docker/fat/Dockerfile.nginx` + `docker/fat/nginx.conf`,
`modules/nexus-nucleus/docker/fat/Dockerfile.nexus-nucleus`,
`modules/nexus-ai/docker/fat/Dockerfile.nexus-ai`, `.env.example` FAT_* section,
`install.sh`, `SELF-HOST.md`, `VERSION`. All three custom images
(`noamanfaisal/neuralops-{nucleus,nexus-ai,nginx}:0.1.0`) built and pushed to
Docker Hub by the owner. Full first-run sequence (`migrate`/`seed_permissions`/
`create_owner`) run successfully; the hosted frontend's "Connect" flow
succeeds against the Tailscale Funnel URL; avatars and typing-status render
correctly through the self-hosted backend, confirming end-to-end parity with
the `dev` profile.

**Distribution address (2026-08-08):** `install.sh`'s `REPO_RAW_BASE`/`REF`
and `SELF-HOST.md`'s curl examples now point at `mapax-io/neuralops-nexus`
on branch `dev` (the canonical/upstream repo, since the fat profile is a
user-facing feature and belongs at the public address, not the personal fork
used during development). **This is forward-looking** — the fat-profile
files only exist on the fork (`noamanfaisal/neuralops-nexus-backend`,
branch `staging`) as of this note. Owner is merging to the fork's `main`
first, then opening a PR from fork `main` → `mapax-io/neuralops-nexus`
`dev`. Until that PR merges, `install.sh`/`SELF-HOST.md` in this repo will
404 against the real `mapax-io` URLs — that's expected and resolves itself
once the PR lands. Update `REF` to a real git tag once one is cut, same as
before.

**Bugs found during end-to-end testing on node-3 (all fixed):**
1. `install.sh` used `mapax-io` GitHub org (copied from `readme.md`'s unrelated
   upstream-fork clone instructions) instead of the real push target
   `noamanfaisal` — fixed in `install.sh` and `SELF-HOST.md`.
2. `curl | bash` consumes stdin for the script body itself, so any `read`
   inside had no terminal to read from — under `set -u` this threw "unbound
   variable" and killed the script. Fixed by dropping the optional
   `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`SUPABASE_SERVICE_KEY` prompts
   entirely (left blank in `.env` by design — end users fill these in later,
   no `.env` authoring expected of them) and redirecting the remaining
   genuinely-interactive prompts (Docker install confirm, Tailscale yes/no,
   `create_owner`) from `< /dev/tty`.
3. `install.sh` installed into `$(pwd)/neuralops`, creating a confusing extra
   nested folder. Fixed to install directly into `$(pwd)`.
4. `pg_isready -U neuralops` with no `-d` flag checks a database matching the
   *username*, not `FAT_POSTGRES_DB` (`neuralops_fat`) — looped forever on a
   false negative even though Postgres was fully healthy (confirmed via raw
   `docker compose logs postgres-fat`). Root cause of the broader redesign
   below rather than a targeted `-d` fix.
5. **`nginx.conf`'s upstream service names are dev-network only**
   (`nucleus-dev:8000`, `realtime-dev:8000`) but `docker/fat/Dockerfile.nginx`
   was baking that exact file into the fat nginx image — on `fat-network`
   those names don't resolve, so every request through `nginx-fat` failed
   (surfaced as "could not connect to server" from the hosted frontend's
   connect flow, containers otherwise healthy). Fixed by adding a dedicated
   `docker/fat/nginx.conf` (upstreams `nucleus-fat:8000`/`realtime-fat:8000`)
   and pointing `docker/fat/Dockerfile.nginx` at it instead of the repo-root
   file. **Requires rebuilding + re-pushing `noamanfaisal/neuralops-nginx`
   and re-pulling on the test host** — not yet done as of this note.
6. **Chrome Private Network Access (PNA) silently blocks the connect fetch.**
   After fix #5, `curl` proved nginx/CORS/Django were all working correctly
   (`GET /api/v1/auth/verify/` → 401 as expected, `OPTIONS` preflight → 200
   with correct `access-control-allow-*` headers) but the hosted frontend
   still showed "Could not connect to server" (the exact string
   `ServerList.tsx` shows only when `verifyServerAccess()`'s `fetch()` throws
   — status `0`, never a real HTTP response). Root cause: Tailscale addresses
   fall in `100.64.0.0/10` (CGNAT), which Chrome classifies as a "private"
   network target. A public-origin page (the Vercel-hosted frontend) fetching
   a private-range target needs `Access-Control-Allow-Private-Network: true`
   on the preflight response or Chrome blocks the request client-side before
   it ever shows up as a real HTTP error — curl has no such check, which is
   why it looked server-side-healthy while the browser still failed. Fixed by
   adding `add_header 'Access-Control-Allow-Private-Network' 'true' always;`
   to the `/api/` location in both `docker/fat/nginx.conf` and the root
   (dev) `nginx.conf`. Same rebuild/push/re-pull requirement as #5 applies to
   the fat image.

**Design change:** `install.sh` originally automated the full first-run
sequence (including a Postgres-readiness wait-loop). After bug #4 made this
opaque to debug, redesigned per owner's instruction: the script now stops
right after `docker compose up -d` and prints `migrate`/`seed_permissions`/
`create_owner`/Tailscale as explicit commands for the user to run one at a
time — trading full automation for visibility.

**Server/frontend version check (2026-08-08):** The hosted frontend always
runs the newest code, but a self-hosted `fat` server can be pinned to any
older `FAT_VERSION` (exactly what caused the avatar bug above — an image
built before the avatar pool existed). Without a check, a stale server just
fails in confusing ways instead of surfacing the real cause. Fix: `FAT_VERSION`
(`"dev"` for the dev profile) is now passed into `nucleus-fat`/`nucleus-dev`
as `NEURALOPS_VERSION`, exposed as `server_version` in the existing
`GET /api/v1/auth/verify/` response (no new endpoint), and compared by the
frontend against `COMPATIBLE_SERVER_VERSION` (`modules/neuralops-react-app/
src/lib/version.ts`) on every connect. On any mismatch (server older or
newer), `ServerList.tsx` shows a non-blocking banner telling the self-hoster
to run `./install.sh update` — doesn't refuse the connection, just makes
version drift visible instead of silent. `"dev"`/`"unknown"` servers skip the
check entirely. Files: `authn/schema.py` (`AuthVerifyResponse.server_version`),
`authn/services.py` (`auth_verify()`), `core/settings.py`
(`NEURALOPS_VERSION`), `docker-compose.yaml` (env var wiring),
`auth.service.ts` (`VerifyResult.serverVersion`), `ServerList.tsx` +
`ServerCard.tsx` (the banner), `lib/version.ts` (`COMPATIBLE_SERVER_VERSION`).

**Real version bump to test it (2026-08-08): `0.1.0` → `0.1.1`.** Reusing the
same `0.1.0` tag for the rebuilt-with-avatars image would have made "did the
rebuild actually take" impossible to verify by tag alone, and there was
nothing to trigger the mismatch banner against. While bumping, found a real
bug in `install.sh update`: it downloads the new `docker-compose.yaml` and
writes the new version to `.neuralops-version`, but never updates `.env`'s
`FAT_VERSION=` line — since image tags come from `FAT_VERSION`, not the
version marker file, `docker compose pull` would keep silently pulling the
OLD image forever after every future `update`. Fixed with a `sed` on `.env`
right after the marker write. `COMPATIBLE_SERVER_VERSION` bumped to `0.1.1`
to match.

**Decision:** Fat distribution uses MULTIPLE pre-built Docker Hub images
orchestrated by a `fat` Compose profile added to the same `docker-compose.yaml`
(alongside `dev`) — NOT a single merged/supervisord image. A merged image was
seriously considered (real precedent: GitLab Omnibus) but rejected for now —
it trades a small UX win (`docker run` vs `docker compose up`) for real costs
(Postgres data-safety risk unless volumes are very carefully externalized, a
full-image rebuild+re-pull on every single-service fix instead of just that
service's image, no per-service restart/log isolation). Multiple pre-built
images keep those benefits while still being effectively "pull and go."

**Services in the `fat` profile:** nucleus, nucleus-celery (reuses the nucleus
image, different `command:` — same pattern as `dev`), postgres, redis,
chromadb, realtime (centrifugo), nginx.

**No frontend service — explicit decision.** Self-hosters connect the
already-hosted frontend to their server instead of running a local UI. Removes
one container, one port to expose, and means frontend fixes only ever ship in
one place. Pairs with Tailscale Funnel exposure (README §3 Option A).

**Images:**
- Reuse as-is: `postgres:17-alpine`, `redis:7-alpine`, `chromadb/chroma:latest`
  (pin to a specific tag, not `latest`), `noamanfaisal/nexus-transport:6.0`.
- Build + push new: `noamanfaisal/neuralops-nucleus:<version>` and
  `noamanfaisal/neuralops-nexus-ai:<version>`, each from a NEW
  `docker/fat/Dockerfile.*` (source baked in, no bind mount, no `--reload`,
  fixed worker count — do NOT reuse the dev Dockerfiles). Also
  `noamanfaisal/neuralops-nginx:<version>` — thin custom image, `FROM
  nginx:alpine` + `COPY nginx.conf` baked in, since the fat bundle ships no
  source tree to bind-mount `nginx.conf` from the way `dev` does.

**Data:** Postgres/Redis/Chroma on host-mounted volumes under their own
`./data/fat/` tree — same pattern as `dev`'s `./data/dev/` — so pulling a new
image version never touches existing data.

**Versioning:** One semver version per release (e.g. `v1.0.0`) covers all
three custom images together, even if only one actually changed — keeps
"which version am I on" simple for the user. The compose file always pins
exact tags, never `:latest`, so updates only happen when deliberately
triggered via the installer, not silently.

**First-run sequence:** `migrate` → `create_owner` → `seed_permissions` →
optional `seed_avatars`. Order between `create_owner` and `seed_permissions`
does NOT actually matter — both do `get_or_create` on the same Owner `Role`
row (confirmed by reading `create_owner.py`'s `_grant_owner_role()` docstring
directly); whichever runs second just populates the `RoleRight` links on the
row the other already created.

**Distribution:** Stays in this same repo — not a separate repo, to avoid a
permanent two-repo sync burden. Git-tagged releases (`v1.0.0`, etc.) make a
specific version's compose file fetchable without a full clone. A dedicated
`SELF-HOST.md` (not the dev-focused `readme.md`) will hold only the
fat-docker install instructions.

**Installer (`install.sh`):** A plain shell script — NOT a Docker-socket-
mounting "installer container" (that pattern, like Watchtower, needs
root-equivalent Docker socket access just to check for updates; a script
achieves the same using whatever Docker permissions the user already has).
Flow: check/install Docker → download the pinned compose file + `.env.example`
→ prompt for required secrets → `docker compose pull && up -d` → run the
first-run sequence → check/install Tailscale → `tailscale up` (plain, **no
auth-key requirement** — the one unavoidable manual step is a single browser
login click, by design; do not build an auth-key path into the default flow)
→ `tailscale funnel --bg <nginx port>` → write the resulting URL into `.env`
as `NEURALOPS_SERVER_URL` → restart `nucleus`/`realtime` → print the connect
URL for the hosted frontend's "add server" flow. Also supports `install.sh
update`: compares a local version marker against the latest published
version, re-pulls if newer. The Tailscale step should be skippable via a flag
for anyone who wants LAN-only access or their own router/port-forward setup.

**RAM budget:** ~2GB total if `nexus-ai` uses an API-based embedding provider;
~3–4GB if it keeps local `fastembed` inference (the single biggest lever on
memory footprint — a local embedding model gets fully loaded into RAM).
Document a 4GB minimum host spec for the fat profile.

**Considered and rejected:**
- **Snap** — real daemon-service support + a close precedent (Nextcloud's
  official snap bundles Apache/PHP/MySQL/Redis into one package), but
  Ubuntu-only reach in practice and throws away today's working Docker
  investment.
- **Flatpak / AppImage** — built around single-window GUI desktop apps, no
  real background-daemon model, no reuse of existing work, more effort for a
  worse fit than either Docker or Snap.
- **Single merged supervisord image** — see main decision above.

**→ SUPERSEDED (addendum, 2026-08-19).** Everything above is kept as history —
do not edit it; it records what the `fat` profile was and what was learned
verifying it end-to-end. But the `fat` profile is **no longer the self-host
path**. It has been replaced by `docker-compose.neuralops.yaml`: a single
unified `noamanfaisal/neuralops` image backing separate `nucleus`/`nexus-ai`/
`centrifugo` containers, dispatched by mode via `neuralops/entrypoint.sh`
(`nucleus-env` / `nexus-ai-env` / `centrifugo` / `init-secrets`), with
per-deployment secrets generated by
`docker run --rm <image> init-secrets > neuralops/secrets.env` and config split
across `neuralops/infra.env` + `neuralops/app.env`.

**Read [`SELF-HOST.md`](./SELF-HOST.md) for the current flow.**
`fat_docker.md` is a quick-reference cheat sheet for it (old fat-profile
commands are retained there under a "superseded" heading).

Note the status difference: the `fat` profile above was **verified end-to-end**
(2026-08-08); the unified-image flow **has not been** as of this addendum.
That's the one reason to still read the history above — bugs #5 (nginx upstream
names baked per-network) and #6 (Chrome Private Network Access needing
`Access-Control-Allow-Private-Network` on the preflight) are properties of the
deployment shape, not of the fat profile specifically, and are the first things
to check if the new flow fails the hosted frontend's connect step.

Still-present leftovers of the old path, deliberately not deleted yet:
`docker-compose.yaml`'s `fat` profile, `install.sh`, `docker/fat/*`, the
`.env.example` `FAT_*` section, the three `noamanfaisal/neuralops-{nucleus,
nexus-ai,nginx}` Docker Hub images, and `Fat-Docker/bootstrap.py` (which is now
referenced by no doc in this repo). Removing them is a separate decision —
nothing should be pruned until the unified-image flow has its own end-to-end
verification.

---

## 21. Before Starting Any Task

1. Read this file (`DECISIONS.md`)
2. Read the specific files you intend to edit — do not assume their contents
3. Check if the feature already exists before implementing it
4. If a requirement contradicts something in this file, ask the owner before proceeding
