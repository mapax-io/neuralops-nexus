# NeuralOps Nexus — Auth API Specification
**Version:** 1.0  
**Auth method:** Google OAuth 2.0 only (no email/password)  
**Backend:** Lovable Cloud (Supabase under the hood)  
**Base URL (frontend routes):** `https://<your-domain>`  
**Base URL (auth API):** `https://<project-ref>.supabase.co/auth/v1`

---

## 1. Overview

NeuralOps Nexus uses **Google as the sole identity provider**. There are no
password endpoints, no email verification endpoints, and no manual signup form.

The same OAuth flow is used for both **Sign Up** and **Login**:
- If the Google account has never authenticated → a new user + profile row is created.
- If the Google account already exists → an existing session is issued.

The frontend triggers OAuth via the Lovable SDK (`lovable.auth.signInWithOAuth("google", ...)`),
which delegates to Supabase Auth and the Google OAuth broker.

---

## 2. Endpoints

### 2.1 `POST /auth/signup` (Initiate Sign Up with Google)

Initiates the Google OAuth flow for a new user. Same wire format as login.

**Request**

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | `string` (enum: `"google"`) | yes | Identity provider |
| `redirect_uri` | `string` (URL) | yes | Where to send the user after Google approves. Must be on an allow-listed origin. Typical: `https://<app>/nexus` |
| `extraParams.prompt` | `string` (enum: `"select_account"`, `"consent"`, `"none"`) | no | Forces Google account chooser |
| `extraParams.hd` | `string` (domain) | no | Restricts to a Google Workspace domain (e.g. `acme.com`) |

**Example request body**
```json
{
  "provider": "google",
  "redirect_uri": "https://nexus.example.com/nexus",
  "extraParams": {
    "prompt": "select_account"
  }
}
```

**Response — 302 Redirect (typical)**
The browser is redirected to Google's consent screen. The body is empty.

```
HTTP/1.1 302 Found
Location: https://accounts.google.com/o/oauth2/v2/auth?...&state=<opaque>
```

**Response — 200 OK (when tokens are returned inline, e.g. silent re-auth)**
```json
{
  "redirected": false,
  "tokens": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "v1.MrefreshT...",
    "expires_in": 3600,
    "expires_at": 1746979200,
    "token_type": "bearer",
    "user": {
      "id": "8f1c...e9",
      "email": "alex@acme.com",
      "user_metadata": {
        "full_name": "Alex Chen",
        "avatar_url": "https://lh3.googleusercontent.com/..."
      }
    }
  }
}
```

**Errors**

| Status | `error.code` | Meaning |
|---|---|---|
| 400 | `invalid_provider` | `provider` is not `"google"` |
| 400 | `invalid_redirect_uri` | `redirect_uri` not on allow-list |
| 401 | `oauth_denied` | User canceled at Google |
| 500 | `oauth_broker_error` | Upstream provider failure |

---

### 2.2 `POST /auth/login` (Initiate Login with Google)

Identical contract to `POST /auth/signup`. The backend resolves whether the
account is new or existing automatically.

Use this endpoint when the user clicks **Continue with Google** on `/login`.

---

### 2.3 `GET /auth/callback` (OAuth Callback)

Google redirects the user here after consent. Handled by Supabase Auth; the
frontend should not call this directly. On success the user is forwarded to
`redirect_uri` with a session cookie set.

**Query parameters (from Google)**

| Param | Description |
|---|---|
| `code` | Authorization code |
| `state` | CSRF token (validated server-side) |

**On success**: 302 → `redirect_uri` (e.g. `/nexus`) with session established.  
**On failure**: 302 → `/login?error=<code>`.

---

### 2.4 `GET /auth/session` (Get current session)

**Request**
```
Authorization: Bearer <access_token>
```

**Response — 200**
```json
{
  "user": {
    "id": "8f1c...e9",
    "email": "alex@acme.com",
    "created_at": "2026-05-11T10:14:22Z",
    "last_sign_in_at": "2026-05-11T10:14:22Z"
  },
  "profile": {
    "id": "8f1c...e9",
    "display_name": "Alex Chen",
    "email": "alex@acme.com",
    "avatar_url": "https://lh3.googleusercontent.com/..."
  },
  "expires_at": 1746979200
}
```

**Response — 401**
```json
{ "error": { "code": "no_session", "message": "Not authenticated" } }
```

---

### 2.5 `POST /auth/refresh` (Refresh access token)

**Request**
```json
{ "refresh_token": "v1.MrefreshT..." }
```

**Response — 200**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "v1.NewRefresh...",
  "expires_in": 3600,
  "expires_at": 1746982800,
  "token_type": "bearer"
}
```

---

### 2.6 `POST /auth/logout`

**Request**
```
Authorization: Bearer <access_token>
```
Body: empty.

**Response — 204 No Content**

---

## 3. Side-Effects on Sign Up

When a brand-new Google identity completes the OAuth flow, the backend trigger
`handle_new_user()` automatically inserts a row into `public.profiles`:

```sql
INSERT INTO public.profiles (id, display_name, email, avatar_url)
VALUES (auth.users.id, full_name, email, avatar_url);
```

The frontend can read it via `GET /rest/v1/profiles?id=eq.<user_id>` once
authenticated.

---

## 4. Frontend Usage (Reference)

```ts
import { lovable } from "@/integrations/lovable";

const result = await lovable.auth.signInWithOAuth("google", {
  redirect_uri: window.location.origin + "/nexus",
});

if (result.error)      { /* show toast */ }
else if (result.redirected) { /* browser will navigate to Google */ }
else                   { window.location.assign("/nexus"); }
```

---

## 5. Status Codes Summary

| Code | Meaning |
|---|---|
| 200 | Success (tokens returned inline) |
| 204 | Success, no body (logout) |
| 302 | Redirect to Google or back to app |
| 400 | Bad request / invalid params |
| 401 | Not authenticated / OAuth denied |
| 500 | Upstream / broker error |

---

## 6. Security Notes

- Sessions are stored in `localStorage` by the Supabase client (`persistSession: true`).
- Access tokens are short-lived (1 hour); refresh tokens auto-rotate.
- `redirect_uri` is validated against an allow-list — arbitrary URLs are rejected.
- Roles (when introduced) live in a separate `user_roles` table, never on `profiles`.

# NeuralOps Nexus — Workspace API Specification

Version: 0.2 (mockup-aligned)
Base URL: `https://api.neuralops.app/v1`
Auth: `Authorization: Bearer <jwt>` (Google OAuth issued)
Content-Type: `application/json`

Hierarchy: **Project → Channel → Topic → Message**
A Topic runs in one of three modes: `collab` | `plain-chat` | `agent`.
Participants are of kind: `human` | `model` | `agent`.

---

## 1. Common Objects

### Participant
```json
{
  "id": "prt_01HZ...",
  "kind": "human | model | agent",
  "name": "John",
  "model": "claude-3.5-sonnet",   // models/agents only
  "mcp": "github",                 // agents only
  "avatarUrl": "https://...",
  "online": true
}
```

### Topic
```json
{
  "id": "tpc_...",
  "channelId": "chn_...",
  "name": "Deploy hotfix to prod",
  "mode": "collab",
  "context": ["repo:acme/api", "env:prod"],
  "participantIds": ["prt_a","prt_b"],
  "createdAt": "2026-05-11T09:14:00Z"
}
```

### Message (collab — mixed-render blocks)
```json
{
  "id": "msg_...",
  "topicId": "tpc_...",
  "authorId": "prt_...",
  "createdAt": "2026-05-11T09:15:21Z",
  "mentions": [{ "participantId": "prt_b", "modelHint": "claude-3.5-sonnet" }],
  "blocks": [
    { "type": "text",  "content": "Please review then run." },
    { "type": "code",  "language": "bash", "content": "kubectl rollout ..." },
    { "type": "json",  "content": { "replicas": 3 } },
    { "type": "form",  "schema": { "fields": [{ "name":"approve","type":"boolean" }] } },
    { "type": "graph", "kind": "line", "data": [...] }
  ]
}
```

### Error envelope
```json
{ "error": { "code": "topic_not_found", "message": "..." } }
```

---

## 2. Projects

### `GET /projects`
**Output**
```json
{ "projects": [ { "id":"prj_1","name":"Platform","channelCount":4 } ] }
```

### `POST /projects`
**Input** `{ "name": "Platform" }`
**Output** `{ "project": { "id":"prj_1","name":"Platform" } }`

---

## 3. Channels

### `GET /projects/{projectId}/channels`
**Output** `{ "channels": [ { "id":"chn_1","name":"#incidents","topicCount":12 } ] }`

### `POST /projects/{projectId}/channels`
**Input** `{ "name": "#incidents" }`
**Output** `{ "channel": { ... } }`

---

## 4. Topics

### `GET /channels/{channelId}/topics`
**Output** `{ "topics": [Topic, ...] }`

### `POST /channels/{channelId}/topics`
**Input**
```json
{
  "name": "Deploy hotfix to prod",
  "mode": "collab",
  "context": ["repo:acme/api"],
  "participantIds": ["prt_a","prt_b"]
}
```
**Output** `{ "topic": Topic }`

### `PATCH /topics/{topicId}/context`
**Input** `{ "add": ["env:prod"], "remove": ["repo:acme/web"] }`
**Output** `{ "context": ["repo:acme/api","env:prod"] }`

### `POST /topics/{topicId}/participants`
**Input** `{ "participantIds": ["prt_c"] }`
**Output** `{ "participantIds": ["prt_a","prt_b","prt_c"] }`

---

## 5. Messages (collab mode)

### `GET /topics/{topicId}/messages?cursor=...&limit=50`
**Output**
```json
{ "messages": [Message, ...], "nextCursor": "msg_..." }
```

### `POST /topics/{topicId}/messages`
**Input**
```json
{
  "blocks": [
    { "type":"text","content":"@John (claude-3.5-sonnet) create k8s script" }
  ],
  "mentions": [{ "participantId":"prt_john","modelHint":"claude-3.5-sonnet" }],
  "attachments": ["att_..."]
}
```
**Output** `{ "message": Message }`

### `POST /attachments` (multipart)
**Output** `{ "id":"att_...","url":"https://..." }`

---

## 6. Plain Chat mode

### `GET /topics/{topicId}/chat`
**Output**
```json
{ "model": "claude-3.5-sonnet",
  "turns": [ { "role":"user","content":"..." }, { "role":"assistant","content":"..." } ] }
```

### `POST /topics/{topicId}/chat`
**Input** `{ "content": "Summarize last incident", "model": "claude-3.5-sonnet" }`
**Output (SSE stream of)** `{ "delta": "..." }` then `{ "done": true, "messageId":"msg_..." }`

---

## 7. Agent mode

### `GET /topics/{topicId}/run`
**Output**
```json
{
  "id":"run_...","status":"running|paused|done|failed",
  "agent":"ssh-runner","model":"openai/gpt-5","mcp":"filesystem",
  "steps":[
    { "id":"stp_1","label":"Plan","status":"done","output":"..." },
    { "id":"stp_2","label":"kubectl apply","status":"awaiting_approval","destructive":true,"command":"..." }
  ]
}
```

### `POST /topics/{topicId}/run`
**Input** `{ "agentPersonaId":"prt_agent","goal":"roll back deploy" }`
**Output** `{ "run": { ... } }`

### `POST /runs/{runId}/steps/{stepId}/approve`
**Input** `{ "approve": true, "note": "ok" }`
**Output** `{ "step": { ... } }`

### `POST /runs/{runId}/cancel`
**Output** `{ "run": { "status":"canceled" } }`

---

## 8. Personas

### `GET /personas`
**Output** `{ "personas": [Participant, ...] }`

### `POST /personas` (model)
**Input**
```json
{ "kind":"model","name":"Claude","model":"anthropic/claude-3.5-sonnet",
  "brief":"Long-form reviewer","systemPrompt":"..." }
```
**Output** `{ "persona": Participant }`

### `POST /personas` (agent)
```json
{ "kind":"agent","name":"DeployBot","agent":"ssh-runner",
  "model":"openai/gpt-5","mcp":"github","brief":"Ships releases" }
```

### `DELETE /personas/{personaId}`

---

## 9. Users / Invites

### `GET /workspace/users`
**Output** `{ "users": [ { "id":"usr_..","email":"..","name":"..","role":"admin|member" } ] }`

### `POST /workspace/invites`
**Input** `{ "emails": ["a@x.com"], "role": "member" }`
**Output** `{ "invites": [ { "id":"inv_..","email":"a@x.com","status":"pending" } ] }`

---

## 10. Realtime (WebSocket)

`wss://api.neuralops.app/v1/realtime?token=<jwt>`

Subscribe:
```json
{ "op":"subscribe","topicId":"tpc_..." }
```

Server events:
```json
{ "event":"message.created", "message": Message }
{ "event":"run.step.updated", "runId":"run_..","step":{...} }
{ "event":"participant.joined", "topicId":"tpc_..","participant":Participant }
```

---

## 11. Status Codes
| Code | Meaning |
|------|---------|
| 200  | OK |
| 201  | Created |
| 400  | Validation error |
| 401  | Missing/invalid token |
| 403  | Forbidden (RLS) |
| 404  | Not found |
| 409  | Conflict (e.g. duplicate name) |
| 429  | Rate-limited |

