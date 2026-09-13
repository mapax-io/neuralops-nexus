# Role stories

One set of stories per role, per scope it's actually assignable at.
Revised after review — several scopes were cut entirely rather than
just having their rights adjusted, noted inline below.

Format: `As a [role] at [scope], I want to..., so that...` — plus a
couple of "I should NOT be able to..." lines per role, since knowing
what's deliberately withheld matters as much as what's granted.

---

## Owner — Company scope only

No Project Owner and no Topic Owner. Admin is the top tier at those two
scopes; Owner exists at the Company level only.

- As the Company Owner, I want to do everything an Admin can, so that I never hit a wall managing my own company.
- As the Company Owner, I want to delete the company entirely, so that I can shut it down if I need to.
- As the Company Owner, I should not be removable by anyone else, including another Admin — there must always be exactly one, and the last Owner can't be stripped of the role.
- There is no ownership transfer. If the Owner needs to be replaced, that means re-initializing the system from scratch (`manage.py create_owner`), not a "transfer" action — no right exists for handing ownership to someone else.

---

## Admin

### Company Admin
- As a Company Admin, I want to invite and remove company members, so that I can manage who has access.
- As a Company Admin, I want to create new projects, so that teams can start new work.
- As a Company Admin, I want to create/delete AI models (including setting their API keys) and personas, so that I can build out the company's AI infrastructure -- these stay Company-scope only, since a model create/delete touches a real provider key and a persona is otherwise unrestricted (see below, still Company-scope-only for now).
- As a Company Admin, I want to create/update/delete AI agents and MCP servers in any project, and attach existing AI models to any project, so that I can manage AI infrastructure company-wide without needing to also hold a Project Admin assignment on every project.
- As a Company Admin, I should not be able to delete the company or remove the Owner — those stay Owner-only.
- As a Company Admin, I should not be able to change, re-scope or remove another Admin — peers are off limits; only the Owner reshapes Admins (promoting a Member to Admin stays mine to do).

### Project Admin
- As a Project Admin, I want to create channels and topics inside my project, so that the team can organize their work.
- As a Project Admin, I want to add and remove people from my project, so that I control who's on the team.
- As a Project Admin, I want to create/update/delete AI agents and MCP servers in my own project, so that I don't need a company-wide assignment just to manage AI tooling my team actually uses. (Revised: `agent.*`/`mcp_server.*` create/update/delete moved from COMPANY to PROJECT scope specifically so Project Admin reaches them -- see USE_CASES.md UC16/UC17.)
- As a Project Admin, I want to attach an already-existing AI Model to my project, so that my team can use it -- without needing to create the model or see its API key. `ai_model.attach` is a separate, lighter PROJECT-scope right from `ai_model.create`/`delete` (see USE_CASES.md UC15) specifically so this works even though I can't create a model myself.
- As a Project Admin, I should still not be able to create, delete, or see the key on an AI Model, or create/update/delete a Persona — `ai_model.create`/`delete` and all of `persona.*` remain Company-scope only (a model's create/delete touches a real provider key; Persona hasn't been revisited since the AI-resource permission redesign).
- As a Project Admin, I want to archive my own project, channels within it, and topics within those channels (instead of deleting them), so that finished work goes read-only without anyone losing history. **Resolves the old open question**: there is no more `project.delete` (irreversible, Owner-only) -- it's been replaced by `project.archive`/`channel.archive`/`topic.archive`, all reversible soft-deletes (`SoftDeleteModel.restore()`), all included in `DEFAULT_ROLE_RIGHTS["Admin"]`, all reachable by a Project Admin on their own project without needing Company Owner/Admin. Member/Viewer never get any of the three.
- As a Project Admin, I want to still see my own archived projects/channels/topics (via `?include_archived=true`), so that I can review or eventually restore them, so that archiving doesn't mean losing access to my own team's history — the same `.archive` right gates both the action and this view, scoped per-object so I only see archived items inside projects I actually administer (see USE_CASES.md UC18).

### Topic Admin
- As a Topic Admin, I want to manage settings and participants within one topic, so that I can run that conversation without needing project-wide access.
- As a Topic Admin, I should not be able to create a new channel or a sibling topic — there's nothing above a topic for this assignment to reach.

---

## Member — no Company scope

Member only exists at Project and Topic scope. There is no
company-wide Member tier.

### Project Member
- As a Project Member, I want to create topics inside any channel in my project, so that I can start new conversations.
- As a Project Member, I want to open and close AI sessions, and @mention personas, so that I can actually use the AI features day to day.
- As a Project Member, I should not be able to create a new channel — that's an Admin action.
- As a Project Member, I should not be able to invite or remove anyone from the project.

### Topic Member
- As a Topic Member, I want to chat, mark the topic read, open a session, and @mention personas — but only in the one topic I was added to.
- As a Topic Member, I should not be able to see or act on any other topic in the same channel or project, until someone explicitly adds me there too, or promotes me to a broader scope.

---

## Viewer — not yet reviewed, left as originally written

### Company / Project / Topic Viewer (same behavior at every scope)
- As a Viewer, I want to see everything at my scope — projects, channels, topics, messages — so that I can stay informed without needing to act.
- As a Viewer, I should not be able to create anything, open a session, or @mention a persona — read-only means read-only, not "read plus trigger AI."
- As a Viewer, I should not be mistaken for a Member just because I can see the same content — the distinction is entirely about write/act rights, not visibility.

Given Owner and Member both lost scopes above, worth confirming: does
Viewer still exist at all three scopes, or does the same narrowing
apply here too?

---

## Custom role example — Persona Builder (Company scope) — not yet reviewed

Included to show a custom role doesn't need to follow the four-tier
shape at all — it can be as narrow as one job.

- As a Persona Builder, I want to create, update, and delete personas, so that I can maintain the company's AI personas without needing full Admin access.
- As a Persona Builder, I should not be able to invite/remove company members, create projects, or touch AI Models/MCP Servers/Agents — this role is deliberately narrow to just personas.
- As a Persona Builder, I want to be assignable to someone alongside their existing Member or Admin role, so that granting this one capability doesn't require re-doing their whole access setup.
