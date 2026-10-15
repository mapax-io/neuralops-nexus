# Permission system — use cases

Plain-language scenarios first, each with the actual `PermissionChecker`
call it maps to. This is meant to be read start to finish once, so you
can see how the same four calls (`can`, `rights_for`, `assign_role`,
`revoke_role`) cover every case that came up while designing this.

None of the `api.py` files listed below have actually been changed yet —
these are the intended call sites, shown so you can see where this
plugs in once you're ready to wire it up.

---

## UC1 — Creating a project

Noaman is Company Admin. He wants to create a new project called "Q3 Launch".

There's no `Project` row yet, so the check is made against the `Company`,
not an object:

```python
# workspace/api.py -> create_project view
if not PermissionChecker.can(request.auth, "project.create", company=company):
    raise HttpError(403, "You don't have permission to create projects.")
```

`project.create` has `scope=COMPANY` (see `rights.py`), so only a
Company-scoped `RoleAssignment` grants it — a Project-scoped one
wouldn't even be found, since there's no project to be scoped to yet.

---

## UC2 — Listing the projects you can see

Sara is Member on "Q3 Launch" only, not Company-wide. She opens the
project list.

```python
# workspace/services.py -> list_projects
visible_project_ids = [
    a.scope_object_id for a in RoleAssignment.objects.filter(
        user=user, scope_object_type="project",
    )
] + [company-wide project ids, if the user holds a company-scoped assignment with project.list]
```

`rights_for(user, company=company)` tells you *whether* `project.list`
is held company-wide; the actual filtered queryset still needs the
per-project `RoleAssignment` rows for anyone scoped narrower than the
company. This is the one case where `can()` alone isn't enough — you're
not asking "can they see one project," you're asking "which ones." Keep
the existing `list_projects` query shape (role-aware filter), just swap
what decides "is this an admin-equivalent" from `CompanyAccess.role`
to `PermissionChecker.can(user, "project.list", company=company)`.

---

## UC3 — Project Admin creates a channel

Sara is promoted to Admin on "Q3 Launch" (Project-scoped, not
Company-scoped). She creates a new channel called "Marketing".

```python
# workspace/api.py -> create_channel view
if not PermissionChecker.can(request.auth, "channel.create", obj=project):
    raise HttpError(403, "You don't have permission to create channels.")
```

`channel.create` has `scope=PROJECT`. Sara's `RoleAssignment` is
anchored directly at this `Project`, so `_scope_chain(project)` finds
it immediately — no need for her to also hold anything at Company scope.

---

## UC4 — Inviting someone as Member of one Topic only

Sara invites Ali to help with a specific conversation, not the whole
project. He's added as Member scoped to that one `ChatTopic`.

```python
role = Role.objects.get(company=company, name="Member")
PermissionChecker.assign_role(ali, role, topic, granted_by=sara)
```

Ali now has `topic.mark_read`, `session.create`, `persona.mention` —
but only reachable through that one `ChatTopic`. Ask
`PermissionChecker.can(ali, "topic.list", obj=some_other_topic)` and it
returns `False`: his only `RoleAssignment` is anchored at the first
topic, and `_scope_chain(some_other_topic)` never includes it. This is
"can't see other topics until added," exactly as discussed.

---

## UC5 — Promoting Ali to Project Admin instead

Sara decides Ali should see the whole project, not just one topic.

```python
project_admin_role = Role.objects.get(company=company, name="Admin")
PermissionChecker.assign_role(ali, project_admin_role, project, granted_by=sara)
```

This doesn't remove his earlier Topic-scoped Member assignment — it's
additive. Ali now holds two `RoleAssignment` rows. It doesn't matter:
his effective rights on any topic under "Q3 Launch" are now the union
of both, and the Project-scoped Admin assignment alone already reaches
every topic in the project, making the narrower one redundant (harmless
to leave, or you can `revoke_role` it for tidiness).

---

## UC6 — A Member tries to create a Persona (denied)

Ali (Project-scoped Admin, not Company-scoped anything) tries to
register a new Persona for the whole company.

```python
# intelligence/api.py -> create_persona view
if not PermissionChecker.can(request.auth, "persona.create", company=company):
    raise HttpError(403, "You don't have permission to create personas.")
```

`persona.create` has `scope=COMPANY`. Ali's only assignment is at
`PROJECT` scope — `_scope_chain` for a `company` argument is just
`[(COMPANY, company.id)]`, and `_matching_assignments` only considers
assignments anchored at COMPANY or broader when the right itself is
COMPANY-scoped. His Project-scoped Admin role never enters the
comparison. Correctly denied, matching "AI infrastructure creation is
Admin/Owner-only, and only at Company scope."

---

## UC7 — Company Admin creates that same Persona (allowed)

Noaman (Company-scoped Admin) makes the same request.

Same check as UC6, but this time `_matching_assignments` finds his
Company-scoped `RoleAssignment`, and `RoleRight` confirms Admin includes
`persona.create` (see `DEFAULT_ROLE_RIGHTS` in `rights.py`) — allowed.

---

## UC8 — Stacking a capability role instead of promoting someone fully

Noaman wants Ali to be able to create Personas for the company, but
doesn't want to make him a full Company Admin (which would also give
him `company.remove_member`, `project.archive`, etc. — too much).

```python
builder_role, _ = Role.objects.get_or_create(
    company=company, name="Persona Builder", scope="company",
    defaults={"description": "Can create/manage personas only. No membership or project rights."},
)
persona_rights = Right.objects.filter(code__in=["persona.create", "persona.update", "persona.delete"])
for right in persona_rights:
    RoleRight.objects.get_or_create(role=builder_role, right=right)

PermissionChecker.assign_role(ali, builder_role, company)
```

Ali now holds Project Admin (on "Q3 Launch") *and* "Persona Builder"
(company-wide) at the same time — two separate, small, honest grants
instead of one bloated role. `PermissionChecker.can(ali, "persona.create", company=company)`
now returns `True`, while `PermissionChecker.can(ali, "company.remove_member", company=company)`
still returns `False`. This is the "no role-copying, just stack a small
additive role" pattern from the design discussion.

---

## UC9 — Opening and closing an AI session

Ali (topic Member) sends `@Nova @session` in a topic.

```python
# chat/api.py -> send_message view, before opening the session
if not PermissionChecker.can(request.auth, "session.create", obj=topic):
    raise HttpError(403, "You don't have permission to open a session here.")
```

Later, `@session close`:

```python
if not PermissionChecker.can(request.auth, "session.close", obj=topic):
    raise HttpError(403, "You don't have permission to close this session.")
```

Both are `scope=TOPIC`, granted by Member (see `DEFAULT_ROLE_RIGHTS`),
not by Viewer.

---

## UC10 — Viewer tries to mention a persona (denied)

A Viewer-role user sends `@Nova what's the status?` in a topic they can
read.

```python
if not PermissionChecker.can(request.auth, "persona.mention", obj=topic):
    raise HttpError(403, "You don't have permission to trigger AI in this topic.")
```

Viewer's `DEFAULT_ROLE_RIGHTS` deliberately excludes `persona.mention`
— they can read, not act. `chat/api.py` would call this right before
firing `trigger_ai_response_async`, so a Viewer's `@mention` is silently
ignored (or shown as text-only) instead of triggering a real AI call.

---

## UC11 — Project Admin archives a project (reversible action)

Sara, Project Admin on "Q3 Launch" (Project-scoped only, no company
assignment), decides the project has wrapped up and archives it.

```python
# workspace/api.py -> archive_project view
if not PermissionChecker.can(request.auth, "project.archive", obj=project):
    raise HttpError(403, "You don't have permission to archive this project.")
svc.archive_project(project)  # soft_delete() -- is_active=False, deleted_at=now
```

Unlike the old `project.delete` (removed -- there is no destructive,
irreversible project action anymore), `project.archive` is `scope=PROJECT`
and IS included in `DEFAULT_ROLE_RIGHTS["Admin"]`, so both a Company Admin
and Sara, this project's own Project Admin, can reach it -- archiving
isn't Owner-tier the way deletion used to be, since `SoftDeleteModel`
already provides an (until now unused) `restore()` method making it
reversible in principle. Member/Viewer never get it.

Once archived, every existing mutation path already filters
`is_active=True` (see `get_project_object`, `get_channel`, `get_topic`),
so the project becomes read-only for free -- no separate enforcement
needed. See UC18 for who can still *see* it.

---

## UC12 — Building a frontend permissions payload in one call

The React app opens a project page and wants to know upfront which
buttons to show (Create Channel? Delete Project? Invite?) without
firing a `can()` call per button.

```python
# workspace/api.py, or a small dedicated endpoint
rights = PermissionChecker.rights_for(request.auth, obj=project)
# -> {"project.view", "channel.create", "topic.create", "session.create", ...}
return {"rights": sorted(rights)}
```

One query pattern, the frontend just checks `"channel.create" in rights`
before rendering the button.

---

## UC13 — Listing AI Models / Agents / MCP Servers / Personas you can see

Ali is Project Member on "Q3 Launch" only, holds no company-wide
assignment. He opens the project's AI panel.

```python
# intelligence/api.py -> list_ai_models / list_agents / list_mcp_servers_all
return [_model_out(m) for m in svc.list_ai_models(company, request.auth)]
```

`svc.list_ai_models` calls `row_rules.visible_ai_models(user, company)`,
same shape as `visible_projects`: broad case checks the company-wide
`ai_model.list` right (Owner/Admin see everything), narrow case falls
back to `_reachable_project_ids(user)` and filters models by their
`projects` M2M. `visible_agents`/`visible_mcp_servers` are identical.
`visible_personas(user, project)` is the one variant shaped differently
-- Persona is single-project via a real FK, and the API always resolves
one specific project first, so the function takes `(user, project)`
rather than `(user, company)`.

This is deliberately never a `can()` 403 at the API layer -- these four
list endpoints always return `200` with a (possibly empty) list, never
a `403`, because "can you see the list" and "what's actually on it" are
answered by the same row-visibility function. (`list_personas` used to
be the exception, gating on a blanket company-wide `persona.list` check
before even calling the service -- fixed to match the other three.)

---

## UC14 — Company Admin creates an AI Model with an API key (Project Admin denied)

Noaman (Company Admin) registers a new OpenAI model, providing a raw API key.

```python
# intelligence/api.py -> create_ai_model view
if not PermissionChecker.can(request.auth, "ai_model.create", company=company):
    raise HttpError(403, "You don't have permission to create AI models.")
```

`ai_model.create` stays `scope=COMPANY` on purpose -- creating a model
means handling (and Fernet-encrypting) a real provider API key, so this
never reaches down to a Project-scoped assignment, even a Project Admin.
Sara, Project Admin on "Q3 Launch" only, gets a 403 on this exact call
-- she can attach an existing model (UC15) but never create or delete
one, and never touches a key.

---

## UC15 — Project Admin attaches an existing AI Model to their project

Noaman already created the OpenAI model company-wide (UC14) but it's
unattached -- invisible to every project until explicitly attached.
Sara, Project Admin on "Q3 Launch" (Project-scoped only, no company
assignment), wants her project to be able to use it.

```python
# intelligence/api.py -> attach_ai_model view
if not PermissionChecker.can(request.auth, "ai_model.attach", obj=project):
    raise HttpError(403, "You don't have permission to attach AI models to this project.")
```

`ai_model.attach` is a separate right from `ai_model.create`/`delete`,
scoped to `PROJECT` -- it never touches the model's key, only the
`projects` M2M visibility gate, so a Project Admin can reach it even
though they can't reach `ai_model.create`. This is the split the design
discussion landed on: "but not the keys, until you are project admin."

---

## UC16 — Project Admin creates/updates/deletes an Agent or MCP Server in their own project

Sara (Project Admin on "Q3 Launch" only, no company-wide assignment)
creates a new internal agent for her project.

```python
# intelligence/api.py -> create_agent view
project = Project.objects.filter(company=company, id=payload.project_id, is_active=True).first()
if not PermissionChecker.can(request.auth, "agent.create", obj=project):
    raise HttpError(403, "You don't have permission to create AI agents in this project.")
```

Unlike `ai_model.create`, `agent.create`/`agent.delete`/`agent.update`
and their `mcp_server.*` twins are `scope=PROJECT` -- an Agent/MCPServer
belongs to exactly one project (see `AIAgent.projects`/`MCPServer.projects`,
kept as an M2M structurally but restricted to one entry by app code), so
that project's own Admin can manage it without needing a company-wide
assignment. `_scope_chain()` in `checker.py` walks the object's
`projects.first()` to produce a `[(PROJECT, project.id), (COMPANY,
company.id)]` chain, which is what lets `obj=agent` reach Sara's
Project-scoped `RoleAssignment` on `delete_agent`/`patch_agent` too --
not just `create_agent`, which checks against the project directly
since the agent doesn't exist yet.

---

## UC17 — Project Admin on one project cannot touch another project's Agent

Sara is Project Admin on "Q3 Launch" only. Ali creates "Other Project"
with its own agent, "Scout". Sara tries to delete it.

```python
# intelligence/api.py -> delete_agent view
agent = svc.get_agent(company, agent_id)  # fetches "Scout"
if not PermissionChecker.can(request.auth, "agent.delete", obj=agent):
    raise HttpError(403, "You don't have permission to delete this AI agent.")
```

`_scope_chain(scout)` resolves to `[(PROJECT, other_project.id), (COMPANY,
company.id)]` -- Sara's only `RoleAssignment` is anchored at
"Q3 Launch", which never appears in that chain, so `_matching_assignments`
finds nothing and `can()` returns `False`. Same isolation as UC3's
project-to-project channel test, just reached through the M2M instead of
a direct FK.

---

## UC18 -- Archiving a Channel/Topic, and viewing archived items

Extends UC11 down two more levels. `channel.archive` (`scope=PROJECT`)
and `topic.archive` (`scope=TOPIC`) work exactly like `project.archive`
-- same reversible soft-delete mechanism, same Admin-reachable-including-
Project-Admin default, same "read-only for free" enforcement:

```python
# workspace/api.py -> archive_channel view
if not PermissionChecker.can(request.auth, "channel.archive", obj=channel):
    raise HttpError(403, "You don't have permission to archive this channel.")
svc.archive_channel(channel)
```

**The same right also gates seeing archived items**, instead of a
separate `.view_archived` right for each resource -- one right, two
jobs. `visible_projects`/`visible_channels`/`visible_topics` all take an
`include_archived=False` kwarg; when `True`, each archived row in scope
is included only if the caller passes `PermissionChecker.can(user,
"<resource>.archive", obj=<that specific row>)` -- checked per-object via
the shared `_with_archived()` helper in `row_rules.py`, not per-list.
This is what makes "Company Owner/Admin sees every archived project,
Sara (Project Admin) only sees archived items inside her own project,
Member/Viewer never see archived items at all" fall out of the existing
`can()` machinery with no new branching:

```python
# workspace/api.py -> list_projects view
@router.get("/", response=List[ProjectOut])
def list_projects(request, include_archived: bool = Query(default=False)):
    company, user = _resolve(request)
    return [_project_out(p) for p in svc.list_projects(company, user, include_archived=include_archived)]
```

Sara calling `GET /projects/?include_archived=true` sees "Q3 Launch"
even after archiving it (she holds `project.archive` directly on it);
Ali, a plain Member with no archive right anywhere, passes the same
query param and gets back exactly what he'd have gotten without it --
the param is a no-op for him, not a 403.
