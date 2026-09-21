# Concepts & Roles

What each core object in NeuralOps actually *is* — the idea behind it, not just
its fields — and the full permissions story: who can create/update/delete
what, what "scope" means, and what owner/admin/member/viewer (and their
project- and topic-level variants) actually get to do.

Everything below is verified against the live code as of this writing —
`nucleus/models/*.py` for the Django models, `authn/permissions/*.py` for the
permission engine — not against what any older doc *says* the system does.
Where the code itself is inconsistent or incomplete, that's called out
explicitly in [Part 5](#part-5--known-gaps-and-inconsistencies) rather than
papered over.

Part 1 covers ten concepts in hierarchy order (Company down to Topic, then the
AI-infrastructure objects, then Context/Knowledge Base) — it reads more
naturally top-down than the Channel → Project → Company → Model → Agent → User
→ MCP Agent → Context → Knowledge Base → Topic order they were originally
asked about, but every concept is still there, just resequenced.

**Contents**
1. [The concepts, one by one](#part-1--the-concepts-one-by-one)
2. [Model / Agent / User / MCP Server — who can create, update, delete, and at what scope](#part-2--creationupdatedelete--scope-for-model-agent-user-mcp-server)
3. [What scope does a user get if invited to just one Topic?](#part-3--the-topic-only-invite-case)
4. [The role hierarchy: Owner, Admin, Member, Viewer — and their project/topic variants](#part-4--the-role-hierarchy)
5. [Known gaps and inconsistencies](#part-5--known-gaps-and-inconsistencies)

---

## Part 1 — The concepts, one by one

### Company

**Philosophy.** The tenant root. Everything else in the system — every
Project, every AI Model, every message — hangs off exactly one Company.
NeuralOps is single-server-per-company by design (see `DECISIONS.md`
principle "One server, one company") — there's no cross-company data sharing
anywhere in the schema, and most other models reach a Company only through a
`company` foreign key, never a join across two different companies. A Company
also owns its own AI configuration (`CompanyAIConfig` — embedding provider,
default LLM) and its own set of permission Roles (see Part 4) — two companies
running the same NeuralOps codebase can have completely different role
definitions.

**Django model** — `nucleus.Company` (`db_table = governance_company`):

| Field | Notes |
|---|---|
| `name`, `slug` | `slug` is globally unique (not just per-something — there's only one Company per server in practice). |
| `is_personal` | Marks a personal/private workspace variant. |
| `owner` | FK to `User`, `on_delete=PROTECT` — the Company can't be deleted out from under its owner by an accidental cascade. |
| `members` | M2M to `User` through `CompanyAccess` (see below). |

`CompanyAccess` (`governance_company_access`) is the through-table: one row
per (company, user), carrying a legacy `role` field
(`owner`/`admin`/`member`/`viewer`), `invited_by`, `joined_at`. This is the
"is this person on the server at all, and what's their headline role"
record — distinct from, and older than, the `RoleAssignment` engine
described in Part 4.

---

### Project

**Philosophy.** The top-level unit of work inside a Company — "Q3 Launch",
"Marketing Site Rebuild". Everything a team actually does (channels, topics,
AI agents, personas, context) is scoped under a Project. A Company can have
any number of Projects, and a Project belongs to exactly one Company. When
someone creates a Project, they're automatically made that project's Admin
(see Part 4) and a default "general" Channel is created for them — a new
Project is never truly empty.

**Django model** — `nucleus.Project` (`workspace_project`), extends
`TenantOperationModel` (company FK + Django's auto-generated
`invite`/`remove`/`archive`/`join` permissions, see Part 5):

| Field | Notes |
|---|---|
| `name`, `slug`, `description` | `slug` unique per company. |
| `members` | M2M to `User` through `ProjectMember` (legacy role field: owner/admin/member/viewer). |

There is no hard-delete path for a Project — only `project.archive`
(soft-delete via `SoftDeleteModel.soft_delete()` / `.restore()`). See UC11 in
`authn/permissions/USE_CASES.md`.

---

### Channel

**Philosophy.** A named subdivision of a Project used to group related
Topics by subject — "Backend", "Design", "general" (the default one every
new Project gets). Channels don't carry messages themselves; they're purely
an organizing layer between Project and Topic. A Channel is not its own
assignable permission scope (see Part 2) — reach into a Channel always comes
from the Project above it.

**Django model** — `nucleus.Channel` (`workspace_channel`), extends
`ProjectOperationModel` (company + project FKs):

| Field | Notes |
|---|---|
| `name`, `slug`, `description` | `slug` unique per project. |

Archived the same way as everything else in this hierarchy —
`channel.archive`, reversible in principle.

---

### Topic (ChatTopic)

**Philosophy.** The actual conversation thread — the unit chat happens in.
Every `ChatMessage`, `ChatSession`, `ChatReadMarker`, `ChatReaction`, and
every attached `ContextSource`/`KnowledgeBase` hangs off a Topic, not off the
Channel or Project directly. This is also the *narrowest* scope in the whole
permission system (see Part 4's `ScopeType`) — it's possible to invite
someone to exactly one Topic and nothing else, which is the scenario Part 3
walks through in detail.

**Django model** — `nucleus.ChatTopic` (`workspace_chat_topic`), extends
`ProjectOperationModel`:

| Field | Notes |
|---|---|
| `channel` | FK — every Topic belongs to exactly one Channel. |
| `title`, `slug` | `slug` unique per channel. |

`TopicParticipant` (`workspace_topic_participant`) is the legacy
membership/role record for a Topic — one row per (topic, user), role choices
`owner` / `moderator` / `participant` / `observer` (default `participant`).
As with `ProjectMember`, this coexists with, and is older than, the
`RoleAssignment` engine — see Part 4.

---

### User

**Philosophy.** One identity model covers both humans and AI personas — a
`User` has a `user_type` of `human` or `persona`. This is deliberate, not
incidental: it means a Persona can be `@mention`ed, appear in a member list,
send a `ChatMessage`, and be added to a Project/Topic using exactly the same
membership machinery as a human, with no special-casing needed throughout
the rest of the codebase. A `persona`-typed User is the "identity shadow"
behind a `Persona` record (see below) — `Persona.identity_user` is a
one-to-one FK to it.

**Django model** — `nucleus.User` (`accounts_user`), a custom
`AbstractUser` with a UUID primary key:

| Field | Notes |
|---|---|
| `user_type` | `human` \| `persona`. |
| `google_sso_id` | Nullable/unique — SSO identity. |
| `display_name`, `avatar` | Shared display fields for both humans and personas. |
| `current_company` | FK, nullable — which Company this user is currently "in" (a user can belong to more than one Company via `CompanyAccess`, but has one active one at a time). |

`nucleus.Human` (`accounts_human`) is a one-to-one profile attached to
human-typed Users: `full_name`, `email` (unique), `timezone`, `locale`,
`phone_number`. Persona-typed Users don't have a `Human` profile — their
profile is the `Persona` record itself.

---

### (AI) Model — AIModel

**Philosophy.** A registered LLM configuration — "GPT-4o", "Claude Haiku" —
company-owned, because registering one means handling a real provider API
key. Every model call in the system goes through LiteLLM, so `model_id` is
always a LiteLLM-format string (`anthropic/claude-haiku-4-5-20251001`,
`openai/gpt-4o`, `ollama/llama3` + `api_base`). An `AIModel` isn't directly
usable by a Project until it's explicitly *attached* — see Part 2, this is a
deliberate two-step (create, then attach) so that creating a model (which
touches its key) and giving a project access to it (which doesn't) are two
different, separately-permissioned actions.

**Django model** — `nucleus.AIModel` (`intelligence_ai_model`), extends
`TenantBaseModel` (company-owned, no project FK):

| Field | Notes |
|---|---|
| `provider` | `litellm` (default, covers every hosted/cloud provider) \| `local` (reserved for a future direct ONNX/llama.cpp runtime). |
| `model_id` | LiteLLM model string. |
| `api_base` | Optional, for self-hosted/Ollama-style endpoints. |
| `api_key_encrypted` | Fernet-encrypted at rest — never touch directly, use `set_api_key()`/`get_api_key()`. |
| `licence_accepted` | Must be true before the model is usable. |
| `temperature`, `max_tokens`, `context_window` | Runtime defaults. |
| `supports_tools` / `supports_streaming` / `supports_vision` / `supports_audio` | Capability flags. |
| `projects` | M2M to `Project` — **visibility gate**, not ownership. An unattached model is invisible to every project (including its own creator's), until a Company Admin explicitly attaches it. |

---

### Agent — AIAgent

**Philosophy.** Where "philosophy" is most literal: an Agent is what turns a
plain LLM into something that can *do* things. It pairs one `AIModel` with
(optionally) one `MCPServer`, so a `Persona` built on that Agent can call
tools, not just talk. Unlike `AIModel`, an Agent belongs to exactly one
Project (via the `projects` M2M, restricted to a single entry by application
code — see the comment in the model itself) — so a Project's own admin can
manage the agents their team actually uses without needing company-wide
access. An `agent_type` of `internal` requires a `model`; `external` requires
an `external_url` instead (two different shapes of "agent," enforced with
`CheckConstraint`s at the DB level).

**Django model** — `nucleus.AIAgent` (`intelligence_ai_agent`), extends
`TenantBaseModel`:

| Field | Notes |
|---|---|
| `agent_type` | `internal` (backed by a local `model`) \| `external` (backed by `external_url` + `secret_ref`). |
| `model`, `mcp_server` | Both nullable FKs — an internal agent needs `model`; `mcp_server` is optional even for an internal agent (a plain-LLM agent with no tools is valid). |
| `safety_mode`, `max_steps`, `allow_parallel_tools` | Guardrails on how much an agent can do per turn. |
| `projects` | M2M, restricted to one project in practice — this is the agent's actual scope. |

---

### MCP Agent — MCPServer

**Philosophy.** "MCP Agent" maps to `MCPServer` in the code — the tool
backend an `AIAgent` calls into (an Odoo ERP connector, a filesystem server,
a SerpAPI shopping search, or anything else speaking the Model Context
Protocol). Like `AIAgent`, it's project-owned (one project via a
structurally-M2M-but-app-restricted-to-one field). It can be `local`,
`docker`, `kubernetes`, `remote`, or `hosted`, over `stdio`, `http`, `sse`,
or `websocket` transport — `CheckConstraint`s enforce that a `stdio` server
has a `command` and an `http`/`sse`/`websocket` server has a `url`.

**Django model** — `nucleus.MCPServer` (`intelligence_mcp_server`), extends
`TenantBaseModel`:

| Field | Notes |
|---|---|
| `server_type` | `local` \| `docker` \| `kubernetes` \| `remote` \| `hosted`. |
| `transport` | `stdio` \| `http` \| `sse` \| `websocket`. |
| `command` / `url` / `docker_image` / `kubernetes_service` | One of these is populated depending on `server_type`/`transport`. |
| `secrets_encrypted` | Fernet-encrypted JSON dict (e.g. `{"GITHUB_PERSONAL_ACCESS_TOKEN": "..."}`) — same encryption pattern as `AIModel.api_key_encrypted`, but a dict since stdio servers often need several env vars at once. Use `set_secrets()`/`get_secrets()`. |
| `is_first_party` | True only for marketplace-published/owned MCP servers — gates whether tool output is even allowed to be embedded (`embed_output`). |
| `projects` | M2M, restricted to one project in practice. |

---

### Context (ContextSource)

**Philosophy.** A file or web URL a user explicitly attaches to a *Topic* as
extra context for AI responses in that conversation — a PDF, a spreadsheet,
a webpage. This is deliberately per-Topic, not per-Project or per-Company:
context you attach in one conversation doesn't leak into every other
conversation by default (that's what `KnowledgeBase`, below, is for). When
attached, nucleus stores the record (`status=pending`), extracts its
content, and calls `nexus-ai`'s `/embed/` endpoint; the returned
`collection_id` is stored back on the record (`status=ready`). Detaching
reverses this — `nexus-ai` is told to delete the embedding collection, then
the record itself is deleted.

**Django model** — `nucleus.ContextSource` (`context_source`), extends
`TenantBaseModel`:

| Field | Notes |
|---|---|
| `topic` | FK — always scoped to one Topic. |
| `type` | `file` \| `web`. |
| `file` / `url` | One or the other depending on `type`. |
| `checksum` | SHA-256 of file content — lets an identical file get attached twice without paying to re-embed it. |
| `collection_id`, `status` (`pending`/`ready`/`error`) | Set by nexus-ai once embedding completes. |

---

### Knowledge Base

**Philosophy.** The company-wide, persistent counterpart to `ContextSource`.
Where a `ContextSource` is one file dropped into one conversation, a
`KnowledgeBase` is a curated, reusable document collection — a product
handbook, a policy library — that can be attached to *multiple* Projects and
multiple Topics at once (both are M2M relationships), so the same knowledge
doesn't have to be re-uploaded into every conversation that needs it.

**Django model** — `nucleus.KnowledgeBase` (`intelligence_knowledge_base`),
extends `TenantBaseModel`:

| Field | Notes |
|---|---|
| `name`, `description` | `name` unique per company. |
| `projects` | M2M — which Projects can see/use this knowledge base. |
| `chat_topics` | M2M — which Topics have it attached. |

`nucleus.KnowledgeFile` (`intelligence_knowledge_file`) is the actual file
content inside a `KnowledgeBase`: `file`, `original_filename`, `mime_type`,
`file_size`, `chroma_collection`, `embedding_status`.

---

## Part 2 — Creation/update/delete & scope for Model, Agent, User, MCP Server

This is driven entirely by `authn/permissions/rights.py`'s `REGISTRY` — the
canonical list of every permissioned action in the system (36 entries as of
this writing), each with a `scope` (the *narrowest* level it can be granted
at; a broader assignment always reaches down to it — see Part 4 for how
"reach" is computed). Nothing below is inferred from the model files alone;
it's the actual `Right` entries that gate the actual API endpoints.

### AI Model

| Action | Right code | Scope | Who reaches it by default |
|---|---|---|---|
| List | `ai_model.list` | Company | Owner, Admin, Member, Viewer (list-only for the last three) |
| Create (incl. setting the API key) | `ai_model.create` | **Company only** | Owner, Admin |
| Delete | `ai_model.delete` | **Company only** | Owner, Admin |
| Attach an existing model to a project | `ai_model.attach` | **Project** | Owner, Admin (company-wide); a **Project Admin reaches this too**, without needing a company-wide assignment |

There is deliberately no `ai_model.update` right in the registry as of this
writing — editing an existing model's non-secret fields isn't yet a
separately-permissioned action.

The `create`/`delete` vs. `attach` split is the key design decision here: a
raw provider API key is company-sensitive, so only a Company-scope
assignment can create or delete a model. But *using* an already-created
model inside one project is lighter-weight and doesn't touch the key, so
`ai_model.attach` is Project-scoped and a Project Admin gets it even with no
company-wide role at all. See UC14/UC15 in `USE_CASES.md` for the worked
example (Sara, a Project Admin, can attach a model Noaman created, but gets
a 403 if she tries to create one herself).

### Agent (AIAgent)

| Action | Right code | Scope | Who reaches it by default |
|---|---|---|---|
| List | `agent.list` | Company | Everyone with the right, **plus** a row-visibility fallback (see below) for everyone else |
| Create | `agent.create` | **Project** | Company Admin (via reach-down) **and** that project's own Project Admin |
| Update | `agent.update` | **Project** | Same as create |
| Delete | `agent.delete` | **Project** | Same as create |

Unlike `AIModel`, an Agent belongs to exactly one project structurally
(`AIAgent.projects`, restricted to a single entry by application code — see
`intelligence/services.py`), so its create/update/delete rights are
Project-scoped from the start — no separate "attach" step exists or is
needed. A Project Admin on "Q3 Launch" can fully manage agents inside "Q3
Launch" but gets a 403 (`_scope_chain` never reaches their assignment) if
they try to touch an agent that belongs to a different project — see
UC16/UC17 in `USE_CASES.md`.

`agent.list` is Company-scoped, but a plain Member with no company-wide
assignment still isn't locked out of seeing agents — `row_rules.py`'s
`visible_agents(user, company)` is what the list endpoint actually calls:
broad case (holds `agent.list`) returns every agent in the company; narrow
case falls back to every agent attached to a project the user can reach at
all (via `_reachable_project_ids`). This same broad/narrow shape is reused
for `visible_ai_models`, `visible_mcp_servers`, and (in its own
single-project form) `visible_personas` — see UC13.

### User

There's no single `User` model with its own CRUD rights the way
Model/Agent/MCP Server have — a User's *membership* in the system is what's
actually permissioned, at three nested levels:

| Action | Right code | Scope | Who reaches it by default |
|---|---|---|---|
| Invite/add someone to the Company | `company.invite_member` | **Company** | Owner, Admin — **but see Part 5: the endpoint doesn't actually check this right** |
| Remove someone from the Company | `company.remove_member` | **Company** | Owner, Admin — **same caveat** |
| Add/remove someone at Project level | *(no dedicated right exists — see Part 5)* | — | Currently: any authenticated user who can resolve the project at all |
| Add someone to one Topic only | via `PermissionChecker.assign_role(user, role, topic, ...)` inside `invite_to_project(..., scope="topic")` | **Topic** | Whoever is doing the inviting, through the project's own invite flow |

`invite_to_system()` in `workspace/services.py` is the one true entry point
for company membership — every project- or topic-scoped invite calls it
first (idempotently) to guarantee the invitee is a real company member
(`CompanyAccess` row + a Company-scope `RoleAssignment`) before layering a
narrower Project- or Topic-scope grant on top. A brand-new email (not yet a
platform user at all) instead gets a pending `Invitation` record with a
signed token; the actual membership + `RoleAssignment` are created later,
when they accept, in `auth_verify()` → `_add_user_to_invited_project()`.

A Persona (a `user_type=persona` User) is added to a project the same way a
human is — through `ProjectMember` — just via `persona_name` instead of
`email` in the invite payload; see `invite_to_project()`.

### MCP Agent (MCPServer)

| Action | Right code | Scope | Who reaches it by default |
|---|---|---|---|
| List | `mcp_server.list` | Company | Everyone with the right, plus row-visibility fallback (`visible_mcp_servers`) for everyone else |
| Create | `mcp_server.create` | **Project** | Company Admin (reach-down) **and** that project's own Project Admin |
| Update | `mcp_server.update` | **Project** | Same as create |
| Delete | `mcp_server.delete` | **Project** | Same as create |

Exactly the same shape as Agent above — project-owned in practice, so
create/update/delete are Project-scoped and a Project Admin doesn't need any
company-wide assignment to manage the MCP servers their own team registered.

### Persona Schedule (#189)

Not one of the four resources originally asked about, but it's in the same
registry and follows a third pattern worth noting — the *ownership-check*
pattern:

| Action | Right code | Scope | Who reaches it by default |
|---|---|---|---|
| Create a scheduled persona query | `schedule.create` | **Topic** | Owner, Admin, Member — same tier as `session.create`/`persona.mention` |
| Pause/resume/delete **someone else's** schedule | `schedule.manage` | **Topic** | Owner, Admin only |

The split is deliberate: a Member who created a schedule can always
pause/delete *their own* via an ownership check in `scheduling/services.py`
(`PersonaSchedule.created_by == user`), independent of holding
`schedule.manage`. `schedule.manage` is only what lets someone act on a
schedule they did *not* create (e.g. an Admin cleaning up after someone who
left) — the same shape as `topic.archive` being separate from `topic.create`.

### Summary — Company scope vs. Project scope, at a glance

| Resource | Create/Delete scope | Why |
|---|---|---|
| AI Model | **Company only** | Touches a real provider API key |
| Agent | **Project** | Belongs to exactly one project; no secret of its own beyond what its Model/MCP Server already encrypt |
| MCP Server | **Project** | Same reasoning as Agent |
| Persona | **Company only** | Not yet revisited since the AI-resource permission redesign — see Part 5 |
| Schedule | **Topic** | Member-tier action; `schedule.manage` gates only other people's schedules |
| Preflight / tool approval (`persona.approve_run`) | **Topic** | Member-tier, like calling a persona: whoever can talk to it can approve what it proposes |
| Routine, Runbook, Inbound hook (`*.manage`) | **Project** | Definitions shared by the project; Admin-tier. `runbook.run` is Member-tier |
| Recall entry, Deliverable (`*.manage`) | **Project** | Team-curated content written by personas or kept from replies; Member-tier |
| Company membership (invite/remove) | **Company** | *(right exists but is bypassed at the endpoint — see Part 5)* |
| Project membership | *(ungated — see Part 5)* | — |
| Topic membership | Granted via the project's own invite flow, scoped to that one Topic | — |

---

## Part 3 — The topic-only-invite case

This is meant to be the narrowest scope the system supports — "invite
someone into exactly one conversation, nothing else." The intended design
(per `ROLE_STORIES.md` / `USE_CASES.md` UC4) and what the current code
actually does turn out to diverge here, so both are worth walking through.

When a Project Admin invites someone with `scope="topic"` and a specific
`topic_id` (`POST /projects/{id}/team/invite/` → `invite_to_project()`),
there are **two different code paths** depending on whether the invitee
already exists as a platform user. Both end in the same place.

**Path A — the invitee already has a NeuralOps account (but isn't on this
company yet).** Everything happens synchronously:

1. `invite_to_project()` calls `invite_to_system()` first. Finding a `User`
   with that email but no `CompanyAccess` row, it creates the `CompanyAccess`
   row **and** a **Company-scope** `RoleAssignment` using the `role` passed
   in — `"member"` by default, i.e. the RBAC engine's `Member` role assigned
   at `ScopeType.COMPANY`.
2. Back in `invite_to_project()`, because `scope="topic"` was passed, it
   calls `_add_to_topic()` (creates a `TopicParticipant` row, legacy field)
   and — separately — `PermissionChecker.assign_role(user, role, topic,
   granted_by=inviter)`, a **Topic-scope** `RoleAssignment` anchored to that
   one `ChatTopic` alone.

**Path B — the invitee is a brand-new email, not a platform user at all.**
`invite_to_system()` instead creates a pending `Invitation` carrying
`access_payload={"project_id", "scope", "topic_id"}`, returns
`is_new_user: True`, and `invite_to_project()` **returns early** — no grants
yet. The grants happen later, on first connect, in `auth_verify()`
(`authn/services.py`): it accepts the invitation, creates `CompanyAccess`,
assigns a **Company-scope** `RoleAssignment` for `invitation.role`, adds the
user to the matching Django `Group`, then calls
`_add_user_to_invited_project()` — which mirrors Path A step 2 exactly,
adding the **Topic-scope** assignment.

**Either way, the invitee ends up holding both a Company-scope and a
Topic-scope assignment — and the narrow-scoping intent dies on the broader
one.** `ScopeType` reach flows downward from `COMPANY`, so a Company-scope
`RoleAssignment` reaches *every* Project and Topic in the company for any
right whose own scope is `PROJECT` or `TOPIC` — and
`DEFAULT_ROLE_RIGHTS["Member"]` is not a trivial set: `project.list`,
`project.view`, `channel.list`, `topic.create`, `topic.list`, `topic.update`,
`topic.mark_read`, `session.create`, `session.close`, `persona.mention`,
`schedule.create`, and every `*.list` right for AI infrastructure. Traced
through `PermissionChecker._matching_assignments()`: checking
`can(invitee, "topic.list", obj=some_unrelated_topic)` builds a chain for
that unrelated topic ending in `(COMPANY, company.id)`; the invitee's
Company-scope Member assignment matches that chain entry, and `Member` holds
`topic.list` — so the check returns **`True`**, not the `False` UC4
describes. The Topic-scope assignment doesn't narrow anything, because a
broader grant already sits alongside it (assignments are additive, never
subtractive — see Part 5).

The *intended* narrow behavior — and the one that does hold when a person's
**only** assignment is the Topic-scope one (e.g. someone re-invited who was
already a company member with no broader role, where `invite_to_system()` is
a genuine no-op) — is `row_rules.py`'s "waypoint, not full access" pattern:
`visible_projects()` surfaces just the parent Project (via
`_reachable_project_ids`, which walks a topic-scoped assignment up to its
parent project); `visible_channels()` surfaces just the Channel containing
their Topic; `visible_topics()` surfaces just that one Topic. This is the
behavior `ROLE_STORIES.md` describes and worth treating as the source of
truth for *intent* — see Part 5 for why it doesn't reliably hold today.

This is the same scenario as UC4 in `authn/permissions/USE_CASES.md`, and
it's meant to be the concrete enforcement point for the `ROLE_STORIES.md`
line: *"As a Topic Member, I should not be able to see or act on any other
topic in the same channel or project, until someone explicitly adds me
there too, or promotes me to a broader scope."* Whether it actually holds
depends entirely on whether the invitee already had a company-scope role
beforehand.

If that person is later promoted to Project Admin (a second,
Project-scoped `RoleAssignment` is added — assignments are additive, never
replacing), their effective rights on every topic in that project become the
*union* of both assignments (see UC5) — same additive mechanism, just
intentional this time.

---

## Part 4 — The role hierarchy

There are, in the actual codebase today, **three separate mechanisms** that
all answer some version of "is this user allowed to do X" — not one. They
overlap in places and this section is written to make that overlap explicit
rather than pretend only one of them exists.

### The three systems

**1. The RBAC engine — `Right` / `Role` / `RoleAssignment` /
`PermissionChecker`.** This is the system everything in Parts 2–3 above
describes, and it's the one actually enforced on almost every endpoint
(`PermissionChecker.can(...)` calls throughout `workspace/api.py`,
`intelligence/api.py`, `chat/api.py`, `scheduling/api.py`). Its own
docstring in `checker.py` says it plainly: *"Nothing else in the codebase
should make a permission decision directly... if a new kind of check is
needed, it's a new Right in `rights.py`, not a new if-statement somewhere
else."* Three tables:

- **`Right`** — a flat registry of 36 possible actions (`project.create`,
  `topic.mark_read`, `ai_model.attach`, `schedule.manage`, ...), each tagged
  with the *narrowest* `ScopeType` it can be granted at.
- **`Role`** — a named, **company-specific** bundle of Rights (the
  "philosophy," per the model's own docstring). **Not hardcoded to exactly
  four** — every company gets Owner/Admin/Member/Viewer seeded by
  `manage.py seed_permissions`, but any company can rename, edit, or add
  entirely custom roles (`Role.company` is a required FK). `USE_CASES.md`
  UC8 walks through a real example: a narrow "Persona Builder" role, stacked
  on top of someone's existing Project Admin assignment, granting exactly
  `persona.create`/`update`/`delete` and nothing else.
- **`RoleAssignment`** — the actual grant: (user, role, scope_object_type,
  scope_object_id). A user can hold **multiple** assignments simultaneously
  — they're additive, and `PermissionChecker` takes the union of every
  reachable role's rights, never picks "the highest one."

`ScopeType` has exactly three levels, and reach flows **downward only**:
`COMPANY` (0) → `PROJECT` (1) → `TOPIC` (2). A Company-scope assignment
reaches every Project and Topic inside it; a Project-scope assignment
reaches that project and every Topic inside it, but not sibling projects; a
Topic-scope assignment reaches only that one Topic. This is computed by
`_scope_chain()` in `checker.py`, walking each model's actual FK hierarchy
up to Company (Channel/Topic → Project → Company; AIAgent/MCPServer →
their one attached Project → Company).

**2. The legacy membership/role fields — `CompanyAccess.role`,
`ProjectMember.role`, `TopicParticipant.role`.** Three separate
`TextChoices` fields, pre-dating the RBAC engine:

- `CompanyAccess.Role`: `owner` / `admin` / `member` / `viewer`
- `ProjectMember.Role`: `owner` / `admin` / `member` / `viewer`
- `TopicParticipant.Role`: `owner` / `moderator` / `participant` / `observer`

These are **still actively written** alongside the RBAC engine, not
abandoned — `create_project()`'s own comment explains why:

> *"Legacy membership record -- kept alongside the new RoleAssignment below
> so untouched code that still reads ProjectMember directly (list_team,
> add_member, invite_to_project, etc.) keeps working during migration."*

In other words: every place that grants a `RoleAssignment` today (project
creation, company/project/topic invites) also writes the matching legacy
row, so both systems stay in sync for anything going through the current
service functions. But `list_team`, `_format_member`, and the whole `/team/`
API surface *read* only the legacy `ProjectMember.role` field — they don't
consult `PermissionChecker` at all for display purposes. See Part 5 for the
sharper edge of this: the `/team/` endpoints don't consult
`PermissionChecker` for *authorization* either, not just display.

**3. Django's built-in auth permission framework.** A third, mostly
separate path, used by exactly two endpoints in the whole system —
`POST /members/invite/` and `DELETE /members/{user_id}/` in
`workspace/api.py` — which gate on `user.has_perm("nucleus.add_invitation")`
/ `user.has_perm("nucleus.remove_invitation")`. These are Django's own
auto-generated model permissions, created because `Invitation` extends
`TenantOperationModel`, whose `default_permissions` is
`("add", "view", "change", "delete", "invite", "remove", "archive", "join")`
(see `OPERATION_PERMISSIONS` in `nucleus/models/base.py`) rather than
Django's stock four.

This system **is** wired up, contrary to what an earlier draft of this
document assumed — `create_owner.py`'s `_create_default_groups()` creates
Django `Group` rows named Owner/Admin/Member/Viewer and populates their
permissions, and `auth_verify()` adds each accepted invitee to the `Group`
matching their role. What it grants is uneven, though — see Part 5.

### The role tiers themselves (from `ROLE_STORIES.md`)

These are the four roles every company's RBAC engine is seeded with. Read
each as "at the scope it's assignable at," because — this is the important,
non-obvious part — **not every role exists at every scope**:

**Owner — Company scope only.** No Project Owner and no Project-tier Owner
exists in the RBAC engine (Admin is the ceiling at Project and Topic scope
— see below). Has every Right, no exceptions, including the one action
nothing else can do: delete the Company entirely. Cannot be removed by
anyone, including another Admin — there must always be exactly one, and the
last Owner can't be stripped. There is deliberately no ownership-transfer
action; replacing an Owner means re-running `manage.py create_owner`, not a
"transfer" click.

**Admin — exists at all three scopes, with different reach at each:**
- *Company Admin*: invite/remove company members; create projects;
  create/delete AI Models (including keys) and Personas — these two stay
  Company-scope-only regardless of who holds Admin; create/update/delete
  Agents and MCP Servers in *any* project, and attach existing models to any
  project — company-wide reach without needing a separate assignment per
  project; `schedule.manage` across any topic. Cannot delete the company or
  remove the Owner. **Peers are off limits:** an Admin manages Members and
  Viewers (and may promote a Member to Admin), but only the Owner changes,
  re-scopes or removes another Admin — enforced by `_refuse_peer()` in
  `workspace/services.py` on the access editor, both server-removal routes
  and project-team removal (a role-name check, so an Admin scoped to one
  project counts as an Admin here too).
- *Project Admin*: create channels/topics inside their own project;
  create/update/delete Agents and MCP Servers *in their own project only*
  (this is what Part 2's Project-scope table reflects — deliberately moved
  down from Company scope specifically so a Project Admin reaches it, see
  UC16/UC17); attach an existing AI Model to their project (`ai_model.attach`
  — but still cannot create/delete a model or see its key); archive their
  own project/channels/topics (reversible, not the old irreversible
  `project.delete` that used to be Owner-only). Still cannot create, delete,
  or see the key on an AI Model, and still cannot touch Personas at all —
  both remain Company-scope-only.
- *Topic Admin*: manage settings and participants within one topic only.
  Nothing above a Topic exists for this assignment to reach — can't create a
  sibling topic or a channel.

**Member — exists at Project and Topic scope only. There is no
company-wide Member tier** *by intent* — though Part 3 shows the invite flow
grants exactly that in practice.
- *Project Member*: create topics inside any channel in their project; open
  and close AI sessions; `@mention` personas; create schedules. Cannot
  create a channel (Admin-only) and cannot manage a schedule someone else
  created.
- *Topic Member*: chat, mark the topic read, open a session, `@mention`
  personas — but only in the one topic they were added to (this is Part 3's
  scenario in full).

**Viewer — exists at all three scopes, same behavior at each.** Sees
everything at their scope (projects, channels, topics, messages) but cannot
create anything, open a session, or `@mention` a persona — read-only means
read-only, not "read plus trigger AI." The one exception is
`topic.mark_read`, which every role gets: it's a personal read-state marker,
not a write to shared content. `ROLE_STORIES.md` itself flags Viewer as "not
yet reviewed" against the same scope-narrowing Owner and Member went
through — worth treating as provisional rather than final.

**Custom roles** are a first-class capability, not a workaround — a company
isn't limited to these four names or shapes. `ROLE_STORIES.md`'s own worked
example, "Persona Builder" (Company scope), holds exactly
`persona.create`/`update`/`delete` and nothing else — no membership rights,
no project creation, no AI Model/MCP Server/Agent access — and is meant to
be *stacked* alongside someone's existing Member or Admin assignment (UC8),
not to replace it.

### How the legacy role choices line up with the RBAC tiers

| Legacy field | Choices | RBAC-engine reality |
|---|---|---|
| `CompanyAccess.role` | owner / admin / member / viewer | Matches the RBAC engine's four company-seedable roles directly — `invite_to_system()` looks up `Role.objects.filter(name=role.capitalize())` using this same string. |
| `ProjectMember.role` | owner / admin / member / viewer | The `owner` choice exists in the schema, but **the RBAC engine has no Project Owner tier** — `create_project()` sets the creator's legacy `ProjectMember.role` to `Role.ADMIN`, not `OWNER`, and assigns them the RBAC `Admin` role, not a project-level Owner. In practice `owner` at project level is unused vocabulary left over from before the "no Project Owner" decision in `ROLE_STORIES.md`. |
| `TopicParticipant.role` | owner / moderator / participant / observer | Doesn't map onto the RBAC engine's role names at all — `_add_to_topic()` always creates new topic participants with the default `PARTICIPANT` role, and the RBAC engine's Topic-scope roles are still named Admin/Member/Viewer, not moderator/participant/observer. These are two independent vocabularies describing the same relationship. |

---

## Part 5 — Known gaps and inconsistencies

Documented here rather than smoothed over, consistent with how the rest of
this repo's docs (`STORY.md`, `DECISIONS.md`) treat known rough edges — these
are things to be aware of, not things this document is pretending are solved:

- **A "topic-only" invite leaks company-wide `Member` visibility.** Traced
  through the actual code in Part 3: because `invite_to_project()` always
  routes company membership through `invite_to_system()`, and that step (or,
  for a brand-new email, `auth_verify()` at acceptance time) grants a
  **Company-scope** `RoleAssignment` for the RBAC `Member` role, a person
  "invited to just one Topic" ends up holding `project.list`/`project.view`/
  `channel.list`/`topic.list`/`topic.create`/`topic.update`/`session.create`/
  `session.close`/`persona.mention`/`schedule.create` and every
  AI-infrastructure `*.list` right across the *entire* company — not just
  the one Topic named in the invite — because `ScopeType` reach flows
  downward from `COMPANY` and none of those rights are excluded from the
  default `Member` set. The Topic-scope `RoleAssignment` added on top is
  real but redundant: it doesn't narrow anything, since the broader
  Company-scope grant already reaches everywhere the narrower one does.
  This directly contradicts the "topic-only invite stays narrow" behavior
  `ROLE_STORIES.md` and `USE_CASES.md` UC4 describe as the intended design.
  It only fails to leak for the narrower case of *re-inviting* someone who
  is already a company member with no broader role — there, `invite_to_system()`
  is a genuine no-op and the Topic-scope assignment is the only one they hold.

- **Project team management borrows `project.archive` as its gate.**
  `add_member`, `invite_to_project` and `remove_team_member` in
  `workspace/api.py` now go through `_require_team_manager()`, which asks
  `PermissionChecker.can(user, "project.archive", obj=project)` — the same
  right the web app's team dialog draws its add/remove controls from, so a
  Project Admin manages their own project's team and a Member or Viewer gets
  a 403 (until 2026-09-13 the only barrier was `_resolve_project()`, i.e.
  being able to *view* the project). `remove_from_server`
  (`DELETE /projects/server/members/{user_id}/`) is gated on
  `company.remove_member`; it used to call only `_resolve()`. `list_team`,
  `available_users` and `available_personas` stay view-gated. There is still
  no `Right` in the registry for team management itself — a
  `project.invite_member` / `project.remove_member` pair would let the gate
  say what it means instead of borrowing the archive right.

- **The company-level `/members/` router bypasses the RBAC engine, and its
  Django-permission substitute is mis-tiered.** `invite_member` and
  `remove_member` check `user.has_perm("nucleus.add_invitation")` /
  `"nucleus.remove_invitation"` — Django's stock auth framework — instead of
  `PermissionChecker.can(user, "company.invite_member"/"company.remove_member")`.
  Those two rights exist in `rights.py` at COMPANY scope and are granted to
  Owner and Admin only, but **nothing reads them**; the Django groups decide
  instead. Tracing what those groups actually hold
  (`create_owner._create_default_groups()`):

  | Django Group | Permission set | `add_invitation` | `remove_invitation` |
  |---|---|---|---|
  | Owner | all `nucleus` perms | ✅ | ✅ |
  | Admin | all except `delete_company`/`remove_company` | ✅ | ✅ |
  | Member | `add_*` \| `change_*` \| `view_*` | ✅ **(unintended)** | ❌ |
  | Viewer | `view_*` only | ❌ | ❌ |

  So the endpoints do work for Owner and Admin — but because
  `add_invitation` matches the blanket `codename__startswith="add_"` filter,
  **an ordinary Member can invite people to the company**, which the RBAC
  side deliberately restricts to Owner/Admin. Two further wrinkles: the
  groups only exist after `manage.py create_owner` has run (it's the only
  caller of `_create_default_groups()`), and `Group.objects.get_or_create(name="Owner")`
  has no company FK — Django groups are global, harmless under
  one-company-per-server but a latent problem if that ever changes. The
  clean fix is to switch both endpoints to `PermissionChecker` and let the
  Django groups go back to being admin-site-only.

- **Two membership systems are kept manually in sync, not unified.** Every
  current invite/create path writes both the legacy role field
  (`CompanyAccess`/`ProjectMember`/`TopicParticipant`) *and* a
  `RoleAssignment` — correctly, as of this reading — but nothing enforces
  that they can't drift apart if a future code path updates one without the
  other. `list_team`/`_format_member` (what the Team UI actually renders)
  reads only the legacy field, so a `RoleAssignment`-only change (e.g. via
  `PermissionChecker.assign_role()` called directly, bypassing the service
  functions) wouldn't show up in the Team list at all.

- **`Role.scope` is seeded inconsistently with how roles are actually
  used.** `seed_permissions` currently seeds all four default roles at
  `scope="company"` regardless of where they end up being assigned — flagged
  directly in a code comment inside `create_project()`: *"fetched by name
  regardless of this Role row's own `scope` field... which is the still-open
  inconsistency flagged earlier (Role.scope forcing one assignment level
  vs. the same Role being assignable at any scope). Revisit once that's
  decided."* In practice this doesn't currently break anything (nothing
  reads `Role.scope` to reject an assignment), but it means the field
  doesn't reliably describe what it claims to.

- **Persona and AI Model permissions haven't been revisited since the
  Agent/MCP Server split.** `agent.*` and `mcp_server.*` create/update/delete
  moved from Company to Project scope specifically so a Project Admin
  reaches them (UC16/UC17) — but `persona.*` and `ai_model.create`/`delete`
  were deliberately left Company-scope-only, and `ROLE_STORIES.md` notes
  Persona specifically as not yet revisited. If Personas are meant to
  eventually get the same Project-scope treatment Agents got, that's an
  open design question, not something already decided.

- **Viewer's per-scope behavior is marked "not yet reviewed."** Unlike
  Owner and Member, which were explicitly narrowed to specific scopes during
  the RBAC redesign, `ROLE_STORIES.md` leaves an open question about whether
  Viewer should still exist at all three scopes the same way, given that
  Owner and Member both lost scopes in the same pass.
