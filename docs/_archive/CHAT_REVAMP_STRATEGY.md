# Chat Module Revamp — Findings & Strategy

Working document compiled from an authn cleanup + chat module security/architecture
review pass, ahead of the planned GitHub launch. Captures what's already fixed, what's
confirmed dead but not yet removed, what's an open concern for the chat revamp, and a
proposed order to tackle it in. Nothing below has been implemented except where marked
**DONE**.

---

## 1. Already fixed this pass

- **Removed the dead device-polling login flow** — `poll_device_activation` (Celery
  task), `auth_init()`/`auth_status()`, `DeviceAuthError`, `AuthInitResponse`/
  `AuthStatusResponse`, the `DeviceSession` model + a drop migration. Confirmed via
  the frontend (`auth.service.ts`, `ServerList.tsx`, `LoginForm.tsx`) that nothing
  ever called `/auth/init/` or `/auth/status/` — the real login flow is Supabase
  sign-in → `/auth/verify/`.
- **Removed `authn/internal_api.py`** — a stale, out-of-date duplicate of the real
  `internal/api.py` (a separate registered Django app). The `authn/` copy was missing
  fields (`is_first_party`, `embed_output`) and an endpoint (`create_ai_request_log`)
  that the live one has. Never imported anywhere.
- **Moved the API registry out of `authn/`** — `NinjaAPI()` instantiation and all
  `add_router(...)` calls moved from `authn/urls.py` into `core/urls.py`, where the
  actual Django project root is. `authn/` should only be identity/authorization, not
  the API composition root.
- **Fixed `chat/api.py`'s `_resolve_topic_sync`** — channel/topic resolution now goes
  through `list_channels()`/`list_topics()` (the same `visible_channels`/
  `visible_topics` row-visibility used by the sidebar) instead of plain unchecked
  `.filter().first()` lookups. A channel/topic outside what the sidebar would show
  now 404s here too, not just in the list endpoints.

Still need to run, if not already done: `git rm -f` for `authn/internal_api.py` and
`authn/urls.py` (both emptied, not yet removed from disk).

---

## 2. Confirmed dead, not yet removed

Same stale-duplicate pattern as the `authn/` cleanup, found while auditing every
`api.py` against what `core/urls.py` actually imports:

- `workspace/members_api.py`, `members_schema.py`, `members_services.py` — dead.
  `members_router` is defined directly inside `workspace/api.py`, using
  `workspace/schema.py` + `workspace/services.py`.
- `workspace/team_api.py`, `team_schema.py`, `team_services.py` — dead, same reason.
  All team endpoints (`list_team`, `add_member`, `invite_to_project`, etc.) live in
  `workspace/api.py` already.
- `chat/tasks.py` — dead. `generate_ai_response` (Celery task) + its Anthropic/OpenAI
  streaming helpers are never called. The live AI-reply path is
  `trigger_ai_response_async` in `chat/services.py`, which hits nexus-ai's
  `/trigger/` endpoint over HTTP instead.

Not yet actioned — held off since the plan was to review every chat file first before
touching anything.

---

## 3. Investigated and confirmed NOT a problem

Raised as open questions during the review, then checked and closed:

- **AI-generated HTML (`render_as="html"`) rendering** — `HtmlRenderer.tsx` renders
  it inside a sandboxed iframe: `sandbox="allow-scripts"`, deliberately *without*
  `allow-same-origin`, `allow-forms`, or `allow-popups`. The iframe has no access to
  the parent app's cookies, localStorage, or DOM — classic stored-XSS (steal the
  session token) doesn't work here. Residual risk is limited to phishing-style visual
  deception (a fake login form inside the sandbox), which is a much lower-severity,
  harder-to-execute concern than data theft.
- **Human-typed messages** — always saved with `render_as="text"` (`save_user_message`
  never sets it in metadata), always rendered via `TextRenderer.tsx`'s `react-markdown`
  — which, without the `rehype-raw` plugin (not installed here), does not execute
  embedded HTML at all; it escapes it as visible text.

---

## 4. Open findings — the actual backlog

### #120 — [P0] No invite flow ever creates a RoleAssignment — RBAC doesn't apply to real invited users

Bigger than first scoped. Checked every place a real user gets added to a
company/project in the live codebase — only two of them ever call
`PermissionChecker.assign_role()`:

- `create_owner.py`'s `_grant_owner_role` — grants the **one bootstrap owner** a
  company-scope `RoleAssignment`. Its own comment confirms this exact class of bug
  already happened once, for the owner specifically ("company.owner had no
  RoleAssignment at all"), and was fixed narrowly rather than generalized.
- `create_project()` — grants whoever **creates** a project a project-scope Admin
  `RoleAssignment`.

Every other membership-creation path never touches `RoleAssignment` at all — only
the legacy `CompanyAccess` / `ProjectMember` / `TopicParticipant` / Django
`auth.Group` models, none of which `PermissionChecker`, `_reachable_project_ids`,
or any `visible_*` function ever queries:

- `invite_to_project()` (the `/invite` slash command, `workspace/services.py`) —
  creates `ProjectMember` + `TopicParticipant` only, regardless of `scope`.
- `_add_user_to_invited_project()` (email invite acceptance, `authn/services.py`)
  — creates `ProjectMember` only.
- `auth_verify()`'s invitation-acceptance branch (`authn/services.py`) — creates
  `CompanyAccess` + adds to a Django `auth.Group`.

`seed_permissions.py` only seeds the `Role`/`RoleRight` *templates* — it never
assigns any actual user to one.

**Net effect:** every real invited team member — company-level, project-level, or
topic-level — currently gets zero `RoleAssignment` rows, and therefore fails
essentially every `PermissionChecker.can()` check in the app. Only the original
bootstrap owner and whoever personally creates a project have working RBAC
permissions today. Never caught because every rights test this session
(`test_workspace_flow.py`, `test_persona_flow.py`, etc.) manually calls
`PermissionChecker.assign_role()` as test setup — none of them exercise a real
invite flow.

The original topic-only-invite framing (UC4) is one symptom of this, not a
separate bug — `USE_CASES.md` documents
`PermissionChecker.assign_role(ali, member_role, topic, granted_by=sara)` as the
intended mechanism, but it (and the company/project-level equivalents) were never
actually wired into any real invite endpoint.

**Fix direction:** every membership-creation point needs to also call
`PermissionChecker.assign_role()` with the appropriate scope (company for
`CompanyAccess`-based invites, project or topic for `invite_to_project` depending
on its `scope` param). Once real `RoleAssignment` rows exist for invited users,
`get_project()` still has its own smaller, secondary issue on top: it checks
`PermissionChecker.can(obj=project)`, whose `_scope_chain(project)` only ever
returns `[PROJECT, COMPANY]` — a pure topic-scoped assignment can never match,
even once it exists. `visible_projects()`'s `_reachable_project_ids()` already
walks topic-scope up to project-scope correctly for *listing*; `get_project()`
needs the same fallback for *resolving*. But that's now a secondary issue layered
on top of the much larger one above.

**Recommend treating as launch-blocking, not backlog-later.**

### #121 — Replace scattered `PermissionChecker.can()` calls with a per-route decorator

Discussed at length. Conclusions:

- **Middleware is ruled out**, not just disfavored. Django's `MIDDLEWARE` list can't
  see individual Ninja operations — the whole API is one Django URL pattern
  (`path("api/v1/", api.urls)`), and Ninja does its *own* internal routing to the
  specific view function after that. By the time Django's `process_view` hook could
  fire, it only sees Ninja's dispatcher, never `send_message` specifically.
- **`auth=` is ruled out as the vehicle**, even though it's Ninja's real "runs before
  your view, per-route" mechanism (already used for `SupabaseBearer`/
  `InternalAPIKey`). It's semantically about identity, not authorization, and
  doesn't parameterize cleanly per-right the way a decorator can — Ninja's
  multi-auth composition is OR logic ("try this token or that one"), not AND logic
  ("authenticate, then also check this specific right").
- **Decorator is the recommended direction** — sits after `auth=`, can be
  parameterized per-route (`@requires_right("topic.send_message", resolve=...)`), can
  resolve the object once and stash it for the view to reuse.
- **Honest caveat, raised and agreed on:** the decorator doesn't add a *stronger*
  check — it's the exact same `PermissionChecker.can()` call, just relocated. The
  only real benefit is structural: a route with no `@requires_right(...)` is visible
  scanning the file, whereas a missing manual check buried in a function body is
  easy to miss (exactly what happened with `_resolve_topic_sync` before it was
  fixed). Worth weighing against the cost of introducing a new pattern, given the
  test-script discipline already in place.
- Also worth deciding first: `send_message` doesn't have a specific right defined
  yet — messaging currently rides entirely on `project.view` + channel/topic
  visibility. A decorator can't sit on this endpoint until it's decided whether
  sending needs its own right or "can see it → can post in it" is the intended
  policy.

Only covers roughly half the endpoints by design — list endpoints (`list_channels`,
`list_topics`, message history) filter querysets via `visible_*`, there's no single
object to gate, so they'd keep their current shape regardless.

### #122 — `embed_message_async` embeds raw, un-stripped message content

In `send_message`, the embed-to-nexus-ai call (step 3) fires with
`content=msg["content"]` — the raw saved text, `@session`/`@output_type`/`@mention`
directives all still in it — because it runs *before* directive-parsing (steps 4–6)
produces `clean_message`. Inconsistent with how AI replies get embedded: those use
the clean final content (`save_content`/`embed_description`), stripped of routing
noise, by the time their embed call fires.

**Fix direction:** reorder so directive-parsing happens first, embed `clean_message`
instead of the raw text (keep the raw text for the DB save/display, which is
deliberately justified separately — "original message with @directives intact for
display"). Possibly skip the embed call entirely for certain message types.

### #123 — Extract a `MessageDirectives` parser out of `send_message`

`send_message` currently mixes two jobs in one function body: figuring out what the
message *means* (parsing `@session`, `@output_type`, `@mentions` — three separate
inline calls with tuple-unpacking) and deciding what to *do* about it (a five-rule
if/elif/else chain, with the "save a system message + fire-and-forget publish it"
pattern duplicated across two branches).

**Proposed shape:**

```python
@dataclass
class MessageDirectives:
    is_session_close: bool
    has_session_open: bool
    output_type: str
    mentioned_names: list[str]
    clean_message: str

def identify_directives(raw_content: str) -> MessageDirectives:
    has_session_open, is_close, after_session = extract_session_directive(raw_content)
    output_type, clean = extract_output_type(after_session)
    names = [n for n in _MENTION_RE.findall(clean) if n.lower() not in _RESERVED]
    return MessageDirectives(is_close, has_session_open, output_type, names, clean)
```

Persona resolution (`_get_persona_by_mention`, a DB lookup needing `project`) stays
separate from this — it isn't pure text-parsing. The five-rule dispatch then reads
against one clean object instead of nested booleans, and the repeated
system-message-plus-publish pattern becomes a shared helper.

---

## 5. Proposed order of attack

Not yet agreed — proposed sequencing, open to reshuffling:

1. **Remove the confirmed-dead files** (`workspace/members_*`, `workspace/team_*`,
   `chat/tasks.py`) — zero behavior change, zero risk, clears noise before anything
   else.
2. **Fix #120** (topic-only invite gap) — a real, user-facing permission bug,
   foundational to get right before restructuring how messaging routes requests
   through it.
3. **Decide + build #121** (rights decorator) — if going ahead with it, better to land
   it before further reshaping `send_message`, so the reshaping happens against the
   final pattern rather than twice.
4. **#122 + #123 together** — both touch the same function (`send_message`), same
   session, makes sense to do in one pass: pull directive-parsing into
   `MessageDirectives`, fix the embed-ordering bug as part of that same reorder.
5. **Re-test** — extend the existing management-command test pattern with a
   dedicated pure-topic-scoped-user scenario (the one case current tests don't
   cover), plus rerun the full suite against the reshaped `send_message`.

---

## 6. System facts confirmed along the way

- 100% Django Ninja. One `NinjaAPI()` instance in `core/urls.py`, six routers
  (`authn`, `members`, `workspace`, `chat`, `intelligence`, `internal`, `context`),
  no DRF, no plain Django views anywhere in the API surface.
- Router-level `auth=SupabaseBearer()` is inherited by every operation on that
  router unless a specific route explicitly overrides it with `auth=None` (only two
  routes do: `/auth/config/` and `/auth/invite-preview/`, both deliberately public).
- Auth is re-verified on every single request (HTTP is stateless, the server keeps
  no memory between requests) — but cheaply: `verify_supabase_token` caches
  Supabase's public keys and does local signature verification, not a network round
  trip per request.
