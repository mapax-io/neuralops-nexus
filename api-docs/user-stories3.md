# NeuralOps Nexus — Unified API Specification

Single source of truth for every API needed to bring the Nexus mockup screens to life.
Organized **screen by screen** in the same order we agreed to build:

1. Login
2. Signup
3. Project sidebar (Projects → Channels → Topics)
4. Users right bar (Roster panel)
5. Chat screen (Collab / Plain-chat / Agent run)
6. Add Persona dialog
7. Add Model
8. Add Agent
9. Add MCP server
10. Add Context (Context bar)

---

## 0. Conventions

- **Base URL**: `/api/v1`
- **Auth**: `Authorization: Bearer <jwt>` (Google OAuth session)
- **Content-Type**: `application/json` for requests, `multipart/form-data` only where noted
- **IDs**: UUIDv4, server-issued
- **Timestamps**: ISO-8601 UTC, suffix `_at`
- **Pagination**: `?cursor=&limit=` → `{ items, next_cursor }`
- **Errors**: `{ error: { code, message, details? } }`, HTTP status carries the semantic
- **Realtime envelope**: `{ type, resource, action: "created"|"updated"|"deleted", payload }` over WebSocket / Supabase Realtime channels noted per resource

---

## 1. Login screen

Google-only sign-in. The exchange itself is handled by the managed OAuth broker; the app only consumes session + profile.

| # | Method | Path | Purpose | Auth |
|---|---|---|---|---|
| L1 | `POST` | `/auth/google` | Exchange Google ID token → session JWT | none |
| L2 | `POST` | `/auth/logout` | Invalidate current session | bearer |
| L3 | `GET`  | `/me` | Current user + profile | bearer |

**`POST /auth/google` → 200**
```json
{
  "session": { "access_token": "...", "refresh_token": "...", "expires_at": "2026-05-12T10:00:00Z" },
  "user": { "id": "uuid", "email": "user@example.com" }
}
```

**`GET /me` → 200**
```json
{ "id": "uuid", "email": "user@example.com", "display_name": "Sara", "avatar_url": "https://...", "created_at": "..." }
```

**Side effects on first login** — server creates a `profiles` row from the Google identity payload (`email`, `display_name`, `avatar_url`).

**Client rules**
- After successful sign-in, redirect to `/nexus`.
- Any `401` from a protected endpoint → redirect to `/login`.
- Signed-in users visiting `/login` are bounced to `/nexus`.

**Out of scope:** email/password, Gmail inbox access (separate per-user OAuth feature, later).

---

## 2. Signup screen

There is no separate signup endpoint. `POST /auth/google` handles both new and returning users:

- New Google account → server creates `auth.users` row + `profiles` row, returns session.
- Existing account → returns session for the existing user.

| # | Method | Path | Purpose | Auth |
|---|---|---|---|---|
| S1 | `POST` | `/auth/google` | Same as L1 — first sign-in implicitly creates the account | none |
| S2 | `PATCH`| `/me` | Optional onboarding edits (display name, avatar) | bearer |

**`PATCH /me`** — body `{ display_name?, avatar_url? }` → returns updated profile.

**Client rules**
- Signup screen UI is a thin wrapper around the same Google button as Login.
- Signed-in users visiting `/signup` are bounced to `/nexus`.

---

## 3. Project sidebar (Projects → Channels → Topics)

Backs the left sidebar tree, search, filters, and unread badges.

### 3.1 Tree CRUD

| # | Method | Path | Purpose |
|---|---|---|---|
| P1 | `GET`    | `/projects` | List projects the user can see |
| P2 | `POST`   | `/projects` | Create — `{ name }` |
| P3 | `PATCH`  | `/projects/:projectId` | Rename |
| P4 | `DELETE` | `/projects/:projectId` | Archive |
| C1 | `GET`    | `/projects/:projectId/channels` | List channels |
| C2 | `POST`   | `/projects/:projectId/channels` | Create — `{ name }` |
| C3 | `PATCH`  | `/channels/:channelId` | Rename |
| C4 | `DELETE` | `/channels/:channelId` | Archive |
| T1 | `GET`    | `/channels/:channelId/topics` | List topics (no messages) |
| T2 | `POST`   | `/channels/:channelId/topics` | Create — `{ name, description, mode: "collab"\|"plain-chat"\|"agent" }` |
| T3 | `GET`    | `/topics/:topicId` | Topic detail (participants, contextChips, mode) |
| T4 | `PATCH`  | `/topics/:topicId` | Rename / change description / change mode |
| T5 | `DELETE` | `/topics/:topicId` | Archive |

`mode` is server-derived from data (presence of `agentRun` / `chatThread`), exposed for the sidebar mode badge.

### 3.2 Search & filters

Backs the sidebar search box + filter popover.

| # | Method | Path | Purpose |
|---|---|---|---|
| SR1 | `GET` | `/search` | Full-text search across projects, channels, topics, and messages |

**Query params**
```
q=string                                    # required
scope=projects,channels,topics,messages     # csv, default: all
projectIds=uuid,uuid                        # narrow to projects
channelIds=uuid,uuid                        # narrow to channels
limit=100
```

**Response** — flat hit list, **one entry per occurrence** (the client groups by topic). Includes `messageId` so a click can deep-link and highlight the exact message.

```json
{
  "hits": [
    {
      "id": "hit_1",
      "kind": "project|channel|topic|text|code|json|link",
      "projectId": "uuid", "projectName": "NeuralOps",
      "channelId": "uuid", "channelName": "Strategy",
      "topicId":   "uuid", "topicName":   "Q3 roadmap planning",
      "messageId": "uuid|null",
      "snippet":   "…reliability shows up 18 times…",
      "matchAt":   42,
      "language":  "yaml"
    }
  ],
  "total": 137
}
```

Click a hit → `/nexus?topic={topicId}&message={messageId}` so the client can scroll + highlight.

### 3.3 Unread badges

| # | Method | Path | Purpose |
|---|---|---|---|
| U1 | `GET`  | `/me/unread` | `{ topicId: count }[]` for sidebar badges |
| U2 | `POST` | `/topics/:topicId/read` | Mark read up to latest message |

**Realtime**
- `project:{projectId}` — topic create/update/delete
- `user:{userId}` — `unread.changed`

---

## 4. Users right bar (Roster panel)

Lists humans, models, and agents on the currently open topic. Also the surface for adding/removing them.

| # | Method | Path | Purpose |
|---|---|---|---|
| R1 | `GET`    | `/topics/:topicId/participants` | List `Participant[]` |
| R2 | `POST`   | `/topics/:topicId/participants` | Add — `{ personaId }` |
| R3 | `DELETE` | `/topics/:topicId/participants/:personaId` | Remove |

**Participant**
```json
{ "id": "uuid", "name": "Maya", "kind": "human|model|agent", "initials": "MA", "modelLabel": "researcher-agent", "online": true }
```

For the **invite a human** action (only when project membership is shared):

| # | Method | Path | Purpose |
|---|---|---|---|
| I1 | `POST`   | `/projects/:projectId/invites` | `{ email, role: "member"\|"admin" }` |
| I2 | `GET`    | `/projects/:projectId/members` | Members + roles |
| I3 | `PATCH`  | `/projects/:projectId/members/:userId` | Change role |
| I4 | `DELETE` | `/projects/:projectId/members/:userId` | Remove |
| I5 | `POST`   | `/invites/:token/accept` | Accept invite (called by invitee) |

**Realtime:** `topic:{topicId}` — `participant.created`, `participant.deleted`, `participant.presence`.

---

## 5. Chat screen

The shared workspace surface. Right-side render is decided by topic mode (`collab`, `plain-chat`, `agent`); the composer and attachment APIs are common to all three.

### 5.1 Collab mode (mixed-render bubbles)

Each message is an ordered list of `blocks`: `text | code | graph | form | json`.

| # | Method | Path | Purpose |
|---|---|---|---|
| M1 | `GET`    | `/topics/:topicId/messages?cursor=&limit=` | Paginated, oldest → newest |
| M2 | `POST`   | `/topics/:topicId/messages` | Send message (body below) |
| M3 | `PATCH`  | `/messages/:messageId` | Edit (author only) |
| M4 | `DELETE` | `/messages/:messageId` | Soft-delete |
| M5 | `POST`   | `/messages/:messageId/forms/:blockKey/submit` | Submit a form block — `{ values: {...} }` |

**`POST /topics/:topicId/messages` body**
```json
{
  "blocks": [
    { "type": "text", "text": "@Maya (researcher-agent) pull retro themes." },
    { "type": "code", "language": "yaml", "code": "..." }
  ],
  "mentions": [{ "personaId": "uuid", "model": "claude-3.5-sonnet" }],
  "attachmentIds": ["uuid"]
}
```

Server parses `@name (model)` mentions, fans out to mentioned models/agents, and streams their replies as new messages.

**Realtime:** `topic:{topicId}` — `message.created | message.updated | message.deleted`.

### 5.2 Plain chat mode

| # | Method | Path | Purpose |
|---|---|---|---|
| PC1 | `GET`    | `/topics/:topicId/chat` | List `PlainChatMsg[]` |
| PC2 | `POST`   | `/topics/:topicId/chat` | `{ text, model }` — returns user msg; assistant reply streams via SSE |
| PC3 | `GET`    | `/topics/:topicId/chat/stream` | SSE stream of assistant tokens (`data: { delta }`) |
| PC4 | `DELETE` | `/topics/:topicId/chat/:msgId` | Remove message |

### 5.3 Agent run mode

| # | Method | Path | Purpose |
|---|---|---|---|
| A1 | `GET`  | `/topics/:topicId/agent-run` | Current run (or 404) |
| A2 | `POST` | `/topics/:topicId/agent-run` | Start: `{ agentId, target, instruction }` |
| A3 | `POST` | `/agent-runs/:runId/cancel` | Cancel running steps |
| A4 | `GET`  | `/agent-runs/:runId/steps` | List steps |
| A5 | `POST` | `/agent-runs/:runId/steps/:stepId/approve` | Approve a paused step |
| A6 | `POST` | `/agent-runs/:runId/steps/:stepId/reject` | Reject a paused step |
| A7 | `GET`  | `/agent-runs/:runId/stream` | SSE: step status changes + stdout chunks |

`StepStatus`: `pending | running | approval | done | failed`.

### 5.4 Composer attachments (shared by all three modes)

| # | Method | Path | Purpose |
|---|---|---|---|
| AT1 | `POST`   | `/uploads` | `multipart/form-data` → `{ id, url, mime, size, name }` |
| AT2 | `GET`    | `/uploads/:id` | Metadata |
| AT3 | `DELETE` | `/uploads/:id` | Remove (only if not referenced) |

Attachment IDs are referenced inside message blocks or as context chips.

---

## 6. Add Persona dialog

A persona is a named participant that wraps either a **model** directly, or an **agent** (which itself uses a model + MCP servers).

| # | Method | Path | Purpose |
|---|---|---|---|
| PR1 | `GET`    | `/personas` | List workspace personas |
| PR2 | `POST`   | `/personas` | Create — body below |
| PR3 | `PATCH`  | `/personas/:id` | Update |
| PR4 | `DELETE` | `/personas/:id` | Remove |

**`POST /personas` body**
```json
{
  "name": "Maya",
  "brief": "Researcher persona",
  "kind": "model | agent",
  "modelId": "uuid",          // when kind=model OR backing model for an agent
  "agentId": "uuid",          // when kind=agent
  "mcpServerIds": ["uuid"]    // when kind=agent
}
```

The dialog also reads the catalogs in §7, §8, §9 to populate combo boxes.

---

## 7. Add Model

Catalog of LLMs that can back a persona or agent.

| # | Method | Path | Purpose |
|---|---|---|---|
| MD1 | `GET`    | `/models` | List `{ id, slug, label, provider }` |
| MD2 | `POST`   | `/models` | Register — body below |
| MD3 | `PATCH`  | `/models/:id` | Update label / api base |
| MD4 | `DELETE` | `/models/:id` | Remove |
| MD5 | `POST`   | `/models/:id/test` | Health-check (round-trip a tiny prompt) |

**`POST /models` body**
```json
{
  "slug": "openai/gpt-5",
  "label": "GPT-5",
  "provider": "openai | anthropic | google | azure | custom",
  "apiBase": "https://api.openai.com/v1",   // optional override
  "apiKeySecretRef": "OPENAI_API_KEY"        // server-side secret name
}
```

API keys are **never** sent or returned in plaintext — only the secret reference name.

---

## 8. Add Agent

Catalog of agents. Each agent has a kind (ssh, k8s, …), a default model, and a set of MCP servers it may call.

| # | Method | Path | Purpose |
|---|---|---|---|
| AG1 | `GET`    | `/agents` | List `{ id, slug, label, kind, defaultModelId, mcpServerIds }` |
| AG2 | `POST`   | `/agents` | Create — body below |
| AG3 | `PATCH`  | `/agents/:id` | Update |
| AG4 | `DELETE` | `/agents/:id` | Remove |

**`POST /agents` body**
```json
{
  "slug": "devops-agent",
  "label": "Rex",
  "kind": "ssh | k8s | git | postgres | browser",
  "defaultModelId": "uuid",
  "mcpServerIds": ["uuid"]
}
```

`kind` matches the `AgentKind` used by the Agent Run view.

---

## 9. Add MCP server

Catalog of Model Context Protocol servers an agent can call as tools.

| # | Method | Path | Purpose |
|---|---|---|---|
| MC1 | `GET`    | `/mcp-servers` | List `{ id, slug, label, transport, url?, status }` |
| MC2 | `POST`   | `/mcp-servers` | Register — body below |
| MC3 | `PATCH`  | `/mcp-servers/:id` | Update |
| MC4 | `POST`   | `/mcp-servers/:id/test` | Health-check the connection |
| MC5 | `DELETE` | `/mcp-servers/:id` | Remove |

**`POST /mcp-servers` body**
```json
{
  "slug": "github",
  "label": "GitHub",
  "transport": "stdio | http",
  "url": "https://mcp.github.com",          // when transport=http
  "command": "npx -y @modelcontextprotocol/server-github",  // when transport=stdio
  "env": { "GITHUB_TOKEN": "secret-ref" }
}
```

`status` (server-computed): `unknown | healthy | error`.

---

## 10. Add Context (Context bar)

Per-topic context chips: files, URLs, mentions, free-text notes. Backs the `+ add context` button on the Context bar.

| # | Method | Path | Purpose |
|---|---|---|---|
| CX1 | `GET`    | `/topics/:topicId/context` | List chips |
| CX2 | `POST`   | `/topics/:topicId/context` | Add chip — `{ kind, label, ref? }` |
| CX3 | `DELETE` | `/topics/:topicId/context/:chipId` | Remove chip |
| CX4 | `POST`   | `/topics/:topicId/context/upload` | `multipart/form-data` for file chips → returns chip + storage URL |

**Chip**
```json
{
  "id": "uuid",
  "kind": "file | url | mention | note",
  "label": "roadmap.pdf",
  "ref": "uploads/uuid | https://… | personaId | null",
  "added_by": "uuid",
  "added_at": "..."
}
```

When the topic mode is `collab`, mentioned personas in chips also become topic participants automatically.

---

## 11. Resource cheatsheet

```text
Project ─┬─ Channel ─┬─ Topic ─┬─ Participants[]
         │           │         ├─ ContextChips[]
         │           │         ├─ Messages[] (collab) ──► blocks: text|code|graph|form|json
         │           │         ├─ ChatThread[]  (plain-chat)
         │           │         └─ AgentRun ── Steps[]
         │           └─ Members[]
         └─ Invites[]

Workspace ─┬─ Personas[] ── (Model | Agent ── MCPServers[])
           ├─ Models[]
           ├─ Agents[]
           └─ MCPServers[]
```

---

## 12. Realtime channels

| Channel | Events |
|---|---|
| `user:{userId}` | `unread.changed`, `me.updated` |
| `project:{projectId}` | `topic.created`, `topic.updated`, `topic.deleted`, `channel.*` |
| `topic:{topicId}` | `message.*`, `participant.*`, `context.*`, `agent-run.*` |
| `agent-run:{runId}` | `step.status`, `step.output` (chunked) |

---

## 13. Build order (for reference)

1. **Login** (§1) — auth + `/me`
2. **Signup** (§2) — same Google flow + optional onboarding `PATCH /me`
3. **Project sidebar** (§3) — Projects/Channels/Topics CRUD + search + unread
4. **Users right bar** (§4) — Participants + Invites
5. **Chat screen** (§5) — Collab → Plain-chat → Agent run
6. **Add Persona** (§6) + Models (§7) / Agents (§8) / MCP servers (§9) catalogs
7. **Add Context** (§10) — chips + uploads
