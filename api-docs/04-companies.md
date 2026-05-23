# Company APIs

> **Concept:** A `Company` is the primary tenant boundary in Nexus. Users belong to one or more companies via `CompanyAccess`. Resources (Projects, Channels, Topics, Agents) live under a Company.
> **Auth:** All endpoints require a valid Supabase JWT.
> **Conventions:**
> - `company_id` is a UUID.
> - `slug` is unique, lowercase, kebab-case (`/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/`).
> - List endpoints support pagination via `?page=&page_size=` (default `20`, max `100`).
> - Roles: `owner`, `admin`, `member`, `viewer` (descending privilege).
> - **Current company** = the company a user is "in" right now; tracked on `User.current_company`. `POST /switch` changes it.

---

## 1. GET /api/v1/companies

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/companies` |
| Auth Required | Yes — Supabase JWT |
| Description | List companies the caller has active membership in. Staff users may pass `?all=true` to list everything. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | No | Search by name / slug (icontains). |
| `is_active` | bool | No | Default unset = all. |
| `all` | bool | No | Staff-only override; lists every company. |
| `page` / `page_size` | int | No | Pagination. |

### Request JSON
```json
// No body. Example:
// GET /api/v1/companies?q=neural&page=1&page_size=20
// Authorization: Bearer <token>
```

### Response JSON
```json
{
  "items": [
    {
      "id": "company-uuid-1",
      "name": "NeuralOps",
      "slug": "neuralops",
      "logo": "https://cdn.example.com/logos/neuralops.png",
      "is_active": true,
      "my_role": "owner",
      "is_current": true,
      "member_count": 42,
      "created_at": "2026-01-10T08:00:00Z"
    },
    {
      "id": "company-uuid-2",
      "name": "Acme",
      "slug": "acme",
      "logo": null,
      "is_active": true,
      "my_role": "member",
      "is_current": false,
      "member_count": 17,
      "created_at": "2026-03-15T10:00:00Z"
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                  // 401
{ "detail": "Forbidden: staff only." }        // 403 — `all=true` from non-staff
```

### Flow
```
Client
  │
  ├─► GET /api/v1/companies?q=...
  │   Authorization: Bearer <token>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Build base queryset:
  │       - if all=true & caller.is_staff → Company.objects.all()
  │       - else → companies via CompanyAccess(user=caller, is_active=True)
  │   3. Apply filters (q, is_active)
  │   4. Annotate per-row:
  │       - my_role  = caller's role in that company
  │       - is_current = (company == caller.current_company)
  │       - member_count = active CompanyAccess count
  │   5. Paginate, serialize
  │
  └─► 200 OK  { items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Company` | `nucleus` | Listing |
| `CompanyAccess` | `nucleus` | Scope + per-row role + member count |
| `User` | `nucleus` | `caller.current_company` for `is_current` |

### Proposed Django ORM Query
```python
from django.db.models import Count, Q, F, Subquery, OuterRef, CharField

if payload.all and caller.is_staff:
    qs = Company.objects.all()
else:
    qs = Company.objects.filter(
        access__user=caller,
        access__is_active=True,
    )

if q:
    qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
if is_active is not None:
    qs = qs.filter(is_active=is_active)

my_role_sq = (
    CompanyAccess.objects
    .filter(user=caller, company=OuterRef("pk"), is_active=True)
    .values("role")[:1]
)

qs = (
    qs.distinct()
    .annotate(
        my_role=Subquery(my_role_sq, output_field=CharField()),
        member_count=Count(
            "access",
            filter=Q(access__is_active=True),
            distinct=True,
        ),
    )
    .order_by("name")
)

current_company_id = caller.current_company_id
total = qs.count()
items = qs[(page - 1) * page_size : page * page_size]
# is_current computed in serializer: company.id == current_company_id
```

### Django Ninja Schemas
```python
from ninja import Schema, FilterSchema, Field
from uuid import UUID
from datetime import datetime


class CompanyListItemOut(Schema):
    id: UUID
    name: str
    slug: str
    logo: str | None = None
    is_active: bool
    my_role: str | None = None
    is_current: bool
    member_count: int
    created_at: datetime


class CompanyListOut(Schema):
    items: list[CompanyListItemOut]
    total: int
    page: int
    page_size: int


class CompanyListFilters(FilterSchema):
    q: str | None = Field(None, q=["name__icontains", "slug__icontains"])
    is_active: bool | None = None
    all: bool | None = False
```

---

## 2. POST /api/v1/companies

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/companies` |
| Auth Required | Yes — Supabase JWT |
| Description | Create a new company. Caller becomes its first `owner` automatically. Slug is generated from name if not provided; uniqueness checked. Optionally sets the new company as caller's `current_company`. |

### Request JSON
```json
{
  "name": "NeuralOps",
  "slug": "neuralops",
  "logo": "https://cdn.example.com/logos/neuralops.png",
  "settings": {
    "timezone": "Asia/Karachi",
    "locale": "en"
  },
  "set_current": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | 1–120 chars. |
| `slug` | string | No | If omitted, auto-derived from `name` (slugify + collision suffix). |
| `logo` | string (URL) | No | |
| `settings` | object | No | Initial CompanySettings (see settings endpoints). |
| `set_current` | bool | No | If `true`, set as `caller.current_company`. Default `true`. |

### Response JSON
```json
{
  "id": "company-uuid-new",
  "name": "NeuralOps",
  "slug": "neuralops",
  "logo": "https://cdn.example.com/logos/neuralops.png",
  "is_active": true,
  "my_role": "owner",
  "is_current": true,
  "member_count": 1,
  "created_at": "2026-05-22T22:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Slug already in use." }                // 409
{ "detail": "Validation error", "errors": { ... } } // 422
```

### Flow
```
Client
  │
  ├─► POST /api/v1/companies  { name, slug?, ... }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Validate payload (Pydantic)
  │   3. Slug resolution:
  │       - If provided → validate format
  │       - Else → slugify(name); on collision, append -2, -3, ...
  │   4. Atomic transaction:
  │       - Create Company(name, slug, logo, is_active=True)
  │       - Create CompanySettings(company, ...)
  │       - Create CompanyAccess(user=caller, company, role="owner", is_active=True, granted_by=caller)
  │       - If set_current: caller.current_company = new company
  │   5. Return company detail (member_count=1, my_role="owner")
  │
  └─► 200 OK  { company }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Company` | `nucleus` | Insert |
| `CompanySettings` *(proposed)* | `nucleus` | Insert (1:1 with Company) |
| `CompanyAccess` | `nucleus` | Insert (caller as owner) |
| `User` | `nucleus` | Update `current_company` if requested |

### Proposed Django ORM Query
```python
from django.utils.text import slugify
from django.db import transaction, IntegrityError

def _resolve_slug(base: str) -> str:
    base = slugify(base)[:60] or "company"
    candidate = base
    suffix = 2
    while Company.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate

with transaction.atomic():
    slug = payload.slug or _resolve_slug(payload.name)
    if payload.slug and Company.objects.filter(slug=slug).exists():
        raise Conflict("Slug already in use.")

    company = Company.objects.create(
        name=payload.name,
        slug=slug,
        logo=payload.logo,
        is_active=True,
    )
    CompanySettings.objects.create(
        company=company,
        timezone=(payload.settings or {}).get("timezone", "UTC"),
        locale=(payload.settings or {}).get("locale", "en"),
    )
    CompanyAccess.objects.create(
        user=caller,
        company=company,
        role="owner",
        is_active=True,
        granted_by=caller,
    )
    if payload.set_current:
        User.objects.filter(pk=caller.pk).update(current_company=company)
```

### Django Ninja Schemas
```python
class CompanySettingsIn(Schema):
    timezone: str | None = "UTC"
    locale: str | None = "en"


class CompanyCreateIn(Schema):
    name: str
    slug: str | None = None
    logo: str | None = None
    settings: CompanySettingsIn | None = None
    set_current: bool | None = True
```

---

## 3. GET /api/v1/companies/{company_id}

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/companies/{company_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Retrieve full company detail. Caller must have active membership or be staff. Includes counts and the caller's role. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "id": "company-uuid-1",
  "name": "NeuralOps",
  "slug": "neuralops",
  "logo": "https://cdn.example.com/logos/neuralops.png",
  "is_active": true,
  "my_role": "owner",
  "is_current": true,
  "stats": {
    "members": 42,
    "projects": 8,
    "channels": 31,
    "topics": 12,
    "agents": 5
  },
  "settings": {
    "timezone": "Asia/Karachi",
    "locale": "en"
  },
  "created_at": "2026-01-10T08:00:00Z",
  "updated_at": "2026-05-21T15:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }    // 401
{ "detail": "Not found." }      // 404 — also when caller lacks visibility
```

### Flow
```
Client
  │
  ├─► GET /api/v1/companies/{company_id}
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility:
  │       caller.is_staff
  │       OR active CompanyAccess(user=caller, company=company_id)
  │       else → 404
  │   3. Fetch company w/ select_related('settings')
  │   4. Compute stats:
  │       - members = active CompanyAccess count
  │       - projects = Project count (is_active=True)
  │       - channels = Channel count (project__company)
  │       - topics   = Topic count
  │       - agents   = Agent count
  │   5. Resolve my_role from CompanyAccess
  │   6. is_current = (company.id == caller.current_company_id)
  │
  └─► 200 OK  { company detail }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Company` | `nucleus` | Fetch |
| `CompanySettings` | `nucleus` | OneToOne |
| `CompanyAccess` | `nucleus` | Visibility + my_role + member count |
| `Project` / `Channel` / `Topic` / `Agent` | `nucleus` | Counts |

### Proposed Django ORM Query
```python
from django.db.models import Count, Q

company = (
    Company.objects
    .select_related("settings")
    .annotate(
        members_count =Count("access", filter=Q(access__is_active=True), distinct=True),
        projects_count=Count("projects", filter=Q(projects__is_active=True), distinct=True),
        channels_count=Count("projects__channels", distinct=True),
        topics_count  =Count("projects__topics", distinct=True),
        agents_count  =Count("agents", distinct=True),
    )
    .get(pk=company_id)
)

# Visibility
my_access = CompanyAccess.objects.filter(
    user=caller, company_id=company_id, is_active=True,
).values_list("role", flat=True).first()
if not (caller.is_staff or my_access):
    raise Http404
```

### Django Ninja Schemas
```python
class CompanyStats(Schema):
    members: int
    projects: int
    channels: int
    topics: int
    agents: int


class CompanySettingsOut(Schema):
    timezone: str
    locale: str


class CompanyDetailOut(Schema):
    id: UUID
    name: str
    slug: str
    logo: str | None = None
    is_active: bool
    my_role: str | None = None
    is_current: bool
    stats: CompanyStats
    settings: CompanySettingsOut
    created_at: datetime
    updated_at: datetime
```

---

## 4. PATCH /api/v1/companies/{company_id}

### API Details
| Field | Value |
|---|---|
| Method | PATCH |
| Endpoint | `/api/v1/companies/{company_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | Partial update of company core fields. Caller must be `owner` or `admin`. Slug change checks uniqueness. Settings changes go through the dedicated `/settings` endpoint, not here. |

### Request JSON
```json
{
  "name": "NeuralOps Inc.",
  "slug": "neuralops-inc",
  "logo": "https://cdn.example.com/logos/neuralops-2.png",
  "is_active": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | No | 1–120 chars. |
| `slug` | string | No | Must be unique. Owner-only. |
| `logo` | string (URL) | No | |
| `is_active` | bool | No | Owner-only. Soft-disable / re-enable. |

### Response JSON
```json
// Same shape as GET /api/v1/companies/{company_id}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                     // 401
{ "detail": "Forbidden: not company admin." }    // 403
{ "detail": "Slug already in use." }             // 409
{ "detail": "Validation error", "errors": ... }  // 422
```

### Flow
```
Client
  │
  ├─► PATCH /api/v1/companies/{company_id}  { partial fields }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Authz: caller is owner/admin in company
  │       - slug, is_active changes → owner-only
  │   3. Atomic:
  │       - select_for_update Company
  │       - If slug present and changed → uniqueness check
  │       - Apply updates
  │   4. Return refreshed detail
  │
  └─► 200 OK  { company detail }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Company` | `nucleus` | Field updates |
| `CompanyAccess` | `nucleus` | Authz |

### Proposed Django ORM Query
```python
OWNER_ONLY_FIELDS = {"slug", "is_active"}

with transaction.atomic():
    company = Company.objects.select_for_update().get(pk=company_id)

    my_role = CompanyAccess.objects.filter(
        user=caller, company=company, is_active=True,
    ).values_list("role", flat=True).first()
    if my_role not in {"owner", "admin"}:
        raise PermissionDenied

    sent = payload.dict(exclude_unset=True)
    for f in OWNER_ONLY_FIELDS:
        if f in sent and my_role != "owner":
            raise PermissionDenied(f"{f} change requires owner role.")

    if "slug" in sent and sent["slug"] != company.slug:
        if Company.objects.filter(slug=sent["slug"]).exclude(pk=company.pk).exists():
            raise Conflict("Slug already in use.")

    for field, value in sent.items():
        setattr(company, field, value)
    company.save(update_fields=list(sent.keys()))
```

### Django Ninja Schemas
```python
class CompanyPatchIn(Schema):
    name: str | None = None
    slug: str | None = None       # owner-only
    logo: str | None = None
    is_active: bool | None = None # owner-only
```

---

## 5. DELETE /api/v1/companies/{company_id}

### API Details
| Field | Value |
|---|---|
| Method | DELETE |
| Endpoint | `/api/v1/companies/{company_id}` |
| Auth Required | Yes — Supabase JWT |
| Description | **Soft delete:** sets `is_active=False`, deactivates all CompanyAccess, ends related sessions, archives projects. Hard delete via `?hard=true` is staff-only and cascades. Caller must be **owner**. Confirmation header required. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `hard` | bool | No | Staff-only. Default `false`. |

### Required Header
| Header | Value |
|---|---|
| `X-Confirm-Slug` | The company's `slug` exactly — guards against accidental deletion. |

### Request JSON
```json
// No body.
// DELETE /api/v1/companies/{company_id}
// Header: X-Confirm-Slug: neuralops
```

### Response JSON
```json
{
  "company_id": "company-uuid-1",
  "mode": "soft",
  "deactivated_members": 42,
  "archived_projects": 8,
  "ended_sessions": 17,
  "deleted_at": "2026-05-22T23:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                            // 401
{ "detail": "Forbidden: owner role required." }         // 403
{ "detail": "Confirmation slug missing or mismatch." }  // 400
{ "detail": "Not found." }                              // 404
```

### Flow
```
Client
  │
  ├─► DELETE /api/v1/companies/{company_id}[?hard=true]
  │   X-Confirm-Slug: <slug>
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch company
  │   3. Authz: caller has role="owner" AND is_active in this company
  │   4. Confirmation: header X-Confirm-Slug == company.slug
  │   5. Atomic:
  │       if hard & staff:
  │         company.delete()  → cascades
  │       else:
  │         company.is_active = False
  │         CompanyAccess(...) → is_active=False
  │         Project(company=...) → is_active=False (archive)
  │         UserSession(user__in=members) → end if scoped
  │         Reset User.current_company for users whose current was this
  │   6. Return summary counts
  │
  └─► 200 OK  { company_id, mode, counts, deleted_at }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `Company` | `nucleus` | Soft or hard delete |
| `CompanyAccess` | `nucleus` | Bulk deactivate |
| `Project` | `nucleus` | Bulk archive |
| `User` | `nucleus` | Reset `current_company` |
| `UserSession` *(proposed)* | `nucleus` | End related sessions |

### Proposed Django ORM Query
```python
with transaction.atomic():
    company = Company.objects.select_for_update().get(pk=company_id)

    # Authz
    if not CompanyAccess.objects.filter(
        user=caller, company=company, role="owner", is_active=True,
    ).exists():
        raise PermissionDenied("Owner role required.")

    # Confirmation
    if request.headers.get("X-Confirm-Slug") != company.slug:
        raise BadRequest("Confirmation slug missing or mismatch.")

    if hard and caller.is_staff:
        # cascades via FK on_delete=CASCADE
        company.delete()
        return {"mode": "hard", ...}

    # Soft path
    deactivated = CompanyAccess.objects.filter(
        company=company, is_active=True,
    ).update(is_active=False)

    archived = Project.objects.filter(
        company=company, is_active=True,
    ).update(is_active=False)

    # Reset current_company for affected users
    User.objects.filter(current_company=company).update(current_company=None)

    Company.objects.filter(pk=company.pk).update(is_active=False)

    return {
        "company_id": company.pk,
        "mode": "soft",
        "deactivated_members": deactivated,
        "archived_projects": archived,
        "ended_sessions": ...,   # if UserSession scoped per-company
        "deleted_at": timezone.now(),
    }
```

### Django Ninja Schemas
```python
class CompanyDeleteOut(Schema):
    company_id: UUID
    mode: str                       # soft | hard
    deactivated_members: int
    archived_projects: int
    ended_sessions: int
    deleted_at: datetime
```

---

## 6. GET /api/v1/companies/{company_id}/members

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/companies/{company_id}/members` |
| Auth Required | Yes — Supabase JWT |
| Description | List active members of a company. Caller must be a member of the company (any role) or staff. Supports search and role filters. |

### Query Parameters
| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | No | Search by user email / username / human_profile.full_name. |
| `role` | string | No | Filter by `owner`, `admin`, `member`, `viewer`. |
| `is_active` | bool | No | Default `true`. Pass `false` to see inactive memberships. |
| `user_type` | string | No | `human` or `agent`. |
| `page` / `page_size` | int | No | Pagination. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "company_id": "company-uuid-1",
  "items": [
    {
      "user": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "noaman@example.com",
        "username": "noaman@example.com",
        "user_type": "human",
        "is_active": true,
        "human_profile": {
          "full_name": "Noaman Faisal",
          "avatar": "https://cdn.example.com/avatars/noaman.jpg"
        }
      },
      "role": "owner",
      "is_active": true,
      "granted_at": "2026-01-10T08:00:00Z",
      "granted_by": "550e8400-e29b-41d4-a716-446655440000"
    }
  ],
  "total": 42,
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
  ├─► GET /api/v1/companies/{company_id}/members?role=admin&q=...
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility: caller has active CompanyAccess in company OR staff → else 404
  │   3. Build queryset over CompanyAccess(company=company_id)
  │       .select_related('user', 'user__human_profile', 'granted_by')
  │   4. Apply filters: role, is_active, q (across user fields), user_type
  │   5. Order by role priority then granted_at
  │   6. Paginate
  │
  └─► 200 OK  { company_id, items, total, page, page_size }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `CompanyAccess` | `nucleus` | Source of membership |
| `User` | `nucleus` | Embedded |
| `Human` | `nucleus` | Embedded profile |

### Proposed Django ORM Query
```python
from django.db.models import Q, Case, When, IntegerField

# Visibility
if not (caller.is_staff or CompanyAccess.objects.filter(
    user=caller, company_id=company_id, is_active=True,
).exists()):
    raise Http404

qs = (
    CompanyAccess.objects
    .filter(company_id=company_id)
    .select_related("user", "user__human_profile", "granted_by")
)

if role:
    qs = qs.filter(role=role)
qs = qs.filter(is_active=is_active if is_active is not None else True)
if user_type:
    qs = qs.filter(user__user_type=user_type)
if q:
    qs = qs.filter(
        Q(user__email__icontains=q)
        | Q(user__username__icontains=q)
        | Q(user__human_profile__full_name__icontains=q)
    )

role_order = Case(
    When(role="owner",  then=0),
    When(role="admin",  then=1),
    When(role="member", then=2),
    When(role="viewer", then=3),
    default=99,
    output_field=IntegerField(),
)
qs = qs.annotate(_role_order=role_order).order_by("_role_order", "granted_at")
```

### Django Ninja Schemas
```python
class HumanProfileOut(Schema):
    full_name: str | None = None
    avatar: str | None = None


class MemberUserOut(Schema):
    id: UUID
    email: str
    username: str
    user_type: str
    is_active: bool
    human_profile: HumanProfileOut | None = None


class MemberOut(Schema):
    user: MemberUserOut
    role: str
    is_active: bool
    granted_at: datetime
    granted_by: UUID | None = None


class MembersListOut(Schema):
    company_id: UUID
    items: list[MemberOut]
    total: int
    page: int
    page_size: int
```

---

## 7. GET /api/v1/companies/{company_id}/settings

### API Details
| Field | Value |
|---|---|
| Method | GET |
| Endpoint | `/api/v1/companies/{company_id}/settings` |
| Auth Required | Yes — Supabase JWT |
| Description | Fetch the full settings document for a company. Visible to any active member. Sensitive integration secrets are redacted unless caller is owner/admin. |

### Request JSON
```json
// No body.
```

### Response JSON
```json
{
  "company_id": "company-uuid-1",
  "timezone": "Asia/Karachi",
  "locale": "en",
  "branding": {
    "primary_color": "#0F62FE",
    "logo_dark": "https://cdn.example.com/logos/neuralops-dark.png"
  },
  "policies": {
    "require_2fa": true,
    "session_idle_minutes": 30,
    "invite_expiry_days": 7
  },
  "integrations": {
    "slack":  { "enabled": true,  "webhook_url": "***redacted***" },
    "github": { "enabled": false, "token": null }
  },
  "features": {
    "agents_enabled": true,
    "topics_enabled": true,
    "realtime_enabled": true
  },
  "updated_at": "2026-05-21T15:00:00Z",
  "updated_by": "caller-user-uuid"
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
  ├─► GET /api/v1/companies/{company_id}/settings
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Visibility: active CompanyAccess in company OR staff → else 404
  │   3. Fetch CompanySettings (OneToOne with company)
  │   4. Determine redaction scope:
  │       - owner/admin → full integrations payload
  │       - member/viewer → integrations.* secrets replaced with "***redacted***"
  │   5. Serialize
  │
  └─► 200 OK  { settings }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `CompanySettings` | `nucleus` | Fetch by company |
| `CompanyAccess` | `nucleus` | Visibility + redaction scope |

### Proposed Django ORM Query
```python
my_role = CompanyAccess.objects.filter(
    user=caller, company_id=company_id, is_active=True,
).values_list("role", flat=True).first()

if not (caller.is_staff or my_role):
    raise Http404

settings_obj = CompanySettings.objects.select_related("updated_by").get(
    company_id=company_id
)

privileged = caller.is_staff or my_role in {"owner", "admin"}
payload = serialize_settings(settings_obj, redact_secrets=not privileged)
```

### Django Ninja Schemas
```python
class CompanyBrandingOut(Schema):
    primary_color: str | None = None
    logo_dark: str | None = None


class CompanyPoliciesOut(Schema):
    require_2fa: bool = False
    session_idle_minutes: int = 30
    invite_expiry_days: int = 7


class IntegrationOut(Schema):
    enabled: bool
    # Free-form per-integration; secrets are redacted when not privileged
    # Use dict[str, Any] in implementation if shape varies.


class CompanyFeaturesOut(Schema):
    agents_enabled: bool = True
    topics_enabled: bool = True
    realtime_enabled: bool = True


class CompanySettingsDetailOut(Schema):
    company_id: UUID
    timezone: str
    locale: str
    branding: CompanyBrandingOut
    policies: CompanyPoliciesOut
    integrations: dict[str, IntegrationOut]   # secrets redacted for non-admin
    features: CompanyFeaturesOut
    updated_at: datetime
    updated_by: UUID | None = None
```

---

## 8. PATCH /api/v1/companies/{company_id}/settings

### API Details
| Field | Value |
|---|---|
| Method | PATCH |
| Endpoint | `/api/v1/companies/{company_id}/settings` |
| Auth Required | Yes — Supabase JWT |
| Description | Partial settings update. Caller must be `owner` or `admin`. Integrations subtree is **deep-merged** so callers can patch a single integration without resending the entire object. Secret fields (e.g., `webhook_url`, `token`) are write-only. |

### Request JSON
```json
{
  "timezone": "Asia/Karachi",
  "policies": {
    "require_2fa": true,
    "session_idle_minutes": 60
  },
  "integrations": {
    "slack": {
      "enabled": true,
      "webhook_url": "https://hooks.slack.com/services/T0/B0/XXX"
    }
  },
  "features": {
    "topics_enabled": true
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `timezone` | string | No | IANA tz. |
| `locale` | string | No | BCP-47. |
| `branding.*` | partial | No | Merged into existing. |
| `policies.*` | partial | No | Merged into existing. |
| `integrations.*` | partial | No | **Deep-merged**: only touched keys are updated. |
| `features.*` | partial | No | Merged into existing. |

### Response JSON
```json
// Same shape as GET /settings (with secrets redacted per role rules).
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                      // 401
{ "detail": "Forbidden: not company admin." }     // 403
{ "detail": "Validation error", "errors": ... }   // 422
```

### Flow
```
Client
  │
  ├─► PATCH /api/v1/companies/{company_id}/settings  { partial fields }
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Authz: owner/admin
  │   3. Atomic:
  │       - select_for_update CompanySettings
  │       - For each top-level field present:
  │           scalar (timezone, locale) → assign
  │           dict (branding, policies, integrations, features) → deep-merge
  │       - settings.updated_at = now(), updated_by = caller
  │       - Persist
  │   4. Return refreshed settings (redacted view per role)
  │
  └─► 200 OK  { settings }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `CompanySettings` | `nucleus` | Update with deep merge on JSON columns |
| `CompanyAccess` | `nucleus` | Authz |

### Proposed Django ORM Query
```python
def deep_merge(base: dict, patch: dict) -> dict:
    """Recursive merge: dicts merge, scalars overwrite."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

with transaction.atomic():
    my_role = CompanyAccess.objects.filter(
        user=caller, company_id=company_id, is_active=True,
    ).values_list("role", flat=True).first()
    if my_role not in {"owner", "admin"} and not caller.is_staff:
        raise PermissionDenied

    settings_obj = CompanySettings.objects.select_for_update().get(company_id=company_id)

    sent = payload.dict(exclude_unset=True)
    if "timezone" in sent: settings_obj.timezone = sent["timezone"]
    if "locale"   in sent: settings_obj.locale   = sent["locale"]
    if "branding"     in sent: settings_obj.branding     = deep_merge(settings_obj.branding,     sent["branding"])
    if "policies"     in sent: settings_obj.policies     = deep_merge(settings_obj.policies,     sent["policies"])
    if "integrations" in sent: settings_obj.integrations = deep_merge(settings_obj.integrations, sent["integrations"])
    if "features"     in sent: settings_obj.features     = deep_merge(settings_obj.features,     sent["features"])

    settings_obj.updated_by = caller
    settings_obj.save()
```

### Django Ninja Schemas
```python
class CompanyBrandingIn(Schema):
    primary_color: str | None = None
    logo_dark: str | None = None


class CompanyPoliciesIn(Schema):
    require_2fa: bool | None = None
    session_idle_minutes: int | None = None
    invite_expiry_days: int | None = None


class CompanyFeaturesIn(Schema):
    agents_enabled: bool | None = None
    topics_enabled: bool | None = None
    realtime_enabled: bool | None = None


class CompanySettingsPatchIn(Schema):
    timezone: str | None = None
    locale: str | None = None
    branding: CompanyBrandingIn | None = None
    policies: CompanyPoliciesIn | None = None
    integrations: dict | None = None     # free-form deep-merged
    features: CompanyFeaturesIn | None = None
```

---

## 9. POST /api/v1/companies/{company_id}/switch

### API Details
| Field | Value |
|---|---|
| Method | POST |
| Endpoint | `/api/v1/companies/{company_id}/switch` |
| Auth Required | Yes — Supabase JWT |
| Description | Set the target company as caller's `current_company`. Lightweight session-context switch — does **not** issue new tokens; subsequent requests use the new context via the user's stored `current_company`. Returns the new active company plus the caller's role. |

### Request JSON
```json
// No body. (You can optionally accept a "remember": false to make it transient — out of scope here.)
```

### Response JSON
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "previous_company_id": "company-uuid-2",
  "current_company": {
    "id": "company-uuid-1",
    "name": "NeuralOps",
    "slug": "neuralops"
  },
  "role": "owner",
  "switched_at": "2026-05-22T22:00:00Z"
}
```

**Error Responses**
```json
{ "detail": "Unauthorized" }                                  // 401
{ "detail": "Not a member of this company." }                 // 403
{ "detail": "Company is inactive." }                          // 409
{ "detail": "Not found." }                                    // 404
```

### Flow
```
Client
  │
  ├─► POST /api/v1/companies/{company_id}/switch
  │
  │   [Django / authn]
  │   1. Verify JWT, resolve caller
  │   2. Fetch company (must exist and be active)
  │   3. Membership check: active CompanyAccess(user=caller, company)
  │   4. Capture previous_company_id = caller.current_company_id
  │   5. Atomic:
  │       - User.objects.filter(pk=caller.pk).update(current_company=company)
  │       - Audit: UserActivityLog(kind="company_switch",
  │                meta={"from": prev, "to": company.id})
  │   6. Return summary
  │
  └─► 200 OK  { user_id, previous_company_id, current_company, role, switched_at }
```

### Proposed Involved Models
| Model | App | Action |
|---|---|---|
| `User` | `nucleus` | Update `current_company` |
| `CompanyAccess` | `nucleus` | Membership + role |
| `Company` | `nucleus` | Sanity check |
| `UserActivityLog` *(proposed)* | `nucleus` | Audit |

### Proposed Django ORM Query
```python
with transaction.atomic():
    company = Company.objects.get(pk=company_id)
    if not company.is_active:
        raise Conflict("Company is inactive.")

    role = CompanyAccess.objects.filter(
        user=caller, company=company, is_active=True,
    ).values_list("role", flat=True).first()
    if not role:
        raise PermissionDenied("Not a member of this company.")

    previous_company_id = caller.current_company_id
    User.objects.filter(pk=caller.pk).update(current_company=company)

    UserActivityLog.objects.create(
        user=caller,
        actor=caller,
        kind="company_switch",
        meta={
            "from": str(previous_company_id) if previous_company_id else None,
            "to": str(company.id),
        },
    )
```

### Django Ninja Schemas
```python
class CompanySwitchOut(Schema):
    user_id: UUID
    previous_company_id: UUID | None = None
    current_company: CompanyMini
    role: str
    switched_at: datetime
```

---

## Proposed Missing / Reused Models

### `Company` *(assumed existing)*

```python
class Company(BaseModel):
    name        = models.CharField(max_length=120)
    slug        = models.SlugField(max_length=64, unique=True, db_index=True)
    logo        = models.URLField(blank=True, null=True)
    is_active   = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_company"
```

### `CompanySettings` *(new — 1:1 with Company)*

```python
class CompanySettings(BaseModel):
    company      = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="settings")
    timezone     = models.CharField(max_length=64, default="UTC")
    locale       = models.CharField(max_length=16, default="en")

    branding     = models.JSONField(default=dict, blank=True)
    policies     = models.JSONField(default=dict, blank=True)
    integrations = models.JSONField(default=dict, blank=True)  # secrets stored here, redacted on read
    features     = models.JSONField(default=dict, blank=True)

    updated_at   = models.DateTimeField(auto_now=True)
    updated_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="updated_company_settings")

    class Meta:
        db_table = "accounts_company_settings"
```

### `User.current_company` *(field expectation)*

```python
class User(AbstractBaseUser):
    ...
    current_company = models.ForeignKey(
        "Company",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="current_users",
    )
```

### Reused (defined in earlier docs)

- `CompanyAccess` — see `02-users.md`
- `UserActivityLog` — see `02-users.md`
- `Project`, `Channel`, `Topic`, `Agent` — assumed existing

### Notes / Decisions

- **Settings are a separate table**, not a `JSONField` on `Company`, because:
  - We need an explicit `updated_by` audit field
  - We can put DB-level constraints / migrations on individual subtrees
  - Easier to evolve: add a column when something graduates from "free-form JSON" to "first-class field"
- **Secret redaction in GET /settings** is done at the serialization layer based on caller role. The DB still stores raw values; only owner/admin reads through.
- **Company switch is just a write to `User.current_company`** — no new JWT, no session re-issue. The Supabase JWT remains the same; "current company" is server-side state. Clients should refetch `/auth/session` after switching to get the new context bundled.
