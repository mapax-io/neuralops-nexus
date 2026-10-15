# Concepts & Roles

**Document version: 2.0 (2026-10-15).** Rewritten from scratch against the
code as it stands at the close of Step 7 (the pre-revamp version is in
`docs/_archive/CONCEPTS-AND-ROLES-pre-revamp.md` — it described AIModel,
AIAgent, LiteLLM and tables that no longer exist). Verified against
`nucleus/models/*.py` and `authn/permissions/*.py`, not against older docs.

| Version | Date | What changed |
|---|---|---|
| 2.0 | 2026-10-15 | Full rewrite for the post-revamp architecture (Steps 0–7) |

What each core object *is* — the idea, not just the fields — and the full
permissions story: rights, roles, scopes, row visibility, and what the four
default roles actually get.

---

## Part 1 — The concepts, one by one

### Company
The tenant root. One active Company per server ("one server, one company").
Everything hangs off it; it owns the role definitions, the AI config
(`CompanyAIConfig`: embedding provider, default/utility/router models), and
the members through `CompanyAccess` (one row per person: the headline role
owner/admin/member/viewer, who invited them, when). The owner is created by
the portal claim flow (or `create_owner` on an air-gapped box) — first
verified claim wins.

### Project
The unit of work. A project is BORN provisioned: a "general" channel, the
reserved **configure topic** (visible only to the four admin-tier roles), one
internal MCPServer row carrying the four capabilities
(filesystem/shell/web_search/web_fetch) pointed at the project's own folder
(`PROJECTS_ROOT/<slug>-<id8>`), the four built-in routines, and the "Draft
and review" template chain. The creator becomes that project's Admin. A
project also carries its `brief` (instructions every persona follows), its
`embedder` spec (+ `reindex_status` lock while memory rebuilds), and is
archived, never hard-deleted.

### Channel
A named subdivision of a project that groups topics — purely organizing, no
messages of its own, and NOT an assignable permission scope: reach into a
channel always comes from the project above it.

### Topic (ChatTopic)
The conversation thread — messages, sessions, read markers, context sources,
schedules and hooks all hang off a topic. It is the NARROWEST permission
scope: a person can be invited to exactly one topic (Part 4). One topic per
project is special: `is_configure=True` — the provisioning room. The flag
never reaches the API; the topic simply appears in lists for the four roles
and for nobody else, enforced in row visibility on every road (a direct
topic invite does not pierce it).

### User (humans and persona shadows)
One identity model for both: `user_type` human | persona. A persona-typed
User is the "identity shadow" behind a Persona record, so a persona can be
@mentioned, listed and shown with an avatar through the same machinery as a
person. Humans sign in with Supabase (the identity anchor) or — offline —
with a local password they set themselves (an HS256 token signed by THIS
server; `LOCAL_LOGIN_ENABLED` can turn the door off).

### ModelConfig (replaced AIModel)
One model endpoint: provider + the BARE model name as two columns (the
pydantic-ai string "provider:model" is composed at the boundary by
`qualified_id`), an optional api_base, a Fernet-encrypted API key, capability
flags, and the admin's three optional price overrides (per million input /
cached / output). Company-owned; a project only sees it once ATTACHED
(`model_config.attach` — a lighter right than creating, because attaching
never touches the key). Deleting is refused while any persona uses it.
Generation settings (temperature, max_tokens) are NOT here — they are
per-persona.

### Persona (absorbed AIAgent)
The composite: exactly one ModelConfig (`model` — the field name
`model_config` is reserved by Pydantic), an optional advisor model, optional
router/deep seats (the router screens cheaply, the deep model takes over on
escalation; an empty router seat fills from the company default), 0..3
ordered fallback models, and 0..N MCP servers. "Agent-ness" is emergent: no
servers = a plain LLM. Plus: its prompt, temperature/max_tokens/max_steps,
`tool_levels` (auto/ask/off per capability or tool), `acts_after_approval`
(propose a plan first), `tool_access` (all|selected), `approval_scope`
(topic|requester_only), `delegation_enabled` (may call another persona, depth
1), `recall_enabled`. Project-owned, not shared, not transferable.

### MCP Server (two kinds in one table)
`is_internal=True` = a pydantic-ai capability configured purely by
`capability_config` — nothing is dialled, no credentials exist (DB
constraints enforce it). `is_internal=False` = a real server reached over
stdio/http/sse/websocket, with Fernet-encrypted secrets, a stored `tools`
list ([{name, description, read_only}] — fetched through the engine at
save + the Refresh button; a tool counts as read-only only if the server
itself says so, unlabeled = write = asks), and one of three auth styles:
none, static secrets, or OAuth2 — where OAuth has three roads: dynamic
client registration (the MCP standard — the install registers ITSELF, PKCE,
no pre-registered list), the famous-three vendor presets
(GitHub/Drive/Atlassian via the portal relay; the client secret never ships),
and paste-your-own (the universal/air-gapped fallback). Project-owned.

### Routine
A saved per-turn preset invoked with `/name`: instructions, optional tool
narrowing (never widening), optional model swap — for ONE reply. Four
built-ins per project (pr-description, incident-summary, weekly-digest,
meeting-notes): editable, never deletable.

### Chain (the Runbook table, grown up in Step 7)
A saved multi-step run: 1–12 steps, each `kind: "persona"` (a persona + a
prompt, each step building on the one before) or `kind: "checkpoint"` (the
run parks and WAITS for a person's answer — the starter or the four roles
answer; 24h expiry applies the step's own stop/skip). One optional
**supervisor** persona reviews EVERY stage — APPROVE / REDO with notes
(reruns the stage, bounded by `redo_limit`, cap 2) / FAIL — visibly, in the
topic. A RunbookRun row is the execution: statuses
queued/running/waiting/done/failed/stopped, per-step results, the persisted
context. The starter is the actor of every step, rights re-checked. A chain
with a checkpoint cannot be scheduled.

### Schedule (PersonaSchedule)
WHEN something fires: celery-beat rows (interval/crontab/clocked), firing a
persona's query or starting a (checkpoint-free) chain in a topic. The
creator is the actor of every fire, re-checked each time; every scheduled
fire is unattended (`interactive=False`) — the persona decides-and-notes
instead of asking questions.

### Inbound hook
A public URL (`/hooks/{token}/`) that makes one persona answer in one topic
AS the hook's creator — the token is the credential; rate-limited and
size-capped; unknown tokens answer a flat 404.

### Context sources, Recall, Deliverables
Context sources: files/web pages attached to a topic, embedded for
retrieval (the context panel shows the tree). Recall: short
decisions/facts/preferences personas record about a project, deduplicated,
read into every reply there, curated under `recall.manage`. Deliverables:
outputs the team KEPT under a name — the same title again is a new version,
never an overwrite.

### Gateway token
A personal `nxg_…` token that lets outside MCP clients (Claude Desktop,
Cursor…) use this server as a tool through `POST /api/v1/mcp/`. Minted in
the UI by the four roles, stored hashed, shown once, revocable; it always
acts AS its person — no token can do more than the person it belongs to.
Personas use the same door from inside with no token (the engine's internal
key + the person's id).

### Usage records (the money tables)
One row per model call, the engine's own numbers, priced at insert
(admin override → online catalog → unpriced-but-counted). NO foreign keys on
purpose — billing rows survive any deletion. Every money figure everywhere
is labeled "estimated — prices not confirmed". Full detail stays on the
install; the only number that ever leaves is phone-home's one all-time token
total.

### PausedRun (durable approvals and questions)
When a persona must ask — a tool approval or an ask_user question — the
engine parks the run's whole state in a database row BEFORE its stream ends.
Decisions are recorded once per call (who, what, when); when every pending
call is decided, the run resumes by itself; after 24 hours an undecided run
is resumed with deny / "nobody answered". Rows, not cache: approvals survive
a restart.

---

## Part 2 — The rights system

Four tables: **Right** (one row per action in the registry — 49 today),
**Role** (a named bundle per company; four are seeded), **RoleRight** (what a
role grants — editable live by whoever holds `role.update`, Owner only by
default), **RoleAssignment** (this person holds this role AT this scope:
company, project, or topic).

**Scope and reach.** Every right declares the NARROWEST scope it can be
granted at; reach flows DOWNWARD — a company-scoped Admin reaches every
project-scoped right in every project, a project-scoped Admin reaches them in
their project only, and never upward (a project Admin never reaches a
COMPANY-scope right like `model_config.create` or `project.embedder`).

**"The four roles"** (a phrase used all over the rulings) = company
owner/admin + project owner/admin — mechanically, whoever reaches a
PROJECT-scope right like `project.update` or `gateway.token` for that
project. The configure fence, token minting and checkpoint answering all
draw this exact line.

**Row visibility is the second half.** Holding `project.list` does not show
you every project: `authn/permissions/row_rules.py` filters every list
(projects, channels, topics, personas, MCP servers, model configs) down to
what THIS person's assignments reach — an invisible thing answers like a
nonexistent one, on every road (API lists, chat, search, the gateway).

**Fail closed.** `PermissionChecker.can()` RAISES on a right code the
database hasn't seen (a server that skipped `seed_permissions`). Anything in
row rules or background paths wraps that and fails CLOSED — a feature hides
rather than crashing or opening.

**Adding a right:** one line in `authn/permissions/rights.py` REGISTRY +
which default bundles get it, then `manage.py seed_permissions` (safe to
re-run; it create-or-updates).

### The 49 rights, grouped (code — narrowest scope — what it gates)

**Company:** `company.invite_member`, `company.remove_member` (both COMPANY);
`role.update` (COMPANY — edit what a role grants; Owner-only by default);
`company.local_password` (COMPANY — reset someone ELSE's offline password;
your own needs no right); `gateway.token` (PROJECT — mint gateway tokens;
company-level holders manage every token).

**Project:** `project.create`, `project.list` (COMPANY — no project to reach
up from yet); `project.view`, `project.update`, `project.archive`,
`project.terminal`, `project.browser`, `model_config.attach` (PROJECT);
`project.embedder` (COMPANY on purpose — a rebuild locks the project).

**Channel:** `channel.create/list/update/archive` (PROJECT — channels are
never their own scope).

**Topic:** `topic.create`, `topic.list` (PROJECT); `topic.update`,
`topic.mark_read`, `topic.archive` (TOPIC — grantable on one topic alone).

**Chat/AI use:** `session.create`, `session.close`, `persona.mention`,
`persona.approve_run` (all TOPIC — using AI is member work, grantable
narrowly); `schedule.create`, `schedule.manage` (TOPIC — a creator always
manages their OWN schedule by ownership, schedule.manage is for other
people's).

**AI infrastructure:** `persona.list`, `mcp_server.list`,
`model_config.list` (COMPANY — ordinary members see rows through visibility
fallbacks instead); `persona.create/update/delete`,
`mcp_server.create/update/delete` (PROJECT — these belong to one project and
its own Admin manages them); `model_config.create/update/delete` (COMPANY —
registering a model touches a real API key, company-wide by nature).

**Team AI operations:** `routine.manage`, `runbook.manage`, `hook.manage`
(PROJECT, Admin-tier — defining things); `runbook.run`, `recall.manage`,
`deliverable.manage` (PROJECT, Member-tier — using and curating).

**Money:** `usage.view_project` (PROJECT), `usage.view_company` (COMPANY);
topic totals need no right — seeing the topic is the gate.

---

## Part 3 — The four default roles

Seeded by `seed_permissions`, editable afterwards like any role (Owner's
`role.update`). A starting point, not a law.

| | Owner | Admin | Member | Viewer |
|---|---|---|---|---|
| Everything in the registry | ✓ | | | |
| Members, local-password resets, gateway tokens | ✓ | ✓ | | |
| Projects: create/edit/archive, terminal, browser, embedder | ✓ | ✓ | | |
| Channels/topics: create, rename, archive | ✓ | ✓ | topics only (create/rename) | |
| Call personas, sessions, approve runs, run chains, schedules | ✓ | ✓ | ✓ | |
| Curate recall + deliverables | ✓ | ✓ | ✓ | |
| Define personas, MCP servers, models, routines, chains, hooks | ✓ | ✓ | | |
| Usage rollups (project + company) | ✓ | ✓ | | |
| Edit what roles grant (`role.update`) | ✓ | | | |
| See lists, read topics, mark read | ✓ | ✓ | ✓ | ✓ |

Deliberate lines: a Member never holds create/delete over AI infrastructure
or archive rights; a Viewer cannot call personas or open sessions at all
(`topic.mark_read` is the one write every role gets — it is a personal
read-state marker, not shared content). Assigning the Admin ROLE at a
PROJECT scope is what makes a "project admin": the same bundle, reaching
only that project's PROJECT- and TOPIC-scope rights.

---

## Part 4 — The topic-only invite

A person invited to exactly one topic gets a RoleAssignment at TOPIC scope
(plus server membership). What that means in practice:

- They see the parent project in their sidebar ONLY as the road to their
  topic (the reachable-projects fallback), that one channel, and that one
  topic — the project's other channels, topics, personas and servers answer
  like they don't exist.
- Inside the topic they do whatever their role's TOPIC-scope rights allow
  (a Member: read, write, mention personas, approve runs, schedule).
- They never reach PROJECT-scope rights (no creating channels, no editing
  the project) and never see the configure topic — a direct invite does not
  pierce the fence.
- Invitation grants are applied at ACCEPTANCE: the invite stores the grants
  (whole project, or a list of topics), and auth_verify applies them when
  the person first signs in.

---

## Part 5 — Known legacy and gaps (honest list)

1. **Three legacy membership records coexist** with RoleAssignment:
   `CompanyAccess.role`, `ProjectMember.role`, `TopicParticipant.role`. They
   are kept so older read paths (team lists, invites) keep working; the
   RoleAssignment engine is what actually gates actions. Collapsing them is
   future cleanup, not a behavior bug.
2. **Team management gates on `project.archive`** (adding/inviting/removing
   project members) — a documented stand-in; a dedicated
   project.invite_member/remove_member pair is the recorded follow-up.
3. **`channel.update` exists with no endpoint** (renaming channels isn't
   built).
4. **Role.scope seeding inconsistency:** the four default Role rows are
   seeded at scope "company" while the same Role is assignable at any scope;
   assignment scope is what matters, the Role row's own field is cosmetic
   today (noted in workspace/services.py).
5. **Members' server invite path** still checks a legacy Django permission
   (`nucleus.add_invitation`) on `/members/invite/` while the project-team
   road uses rights — works, inconsistent in style.
