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

**Files:** `workspace/services.py` → `_format_member()`, `list_members()` (server members carry `name`
the same way — the app never derives a name from the email itself)

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
| 0.16.0  | 2026-09-11 | **Scoped permissions in the UI** — every management control gates on a RIGHT against the object it acts on (`GET /api/v1/me/permissions/`), replacing the `connection.role` string check; `isCompanyAdmin`/`isViewer` removed, so the client holds no role rule of its own. A server without the endpoint is reported as out of date (`PermissionsBanner`) rather than silently hiding everything. **@mention chips in the transcript** — a known persona/teammate/self renders as the same pill the composer draws (`rehypeMentions`, sharing the composer's `findPillRanges`); an unknown name stays plain text; being mentioned yourself is the loudest flavour. **Persona activity from the server** — the cue under a working persona shows nucleus's own `tool_activity` wording ("Searching the web") instead of a fixed "Thinking". See docs/OPEN-ITEMS.md. |
| 0.17.0  | 2026-09-11 | **Profile photos** — people can upload their own picture from the Profile dialog, or remove it and fall back to a server-assigned one (`POST`/`DELETE /api/v1/me/avatar/`). The upload is decoded and re-encoded server side, so the stored file is always a real image with its EXIF stripped. Also fixes **broken default avatars**: `get_avatar_url()` returned a URL pinned to `NEURALOPS_SERVER_URL`, which 404s whenever the client reached the server by any other name (localhost, LAN, a tunnel); paths are now server-relative and resolved against the connected server. |
| 0.18.0  | 2026-09-11 | **Invite into projects, channels and topics** — the invite form (members page and members dialog) gains a tree: tick a project for the whole project (topics created later included), untick topics to narrow it to just those, tick a channel to move all of its topics at once. Sends `grants` on `POST /members/invite/`; a server that ignores the field (pre-grants) is called out rather than passing as done. The Role field reads "Company role" and its hint states the server's rule: a scoped invite puts the role on the picked objects only. Both surfaces share one hook (`useInvite`) and one fields component (`InviteFields`); the tri-state checkbox moved into the field primitives. |
| 0.18.1  | 2026-09-11 | **Member access, a stuck-loader fix, UI polish.** (1) Members page: an **Access** button per member opens the same role select + project/channel/topic tree as the invite, loaded with what they hold, and saves a full replace (`GET/PUT /members/{id}/access/`). (2) A signed-in user could sit on the loader forever after a deploy: the session read now has a watchdog (8 s) and a catch, every request has a timeout (20 s reads / 90 s writes), and the loader offers Reload / Sign out after 10 s. (3) Creating a project/channel/persona no longer flashes "already exists" while the dialog waits for rights. (4) Hover feedback never moves a control (`Button`, `EntityCard`, landing cards — translate lifts flickered at the control's edge). (5) Text actions read as actions: `Button` `link` variant for "View all members →" and every "Retry", chip hover on code-block "Copy", chrome on the team dialog's "Add", expanders answer hover in accent. (6) The invite toast carries the server's note when a sign-in email went instead of an invite. |
| 0.18.2  | 2026-09-11 | **Invite outcome never mentions email** (owner decision). A pending invite always reads "X is invited — they sign up with that exact address, add this server, and they're in with the access you gave them", with the steps to copy; whether the server emailed them (it needs a service key) is not surfaced. The toast stays until the inviter copies the steps or closes it. Same toast on the members page, the members dialog and the composer's `/invite`. |
| 0.18.3  | 2026-09-12 | **Model id suggestions, hardened.** Upstream #128 added a model id dropdown fed by OpenRouter's public catalog (Anthropic, OpenAI, Google) and #127 aligned the capability keys with nexus-ai's registry and fixed the globs textareas eating a typed newline. Review fixes on top: the model id is always one field (the catalog arriving no longer swaps the input out from under a typing user); one hook (`useProviderModels`) owns the provider list, filtering, payload validation and gating (nothing is fetched until a model dialog is open); the list is a WAI-ARIA combobox — arrows highlight, Enter picks without submitting, Escape closes the list and the `Dialog` yields the key to an open combobox instead of closing. Regression tests for the textarea fix and the Escape chain. |
| 0.18.4  | 2026-09-12 | **A chat stuck on its loader says so.** Reported: the messages pane sometimes sat on its skeleton until another tab was visited. The frontend chain does not latch (proved against the real hook with fake timers); the wait was the server, whose Supabase signing-key set expired every 5 minutes and was re-fetched synchronously on the one sync thread (fixed in nucleus: per-key cache, bounded timeout). On this side the skeleton now says "Still loading this chat…" with a Retry after 10 s — the same rule the full-page loader already follows, now one hook (`useSlowAfter`) for both. |
| 0.18.5  | 2026-09-13 | **Expects a 0.2 server.** The 0.2.0 release bumps the image version (`NEURALOPS_VERSION`) for the permissions, scoped-invite and model-config contract changes, so `COMPATIBLE_SERVER_VERSION` moves to 0.2.0 in the same release: a 0.1.x server now shows as breaking, `dev` still passes unchecked. Closes the OPEN-ITEMS entry left after PR #99. |
| 0.18.6  | 2026-09-13 | **Built-in capability editor, per #132.** Globs are input chips: Enter, a comma or a pasted list adds, Backspace on an empty draft removes the last, a pending draft is added on blur (nothing typed right before Save is lost), and Enter never submits the dialog. The shell's commands are ONE policy — Any command / Only these / All but these — because the AI worker's Shell refuses to start with both an allow list and a block list: every write fills the chosen list and empties the other; a row saved with both shows the error with "Keep the allow list" / "Keep the block list" and blocks Save until one is kept; an empty allow list says that any command may run. The command list matches the worker's enum again (`sed`, `wget` were missing) and a saved command outside it still shows. No "Advisor" row — the persona dialog's advisor-model slot is that feature; a row that already holds the key keeps it. |
| 0.18.7  | 2026-09-13 | **Peers are off limits on the members page.** An admin manages members and viewers, and may still promote a member to admin, but only the owner changes, re-scopes or removes another admin — so Access and Remove no longer show on an admin's row unless you own the server. The same rule is enforced by nucleus (peer guard on access replace, server removal and project-team removal; rights gates on the team routes), so an older app against the new server gets a clear refusal rather than a silent change. (0.18.5 is the 0.2 release row; 0.18.6 is the capability editor, #132.) |
| 0.18.8  | 2026-09-14 | **A refused persona says so.** Nucleus now enforces `persona.mention` on the send path (it was registry-only; the picker was the only gate), so a message can post while its personas are refused. The send response carries `refusals[]` and the topic channel a sender-addressed `mention_refused` event; the app pins a note under the sender's message ("@Sara didn't answer: …", with the reset time once limits exist) and toasts once. Notes park until their message lands and survive a history reload. Plan phase 0 (`contribution/plan-usage-and-persona-access.md`). |

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
0..N `MCPServer`s (`mcp_servers` — external servers and, since #104, internal capability rows), plus per-persona generation settings (`temperature`, `max_tokens`,
`max_steps`). "Agent-ness" is emergent: a persona with tool servers acts, one without just answers.

**What can be patched:** everything above plus `name`, `description`, `prompt.system_prompt`,
`prompt.output_type`. **The backing is mutable** — the earlier rule ("cannot be changed after creation —
delete and recreate") died with `AIAgent`. Two PATCH conventions, because handlers apply
`dict(exclude_none=True)`: `clear_advisor: true` is the ONLY way to remove the advisor (a null means
"not sent"), and `mcp_server_ids: []` is a real value that detaches every server.

**Server-side wiring rules** (`_validate_persona_wiring()` in `intelligence/services.py`, 400 on
violation): the model and advisor must be attached to the persona's project; the advisor must differ
from the model; tool servers must belong to the same project and require a model with
`supports_tools` (the former cap of five, `MAX_MCP_SERVERS_PER_PERSONA`, was removed in #104). A PATCH re-validates the
existing servers against a newly chosen model.

**Backend:** `PATCH /api/v1/personas/{id}/` → `PersonaPatchIn` schema → `patch_persona()` in `intelligence/services.py`.

**Frontend (`neuralops-web-app`):** Pencil button on each persona card in **Intelligence → Personas**.
The edit dialog carries the same composition controls as create — model and advisor pickers (with
attach & use for models not yet attached to the project), the tool-server checklist, generation
settings — and mirrors the wiring rules client-side (advisor excluded from the primary's id and cleared
if the primary takes it; no cap since #104; a non-tool model unticks and disables the
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

---

## 22. Team AI Operations — rights and wire contract (2026-09-20)

**Decision:** the capabilities in `contribution/plan-implementation-master.md` (Preflight, Routines, Recall,
Runbooks, Inbound hooks, Deliverables, Tool approvals, …) share one foundation, shipped first and on its own:

- **Rights are seeded ahead of use.** `persona.approve_run` (topic), `routine.manage`, `runbook.manage`,
  `runbook.run`, `hook.manage`, `recall.manage`, `deliverable.manage` (project) live in the registry now;
  a capability PR only *uses* them. Member-tier: approve, run a runbook, curate Recall/Deliverables.
  Admin-tier: define routines, runbooks, hooks. `manage.py seed_permissions` must run on every upgrade.
- **Wire changes are additive and feature-detected on both sides.** `MessageOut` carries `activity_trail`,
  `preflight`, `answered_by_model`, `usage` with defaults; `message_done` carries `prompt_tokens`,
  `output_tokens`, `context_window` (null when the worker does not know). An older app ignores them; a newer
  app hides a control whose endpoint answers 404. Never a breaking rename.
- **Versions.** `NEURALOPS_VERSION` moves a MINOR only when the app *requires* a new server capability for a
  control it shows; additive fields are a PATCH. The app's `COMPATIBLE_SERVER_VERSION` follows each MINOR.
- **Project Brief (W1, 2026-09-21).** `Project.brief` (≤ 8,000 chars, `workspace/services.py
  update_project`) is edited under the new `project.update` right (Admin-tier) via `PATCH /projects/{id}/`;
  the detail route returns `brief`, the list only `brief_length`. The internal persona payload carries
  `project_brief`, and the worker puts it in its own system block *ahead of* the persona prompt — order is
  brief → persona → output instruction. First app-required capability: server `0.3.0`.
- **Utility model (W17, 2026-09-21).** `CompanyAIConfig.utility_model` (FK ModelConfig, SET_NULL; cleared
  when that config is deleted) is the one model the server's own small passes run on (recall, runbook
  conditions, titles — nothing consumes it yet; the worker falls back to the persona's model). Chosen from the
  AI models tab via `POST/DELETE /model-configs/{id}/utility/` under `model_config.update`; lists mark it with
  `is_utility`; the persona payload carries `utility_model`. `PUT /ai-config/` now requires the same right — it
  had no gate before.
- **Preflight (W3, 2026-09-21).** `Persona.acts_after_approval` (off by default) makes a persona propose
  before acting: nucleus flags the job (`preflight`) whenever no plan is approved yet, and the WORKER decides
  whether the run would act (any MCP server, or a shell/filesystem capability — nucleus never reads capability
  configs); if so the turn runs with no tools in the `preflight` output type (`{summary, steps[{title, tools,
  writes}], risks}`, ≤ 12 steps). Nucleus stores the parsed plan in `metadata.preflight` (`status: proposed`,
  with the asking message) and `POST …/messages/{id}/preflight/` (`approve | adjust | decline`, right
  `persona.approve_run` at the topic) decides it once: approve re-triggers with `approved_plan` ahead of the
  persona prompt and the tools back on; adjust re-triggers a planning turn with the note; decline posts a system
  line. Every decision publishes `preflight_decided`. Scheduled and swarm runs never plan (nobody is waiting).
  Server `0.4.0` — the app relies on the endpoint.
- **Tool approvals (W16, 2026-09-21).** `Persona.tool_levels` (`{capability id | "<capability>/<tool>":
  "auto"|"ask"|"off"}`, keys `shell`, `filesystem`, `web_search`, `web_fetch`, `mcp:<server id>`) is stored and
  shape-validated by nucleus; the WORKER owns the defaults (reading is automatic; `run_command`, `start_command`,
  `write_file`, `edit_file`, `create_directory` ask; an MCP tool asks unless its annotations say `readOnlyHint`)
  and hides `off` tools from the model. An Ask tool holds the run in process: the worker sends
  `approval_requested {call_id, tool, capability_id, args_preview}`, the relay stores it at once under
  `metadata.approvals` (status `pending`) and publishes `tool_approval`; the worker polls
  `GET /internal/messages/{id}/approvals/{call_id}/` (pending | allowed | denied | stopped) and sends `keepalive`
  events so the relay's two-minute idle timeout never ends the reply. `POST …/messages/{id}/approvals/{call_id}/`
  (`allow | deny`, `always`) decides once under `persona.approve_run` at the topic; `always` writes
  `"<capability>/<tool>": "auto"` onto the persona and therefore also needs `persona.update`. Denied, timed out
  (`APPROVAL_TIMEOUT_SECONDS`, 600) and stopped calls are skipped with a one-line reason the model sees; a reply
  that ends expires its pending calls. Scheduled (`interactive=False`) and swarm runs refuse Ask tools at once —
  nobody can answer there. Not the plan's Redis wait: the worker has no Redis, and Stop already works as
  nucleus-held state that a poll reads. Server `0.5.0` — the app relies on the decision endpoint.
- **Routines (W4, 2026-09-21).** `Routine` (project-owned: `name` `[a-z0-9-]{1,40}` unique per project, `title`,
  `purpose` ≤ 200, `instructions` ≤ 8 000, `allowed_capabilities` null | list of capability ids, `model_config` null,
  `is_builtin`) under `/projects/{id}/routines/` — list needs `topic.list` at the project, writes `routine.manage`;
  built-ins are editable, never deletable (409). Four are seeded per project on creation and by
  `manage.py seed_routines` (idempotent by name). The send path reads the FIRST standalone `/name` token
  (`MessageDirectives.routine_name`, stripped from the message; `/swarm`, paths and mid-word slashes are not
  tokens): known in the topic's project → `routine_id` on the job; unknown with personas to answer → refusal
  `unknown_routine` (the message still posts, they do not reply); no persona → plain text. The WORKER fetches the
  routine (`GET /internal/routines/{id}/`, key decrypted there) and applies it for that turn only: instructions as
  their own block after brief + persona prompt, `allowed_capabilities` INTERSECTS the persona's tools (never widens),
  `model_config` replaces the model. Swarm runs ignore routines. Server `0.5.1` (additive).
- **Run ownership (W22, owner's rule, 2026-09-21).** A persona reply belongs to the person who called it:
  `create_ai_message` records `metadata.triggered_by_id` / `triggered_by_name` (the sender; a schedule's creator; on a
  preflight approve/adjust the person who ASKED, resolved from the asking message, else the decider; a swarm and its
  delegate replies the sender), and `MessageOut` + `message_start` carry `triggered_by_id`. **Only the caller may stop
  the reply** — `request_stop_for_message(topic, id, user)` answers `not_owner` → 403 — which replaces the earlier
  "anyone who can read the topic can stop a run in it"; a reply with no recorded caller (created before this) keeps
  that earlier rule so nothing running becomes unstoppable, and the worker's own timeouts still end a stuck run. No
  owner/admin override, by the owner's word. The app applies the same rule to a choice card (only the person the
  persona asked may pick; everyone else sees "Waiting for <name> to choose"). Preflight decisions and tool approvals
  stay team-decidable under `persona.approve_run` — a second person deciding is their point. Server `0.5.2`.
- **Terminal pane (W21, owner's ask, 2026-09-21).** A Terminal in the app is a REAL terminal — the owner rejected a
  one-command-per-request runner ("it should work just like an actual terminal with all its features"). The worker
  starts a shell (`TERMINAL_SHELL`, bash) on a PTY in the project's folder, with a controlling terminal, so interactive
  programs, job control, colours, `cd` and resizing all behave; the app is its screen (xterm.js) over a WebSocket
  (`/terminal/ws`, nginx → worker `/api/v1/terminal/ws`; binary frames are the terminal's bytes, text frames small JSON
  control messages: `resize` in, `exit`/`error`/`idle` out). Access: new right `project.terminal` (PROJECT scope,
  Admin-tier; `seed_permissions` seeds it) gates `POST /projects/{id}/terminal/session/`, which answers a 60-second
  HMAC ticket signed with the internal key (`workspace/services.py sign_terminal_ticket` ↔ worker
  `apps/managers/terminal.py verify_ticket`; claims: project, user, cwd — the shell capability's `cwd`, else the
  provisioned folder; 409 without a folder, 503 without the key) and logs who opened what. The worker verifies the
  ticket on connect (close 4401), caps open sessions (`TERMINAL_MAX_SESSIONS`, 4429), ends a session after
  `TERMINAL_IDLE_SECONDS` without input (4408) and kills the shell's whole process group when the socket goes.
  Security stance: the personas' shell allow-list does NOT apply to a person's shell — the Admin-tier right is the
  boundary and the container (uid 1000, the project folder as HOME) the hard one; the shell gets a sanitized
  environment (PATH/LANG/LC_ALL/TZ only — the worker's own env holds the secrets), never the worker's. Nothing a
  terminal does is posted to the chat. Server `0.5.3`.
- **Model fallbacks (W7, 2026-09-21).** A persona names up to three fallback models, in order
  (`Persona.fallback_models` through `PersonaFallbackModel(position)`, migration `nucleus 0024`;
  `fallback_model_config_ids` on create/patch — `[]` clears, unsent leaves; ≤ 3, no repeats, never the primary,
  attached to the project, enforced in `_validate_persona_wiring`; the model detach/delete guards count fallback use).
  The WORKER retries (`apps/managers/fallbacks.py FallbackRun`, one place for the single-persona manager and the
  swarm loop): when the runner's exception is a model failure (`is_model_failure`: HTTP 401/402/403/404/408/409/425/429
  or ≥ 500, or the litellm/pydantic-ai classes for a revoked key, no credit, rate limit, unknown model, provider
  down/unreachable/timeout — NOT 400/422, context length, content policy or `UnexpectedModelBehavior`, which are the
  model answering) and NOTHING has reached the reader yet (no delta, tool call or approval request), the same turn
  runs again on the next model; a failure after text streamed is reported, never silently restarted; the last
  candidate's error passes through unchanged so `chat/reasons.py` words it as today. The reply then carries
  `message_done.answered_by_model = "<model name> (fallback)"`, which nucleus keeps in `metadata.answered_by_model`
  (serialised since Wave 0) and republishes; the app shows "Answered by <name> · fallback" under the bubble.
  `chat/reasons.py` decides the wording of a failure, the worker decides the retry — two small classifiers on
  purpose. Server `0.5.4`.
- **Model check on register / edit (owner's ask, 2026-09-21).** The Register and Edit model dialogs verify a model
  with the provider BEFORE saving it, and show what is wrong otherwise: `POST /model-configs/check/`
  (`model_config.create` or `.update`; `intelligence/services.py check_model_config`) asks the worker's
  `POST /api/v1/models/check/` (`apps/managers/model_check.py`: one tiny call, `max_tokens` 5, built by the same
  `PydanticAIRunner.build_model` a persona runs on, `MODEL_CHECK_TIMEOUT_SECONDS` 20) and answers `{ok, reason,
  latency_ms}` — the reason is the `chat/reasons.py` sentence (bad key, no credit, rate limit, unknown model,
  unreachable, timeout), or "This server's AI worker cannot run <provider> models yet" when the worker has no
  runner for the provider; never the provider's raw text (it can carry the key). An edit without a new key checks
  with the stored one (`config_id`). The API create/patch stay unguarded (scripts and tests register models offline);
  the dialogs are where the rule lives; an older server (404 on the check) saves as before. Side fix: the worker
  now passes `api_base` to OpenAI-shaped providers (it was dropped, so compatible endpoints never worked).
  Server `0.5.5`.
- **Recall (W5, 2026-09-21).** What the team's personas record about a project outlives the topic it came up in.
  `RecallEntry(ProjectBaseModel)`: kind (decision|fact|preference), text ≤ 500, `normalized` (the dedupe key,
  enforced in `intelligence/recall.py` — not a DB constraint, so a removed entry can be recorded again), source
  topic/message, author persona, created_by; migration `nucleus 0025` (with `Persona.recall_enabled`, default on,
  which gates both what the persona is fed and what it records). Caps: 5 entries per reply, 500 per project.
  Nucleus is the writer of record and the worker owns the vectors: every create/edit → worker
  `POST /api/v1/embed/recall/` into `company_{id}_recall` (doc id = entry id, so an edit upserts), soft delete →
  `DELETE /api/v1/embed/recall/{id}/` — both best effort (a missing vector is weaker recall, not a failed write).
  Every trigger carries a `recall` context source (`source_id` = the project id) unless the persona has recall
  off; the worker's third plugin `RecallContextSource` retrieves top-k `RECALL_TOP_K` (8) by project and the prompt
  builder puts them in their OWN block "What the team has recorded" after the attached sources and before the
  conversation. The remember pass (`apps/managers/recall.py`): after a successful reply, the persona's utility
  model (else its own) reads the exchange and answers `{entries: [{kind, text}]}` (structured output, max_tokens
  400, `RECALL_REMEMBER_TIMEOUT_SECONDS` 15, "nothing durable → empty list"); the worker POSTs
  `/internal/recall/` and `message_done.recalled` says how many were kept (`metadata.recalled`,
  `MessageOut.recalled`); any failure in the pass is logged and never touches the reply. Rights: reading needs
  project access (`topic.list`); editing/removing is `recall.manage`, which the registry places in the MEMBER tier
  (a member curates what personas recorded; Viewers read only). Routes `GET/PATCH/DELETE /projects/{id}/recall/…`.
  Follow-ups kept out of this item and logged in OPEN-ITEMS: the persona-callable `remember` tool, the nightly
  consolidation, per-project exclusions, the Routine proposal. Server `0.5.6`.
- **Follow along (W9, 2026-09-21).** A web tool call's trail row carries the page it went to:
  `ToolResultData.url` (worker `tool_events.url_of`: `web_fetch`'s http(s) `url`; a search query becomes a Bing
  results page — Bing allows framing, DuckDuckGo does not), relayed on `tool_activity_end` and kept on the trail
  row (`chat/services.py remember_tool_call`). The app's Web pane opens it beside the chat. Server `0.5.7`.
- **Nudge (W8 part 2, 2026-09-21).** The caller adds to a persona reply that is still running:
  `POST …/messages/{id}/nudge/ {text ≤ 2000}` (`request_nudge_for_message`: the reply is its caller's to steer —
  403 for anyone else, 409 once finished) queues it on the signal store (`nx:nudge:{msg_id}`, TTL 600 s; the store
  gained list ops for Memory and Redis). The worker's `NudgeGate` (`apps/managers/nudges.py`, interactive runs
  only) polls `GET /internal/messages/{id}/nudges/` after each tool call — pydantic-ai's `after_tool_execute` is
  the one place a running agent reads new words — appends "[The reader adds while you work: …]" to that tool's
  result and emits `nudge_taken`; the relay publishes `{type: nudge_taken, id, text}` and keeps `metadata.nudges`
  (`MessageOut.nudges`). Never lost: when the reply ends or is stopped, `repost_untaken_nudges` posts what the
  persona never reached as an ordinary message from the nudger. A run without tool calls therefore never takes a
  nudge (it arrives as a message). pydantic-ai only (the LiteLLM runner is unmaintained, OPEN-ITEMS). Server `0.5.8`.
- **Runbooks (W6 phase 1, 2026-09-21).** `Runbook(project, title ≤ 120, description ≤ 500, steps JSON 1–12 of
  {persona_id, prompt ≤ 4000, routine_id|null, output_type, on_failure stop|skip|retry})` and
  `RunbookRun(runbook, topic, started_by, status queued|running|done|failed|stopped, current_step, step_results,
  started_at, ended_at, error)` in `nucleus/models/scheduling.py` (migration 0026, which also makes
  `PersonaSchedule.persona` nullable and adds `PersonaSchedule.runbook`: a schedule runs a persona OR starts a
  runbook, `scheduling/services.py` refuses both or neither). Routes under `/projects/{id}/runbooks/`
  (`scheduling/api.py`; the fixed `runs/` paths register before `{runbook_id}/`): reading needs `topic.list` at the
  project, defining `runbook.manage` (Admin), starting and stopping `runbook.run` (Member) PLUS `persona.mention` in
  the topic — a run is the starter's series of mentions — and `topic.create` on the channel when "Run now" makes a
  new topic. Execution is the Celery task `scheduling.tasks.run_runbook` → `scheduling/runbooks.py execute_run`:
  the starter's mention right is re-checked (as a schedule's creator is); every step goes through the ONE trigger,
  `trigger_ai_response_async(..., interactive=False, routine=, output_type=, step_context=<previous reply>,
  runbook_run={id, title, step, of}, triggered_by=starter)`, which now returns the reply's id; the row decides:
  completed → its content is the next step's context, failed → `on_failure` (stop: run failed and the line says
  which step and why; skip: recorded, context unchanged; retry: one more attempt, then the stop rule), a stopped
  reply or a run marked stopped → run stopped. A step's model override comes through its routine (one mechanism;
  the plan's per-step `model_config_id` was dropped as a second path to the same thing). Every transition
  publishes `{type: "runbook_run", id, run}` on the topic and posts system lines (started / finished / failed at
  step n / stopped …); the reply rows carry `metadata.runbook_run` (`MessageOut.runbook_run`, `message_start`
  too). The worker puts `TriggerJob.step_context` into the persona prompt as its own block after the routine's
  (`apps/managers/runbooks.py`, clipped to `RUNBOOK_STEP_CONTEXT_MAX` = 12 000 chars). Phase 2 (condition/output
  steps, Describe, evidence, catch-up) stays in the master plan. Server `0.6.0` (MINOR: new tables and a
  schedule field).
- **Inbound hooks (W12, 2026-09-21).** `InboundHook(project, topic, persona, label, token_hash, token_hint,
  created_by, is_paused, last_fired_at, fire_count, last_status, last_error)` (migration 0027). The token is
  generated once (`secrets.token_urlsafe(32)`), returned by create and regenerate ONLY, and stored as its sha256
  plus its last four characters — nucleus cannot show it again, and says so in the dialog. Management under the
  topic, like schedules (`scheduling/api.py`): list/create/patch/regenerate/delete under `hook.manage` (Admin),
  and creating or regenerating ALSO needs `persona.mention` in that topic — a hook lends a persona's reach to a
  machine, so it may not lend more reach than its maker has. Firing is the ONE public write path in nucleus:
  `POST /api/v1/hooks/{token}/` on a router with no auth (`scheduling/hooks_api.py`; nginx blocks only
  `/api/v1/internal/`), body `{text ≤ 4000, data? ≤ 32 KB}`. It answers 404 for an unknown or removed token (a
  public route must not confirm that a token ever existed), 409 paused, 400 empty text or non-JSON data, 413 too
  large, 429 over 30 fires a minute for that hook (with `Retry-After`), 403 when the creator may no longer call
  personas there — recorded on the hook as `last_error`, which the pane shows, rather than posting a line into
  the chat on every blocked fire. A fire posts `@persona <text>` (plus a fenced json block when `data` came) as
  the creator through `save_user_message`, publishes it, and calls `chat/api.py:_trigger_personas` — the reply is
  the creator's (W22). Rate limiting extends the process's existing shared store (`chat/stop_signals.py` gained
  `incr` and `signal_store()`) rather than opening a second Redis client; a store hiccup never blocks a fire.
  Server `0.6.1` (additive).

**Files:** `authn/permissions/rights.py`, `authn/permissions/models.py` (`ObjectType`), `chat/schema.py`,
`chat/services.py` (`_serialise`, `usage_from`, `with_usage`).
