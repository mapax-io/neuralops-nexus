# NeuralOps — The Story

> This document is a living narrative of the NeuralOps project. It captures every major decision, every pivot, every simplification, and the thinking behind them. If you're a new contributor or you're picking up this codebase after a break, read this first.

---

## What Is NeuralOps?

NeuralOps is a self-hosted AI workspace platform. Think of it as a private Slack where every channel has an AI teammate built in — one that your organisation controls completely, running on models and data you choose.

The core idea: a company installs NeuralOps on their own server, invites their team, and gets a real-time chat interface where conversations can be directed to AI personas, agents, or just people. Everything is private. Nothing leaves the server unless you configure it to.

The architecture is split across services:
- **nexus-nucleus** — Django backend. Auth, permissions, projects, channels, messages, teams.
- **nexus-ai** — FastAPI AI worker. Handles model calls, streaming, persona logic.
- **neuralops-react-app** — The React frontend. What users actually see.
- **realtime** — Centrifugo. WebSocket broker for live streaming tokens.
- **Supabase** — Identity provider. Handles signup, login, JWT issuance.
- **Redis + Celery** — Background jobs. AI generation, polling, async work.

---

## How We Got Here

### The Starting Point

The project began with a need for a clean, API-first backend for an AI chat platform. The initial instinct was to use Django REST Framework (DRF), but after reviewing the codebase needs — typed schemas, automatic OpenAPI docs, clean decorator-based routing — **Django Ninja** was chosen instead. It gives you Pydantic schemas, async support, and OpenAPI out of the box without DRF's verbosity.

Decision: **Django Ninja over DRF**. No regrets.

### Auth: Why Not Just Username/Password?

Early on we discussed handling auth entirely ourselves. But managing password resets, email confirmation flows, OAuth, MFA — that's a product in itself. We decided to delegate identity to **Supabase**, which handles all of that and issues JWTs we can verify on the Django side.

The Django backend never stores passwords. It receives a Supabase JWT, verifies it using the Supabase service key, looks up (or creates) the local user by `supabase_id`, and issues its own session context from there.

Decision: **Supabase for identity, Django for business logic**.

### The Device Flow

The first version of the auth flow was standard: user opens the app, types email + password, gets a JWT, done. But NeuralOps is a desktop-first, server-connection product. You don't just "log in" — you connect your client to a specific server.

So we built a **device activation flow** inspired by OAuth device flow (like how you pair a TV with your phone):

1. Client calls `POST /auth/init/` → gets a `device_id` and a Supabase deep-link URL
2. A Celery task (`poll_device_activation`) starts polling Supabase every 3 seconds
3. User clicks the link, authenticates in browser
4. Supabase activates the device
5. Celery task detects activation, saves user info to `DeviceSession`
6. Client polls `GET /auth/status/?device_id=...` until it sees `active`
7. Client calls `POST /auth/verify/` with the Supabase JWT — gets full server access

This means the React app never handles passwords directly. The browser handles auth, the app handles the server connection.

Decision: **Device flow over direct login** — cleaner separation between identity and server connection.

### Infrastructure: Redis, Celery, Centrifugo

Three infrastructure choices made early that shaped everything:

**Redis** — needed for Celery's message broker and result backend. Already in most stacks. Easy.

**Celery** — AI generation can take 10–30 seconds. You cannot block an HTTP response for that. Every AI response is triggered via a Celery task. The endpoint returns immediately with a placeholder message ID; the task does the work in the background.

**Centrifugo** — chosen over raw WebSockets or Django Channels for two reasons: it has a proper pub/sub model with channels and namespaces, and it has a simple HTTP API for server-side publishing. A Celery task can call `POST /api` on Centrifugo to push a token to the browser without needing a persistent WebSocket connection on the Django side. The React app subscribes to `topic:{topic_id}` and receives streaming tokens in real time.

Decision: **Celery for async AI, Centrifugo for real-time streaming**. These are load-bearing choices — the entire chat architecture depends on them.

---

## Phase 1: The Build

### Company + Owner Setup (Task #18)

The first structural decision: **one Django instance = one company**. NeuralOps is self-hosted. You don't share a NeuralOps server with strangers. So there's no multi-tenancy in the traditional SaaS sense — but there is a `Company` model with a `CompanyAccess` table, because you still need to distinguish the owner from regular members.

The `create_owner` management command was written to bootstrap the first user (the person who installed the server) as the company owner. It links their Supabase identity to a local Django user and creates their `CompanyAccess` record with `role=OWNER`.

What we learned: keep model setup in management commands, not in migrations. Migrations are for schema, not data.

### Projects, Channels, Topics (Task #20)

The workspace hierarchy:

```
Company
  └── Project (e.g. "Engineering", "Marketing")
        └── Channel (e.g. "general", "bugs")
              └── Topic (a conversation thread inside a channel)
                    └── ChatMessage
```

This was modelled after how real teams work. A project is a team or department. A channel is a persistent conversation area. A topic is a thread — AI responds at the topic level, not the channel level. This keeps conversations contained and makes AI context management clean.

All models extend `ProjectOperationModel` which carries `company`, `project`, `is_active`, `created_at`, `updated_at`. Soft deletes everywhere — nothing is hard-deleted in Phase 1.

### The Invite System — Three Iterations

This went through the most iterations of anything in Phase 1.

**Iteration 1 (original plan):** Generate a signed token, put it in a `/join?token=xyz` URL, email the link to the invitee. Standard SaaS invite pattern.

Problem: We're self-hosted. There's no email server configured by default. And the user feedback was blunt: *"why are we making someone's life hell?"*

**Iteration 2:** No email. Generate the join link, show it in the chat as a copyable toast notification. The inviter copies it and pastes it to the person however they like (Slack, WhatsApp, whatever). A `/join` route in the React app handles redemption — the user clicks the link, it calls `POST /auth/invite/redeem/`, and they're in.

Problem: Still too many moving parts. The `/join` page had token parsing, API calls, redirect logic. The `redeem` endpoint had to handle tokens, check expiry, find the user's Supabase JWT. Bugs appeared: the redeem endpoint expected `PENDING` invitations but `auth_verify` had already marked them `ACCEPTED`. Edge cases everywhere.

**Iteration 3 (final, current):** Strip it to the bone.

- `/invite email@example.com` in chat → creates an `Invitation` record in the DB with `access_payload: {"project_id": "..."}`. No token is exposed publicly.
- The toast shows the **server address** (`NEURALOPS_SERVER_URL`). That's it. The inviter tells the person: *"Sign up at our portal and connect to this server address."*
- The invitee signs up normally through Supabase.
- On first `POST /auth/verify/`, the backend checks for a pending `Invitation` by email. If found: accept it, create `CompanyAccess`, create `ProjectMember` for the specific project they were invited to. Done.

No tokens. No redemption page. No email server. No `/join` route logic. The join route now just redirects to `/`.

What we learned: **the simpler the invite flow, the fewer attack surfaces and the fewer bugs**. The complexity of the old flow was entirely unnecessary.

### Per-Project Access

Early version added invited users to all active projects. Wrong.

The right behaviour: you invite someone from *within* a project's channel. They should see that project and only that project. The `access_payload` on the `Invitation` record stores the `project_id`. `auth_verify` reads it and creates exactly one `ProjectMember` record.

If the owner later wants to give them access to another project, they invite them again from there.

### Remove From Server

Simple but important. `DELETE /api/v1/projects/server/members/{user_id}/`:

1. Deactivates their `CompanyAccess`
2. Deactivates all their `ProjectMember` records

Cannot remove yourself. Cannot remove the owner. Everything is soft-deleted — if they're re-invited later, their access is simply re-activated.

---

## Key Architecture Decisions — Summary

| Decision | What we chose | What we rejected | Why |
|---|---|---|---|
| API framework | Django Ninja | DRF | Pydantic schemas, OpenAPI, less boilerplate |
| Identity | Supabase | DIY auth | Password management, OAuth, MFA — not our problem |
| Auth flow | Device activation | Direct JWT login | Clean separation of identity from server connection |
| Async jobs | Celery + Redis | Django async views | AI calls take 10-30s — can't block HTTP |
| Real-time | Centrifugo | Django Channels | HTTP publish API — Celery tasks can push without WebSocket |
| Multi-tenancy | One server = one company | True multi-tenant | Self-hosted product, different threat model |
| Invite flow | Email pre-auth, server URL | Token links, email delivery | Fewer moving parts, no email server needed |
| Project access | Per-project, explicit | All projects on join | Principle of least privilege |
| Deletes | Soft delete everywhere | Hard delete | Audit trail, re-activation, Phase 1 simplicity |
| AI SDK | httpx (direct API calls) | anthropic/openai SDK | No extra dependency, streaming is just SSE parsing |

---

## What Got Simplified (And Why)

**The /join route** went from a full redemption page (form, API call, redirect logic) to a single-line redirect to `/`. The whole complexity was unnecessary once we dropped token-based invites.

**The invite endpoints** `GET /auth/invite/info/` and `POST /auth/invite/redeem/` were removed entirely. They had bugs, edge cases, and were solving a problem we'd already decided not to have.

**InviteInfoOut schema** removed. `invite_link` field replaced with `server_url` (the address the inviter shares verbally or via any channel they prefer).

**Team list filtering** — the team list only shows users who have actually connected (have a `CompanyAccess` record). Pending invitations don't appear. Inviting someone doesn't add them to the team list until they actually show up.

---

## Current State (as of Phase 1)

**Done:**
- Full auth flow: device activation → Supabase → JWT verify → server connection
- Company + owner bootstrap
- Projects, Channels, Topics CRUD APIs
- Invite system (simplified, email pre-auth)
- Per-project access on join
- Remove-from-server
- React left panel: project list, channel list, topic list
- React chat input with `/invite` slash command

**In progress:**
- Task #21: Chat API — `chat_schema.py`, `chat_services.py`, `chat_tasks.py` written. `chat_api.py` and URL wiring pending (under discussion).

**Pending:**
- Task #22: React main screen layout
- Task #23: React chat window (real data, Centrifugo streaming)
- Task #24: React invite users UI

---

## What's Next (Phase 2 thinking)

Nothing is decided for Phase 2 yet. But the directions being considered:

- **Personas** — each topic can have an assigned AI persona with its own system prompt, model, and knowledge base
- **Knowledge base** — files and documents that AI can reference in conversations
- **Agents** — AI that can take actions (call APIs, write code, search the web) not just generate text
- **Audit log** — who did what, when
- **Notifications** — @mentions, topic updates

These are not commitments. Phase 1 ships first.

---

## Principles We're Holding To

1. **Simple beats clever.** Every time we made the invite flow more sophisticated, it broke. The simplest version works.
2. **Don't block HTTP with AI.** Always Celery. Always async.
3. **Soft delete everything in Phase 1.** Hard deletes can come when we know what we're doing.
4. **The backend is just data.** No business logic in views. Services layer handles decisions, API layer handles HTTP.
5. **One server, one company.** Don't add multi-tenancy complexity until there's a real reason to.
6. **Don't solve problems you don't have yet.** No email server? Don't design flows that require one.

---

*Last updated: Phase 1 / feat/phase1-team-invite merge*
