## MVP Registration Strategy

For the MVP, NeuralOps will support Google authentication only.

Users will register and sign in using Google OAuth.

Later versions may support:

- email/password signup
- Apple Sign-In
- Microsoft SSO
- GitHub login
- enterprise SSO

Google authentication is used for identity verification and account creation.

Google Gmail access is handled as a separate consent flow because email access requires additional OAuth scopes and user approval.

---

## Story: Register with Google

As a new user,  
I want to register using my Google account,  
So that I can access NeuralOps without creating a separate password.

### Flow

```text
User clicks "Continue with Google"
→ redirect to Google OAuth consent
→ user grants basic profile/email permission
→ backend validates Google token
→ create User
→ create Human
→ create default Company
→ create CompanyAccess(owner)
→ issue application session/JWT
```

### Acceptance Criteria

- User can register using Google
- Google token is validated server-side
- Email is retrieved from Google profile
- User is created if not already present
- Human is linked to User
- Default Company is created for first-time user
- User becomes company owner
- Application session/JWT is issued
- Audit log is created

---

## Story: Login with Google

As an existing user,  
I want to sign in using Google,  
So that I can access my existing workspace.

### Flow

```text
User clicks "Continue with Google"
→ backend validates Google identity
→ find existing Human by Google identity or email
→ update last_login
→ issue application session/JWT
```

### Acceptance Criteria

- Existing user can login with Google
- Duplicate users are not created
- Google account is linked to existing Human
- Session/JWT is issued
- Failed token validation is rejected
- Login event is audited

---

## Story: Request Gmail Access Permission

As a user,  
I want to grant NeuralOps permission to access my Gmail,  
So that AI agents can later help me search, summarize, or process emails.

### Flow

```text
User registers/logs in with Google
→ app explains why Gmail permission is needed
→ user grants Gmail OAuth scopes
→ backend receives authorization code
→ backend exchanges code for tokens
→ store token reference securely
→ mark Gmail integration as connected
```

### Acceptance Criteria

- Gmail access is requested with clear explanation
- Gmail consent is separate from basic login
- User can deny Gmail access and still use normal login if allowed
- OAuth tokens are stored securely
- Raw tokens are not exposed in UI or logs
- Gmail integration status is stored
- User can disconnect Gmail later

---

## Story: Store Google OAuth Identity

As the system,  
I want to store Google identity mapping,  
So that future logins connect to the same Human account.

### Suggested Fields

```text
HumanExternalIdentity
- id
- human_id
- provider = "google"
- provider_subject_id
- email
- email_verified
- scopes_granted
- created_at
- updated_at
```

### Acceptance Criteria

- Google `sub` value is stored as stable provider identity
- Email is stored for display and fallback matching
- Email verification status is stored
- Granted scopes are tracked
- One Google account cannot be linked to multiple Humans in same system

---

## Story: Store Gmail Integration

As the system,  
I want to store Gmail integration separately from login identity,  
So that email access can be managed independently.

### Suggested Fields

```text
UserIntegration
- id
- human_id
- company_id
- provider = "gmail"
- status
- scopes_granted
- token_secret_ref
- refresh_token_secret_ref
- connected_at
- disconnected_at
```

### Acceptance Criteria

- Gmail integration belongs to Human and Company
- OAuth tokens are stored through secret manager
- Database stores only secret references
- Granted scopes are recorded
- Integration can be disabled or revoked
- Gmail access is not required for normal authentication unless business rule requires it

---

## Story: Disconnect Gmail Access

As a user,  
I want to disconnect Gmail access,  
So that NeuralOps can no longer access my emails.

### Flow

```text
User opens integrations
→ clicks disconnect Gmail
→ revoke Google token if possible
→ disable Gmail integration
→ remove/disable secret references
→ audit event is created
```

### Acceptance Criteria

- User can disconnect Gmail
- Tokens are revoked or disabled
- Gmail integration status becomes disconnected
- Existing derived data policy is respected
- Audit log is created

# Registration & Authentication APIs

## 1. Start Google Login

### `GET /api/v1/auth/google/start`

Starts Google OAuth login/signup flow.

### Query Params

```json
{
  "redirect_uri": "https://app.neuralops.ai/auth/callback",
  "intent": "login"
}
```

### Response

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "secure-random-state-token"
}
```

---

## 2. Google OAuth Callback

### `POST /api/v1/auth/google/callback`

Handles Google OAuth response and creates/logs in user.

### Input

```json
{
  "code": "google_authorization_code",
  "state": "secure-random-state-token",
  "redirect_uri": "https://app.neuralops.ai/auth/callback"
}
```

### Success Response

```json
{
  "access_token": "app_jwt_access_token",
  "refresh_token": "app_jwt_refresh_token",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "user_uuid",
    "type": "human",
    "display_name": "Noaman Faisal"
  },
  "human": {
    "id": "human_uuid",
    "email": "noaman@gmail.com",
    "email_verified": true,
    "timezone": null,
    "locale": "en"
  },
  "current_company": {
    "id": "company_uuid",
    "name": "Noaman Faisal Workspace",
    "role": "owner"
  },
  "is_new_user": true
}
```

### Error Response

```json
{
  "error": {
    "code": "GOOGLE_AUTH_FAILED",
    "message": "Google authentication failed."
  }
}
```

---

## 3. Refresh Token

### `POST /api/v1/auth/token/refresh`

Refreshes app session token.

### Input

```json
{
  "refresh_token": "app_jwt_refresh_token"
}
```

### Response

```json
{
  "access_token": "new_app_jwt_access_token",
  "refresh_token": "new_app_jwt_refresh_token",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## 4. Logout

### `POST /api/v1/auth/logout`

Logs out current session.

### Input

```json
{
  "refresh_token": "app_jwt_refresh_token"
}
```

### Response

```json
{
  "success": true,
  "message": "Logged out successfully."
}
```

---

# Google Identity APIs

## 5. Get Current User

### `GET /api/v1/me`

Returns signed-in user profile.

### Response

```json
{
  "user": {
    "id": "user_uuid",
    "type": "human",
    "display_name": "Noaman Faisal",
    "avatar_url": "https://..."
  },
  "human": {
    "id": "human_uuid",
    "email": "noaman@gmail.com",
    "email_verified": true,
    "timezone": "America/Edmonton",
    "locale": "en"
  },
  "current_company": {
    "id": "company_uuid",
    "name": "Noaman Faisal Workspace",
    "role": "owner"
  }
}
```

---

## 6. List Connected External Identities

### `GET /api/v1/me/external-identities`

### Response

```json
{
  "items": [
    {
      "id": "identity_uuid",
      "provider": "google",
      "email": "noaman@gmail.com",
      "email_verified": true,
      "scopes_granted": [
        "openid",
        "email",
        "profile"
      ],
      "created_at": "2026-05-11T10:00:00Z"
    }
  ]
}
```

---

# Gmail Integration APIs

## 7. Start Gmail Connection

### `GET /api/v1/integrations/gmail/start`

Starts Gmail permission consent flow.

### Query Params

```json
{
  "company_id": "company_uuid",
  "redirect_uri": "https://app.neuralops.ai/integrations/gmail/callback"
}
```

### Response

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "secure-random-state-token",
  "requested_scopes": [
    "https://www.googleapis.com/auth/gmail.readonly"
  ]
}
```

---

## 8. Gmail OAuth Callback

### `POST /api/v1/integrations/gmail/callback`

Stores Gmail integration token references.

### Input

```json
{
  "company_id": "company_uuid",
  "code": "google_authorization_code",
  "state": "secure-random-state-token",
  "redirect_uri": "https://app.neuralops.ai/integrations/gmail/callback"
}
```

### Success Response

```json
{
  "integration": {
    "id": "integration_uuid",
    "provider": "gmail",
    "status": "connected",
    "human_id": "human_uuid",
    "company_id": "company_uuid",
    "scopes_granted": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "connected_at": "2026-05-11T10:15:00Z"
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "GMAIL_CONNECTION_FAILED",
    "message": "Unable to connect Gmail account."
  }
}
```

---

## 9. Get Gmail Integration Status

### `GET /api/v1/integrations/gmail/status`

### Query Params

```json
{
  "company_id": "company_uuid"
}
```

### Response

```json
{
  "provider": "gmail",
  "status": "connected",
  "email": "noaman@gmail.com",
  "scopes_granted": [
    "https://www.googleapis.com/auth/gmail.readonly"
  ],
  "connected_at": "2026-05-11T10:15:00Z",
  "last_checked_at": "2026-05-11T10:20:00Z"
}
```

---

## 10. Disconnect Gmail

### `DELETE /api/v1/integrations/gmail`

### Input

```json
{
  "company_id": "company_uuid"
}
```

### Response

```json
{
  "success": true,
  "provider": "gmail",
  "status": "disconnected",
  "disconnected_at": "2026-05-11T10:30:00Z"
}
```

---

# Optional MVP Gmail Read APIs

## 11. Search Gmail Messages

### `POST /api/v1/integrations/gmail/messages/search`

### Input

```json
{
  "company_id": "company_uuid",
  "query": "from:client@example.com newer_than:30d",
  "limit": 10
}
```

### Response

```json
{
  "items": [
    {
      "gmail_message_id": "gmail_msg_id",
      "thread_id": "gmail_thread_id",
      "subject": "Project Update",
      "from": "client@example.com",
      "snippet": "Here is the latest update...",
      "received_at": "2026-05-10T18:30:00Z"
    }
  ]
}
```

---

## 12. Read Gmail Message

### `GET /api/v1/integrations/gmail/messages/{gmail_message_id}`

### Query Params

```json
{
  "company_id": "company_uuid"
}
```

### Response

```json
{
  "gmail_message_id": "gmail_msg_id",
  "thread_id": "gmail_thread_id",
  "subject": "Project Update",
  "from": "client@example.com",
  "to": [
    "noaman@gmail.com"
  ],
  "received_at": "2026-05-10T18:30:00Z",
  "body_text": "Email body text...",
  "attachments": [
    {
      "filename": "proposal.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 245000
    }
  ]
}
```


# NeuralOps MVP API List

## 1. Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/login` | Login with email/password through Supabase |
| POST | `/api/v1/auth/signin` | Sign in using existing Supabase access token |
| GET | `/api/v1/auth/me` | Get current local NeuralOps user |
| POST | `/api/v1/auth/refresh` | Refresh Supabase access token |
| POST | `/api/v1/auth/logout` | Logout / clear session |

---

## 2. Instance Setup

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/instance/status` | Check if local Personal Edition instance is initialized |
| POST | `/api/v1/instance/setup-owner` | Set first owner of this local instance |
| GET | `/api/v1/instance/me` | Current user’s instance role/status |

---

## 3. Users / Humans

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/users` | List local users allowed in this instance |
| GET | `/api/v1/users/{user_id}` | Get user detail |
| PATCH | `/api/v1/users/{user_id}` | Update user profile/role metadata |
| DELETE | `/api/v1/users/{user_id}` | Disable/remove user from local instance |

---

## 4. Invitations

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/invitations` | Invite user by email to company/project/channel |
| GET | `/api/v1/invitations` | List pending invitations |
| POST | `/api/v1/invitations/accept` | Accept invitation after Supabase login |
| DELETE | `/api/v1/invitations/{invitation_id}` | Revoke invitation |

---

## 5. Companies

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/companies` | List companies user can access |
| GET | `/api/v1/companies/{company_id}` | Get company detail |
| PATCH | `/api/v1/companies/{company_id}` | Update company name/settings |
| GET | `/api/v1/companies/{company_id}/members` | List company members |

---

## 6. Projects

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/projects` | List projects |
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects/{project_id}` | Get project detail |
| PATCH | `/api/v1/projects/{project_id}` | Update project |
| DELETE | `/api/v1/projects/{project_id}` | Archive/delete project |
| GET | `/api/v1/projects/{project_id}/members` | List project members |
| POST | `/api/v1/projects/{project_id}/members` | Add member to project |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | Remove project member |

---

## 7. Channels

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/projects/{project_id}/channels` | List project channels |
| POST | `/api/v1/projects/{project_id}/channels` | Create channel |
| GET | `/api/v1/channels/{channel_id}` | Get channel detail |
| PATCH | `/api/v1/channels/{channel_id}` | Update channel |
| DELETE | `/api/v1/channels/{channel_id}` | Archive/delete channel |
| GET | `/api/v1/channels/{channel_id}/members` | List channel members |
| POST | `/api/v1/channels/{channel_id}/members` | Add member to channel |
| DELETE | `/api/v1/channels/{channel_id}/members/{user_id}` | Remove channel member |

---

## 8. Chat Topics

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/channels/{channel_id}/topics` | List topics in channel |
| POST | `/api/v1/channels/{channel_id}/topics` | Create chat topic |
| GET | `/api/v1/topics/{topic_id}` | Get topic detail |
| PATCH | `/api/v1/topics/{topic_id}` | Update topic |
| DELETE | `/api/v1/topics/{topic_id}` | Archive/delete topic |
| POST | `/api/v1/topics/{topic_id}/read` | Mark topic as read |

---

## 9. Chat Messages

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/topics/{topic_id}/messages` | List topic messages |
| POST | `/api/v1/topics/{topic_id}/messages` | Send message |
| GET | `/api/v1/messages/{message_id}` | Get message detail |
| PATCH | `/api/v1/messages/{message_id}` | Edit message |
| DELETE | `/api/v1/messages/{message_id}` | Delete message |
| POST | `/api/v1/messages/{message_id}/forms/{block_key}/submit` | Submit form block |

---

## 10. Topic Participants

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/topics/{topic_id}/participants` | List humans/personas/agents in topic |
| POST | `/api/v1/topics/{topic_id}/participants` | Add participant/persona/agent |
| DELETE | `/api/v1/topics/{topic_id}/participants/{participant_id}` | Remove participant |

---

## 11. AI Models

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/models` | List AI models |
| POST | `/api/v1/models` | Create AI model |
| GET | `/api/v1/models/{model_id}` | Get model detail |
| PATCH | `/api/v1/models/{model_id}` | Update model |
| DELETE | `/api/v1/models/{model_id}` | Disable/delete model |
| POST | `/api/v1/models/{model_id}/test` | Test model connection |

---

## 12. MCP Servers

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/mcp-servers` | List MCP servers |
| POST | `/api/v1/mcp-servers` | Create MCP server |
| GET | `/api/v1/mcp-servers/{server_id}` | Get MCP server detail |
| PATCH | `/api/v1/mcp-servers/{server_id}` | Update MCP server |
| DELETE | `/api/v1/mcp-servers/{server_id}` | Delete MCP server |
| POST | `/api/v1/mcp-servers/{server_id}/test` | Test MCP server |

---

## 13. AI Agents

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/agents` | List AI agents |
| POST | `/api/v1/agents` | Create AI agent |
| GET | `/api/v1/agents/{agent_id}` | Get agent detail |
| PATCH | `/api/v1/agents/{agent_id}` | Update agent |
| DELETE | `/api/v1/agents/{agent_id}` | Disable/delete agent |
| POST | `/api/v1/agents/{agent_id}/test` | Test agent execution |

---

## 14. Personas

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/personas` | List personas |
| POST | `/api/v1/personas` | Create persona |
| GET | `/api/v1/personas/{persona_id}` | Get persona detail |
| PATCH | `/api/v1/personas/{persona_id}` | Update persona |
| DELETE | `/api/v1/personas/{persona_id}` | Delete persona |

---

## 15. Knowledge Bases

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/knowledge-bases` | List knowledge bases |
| POST | `/api/v1/knowledge-bases` | Create knowledge base |
| GET | `/api/v1/knowledge-bases/{kb_id}` | Get knowledge base detail |
| PATCH | `/api/v1/knowledge-bases/{kb_id}` | Update knowledge base |
| DELETE | `/api/v1/knowledge-bases/{kb_id}` | Delete knowledge base |
| POST | `/api/v1/knowledge-bases/{kb_id}/attach` | Attach KB to project/channel/topic |
| POST | `/api/v1/knowledge-bases/{kb_id}/detach` | Detach KB |

---

## 16. Knowledge Files

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/knowledge-bases/{kb_id}/files` | List KB files |
| POST | `/api/v1/knowledge-bases/{kb_id}/files` | Upload file |
| GET | `/api/v1/knowledge-files/{file_id}` | Get file detail |
| DELETE | `/api/v1/knowledge-files/{file_id}` | Delete file |
| POST | `/api/v1/knowledge-files/{file_id}/reprocess` | Reprocess file |

---

## 17. Search

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/search` | Search projects/channels/topics/messages |
| POST | `/api/v1/knowledge/search` | Semantic search inside attached knowledge |

---

## 18. Uploads

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/uploads` | Upload attachment |
| GET | `/api/v1/uploads/{upload_id}` | Get upload metadata |
| DELETE | `/api/v1/uploads/{upload_id}` | Delete upload |