# Invitation APIs

> **Purpose:** Invite humans (and optionally agents) into a Company, optionally pre-assigning Project / Channel / Topic memberships.
> **Auth:** All endpoints require a valid Supabase JWT *except* `POST /api/v1/invitations/accept`, which is open (the invitation `token` is the credential, paired with a Supabase JWT proving the recipient owns the email).
> **Lifecycle:** `pending → accepted | revoked | expired`. Pending invitations carry a single-use opaque `token`; expiry is enforced server-side (default 7 days).
> **Conventions:**
> - `invitation_id` is a UUID.
> - List endpoints support `?page=&page_size=` (default `20`, max `100`).
> - Mutations require the caller to be **owner/admin** of the target Company.

---

## 1. POST /api/v1/invitations

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/invitations` |
| Auth Required | Yes — Supabase JWT |
| Description | Create one or more invitations for a Company. Sends an email with the accept link containing the opaque `token`. Optionally pre-assigns Project / Channel / Topic memberships that activate on accept. |

### Request JSON
```json
{
  "company_id": "company-uuid-1",
  "invitees": [
    {
      "email": "alice@example.com",
      "role": "member",
      "full_name": "Alice Doe",
      "preassign": {
        "project_ids": ["project-uuid-1"],
        "channel_ids": ["channel-uuid-7"],
        "topic_ids": ["topic-uuid-3"]
      }
    },
    {
      "email": "bob@example.com",
      "role": "admin"
    }
  ],
  "expires_in_days": 7,
  "message": "Welcome to NeuralOps. Onboarding doc inside."
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company_id` | UUID | Yes | Target company. Caller must be owner/admin. |
| `invitees` | array | Yes | One or more invitee objects (max 50 per call). |
| `invitees[].email` | string | Yes | RFC-5322 email. |
| `invitees[].role` | string | No | One of `owner`, `admin`, `member`, `viewer`. Default `member`. `owner` requires staff or current owner. |
| `invitees[].full_name` | string | No | Pre-fill on Human profile when accepted. |
| `invitees[].preassign.project_ids` | UUID[] | No | Auto-add to projects on accept. |
| `invitees[].preassign.channel_ids` | UUID[] | No | Auto-add to channels on accept. |
| `invitees[].preassign.topic_ids` | UUID[] | No | Auto-subscribe to topics on accept. |
| `expires_in_days` | int | No | 1–30. Default `7`. |
| `message` | string | No | Free text included in the email. |

### Response JSON
```json
{
  "items": [
    {
      "id": "invitation-uuid-1",
      "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
      "email": "alice@example.com",
      "role": "member",
      "status": "pending",
      "invited_by": "caller-user-uuid",
      "expires_at": "2026-05-29T22:00:00Z",
      "created_at": "2026-05-22T22:00:00Z",
      "accept_url": "https://app.example.com/invite/accept?token=opaque-token-string"
    },
    {
      "id": "invitation-uuid-2",
      "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
      "email": "bob@example.com",
      "role": "admin",
      "status": "pending",
      "invited_by": "caller-user-uuid",
      "expires_at": "2026-05-29T22:00:00Z",
      "created_at": "2026-05-22T22:00:00Z",
      "accept_url": "https://app.example.com/invite/accept?token=another-opaque-token"
    }
  ],
  "skipped": [
    { "email": "carol@example.com", "reason": "already_member" }
  ]
}
```

> The full `accept_url` (with token) is returned **only at creation time** to the caller. Subsequent GETs will not echo the raw token; only `id` and metadata.

**Error Responses**
```json
{ "detail": "Unauthorized" }                          // 401
{ "detail": "Forbidden: not company admin." }         // 403
{ "detail": "Company not found." }                    // 404
{ "detail": "Validation error", "errors": { ... } }   // 422
{ "detail": "Too many invitees (max 50)." }           // 422
```

### Flow
```
Client
  │
  ├─► POST /api/v1/invitations  { company_id, invitees[], ... }
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Assert caller is owner/admin in company_id
  │   3. Per invitee:
  │       a. Validate email format
  │       b. If User already exists with email AND already CompanyAccess(active)
  │            → skip with reason="already_member"
  │       c. If existing pending Invitation(email, company)
  │            → skip with reason="already_invited"
  │            (use POST /resend instead)
  │       d. Else:
  │            - Generate opaque token (secrets.token_urlsafe(32))
  │            - Hash token (SHA-256) for storage
  │            - Insert Invitation(status="pending", token_hash, expires_at, role, preassign_json)
  │            - Enqueue email send (Celery / async)
  │   4. Return created list + skipped list (raw accept_url for created only)
  │
  └─► 200 OK  { items[], skipped[] }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` *(new)* | `nucleus` | Bulk create |
| `User` | `nucleus` | Existence check by email |
| `CompanyAccess` | `nucleus` | Existence check (already member?) |
| `Company` | `nucleus` | Resolve and authorize |

### Proposed Django ORM Query
```python
import secrets, hashlib
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

with transaction.atomic():
    # Authorization
    if not CompanyAccess.objects.filter(
        user=caller, company_id=payload.company_id,
        role__in=["owner", "admin"], is_active=True,
    ).exists():
        raise PermissionDenied

    expires_at = timezone.now() + timedelta(days=payload.expires_in_days or 7)
    existing_member_emails = set(
        User.objects
        .filter(
            email__in=[i.email for i in payload.invitees],
            company_access__company_id=payload.company_id,
            company_access__is_active=True,
        )
        .values_list("email", flat=True)
    )
    existing_pending_emails = set(
        Invitation.objects
        .filter(
            company_id=payload.company_id,
            email__in=[i.email for i in payload.invitees],
            status="pending",
        )
        .values_list("email", flat=True)
    )

    created, skipped = [], []
    for inv in payload.invitees:
        if inv.email in existing_member_emails:
            skipped.append({"email": inv.email, "reason": "already_member"})
            continue
        if inv.email in existing_pending_emails:
            skipped.append({"email": inv.email, "reason": "already_invited"})
            continue

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        invitation = Invitation.objects.create(
            company_id=payload.company_id,
            email=inv.email,
            role=inv.role or "member",
            full_name=inv.full_name,
            preassign={
                "project_ids": inv.preassign.project_ids if inv.preassign else [],
                "channel_ids": inv.preassign.channel_ids if inv.preassign else [],
                "topic_ids":   inv.preassign.topic_ids   if inv.preassign else [],
            },
            token_hash=token_hash,
            invited_by=caller,
            expires_at=expires_at,
            message=payload.message,
            status="pending",
        )
        created.append((invitation, raw_token))

    # Hand off to email task (raw token only at this point)
    for invitation, raw_token in created:
        send_invitation_email.delay(invitation.id, raw_token)
```

### Django Ninja Schemas
```python
from ninja import Schema
from uuid import UUID
from datetime import datetime


class InvitePreassign(Schema):
    project_ids: list[UUID] = []
    channel_ids: list[UUID] = []
    topic_ids:   list[UUID] = []


class InviteeIn(Schema):
    email: str
    role: str | None = "member"     # owner | admin | member | viewer
    full_name: str | None = None
    preassign: InvitePreassign | None = None


class InvitationCreateIn(Schema):
    company_id: UUID
    invitees: list[InviteeIn]
    expires_in_days: int | None = 7
    message: str | None = None


class CompanyMini(Schema):
    id: UUID
    name: str
    slug: str


class InvitationOut(Schema):
    id: UUID
    company: CompanyMini
    email: str
    role: str
    status: str                      # pending | accepted | revoked | expired
    invited_by: UUID
    expires_at: datetime
    created_at: datetime
    accept_url: str | None = None    # only on creation response


class InvitationSkipped(Schema):
    email: str
    reason: str                      # already_member | already_invited


class InvitationCreateOut(Schema):
    items: list[InvitationOut]
    skipped: list[InvitationSkipped] = []
```

---

## 2. GET /api/v1/invitations

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/invitations` |
| Auth Required | Yes — Supabase JWT |
| Description | List invitations visible to the caller. Default scope: invitations belonging to companies the caller is owner/admin of. With `?mine=true`, returns invitations addressed to the caller's email (any company). Supports filtering and pagination. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `company_id` | UUID | No | Filter to one company (caller must be admin/owner). |
| `status` | string | No | `pending`, `accepted`, `revoked`, `expired`. |
| `email` | string | No | Filter by invitee email (icontains). |
| `mine` | bool | No | If `true`, list invitations sent **to** caller's email instead. |
| `page` / `page_size` | int | No | Pagination. |

### Request JSON
```json
// No body. Example:
// GET /api/v1/invitations?company_id=...&status=pending&page=1
```

### Response JSON
```json
{
  "items": [
    {
      "id": "invitation-uuid-1",
      "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
      "email": "alice@example.com",
      "role": "member",
      "status": "pending",
      "invited_by": "caller-user-uuid",
      "expires_at": "2026-05-29T22:00:00Z",
      "created_at": "2026-05-22T22:00:00Z"
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 20
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Forbidden." }      // 403 — company_id given but caller is not admin
```

### Flow
```
Client
  │
  ├─► GET /api/v1/invitations?status=pending&...
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Resolve scope:
  │       - mine=true → filter Invitation(email=caller.email)
  │       - else → companies where caller is owner/admin
  │           if company_id given → assert membership in that scope
  │   3. Apply filters: status, email-icontains
  │   4. Order by -created_at, paginate
  │
  └─► 200 OK  { items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` | `nucleus` | List with filters |
| `Company` | `nucleus` | Embedded mini |
| `CompanyAccess` | `nucleus` | Scope resolution |

### Proposed Django ORM Query
```python
if payload.mine:
    qs = Invitation.objects.filter(email=caller.email)
else:
    admin_company_ids = CompanyAccess.objects.filter(
        user=caller, role__in=["owner", "admin"], is_active=True,
    ).values_list("company_id", flat=True)

    if company_id and company_id not in set(admin_company_ids):
        raise PermissionDenied
    target_company_ids = [company_id] if company_id else list(admin_company_ids)

    qs = Invitation.objects.filter(company_id__in=target_company_ids)

if status:
    qs = qs.filter(status=status)
if email:
    qs = qs.filter(email__icontains=email)

qs = qs.select_related("company").order_by("-created_at")
total = qs.count()
items = qs[(page - 1) * page_size : page * page_size]
```

### Django Ninja Schemas
```python
from ninja import FilterSchema, Field


class InvitationListFilters(FilterSchema):
    company_id: UUID | None = None
    status: str | None = None
    email: str | None = Field(None, q="email__icontains")
    mine: bool | None = False


class InvitationListOut(Schema):
    items: list[InvitationOut]
    total: int
    page: int
    page_size: int
```

---

## 3. GET /api/v1/invitations/{invitation_id}

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/invitations/{invitation_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Retrieve a single invitation. Visible to: company admins/owners of the target company, the recipient (matching email), or staff. Raw `token` is **never** returned. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "id": "invitation-uuid-1",
  "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
  "email": "alice@example.com",
  "full_name": "Alice Doe",
  "role": "member",
  "status": "pending",
  "invited_by": {
    "id": "caller-user-uuid",
    "email": "noaman@example.com",
    "full_name": "Noaman Faisal"
  },
  "expires_at": "2026-05-29T22:00:00Z",
  "created_at": "2026-05-22T22:00:00Z",
  "accepted_at": null,
  "revoked_at": null,
  "preassign": {
    "project_ids": ["project-uuid-1"],
    "channel_ids": ["channel-uuid-7"],
    "topic_ids": ["topic-uuid-3"]
  },
  "message": "Welcome to NeuralOps. Onboarding doc inside.",
  "resends": 0,
  "last_resent_at": null
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Not found." }      // 404 (also returned for not-visible to avoid id probing)
```

### Flow
```
Client
  │
  ├─► GET /api/v1/invitations/{invitation_id}
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch invitation with select_related('company','invited_by')
  │   3. Visibility:
  │       caller.is_staff
  │       OR caller.email == invitation.email
  │       OR caller is owner/admin of invitation.company
  │       else → 404
  │   4. Serialize (omit token / token_hash)
  │
  └─► 200 OK  { invitation detail }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` | `nucleus` | Fetch with related |
| `Company` | `nucleus` | Embedded |
| `User` | `nucleus` | Embedded for invited_by |
| `CompanyAccess` | `nucleus` | Visibility check |

### Proposed Django ORM Query
```python
invitation = (
    Invitation.objects
    .select_related("company", "invited_by", "invited_by__human_profile")
    .get(pk=invitation_id)
)

is_admin = CompanyAccess.objects.filter(
    user=caller, company_id=invitation.company_id,
    role__in=["owner", "admin"], is_active=True,
).exists()
visible = (
    caller.is_staff
    or caller.email.lower() == invitation.email.lower()
    or is_admin
)
if not visible:
    raise Http404
```

### Django Ninja Schemas
```python
class UserMini(Schema):
    id: UUID
    email: str
    full_name: str | None = None


class InvitationDetailOut(Schema):
    id: UUID
    company: CompanyMini
    email: str
    full_name: str | None = None
    role: str
    status: str
    invited_by: UserMini
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    preassign: InvitePreassign
    message: str | None = None
    resends: int
    last_resent_at: datetime | None = None
```

---

## 4. POST /api/v1/invitations/accept

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/invitations/accept` |
| Auth Required | **Yes — Supabase JWT** (proves the recipient owns the email). The `token` is the second factor: it ties the JWT-verified email to a specific invitation. |
| Description | Accept an invitation. Verifies token + JWT email match, creates the local User if needed, grants CompanyAccess, applies preassigned memberships, marks invitation `accepted`. |

### Request JSON
```json
{
  "token": "opaque-token-string-from-email"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `token` | string | Yes | Raw token from the invite email. |

### Response JSON
```json
{
  "invitation_id": "invitation-uuid-1",
  "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "alice@example.com",
    "username": "alice@example.com",
    "is_new_user": true
  },
  "role": "member",
  "preassigned": {
    "projects": 1,
    "channels": 1,
    "topics": 1
  },
  "accepted_at": "2026-05-22T23:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Invalid or expired token." }                  // 400
{ "detail": "Token email mismatch." }                      // 403 — JWT email != invitation email
{ "detail": "Invitation already accepted." }               // 409
{ "detail": "Invitation revoked." }                        // 409
{ "detail": "Invitation expired." }                        // 410
```

### Flow
```
Client (signed in via Supabase as the invited email)
  │
  ├─► POST /api/v1/invitations/accept  { token }
  │   Authorization: Bearer <supabase_jwt>
  │
  │   [Django / authn]
  │   1. Verify Supabase JWT → caller (email_from_jwt)
  │   2. Hash incoming token → token_hash
  │   3. Lookup Invitation(token_hash=token_hash)
  │       not found → 400
  │   4. Validate state:
  │       status == "pending"  else → 409 (accepted/revoked) / 410 (expired)
  │       expires_at > now()   else → mark expired, return 410
  │       email_from_jwt.lower() == invitation.email.lower()  else → 403
  │   5. Atomic transaction:
  │       a. get_or_create User by email
  │           if creating: copy full_name into Human profile
  │       b. update_or_create CompanyAccess(user, company,
  │            defaults={role, is_active=True, granted_by=invitation.invited_by})
  │       c. Apply preassign:
  │            - bulk_create ProjectMembership for project_ids
  │            - bulk_create ChannelMembership for channel_ids
  │            - bulk_create TopicSubscription for topic_ids
  │           (idempotent — ignore duplicates)
  │       d. Mark Invitation.status = "accepted",
  │          accepted_at = now(), accepted_by = user
  │       e. Audit: UserActivityLog(kind="invitation_accepted", actor=user)
  │   6. Return summary
  │
  └─► 200 OK  { invitation_id, company, user, role, preassigned, accepted_at }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` | `nucleus` | Lookup by token hash, mutate status |
| `User` | `nucleus` | `get_or_create` |
| `Human` | `nucleus` | `update_or_create` profile |
| `CompanyAccess` | `nucleus` | `update_or_create` |
| `ProjectMembership` | `nucleus` | Bulk insert (preassign) |
| `ChannelMembership` | `nucleus` | Bulk insert (preassign) |
| `TopicSubscription` | `nucleus` | Bulk insert (preassign) |
| `UserActivityLog` | `nucleus` | Audit |

### Proposed Django ORM Query
```python
import hashlib
from django.db import transaction, IntegrityError
from django.utils import timezone

token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

with transaction.atomic():
    invitation = (
        Invitation.objects
        .select_for_update()
        .select_related("company")
        .filter(token_hash=token_hash)
        .first()
    )
    if not invitation:
        raise BadRequest("Invalid or expired token.")

    if invitation.status == "accepted":
        raise Conflict("Invitation already accepted.")
    if invitation.status == "revoked":
        raise Conflict("Invitation revoked.")
    if invitation.expires_at <= timezone.now() or invitation.status == "expired":
        Invitation.objects.filter(pk=invitation.pk).update(status="expired")
        raise Gone("Invitation expired.")

    if email_from_jwt.lower() != invitation.email.lower():
        raise PermissionDenied("Token email mismatch.")

    # 1. Local user
    user, created = User.objects.get_or_create(
        email=invitation.email,
        defaults={"username": invitation.email, "is_active": True},
    )
    if created and invitation.full_name:
        Human.objects.update_or_create(
            user=user,
            defaults={"full_name": invitation.full_name},
        )

    # 2. CompanyAccess
    CompanyAccess.objects.update_or_create(
        user=user,
        company=invitation.company,
        defaults={
            "role": invitation.role,
            "is_active": True,
            "granted_by": invitation.invited_by,
        },
    )

    # 3. Preassign — best-effort, idempotent
    pre = invitation.preassign or {}
    proj_ids    = pre.get("project_ids", [])
    chan_ids    = pre.get("channel_ids", [])
    topic_ids   = pre.get("topic_ids", [])

    ProjectMembership.objects.bulk_create(
        [ProjectMembership(user=user, project_id=p, role="member") for p in proj_ids],
        ignore_conflicts=True,
    )
    ChannelMembership.objects.bulk_create(
        [ChannelMembership(user=user, channel_id=c, role="member") for c in chan_ids],
        ignore_conflicts=True,
    )
    TopicSubscription.objects.bulk_create(
        [TopicSubscription(user=user, topic_id=t) for t in topic_ids],
        ignore_conflicts=True,
    )

    # 4. Mark invitation accepted
    Invitation.objects.filter(pk=invitation.pk).update(
        status="accepted",
        accepted_at=timezone.now(),
        accepted_by=user,
    )

    # 5. Audit
    UserActivityLog.objects.create(
        user=user,
        actor=user,
        kind="invitation_accepted",
        meta={"invitation_id": str(invitation.id), "company_id": str(invitation.company_id)},
    )
```

### Django Ninja Schemas
```python
class InvitationAcceptIn(Schema):
    token: str


class AcceptedUserOut(Schema):
    id: UUID
    email: str
    username: str
    is_new_user: bool


class PreassignedCount(Schema):
    projects: int
    channels: int
    topics: int


class InvitationAcceptOut(Schema):
    invitation_id: UUID
    company: CompanyMini
    user: AcceptedUserOut
    role: str
    preassigned: PreassignedCount
    accepted_at: datetime
```

---

## 5. DELETE /api/v1/invitations/{invitation_id}

### API Details
| Field | Value |
|---|---|
| Method | DELETE |
| Endpoint | `/api/v1/invitations/{invitation_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Revoke a pending invitation. Soft revoke: sets `status="revoked"`, blanks the `token_hash`, records the actor and time. Idempotent on already-revoked. Cannot revoke an `accepted` invitation. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "invitation_id": "invitation-uuid-1",
  "status": "revoked",
  "revoked_at": "2026-05-22T23:30:00Z",
  "revoked_by": "caller-user-uuid"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                      // 401
{ "detail": "Forbidden: not company admin." }     // 403
{ "detail": "Not found." }                        // 404
{ "detail": "Cannot revoke an accepted invitation." } // 409
```

### Flow
```
Client
  │
  ├─► DELETE /api/v1/invitations/{invitation_id}
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch invitation
  │   3. Authorization:
  │       caller.is_staff
  │       OR caller is owner/admin of invitation.company
  │       else → 403
  │   4. State guard:
  │       accepted → 409
  │       revoked  → idempotent return existing
  │   5. Atomic:
  │       - status = "revoked"
  │       - token_hash = null  (invalidate the link)
  │       - revoked_at = now(), revoked_by = caller
  │   6. Return
  │
  └─► 200 OK  { invitation_id, status, revoked_at, revoked_by }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` | `nucleus` | Update status, clear token_hash |
| `CompanyAccess` | `nucleus` | Auth check |

### Proposed Django ORM Query
```python
with transaction.atomic():
    invitation = Invitation.objects.select_for_update().get(pk=invitation_id)

    # Authorization
    is_admin = CompanyAccess.objects.filter(
        user=caller, company_id=invitation.company_id,
        role__in=["owner", "admin"], is_active=True,
    ).exists()
    if not (caller.is_staff or is_admin):
        raise PermissionDenied

    if invitation.status == "accepted":
        raise Conflict("Cannot revoke an accepted invitation.")

    if invitation.status != "revoked":
        Invitation.objects.filter(pk=invitation.pk).update(
            status="revoked",
            token_hash=None,
            revoked_at=timezone.now(),
            revoked_by=caller,
        )
```

### Django Ninja Schemas
```python
class InvitationRevokeOut(Schema):
    invitation_id: UUID
    status: str
    revoked_at: datetime
    revoked_by: UUID
```

---

## 6. POST /api/v1/invitations/{invitation_id}/resend

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/invitations/{invitation_id}/resend` |
| Auth Required | Yes — Supabase JWT |
| Description | Re-send the invitation email. Rotates the token (issues a new opaque token, invalidating the previous one) and optionally extends `expires_at`. Rate-limited per invitation (e.g., max 5 resends, min 60s between calls). |

### Request JSON
```json
{
  "extend_expiry": true,
  "expires_in_days": 7
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `extend_expiry` | bool | No | If `true`, push `expires_at` forward. Default `true`. |
| `expires_in_days` | int | No | New TTL window. Default `7` (only used if `extend_expiry=true`). |

### Response JSON
```json
{
  "invitation_id": "invitation-uuid-1",
  "status": "pending",
  "resends": 1,
  "last_resent_at": "2026-05-22T23:45:00Z",
  "expires_at": "2026-05-29T23:45:00Z",
  "accept_url": "https://app.example.com/invite/accept?token=new-opaque-token"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                              // 401
{ "detail": "Forbidden: not company admin." }             // 403
{ "detail": "Not found." }                                // 404
{ "detail": "Cannot resend a non-pending invitation." }   // 409
{ "detail": "Resend rate limit exceeded." }               // 429
```

### Flow
```
Client
  │
  ├─► POST /api/v1/invitations/{invitation_id}/resend  { extend_expiry?, expires_in_days? }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch invitation
  │   3. Authorization (admin/owner of company or staff)
  │   4. State guard: status == "pending" else → 409
  │   5. Rate limit:
  │       resends >= 5 → 429
  │       (now() - last_resent_at) < 60s → 429
  │   6. Atomic:
  │       - Generate new raw token + token_hash
  │       - Update Invitation:
  │            token_hash = new hash
  │            resends = resends + 1
  │            last_resent_at = now()
  │            (optional) expires_at = now() + expires_in_days
  │   7. Enqueue email
  │   8. Return new accept_url + meta
  │
  └─► 200 OK  { invitation_id, status, resends, last_resent_at, expires_at, accept_url }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Invitation` | `nucleus` | Rotate token, increment resends |
| `CompanyAccess` | `nucleus` | Auth check |

### Proposed Django ORM Query
```python
import secrets, hashlib
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

MAX_RESENDS = 5
MIN_INTERVAL = timedelta(seconds=60)

with transaction.atomic():
    invitation = Invitation.objects.select_for_update().get(pk=invitation_id)

    # Authz
    is_admin = CompanyAccess.objects.filter(
        user=caller, company_id=invitation.company_id,
        role__in=["owner", "admin"], is_active=True,
    ).exists()
    if not (caller.is_staff or is_admin):
        raise PermissionDenied

    # State guard
    if invitation.status != "pending":
        raise Conflict("Cannot resend a non-pending invitation.")

    # Rate limit
    now = timezone.now()
    if invitation.resends >= MAX_RESENDS:
        raise TooManyRequests("Resend rate limit exceeded.")
    if invitation.last_resent_at and (now - invitation.last_resent_at) < MIN_INTERVAL:
        raise TooManyRequests("Resend rate limit exceeded.")

    # Rotate token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    update_kwargs = {
        "token_hash": token_hash,
        "resends": F("resends") + 1,
        "last_resent_at": now,
    }
    if payload.extend_expiry:
        update_kwargs["expires_at"] = now + timedelta(days=payload.expires_in_days or 7)

    Invitation.objects.filter(pk=invitation.pk).update(**update_kwargs)

# Enqueue email outside the transaction
send_invitation_email.delay(invitation.id, raw_token)
```

### Django Ninja Schemas
```python
class InvitationResendIn(Schema):
    extend_expiry: bool | None = True
    expires_in_days: int | None = 7


class InvitationResendOut(Schema):
    invitation_id: UUID
    status: str
    resends: int
    last_resent_at: datetime
    expires_at: datetime
    accept_url: str
```

---

## Proposed Missing / Reused Models

> Captured here for the modeling pass.

### `Invitation` *(new)*

```python
class Invitation(BaseModel):
    company         = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="invitations")
    email           = models.EmailField(db_index=True)
    full_name       = models.CharField(max_length=255, blank=True, default="")
    role            = models.CharField(max_length=32, default="member")  # owner | admin | member | viewer
    status          = models.CharField(max_length=16, default="pending", db_index=True)  # pending | accepted | revoked | expired

    token_hash      = models.CharField(max_length=64, null=True, blank=True, unique=True)  # SHA-256 hex of raw token; null after revoke
    preassign       = models.JSONField(default=dict, blank=True)
    message         = models.TextField(blank=True, default="")

    invited_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="invitations_sent")
    accepted_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="invitations_accepted")
    revoked_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="invitations_revoked")

    created_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at      = models.DateTimeField(db_index=True)
    accepted_at     = models.DateTimeField(null=True, blank=True)
    revoked_at      = models.DateTimeField(null=True, blank=True)

    resends         = models.PositiveIntegerField(default=0)
    last_resent_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_invitation"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"],
                condition=Q(status="pending"),
                name="uniq_pending_invite_per_company_email",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["email", "status"]),
        ]
```

### Why hash the token?

- The raw token is sent in the invite email. Treating it like a password: store only the SHA-256 hash; verify on accept by hashing the incoming token.
- Mitigates DB-leak risk: an attacker reading the table cannot replay invites.
- On revoke we additionally null the hash so even constant-time matches no longer succeed.

### Reused (assumed existing)

- `User`, `Human`, `Company`, `CompanyAccess`
- `ProjectMembership`, `ChannelMembership`, `TopicSubscription`
- `UserActivityLog` *(proposed in `02-users.md`)*

### Out-of-band

- `send_invitation_email` — Celery task (or equivalent). Renders the email with `{accept_url}` containing the **raw** token. Raw token never written to logs; never re-derivable from the DB.
