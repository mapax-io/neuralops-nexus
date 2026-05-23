# User / Human APIs

> **Scope:** Manage local Django users (synced from Supabase) and their human profiles, access, and resource memberships.
> **Auth:** All endpoints require a valid Supabase JWT. Most are scoped to the **current company** of the caller; cross-company reads/writes require staff/owner role.
> **Conventions:**
> - `user_id` is the Django `User.id` (UUID).
> - List endpoints support pagination via `?page=&page_size=` (default `page=1`, `page_size=20`, max `100`).
> - Mutations are scoped: a regular user may only PATCH/DELETE themselves; company admins may act on members of their company; staff may act globally.

---

## 1. GET /api/v1/users

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users` |
| Auth Required | Yes — Supabase JWT |
| Description | List users visible to the caller. Default scope = current company members. Supports search, filtering, and pagination. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | No | Search by email / username / full_name (icontains) |
| `user_type` | string | No | Filter by type: `human`, `agent` |
| `is_active` | bool | No | Filter active/inactive |
| `company_id` | UUID | No | Override scope (requires staff or membership in that company) |
| `page` | int | No | Default `1` |
| `page_size` | int | No | Default `20`, max `100` |

### Request JSON
```json
// No body. Example query:
// GET /api/v1/users?q=noaman&user_type=human&is_active=true&page=1&page_size=20
// Authorization: Bearer <token>
```

### Response JSON
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "noaman@example.com",
      "username": "noaman@example.com",
      "user_type": "human",
      "is_active": true,
      "human_profile": {
        "full_name": "Noaman Faisal",
        "avatar": "https://cdn.example.com/avatars/noaman.jpg"
      },
      "created_at": "2026-05-22T02:00:00Z"
    }
  ],
  "total": 137,
  "page": 1,
  "page_size": 20
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                  // 401
{ "detail": "company_id not accessible." }    // 403
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users?q=...&page=1
  │   Authorization: Bearer <token>
  │
  │   [Django / authn middleware]
  │   1. Verify JWT, resolve caller User
  │   2. Resolve scope:
  │       - If company_id given → assert caller has CompanyAccess
  │       - Else → use caller.current_company
  │   3. Build queryset:
  │       User.objects
  │         .filter(company_access__company=scope_company)
  │         .filter(<q>, <user_type>, <is_active>)
  │         .select_related('human_profile')
  │         .distinct()
  │   4. Paginate, serialize
  │
  └─► 200 OK  { items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Filter by company access, search, pagination |
| `Human` | `nucleus` | `select_related('human_profile')` for profile fields |
| `CompanyAccess` | `nucleus` | Used to scope users to caller's company |

### Proposed Django ORM Query
```python
qs = (
    User.objects
    .filter(company_access__company=scope_company, company_access__is_active=True)
    .select_related("human_profile")
    .distinct()
)

if q:
    qs = qs.filter(
        Q(email__icontains=q)
        | Q(username__icontains=q)
        | Q(human_profile__full_name__icontains=q)
    )
if user_type:
    qs = qs.filter(user_type=user_type)
if is_active is not None:
    qs = qs.filter(is_active=is_active)

total = qs.count()
items = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
```

### Django Ninja Schemas
```python
from ninja import Schema, FilterSchema, Field
from uuid import UUID
from datetime import datetime


class HumanProfileOut(Schema):
    full_name: str | None = None
    avatar: str | None = None


class UserListItemOut(Schema):
    id: UUID
    email: str
    username: str
    user_type: str
    is_active: bool
    human_profile: HumanProfileOut | None = None
    created_at: datetime


class UserListOut(Schema):
    items: list[UserListItemOut]
    total: int
    page: int
    page_size: int


class UserListFilters(FilterSchema):
    q: str | None = Field(None, q=["email__icontains", "username__icontains", "human_profile__full_name__icontains"])
    user_type: str | None = None
    is_active: bool | None = None
    company_id: UUID | None = None
```

---

## 2. GET /api/v1/users/{user_id}

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users/{user_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Retrieve a single user with profile, current company, and basic counts. Caller must share at least one company with the target, or be staff. |

### Request JSON
```json
// No body.
// Authorization: Bearer <token>
```

### Response JSON
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
  },
  "stats": {
    "projects": 12,
    "channels": 34,
    "topics": 7
  },
  "created_at": "2026-05-22T02:00:00Z",
  "updated_at": "2026-05-22T02:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }      // 401
{ "detail": "Not found." }        // 404 — user does not exist or not visible to caller
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users/{user_id}
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch target user with select_related
  │   3. Visibility check:
  │       caller.is_staff
  │       OR exists CompanyAccess(user=caller, company__in=target.companies)
  │   4. Compute stats counts (annotate or separate queries)
  │   5. Serialize and return
  │
  └─► 200 OK  { user detail }
       or
      404     { detail: "Not found." }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Fetch with related |
| `Human` | `nucleus` | OneToOne profile |
| `Company` | `nucleus` | Read current_company |
| `CompanyAccess` | `nucleus` | Visibility check |
| `ProjectMembership` / `ChannelMembership` / `TopicSubscription` | `nucleus` | Counts |

### Proposed Django ORM Query
```python
user = (
    User.objects
    .select_related("current_company", "human_profile")
    .annotate(
        projects_count=Count("project_memberships", distinct=True),
        channels_count=Count("channel_memberships", distinct=True),
        topics_count=Count("topic_subscriptions", distinct=True),
    )
    .get(pk=user_id)
)

# Visibility
shared = CompanyAccess.objects.filter(
    user=caller,
    company__in=user.companies.all(),
    is_active=True,
).exists()
if not (caller.is_staff or shared):
    raise Http404
```

### Django Ninja Schemas
```python
class CompanyMini(Schema):
    id: UUID
    name: str
    slug: str


class HumanProfileOut(Schema):
    full_name: str | None = None
    avatar: str | None = None
    timezone: str | None = None
    locale: str | None = None


class UserStats(Schema):
    projects: int
    channels: int
    topics: int


class UserDetailOut(Schema):
    id: UUID
    email: str
    username: str
    user_type: str
    is_active: bool
    current_company: CompanyMini | None = None
    human_profile: HumanProfileOut | None = None
    stats: UserStats
    created_at: datetime
    updated_at: datetime
```

---

## 3. PATCH /api/v1/users/{user_id}

### API Details
| Field | Value |
|---|---|
| Method | PATCH |
| Endpoint | `/api/v1/users/{user_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Partial update of user + nested human profile fields. Self-edit always allowed for own profile fields; admin/staff required for `is_active`, `user_type`, `email`. |

### Request JSON
```json
{
  "username": "noaman.f",
  "human_profile": {
    "full_name": "Noaman Faisal",
    "avatar": "https://cdn.example.com/avatars/noaman-2.jpg",
    "timezone": "Asia/Karachi",
    "locale": "en"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | string | No | New username (must be unique) |
| `email` | string | No | Admin-only |
| `is_active` | bool | No | Admin-only |
| `user_type` | string | No | Admin-only |
| `human_profile.full_name` | string | No | |
| `human_profile.avatar` | string (URL) | No | |
| `human_profile.timezone` | string | No | IANA tz name |
| `human_profile.locale` | string | No | BCP-47 |

### Response JSON
```json
// Same shape as GET /api/v1/users/{user_id}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                       // 401
{ "detail": "Forbidden: cannot edit other users." } // 403
{ "detail": "Username already taken." }            // 409
{ "detail": "Validation error", "errors": { ... } } // 422
```

### Flow
```
Client
  │
  ├─► PATCH /api/v1/users/{user_id}  { partial fields }
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Permission gate:
  │       - target == caller            → allow non-privileged fields
  │       - caller.is_staff             → allow all
  │       - caller is company admin AND target shares company
  │                                     → allow privileged within scope
  │       - else                        → 403
  │   3. Validate payload (Pydantic schema, partial)
  │   4. Atomic transaction:
  │       - Update User fields
  │       - update_or_create Human profile
  │   5. Return refreshed detail
  │
  └─► 200 OK  { user detail }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Field updates |
| `Human` | `nucleus` | `update_or_create` profile |
| `CompanyAccess` | `nucleus` | Permission check (admin role) |

### Proposed Django ORM Query
```python
with transaction.atomic():
    user = User.objects.select_for_update().get(pk=user_id)

    # Privilege gate
    can_edit_privileged = caller.is_staff or _is_company_admin(caller, user)
    if user.pk != caller.pk and not can_edit_privileged:
        raise PermissionDenied

    # Apply updates
    for field in ("username",):
        if field in payload:
            setattr(user, field, payload[field])
    if can_edit_privileged:
        for field in ("email", "is_active", "user_type"):
            if field in payload:
                setattr(user, field, payload[field])
    user.save()

    if "human_profile" in payload:
        Human.objects.update_or_create(
            user=user,
            defaults=payload["human_profile"],
        )
```

### Django Ninja Schemas
```python
class HumanProfileIn(Schema):
    full_name: str | None = None
    avatar: str | None = None
    timezone: str | None = None
    locale: str | None = None


class UserPatchIn(Schema):
    username: str | None = None
    email: str | None = None        # admin only
    is_active: bool | None = None   # admin only
    user_type: str | None = None    # admin only
    human_profile: HumanProfileIn | None = None
```

---

## 4. DELETE /api/v1/users/{user_id}

### API Details
| Field | Value |
|---|---|
| Method | DELETE |
| Endpoint | `/api/v1/users/{user_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | **Soft delete**: deactivates the user, ends sessions, and revokes all CompanyAccess. Hard delete via `?hard=true` is staff-only and cascades. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `hard` | bool | No | Staff-only. If `true`, performs hard delete. Default `false`. |

### Request JSON
```json
// No body.
// DELETE /api/v1/users/{user_id}            -> soft delete
// DELETE /api/v1/users/{user_id}?hard=true  -> hard delete (staff)
```

### Response JSON
```json
{
  "detail": "User deactivated.",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "mode": "soft"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                  // 401
{ "detail": "Forbidden." }                    // 403
{ "detail": "Not found." }                    // 404
{ "detail": "Cannot delete the last owner." } // 409
```

### Flow
```
Client
  │
  ├─► DELETE /api/v1/users/{user_id}[?hard=true]
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Permission gate (self / company-admin / staff)
  │   3. Last-owner guard:
  │       - For each company where target is the only owner → block
  │   4. Atomic transaction:
  │       - if hard & staff:  user.delete()
  │       - else: is_active = False;
  │               CompanyAccess.is_active = False;
  │               UserSession.is_active = False
  │   5. Return result
  │
  └─► 200 OK  { detail, user_id, mode }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Update `is_active=False` or hard `delete()` |
| `CompanyAccess` | `nucleus` | Bulk deactivate |
| `UserSession` *(proposed)* | `nucleus` | End all active sessions |
| `Company` | `nucleus` | Owner-count check |

### Proposed Django ORM Query
```python
with transaction.atomic():
    user = User.objects.select_for_update().get(pk=user_id)

    # Owner guard
    sole_owner_companies = (
        Company.objects
        .filter(access__user=user, access__role="owner", access__is_active=True)
        .annotate(owner_count=Count("access", filter=Q(access__role="owner", access__is_active=True)))
        .filter(owner_count=1)
    )
    if sole_owner_companies.exists():
        raise Conflict("Cannot delete the last owner.")

    if hard and caller.is_staff:
        user.delete()
        mode = "hard"
    else:
        User.objects.filter(pk=user.pk).update(is_active=False)
        CompanyAccess.objects.filter(user=user).update(is_active=False)
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False, ended_at=now()
        )
        mode = "soft"
```

### Django Ninja Schemas
```python
class UserDeleteOut(Schema):
    detail: str
    user_id: UUID
    mode: str  # "soft" | "hard"
```

---

## 5. GET /api/v1/users/{user_id}/access

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users/{user_id}/access` |
| Auth Required | Yes — Supabase JWT |
| Description | Lists all CompanyAccess records for the user — which companies they belong to, with what role, and active flag. |

### Request JSON
```json
// No body.
// Authorization: Bearer <token>
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "items": [
    {
      "company": {
        "id": "company-uuid-1",
        "name": "NeuralOps",
        "slug": "neuralops"
      },
      "role": "owner",
      "is_active": true,
      "granted_at": "2026-01-10T08:00:00Z",
      "granted_by": "550e8400-e29b-41d4-a716-446655440000"
    },
    {
      "company": {
        "id": "company-uuid-2",
        "name": "Acme",
        "slug": "acme"
      },
      "role": "member",
      "is_active": true,
      "granted_at": "2026-03-15T10:00:00Z",
      "granted_by": "another-user-uuid"
    }
  ]
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Forbidden." }      // 403
{ "detail": "Not found." }      // 404
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users/{user_id}/access
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility:
  │       caller == target → allow
  │       OR caller is admin in any company target belongs to → allow
  │       OR caller.is_staff → allow
  │       else → 403
  │   3. Fetch CompanyAccess.filter(user=target).select_related('company')
  │
  └─► 200 OK  { user_id, items[] }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `CompanyAccess` | `nucleus` | List all for user |
| `Company` | `nucleus` | Embedded |

### Proposed Django ORM Query
```python
items = (
    CompanyAccess.objects
    .filter(user_id=user_id)
    .select_related("company", "granted_by")
    .order_by("-granted_at")
)
```

### Django Ninja Schemas
```python
class CompanyAccessOut(Schema):
    company: CompanyMini
    role: str
    is_active: bool
    granted_at: datetime
    granted_by: UUID | None = None


class UserAccessListOut(Schema):
    user_id: UUID
    items: list[CompanyAccessOut]
```

---

## 6. PATCH /api/v1/users/{user_id}/access

### API Details
| Field | Value |
|---|---|
| Method | PATCH |
| Endpoint | `/api/v1/users/{user_id}/access` |
| Auth Required | Yes — Supabase JWT |
| Description | Grant, revoke, or change role on a CompanyAccess for the target user. Caller must be admin/owner of the company in question. Operates on a single company per call. |

### Request JSON
```json
{
  "company_id": "company-uuid-1",
  "role": "admin",
  "is_active": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company_id` | UUID | Yes | Company on which to mutate access |
| `role` | string | No | One of `owner`, `admin`, `member`, `viewer` |
| `is_active` | bool | No | `false` to revoke; `true` to grant/restore |

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "company": { "id": "company-uuid-1", "name": "NeuralOps", "slug": "neuralops" },
  "role": "admin",
  "is_active": true,
  "granted_at": "2026-01-10T08:00:00Z",
  "granted_by": "caller-user-uuid"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                   // 401
{ "detail": "Forbidden: not company admin." }  // 403
{ "detail": "Cannot demote the last owner." }  // 409
{ "detail": "Validation error", "errors": ... } // 422
```

### Flow
```
Client
  │
  ├─► PATCH /api/v1/users/{user_id}/access  { company_id, role?, is_active? }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Assert caller is owner/admin in {company_id}
  │   3. Last-owner guard if demoting/deactivating an owner
  │   4. update_or_create CompanyAccess(user=target, company=company_id)
  │       - role = payload.role  (if given)
  │       - is_active = payload.is_active (if given)
  │       - granted_by = caller (on first create)
  │   5. Return updated record
  │
  └─► 200 OK  { access record }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `CompanyAccess` | `nucleus` | `update_or_create` |
| `User` | `nucleus` | Resolve target |
| `Company` | `nucleus` | Resolve target company |

### Proposed Django ORM Query
```python
with transaction.atomic():
    # Caller must be owner/admin in this company
    if not CompanyAccess.objects.filter(
        user=caller,
        company_id=payload.company_id,
        role__in=["owner", "admin"],
        is_active=True,
    ).exists():
        raise PermissionDenied

    # Last-owner guard
    if (payload.role and payload.role != "owner") or payload.is_active is False:
        owner_count = CompanyAccess.objects.filter(
            company_id=payload.company_id,
            role="owner",
            is_active=True,
        ).exclude(user_id=user_id).count()
        existing = CompanyAccess.objects.filter(
            user_id=user_id, company_id=payload.company_id, role="owner", is_active=True,
        ).exists()
        if existing and owner_count == 0:
            raise Conflict("Cannot demote the last owner.")

    defaults = {"granted_by": caller}
    if payload.role is not None:
        defaults["role"] = payload.role
    if payload.is_active is not None:
        defaults["is_active"] = payload.is_active

    access, _ = CompanyAccess.objects.update_or_create(
        user_id=user_id,
        company_id=payload.company_id,
        defaults=defaults,
    )
```

### Django Ninja Schemas
```python
class UserAccessPatchIn(Schema):
    company_id: UUID
    role: str | None = None        # owner | admin | member | viewer
    is_active: bool | None = None
```

---

## 7. GET /api/v1/users/{user_id}/projects

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users/{user_id}/projects` |
| Auth Required | Yes — Supabase JWT |
| Description | Lists projects the user has membership in. Scoped to companies the caller can see. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `company_id` | UUID | No | Filter to a single company |
| `is_active` | bool | No | Filter active projects |
| `page` / `page_size` | int | No | Pagination |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "items": [
    {
      "id": "project-uuid-1",
      "name": "Atlas",
      "slug": "atlas",
      "company": { "id": "company-uuid", "name": "NeuralOps", "slug": "neuralops" },
      "role": "lead",
      "is_active": true,
      "joined_at": "2026-02-01T09:00:00Z"
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
{ "detail": "Not found." }      // 404
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users/{user_id}/projects
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility check on target user
  │   3. Resolve allowed company scope (intersection of caller's companies & target's)
  │   4. Query ProjectMembership:
  │       .filter(user=target, project__company__in=allowed)
  │       .select_related('project', 'project__company')
  │   5. Paginate
  │
  └─► 200 OK  { user_id, items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Project` | `nucleus` | Embedded |
| `ProjectMembership` | `nucleus` | Source of role + joined_at |
| `Company` | `nucleus` | Embedded mini |
| `CompanyAccess` | `nucleus` | Visibility scope |

### Proposed Django ORM Query
```python
allowed_companies = CompanyAccess.objects.filter(
    user=caller, is_active=True,
).values_list("company_id", flat=True)

qs = (
    ProjectMembership.objects
    .filter(user_id=user_id, project__company_id__in=allowed_companies)
    .select_related("project", "project__company")
)
if company_id:
    qs = qs.filter(project__company_id=company_id)
if is_active is not None:
    qs = qs.filter(project__is_active=is_active)
```

### Django Ninja Schemas
```python
class ProjectMembershipOut(Schema):
    id: UUID
    name: str
    slug: str
    company: CompanyMini
    role: str
    is_active: bool
    joined_at: datetime


class UserProjectsOut(Schema):
    user_id: UUID
    items: list[ProjectMembershipOut]
    total: int
    page: int
    page_size: int
```

---

## 8. GET /api/v1/users/{user_id}/channels

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users/{user_id}/channels` |
| Auth Required | Yes — Supabase JWT |
| Description | Lists realtime channels the user is a member of. Channels are owned by a project; visibility scoped through caller's company membership. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `project_id` | UUID | No | Filter to one project |
| `company_id` | UUID | No | Filter to one company |
| `kind` | string | No | `direct`, `group`, `broadcast`, `system` |
| `page` / `page_size` | int | No | Pagination |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "items": [
    {
      "id": "channel-uuid-1",
      "name": "atlas-engineering",
      "kind": "group",
      "project": { "id": "project-uuid", "name": "Atlas", "slug": "atlas" },
      "company": { "id": "company-uuid", "name": "NeuralOps", "slug": "neuralops" },
      "role": "member",
      "joined_at": "2026-02-05T10:00:00Z",
      "last_read_at": "2026-05-21T18:42:00Z"
    }
  ],
  "total": 34,
  "page": 1,
  "page_size": 20
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Not found." }      // 404
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users/{user_id}/channels
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility check on target
  │   3. Resolve allowed company scope (caller ∩ target)
  │   4. Query ChannelMembership:
  │       .filter(user=target, channel__project__company_id__in=allowed)
  │       .select_related('channel', 'channel__project', 'channel__project__company')
  │   5. Apply optional filters, paginate
  │
  └─► 200 OK  { user_id, items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Channel` | `nucleus` | Embedded |
| `ChannelMembership` | `nucleus` | Source of role / joined_at / last_read_at |
| `Project` | `nucleus` | Embedded mini |
| `Company` | `nucleus` | Embedded mini |
| `CompanyAccess` | `nucleus` | Visibility scope |

### Proposed Django ORM Query
```python
allowed_companies = CompanyAccess.objects.filter(
    user=caller, is_active=True,
).values_list("company_id", flat=True)

qs = (
    ChannelMembership.objects
    .filter(
        user_id=user_id,
        channel__project__company_id__in=allowed_companies,
    )
    .select_related("channel", "channel__project", "channel__project__company")
)
if project_id:
    qs = qs.filter(channel__project_id=project_id)
if company_id:
    qs = qs.filter(channel__project__company_id=company_id)
if kind:
    qs = qs.filter(channel__kind=kind)
```

### Django Ninja Schemas
```python
class ProjectMini(Schema):
    id: UUID
    name: str
    slug: str


class ChannelMembershipOut(Schema):
    id: UUID
    name: str
    kind: str
    project: ProjectMini
    company: CompanyMini
    role: str
    joined_at: datetime
    last_read_at: datetime | None = None


class UserChannelsOut(Schema):
    user_id: UUID
    items: list[ChannelMembershipOut]
    total: int
    page: int
    page_size: int
```

---

## 9. GET /api/v1/users/{user_id}/topics

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/users/{user_id}/topics` |
| Auth Required | Yes — Supabase JWT |
| Description | Lists topics the user is subscribed to (pub/sub style). Topics live under projects; visibility scoped via company membership. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `project_id` | UUID | No | Filter to one project |
| `company_id` | UUID | No | Filter to one company |
| `page` / `page_size` | int | No | Pagination |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "items": [
    {
      "id": "topic-uuid-1",
      "name": "deployments.atlas",
      "project": { "id": "project-uuid", "name": "Atlas", "slug": "atlas" },
      "company": { "id": "company-uuid", "name": "NeuralOps", "slug": "neuralops" },
      "subscribed_at": "2026-02-10T11:00:00Z",
      "muted": false
    }
  ],
  "total": 7,
  "page": 1,
  "page_size": 20
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Not found." }      // 404
```

### Flow
```
Client
  │
  ├─► GET /api/v1/users/{user_id}/topics
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility check on target
  │   3. Resolve allowed company scope
  │   4. Query TopicSubscription:
  │       .filter(user=target, topic__project__company_id__in=allowed)
  │       .select_related('topic', 'topic__project', 'topic__project__company')
  │   5. Paginate
  │
  └─► 200 OK  { user_id, items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Topic` | `nucleus` | Embedded |
| `TopicSubscription` | `nucleus` | Source of subscribed_at, muted |
| `Project` | `nucleus` | Embedded mini |
| `Company` | `nucleus` | Embedded mini |

### Proposed Django ORM Query
```python
allowed_companies = CompanyAccess.objects.filter(
    user=caller, is_active=True,
).values_list("company_id", flat=True)

qs = (
    TopicSubscription.objects
    .filter(
        user_id=user_id,
        topic__project__company_id__in=allowed_companies,
    )
    .select_related("topic", "topic__project", "topic__project__company")
)
if project_id:
    qs = qs.filter(topic__project_id=project_id)
if company_id:
    qs = qs.filter(topic__project__company_id=company_id)
```

### Django Ninja Schemas
```python
class TopicSubscriptionOut(Schema):
    id: UUID
    name: str
    project: ProjectMini
    company: CompanyMini
    subscribed_at: datetime
    muted: bool


class UserTopicsOut(Schema):
    user_id: UUID
    items: list[TopicSubscriptionOut]
    total: int
    page: int
    page_size: int
```

---

## 10. POST /api/v1/users/{user_id}/activate

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/users/{user_id}/activate` |
| Auth Required | Yes — Supabase JWT |
| Description | Reactivate a previously deactivated user. Sets `is_active=True`. Does **not** automatically restore CompanyAccess records (those must be re-granted explicitly via `/access`). Caller must be company admin or staff. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": true,
  "activated_at": "2026-05-22T22:00:00Z",
  "activated_by": "caller-user-uuid"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }            // 401
{ "detail": "Forbidden." }              // 403
{ "detail": "Not found." }              // 404
{ "detail": "User is already active." } // 409
```

### Flow
```
Client
  │
  ├─► POST /api/v1/users/{user_id}/activate
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Permission gate (company admin / staff)
  │   3. Atomic:
  │       - Fetch user; if already active → 409
  │       - Set is_active = True
  │       - Write UserActivityLog (kind="activate", actor=caller)
  │   4. Return
  │
  └─► 200 OK  { user_id, is_active, activated_at, activated_by }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Set `is_active=True` |
| `UserActivityLog` *(proposed)* | `nucleus` | Audit entry |

### Proposed Django ORM Query
```python
with transaction.atomic():
    user = User.objects.select_for_update().get(pk=user_id)
    if user.is_active:
        raise Conflict("User is already active.")
    User.objects.filter(pk=user.pk).update(is_active=True)
    UserActivityLog.objects.create(
        user=user,
        actor=caller,
        kind="activate",
    )
```

### Django Ninja Schemas
```python
class UserActivationOut(Schema):
    user_id: UUID
    is_active: bool
    activated_at: datetime
    activated_by: UUID
```

---

## 11. POST /api/v1/users/{user_id}/deactivate

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/users/{user_id}/deactivate` |
| Auth Required | Yes — Supabase JWT |
| Description | Mark a user inactive without deleting them. Ends all active sessions. CompanyAccess records remain (so reactivation restores prior memberships). Caller must be company admin or staff. Self-deactivation allowed. |

### Request JSON
```json
{
  "reason": "left the organization"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | No | Free-text reason, stored on audit log |

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": false,
  "deactivated_at": "2026-05-22T22:10:00Z",
  "deactivated_by": "caller-user-uuid",
  "sessions_ended": 3
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                   // 401
{ "detail": "Forbidden." }                     // 403
{ "detail": "Not found." }                     // 404
{ "detail": "User is already inactive." }      // 409
{ "detail": "Cannot deactivate the last owner." } // 409
```

### Flow
```
Client
  │
  ├─► POST /api/v1/users/{user_id}/deactivate  { reason? }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Permission gate (self / company admin / staff)
  │   3. Last-owner guard across all owned companies
  │   4. Atomic:
  │       - Set User.is_active = False
  │       - End all active UserSession (is_active=False, ended_at=now)
  │       - Write UserActivityLog (kind="deactivate", reason)
  │   5. Return summary
  │
  └─► 200 OK  { user_id, is_active, deactivated_at, deactivated_by, sessions_ended }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Set `is_active=False` |
| `UserSession` *(proposed)* | `nucleus` | End all active |
| `UserActivityLog` *(proposed)* | `nucleus` | Audit entry |
| `Company` / `CompanyAccess` | `nucleus` | Last-owner check |

### Proposed Django ORM Query
```python
with transaction.atomic():
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.is_active:
        raise Conflict("User is already inactive.")

    # Last-owner guard
    sole_owner = (
        Company.objects
        .filter(access__user=user, access__role="owner", access__is_active=True)
        .annotate(owner_count=Count("access", filter=Q(access__role="owner", access__is_active=True)))
        .filter(owner_count=1)
    )
    if sole_owner.exists():
        raise Conflict("Cannot deactivate the last owner.")

    User.objects.filter(pk=user.pk).update(is_active=False)
    sessions_ended = UserSession.objects.filter(
        user=user, is_active=True
    ).update(is_active=False, ended_at=now())

    UserActivityLog.objects.create(
        user=user,
        actor=caller,
        kind="deactivate",
        meta={"reason": payload.reason},
    )
```

### Django Ninja Schemas
```python
class UserDeactivateIn(Schema):
    reason: str | None = None


class UserDeactivationOut(Schema):
    user_id: UUID
    is_active: bool
    deactivated_at: datetime
    deactivated_by: UUID
    sessions_ended: int
```

---

## Proposed Missing / Reused Models

> Several endpoints above reference models that may not yet exist. Capturing them here for the modeling pass.

### `UserActivityLog` *(new)*

```python
class UserActivityLog(BaseModel):
    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_logs")
    actor     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="acted_logs")
    kind      = models.CharField(max_length=64, db_index=True)   # activate | deactivate | role_change | ...
    meta      = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "accounts_user_activity_log"
        indexes = [models.Index(fields=["user", "-created_at"])]
```

### `CompanyAccess` *(assumed existing)*

Expected fields used by these APIs:

```python
class CompanyAccess(BaseModel):
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_access")
    company    = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="access")
    role       = models.CharField(max_length=32)   # owner | admin | member | viewer
    is_active  = models.BooleanField(default=True, db_index=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="granted_access")

    class Meta:
        db_table = "accounts_company_access"
        unique_together = [("user", "company")]
```

### Membership / subscription models (assumed)

- `ProjectMembership(user, project, role, is_active, joined_at)`
- `ChannelMembership(user, channel, role, joined_at, last_read_at)`
- `TopicSubscription(user, topic, subscribed_at, muted)`

> Confirm names + fields when we get to the modeling pass.
