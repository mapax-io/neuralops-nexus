## 1. Authentication APIs

| Method | Endpoint |
| --- | --- |
| POST | /api/v1/auth/signin |
| GET | /api/v1/auth/me |
| POST | /api/v1/auth/logout |
| POST | /api/v1/auth/refresh |
| GET | /api/v1/auth/session |

# Authentication APIs

> **Auth Provider:** Supabase  
> **Strategy:** Supabase issues JWTs. Django verifies the token, syncs the local user, and returns session context. Django does **not** manage passwords or issue its own tokens.

---

## 1. POST /api/v1/auth/signin

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/auth/signin` |
| Auth Required | No |
| Description | Accepts a Supabase access token, verifies it against Supabase JWKS, syncs or creates the local Django user, and returns the local user profile along with identity details. |

### Request
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `access_token` | string | Yes | Valid Supabase JWT access token issued after Supabase sign-in |

### Response
```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "noaman@example.com",
    "username": "noaman@example.com",
    "is_new_user": false
  },
  "external_identity": {
    "provider": "supabase",
    "provider_user_id": "auth-uuid-from-supabase",
    "email": "noaman@example.com",
    "email_verified": true
  }
}
```

**Error Responses**
```json
{ "detail": "Invalid Supabase token." }         // 401 — bad/expired token
{ "detail": "Email is missing from token." }    // 401 — token has no email claim
```

### Flow
```
Client
  │
  ├─► POST /api/v1/auth/signin  { access_token }
  │
  │   [Django / authn]
  │   1. Extract access_token from request body
  │   2. Fetch JWKS from Supabase (cached via PyJWKClient)
  │   3. Verify JWT signature + audience + issuer
  │   4. Extract claims: sub (supabase uid), email, email_verified
  │   5. get_or_create Django User by email
  │   6. Ensure username is set, is_active = True
  │   7. Return local user + external identity
  │
  └─► 200 OK  { user, external_identity }
       or
      401     { detail: "..." }
```

### Models Used
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | `get_or_create` by email; update username/is_active if needed |

### Proposed Django ORM Queries
```python
# Sync or create local user from Supabase claims
user, created = User.objects.get_or_create(
    email=email,
    defaults={
        "username": email,
        "is_active": True,
    },
)

# Patch stale fields if needed
if not user.username or not user.is_active:
    User.objects.filter(pk=user.pk).update(
        username=email,
        is_active=True,
    )
```

---

## 2. GET /api/v1/auth/me

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/auth/me` |
| Auth Required | Yes — Supabase JWT in `Authorization: Bearer <token>` |
| Description | Returns the authenticated user's local profile, current active company, and human profile if it exists. |

### Request
```json
// No request body. Auth via header:
// Authorization: Bearer <supabase_access_token>
```

### Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "noaman@example.com",
  "username": "noaman@example.com",
  "user_type": "human",
  "is_active": true,
  "current_company": {
    "id": "company-uuid",
    "name": "NeuralOps",
    "slug": "neuralops"
  },
  "human_profile": {
    "full_name": "Noaman Faisal",
    "avatar": "https://cdn.example.com/avatars/noaman.jpg",
    "timezone": "Asia/Karachi",
    "locale": "en"
  }
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401 — missing or invalid token
```

### Flow
```
Client
  │
  ├─► GET /api/v1/auth/me
  │   Authorization: Bearer <token>
  │
  │   [Django / authn middleware]
  │   1. Extract Bearer token from Authorization header
  │   2. Verify JWT via Supabase JWKS
  │   3. Resolve local User by email claim
  │   4. Fetch related: current_company, human_profile
  │   5. Serialize and return
  │
  └─► 200 OK  { user profile }
       or
      401     { detail: "Unauthorized" }
```

### Models Used
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Fetch by email from JWT claim |
| `Company` | `nucleus` | Read via `user.current_company` FK |
| `Human` | `nucleus` | Read via `user.human_profile` OneToOne |

### Proposed Django ORM Queries
```python
# Fetch user with related data in one query
user = (
    User.objects
    .select_related("current_company", "human_profile")
    .get(email=email)   # email extracted from verified JWT
)
```

---

## 3. POST /api/v1/auth/logout

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/auth/logout` |
| Auth Required | Yes — Supabase JWT |
| Description | Signals logout intent. Since JWTs are stateless, Django itself has no session to destroy. This endpoint is the hook for any server-side cleanup (e.g., clearing UserSession records, invalidating refresh tokens stored server-side). The actual Supabase token invalidation must be called from the client via the Supabase SDK. |

### Request
```json
// No body required.
// Authorization: Bearer <supabase_access_token>
```

### Response
```json
{
  "detail": "Logged out successfully."
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
```

### Flow
```
Client
  │
  ├─► POST /api/v1/auth/logout
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT (resolve local user)
  │   2. Delete or invalidate any server-side UserSession for this user
  │   3. Return 200 OK
  │
  │   [Client responsibility]
  │   4. Client calls supabase.auth.signOut() to invalidate Supabase token
  │
  └─► 200 OK  { "detail": "Logged out successfully." }
```

> ⚠️ Django cannot invalidate a Supabase JWT. The client **must** also call `supabase.auth.signOut()`.

### Models Used
| Model | App | Action |
|---|---|---|
| `UserSession` *(proposed)* | `nucleus` | Delete active session record for this user |

### Proposed Django ORM Queries
```python
# Invalidate server-side session record (once UserSession model exists)
UserSession.objects.filter(user=request.user, is_active=True).update(
    is_active=False,
    ended_at=now(),
)
```

---

## 4. POST /api/v1/auth/refresh

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/auth/refresh` |
| Auth Required | No (the refresh token itself is the credential) |
| Description | Accepts a Supabase refresh token, calls the Supabase token refresh endpoint server-side, and returns a new access + refresh token pair. Keeps the Django backend as the single token exchange point — the client never calls Supabase directly for refreshes. |

### Request
```json
{
  "refresh_token": "supabase-refresh-token-string"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `refresh_token` | string | Yes | Supabase refresh token |

### Response
```json
{
  "access_token": "new-jwt-access-token",
  "refresh_token": "new-refresh-token",
  "expires_in": 3600,
  "token_type": "bearer"
}
```

**Error Responses**
```json
{ "detail": "Refresh token is invalid or expired." }   // 401
```

### Flow
```
Client
  │
  ├─► POST /api/v1/auth/refresh  { refresh_token }
  │
  │   [Django / authn]
  │   1. Receive refresh_token
  │   2. POST to Supabase token endpoint:
  │      POST https://<project>.supabase.co/auth/v1/token?grant_type=refresh_token
  │      Body: { refresh_token }
  │   3. On success: return new access_token + refresh_token to client
  │   4. On failure: return 401
  │
  └─► 200 OK  { access_token, refresh_token, expires_in, token_type }
       or
      401     { detail: "..." }
```

> **Note:** This is a proxy call to Supabase. Django acts as intermediary — useful for hiding Supabase credentials from the client and centralizing token handling.

### Models Used
| Model | App | Action |
|---|---|---|
| `UserSession` *(proposed)* | `nucleus` | Optionally update last refreshed timestamp |

### Proposed Django ORM Queries
```python
# Supabase refresh call via httpx (no ORM query for the refresh itself)
import httpx

async def refresh_supabase_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            json={"refresh_token": refresh_token},
            headers={"apikey": settings.SUPABASE_ANON_KEY},
        )
        response.raise_for_status()
        return response.json()

# Optionally touch UserSession
UserSession.objects.filter(user=user, is_active=True).update(
    last_refreshed_at=now()
)
```

---

## 5. GET /api/v1/auth/session

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/auth/session` |
| Auth Required | Yes — Supabase JWT |
| Description | Returns the current session state: local user summary, active company context, JWT metadata (expiry, issued-at), and any server-side session record. Useful for client app boot — one call to establish full context. |

### Request
```json
// No body.
// Authorization: Bearer <supabase_access_token>
```

### Response
```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "noaman@example.com",
    "username": "noaman@example.com",
    "user_type": "human"
  },
  "company": {
    "id": "company-uuid",
    "name": "NeuralOps",
    "slug": "neuralops",
    "role": "owner"
  },
  "token_meta": {
    "issued_at": "2026-05-22T02:00:00Z",
    "expires_at": "2026-05-22T03:00:00Z"
  },
  "session": {
    "id": "session-uuid",
    "created_at": "2026-05-22T02:00:00Z",
    "last_active_at": "2026-05-22T02:43:00Z"
  }
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
```

### Flow
```
Client
  │
  ├─► GET /api/v1/auth/session
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, extract claims (sub, email, iat, exp)
  │   2. Resolve local User by email
  │   3. Fetch current_company + user's role in that company (CompanyAccess)
  │   4. Fetch or create UserSession record; update last_active_at
  │   5. Build and return full session context
  │
  └─► 200 OK  { user, company, token_meta, session }
       or
      401     { detail: "Unauthorized" }
```

### Models Used
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Fetch by email |
| `Company` | `nucleus` | Read via `user.current_company` |
| `CompanyAccess` | `nucleus` | Read role for current company |
| `UserSession` *(proposed)* | `nucleus` | get_or_create; update `last_active_at` |

### Proposed Django ORM Queries
```python
# Fetch user + company context
user = (
    User.objects
    .select_related("current_company")
    .get(email=email)
)

# Get user's role in current company
company_access = CompanyAccess.objects.get(
    user=user,
    company=user.current_company,
    is_active=True,
)

# Upsert UserSession
session, _ = UserSession.objects.update_or_create(
    user=user,
    is_active=True,
    defaults={"last_active_at": now()},
)
```

---

## Proposed Missing Model: UserSession

> Referenced by logout, refresh, and session endpoints. Needs to be added to `nucleus/models/account.py`.

```python
class UserSession(BaseModel):
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    is_active    = models.BooleanField(default=True, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)
    ended_at     = models.DateTimeField(null=True, blank=True)
    ip_address   = models.GenericIPAddressField(null=True, blank=True)
    user_agent   = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "accounts_user_session"
```
