# 18–20. Embedding / Vector, Permission / RBAC, and Audit / Activity APIs

| Method | Endpoint | Group |
| --- | --- | --- |
| GET | /api/v1/embeddings/jobs | Embedding / Vector |
| GET | /api/v1/embeddings/jobs/{job_id} | Embedding / Vector |
| POST | /api/v1/embeddings/jobs/{job_id}/retry | Embedding / Vector |
| DELETE | /api/v1/embeddings/vectors/{vector_id} | Embedding / Vector |
| GET | /api/v1/permissions | Permission / RBAC |
| GET | /api/v1/roles | Permission / RBAC |
| POST | /api/v1/roles | Permission / RBAC |
| PATCH | /api/v1/roles/{role_id} | Permission / RBAC |
| DELETE | /api/v1/roles/{role_id} | Permission / RBAC |
| GET | /api/v1/audit/events | Audit / Activity |
| GET | /api/v1/audit/events/{event_id} | Audit / Activity |
| GET | /api/v1/activity/feed | Audit / Activity |

---

## Background

### Embedding / Vector

The embedding pipeline converts `KnowledgeFile` documents into vector representations stored in ChromaDB. Each file generates one `EmbeddingJob` record that tracks the lifecycle of the chunking + embedding process. `VectorDocument` records serve as the DB-side index of what lives in the vector store — one record per chunk per file. These APIs expose the pipeline state for monitoring and manual intervention.

### Permission / RBAC

> **These models do not yet exist in the migration.** `Role` and `Permission` are listed as missing models in api4.md. The current system uses a flat string `role` field on `CompanyAccess` (`owner`, `admin`, `member`, `viewer`). The RBAC APIs introduce a proper permission system with custom roles and fine-grained permission codenames. Proposed model definitions are included below.

### Audit / Activity

Every significant state-changing action in NeuralOps is written to `AuditEvent`. This model is already migrated (migration 0002). The audit endpoints expose these records for compliance, security review, and admin dashboards. The activity feed is a user-facing derivative — filtered to events relevant to the authenticated user.

---

## Part A — Embedding / Vector APIs

---

## 18.1 GET /api/v1/embeddings/jobs

### Detail

Returns a paginated list of `EmbeddingJob` records for the authenticated user's active company. Supports filtering by `status`, `target_type`, and date range. Designed for an admin dashboard showing the health of the embedding pipeline — how many jobs are queued, running, completed, or failed.

### Flow

1. Authenticate request; resolve `current_company`.
2. Query `EmbeddingJob` filtered by `company`.
3. Apply optional filters (`status`, `target_type`, `from_date`, `to_date`).
4. Enrich each job with the target resource name (e.g. `KnowledgeFile.original_filename`).
5. Log nothing — read-only.
6. Return paginated list ordered by `created_at DESC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/embeddings/jobs?status=failed&target_type=knowledge_file&page=1
{
  "status": "failed",              // optional: "pending" | "running" | "completed" | "failed"
  "target_type": "knowledge_file", // optional: "knowledge_file"
  "from_date": "2026-05-01",
  "to_date": null,
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "ej1b2c3d-e5f6-7890-abcd-ef1234567890",
      "target_type": "knowledge_file",
      "target_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
      "target_label": "installation_guide.pdf",
      "status": "failed",
      "error": "ChromaDB connection timeout after 60s",
      "metadata": { "chunk_size": 512, "chunk_overlap": 64 },
      "started_at": "2026-05-20T08:00:10Z",
      "completed_at": "2026-05-20T08:01:10Z",
      "created_at": "2026-05-20T08:00:00Z",
      "updated_at": "2026-05-20T08:01:10Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, date


class EmbeddingJobFilterSchema(Schema):
    status: Optional[str] = None        # "pending" | "running" | "completed" | "failed"
    target_type: Optional[str] = None   # "knowledge_file"
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class EmbeddingJobListItemOut(Schema):
    id: UUID
    target_type: str
    target_id: UUID
    target_label: Optional[str]         # resolved display name of the target
    status: str
    error: Optional[str]
    metadata: dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class EmbeddingJobListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[EmbeddingJobListItemOut]
```

### Models Involved

- `EmbeddingJob` — primary listing model
- `KnowledgeFile` — resolved for `target_label` when `target_type=knowledge_file`
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Q
from nucleus.models import EmbeddingJob, KnowledgeFile
from ninja.errors import HttpError


def list_embedding_jobs(request, filters: EmbeddingJobFilterSchema):
    company = request.auth.current_company

    qs = EmbeddingJob.objects.filter(company=company)

    if filters.status:
        qs = qs.filter(status=filters.status)

    if filters.target_type:
        qs = qs.filter(target_type=filters.target_type)

    if filters.from_date:
        qs = qs.filter(created_at__date__gte=filters.from_date)

    if filters.to_date:
        qs = qs.filter(created_at__date__lte=filters.to_date)

    qs = qs.order_by("-created_at")

    # Enrich with target labels (batch resolve for performance)
    jobs = list(qs)

    kf_ids = [
        j.target_id for j in jobs if j.target_type == "knowledge_file"
    ]
    kf_label_map = dict(
        KnowledgeFile.objects.filter(id__in=kf_ids)
        .values_list("id", "original_filename")
    )

    for job in jobs:
        if job.target_type == "knowledge_file":
            job.target_label = kf_label_map.get(job.target_id)
        else:
            job.target_label = None

    return jobs
```

---

## 18.2 GET /api/v1/embeddings/jobs/{job_id}

### Detail

Retrieves the full detail of a single `EmbeddingJob` by its UUID. Returns all status fields, timing, error message, and metadata including any chunk parameters used. Also returns a link back to the target resource (e.g. the `KnowledgeFile` that was being processed). Scoped to `current_company`.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `EmbeddingJob` by `job_id` scoped to `company`.
3. Return 404 if not found.
4. Resolve `target_label` from the target resource.
5. Return full job detail.

### Request JSON

```json
// No request body — job_id is a path parameter
// GET /api/v1/embeddings/jobs/ej1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
{
  "id": "ej1b2c3d-e5f6-7890-abcd-ef1234567890",
  "target_type": "knowledge_file",
  "target_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "target_label": "installation_guide.pdf",
  "target_url": "/api/v1/knowledge-files/kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "status": "failed",
  "error": "ChromaDB connection timeout after 60s",
  "metadata": {
    "chunk_size": 512,
    "chunk_overlap": 64,
    "chunks_processed": 0,
    "total_chunks": 64
  },
  "started_at": "2026-05-20T08:00:10Z",
  "completed_at": "2026-05-20T08:01:10Z",
  "created_at": "2026-05-20T08:00:00Z",
  "updated_at": "2026-05-20T08:01:10Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class EmbeddingJobDetailOut(Schema):
    id: UUID
    target_type: str
    target_id: UUID
    target_label: Optional[str]
    target_url: Optional[str]
    status: str
    error: Optional[str]
    metadata: dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `EmbeddingJob` — primary record
- `KnowledgeFile` — resolved for `target_label` and `target_url`
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import EmbeddingJob, KnowledgeFile
from ninja.errors import HttpError


def get_embedding_job(request, job_id):
    company = request.auth.current_company

    try:
        job = EmbeddingJob.objects.get(id=job_id, company=company)
    except EmbeddingJob.DoesNotExist:
        raise HttpError(404, "Embedding job not found.")

    # Resolve target label
    target_label = None
    target_url = None
    if job.target_type == "knowledge_file":
        kf = KnowledgeFile.objects.filter(id=job.target_id).first()
        if kf:
            target_label = kf.original_filename
            target_url = f"/api/v1/knowledge-files/{kf.id}"

    job.target_label = target_label
    job.target_url = target_url
    return job
```

---

## 18.3 POST /api/v1/embeddings/jobs/{job_id}/retry

### Detail

Retries a failed `EmbeddingJob`. Resets the job's `status` to `pending`, clears `error`, `started_at`, and `completed_at`, and re-dispatches the embedding worker. Only jobs in `failed` status can be retried. The target file's `embedding_status` is also reset to `pending`. Allows optional metadata overrides (e.g. new chunk size).

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `EmbeddingJob` by `job_id` scoped to `company`.
3. Validate `status == "failed"` — reject any other status.
4. Merge optional metadata overrides into `job.metadata`.
5. Reset `status`, `error`, `started_at`, `completed_at`.
6. Reset target file's `embedding_status` to `"pending"`.
7. Dispatch async worker with the same job ID.
8. Return updated job detail.

### Request JSON

```json
{
  "chunk_size": 256,      // optional metadata override
  "chunk_overlap": 32     // optional metadata override
}
```

### Response JSON

```json
{
  "id": "ej1b2c3d-e5f6-7890-abcd-ef1234567890",
  "target_type": "knowledge_file",
  "target_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "target_label": "installation_guide.pdf",
  "status": "pending",
  "error": null,
  "metadata": {
    "chunk_size": 256,
    "chunk_overlap": 32,
    "retry_count": 2
  },
  "started_at": null,
  "completed_at": null,
  "created_at": "2026-05-20T08:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional


class EmbeddingJobRetryIn(Schema):
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


# Response reuses EmbeddingJobDetailOut
```

### Models Involved

- `EmbeddingJob` — status reset + metadata updated
- `KnowledgeFile` — `embedding_status` reset to `"pending"`
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import EmbeddingJob, KnowledgeFile
from ninja.errors import HttpError


def retry_embedding_job(request, job_id, payload: EmbeddingJobRetryIn):
    company = request.auth.current_company

    try:
        job = EmbeddingJob.objects.get(id=job_id, company=company)
    except EmbeddingJob.DoesNotExist:
        raise HttpError(404, "Embedding job not found.")

    if job.status != "failed":
        raise HttpError(409, f"Only failed jobs can be retried. Current status: '{job.status}'.")

    # Merge metadata overrides
    updated_meta = {**job.metadata}
    if payload.chunk_size is not None:
        updated_meta["chunk_size"] = payload.chunk_size
    if payload.chunk_overlap is not None:
        updated_meta["chunk_overlap"] = payload.chunk_overlap
    updated_meta["retry_count"] = updated_meta.get("retry_count", 0) + 1

    job.status = "pending"
    job.error = None
    job.started_at = None
    job.completed_at = None
    job.metadata = updated_meta
    job.save(update_fields=["status", "error", "started_at", "completed_at", "metadata", "updated_at"])

    # Reset target file status
    if job.target_type == "knowledge_file":
        KnowledgeFile.objects.filter(id=job.target_id).update(
            embedding_status="pending"
        )

    # Re-dispatch worker
    process_embedding_job.delay(str(job.id))

    # Resolve label for response
    target_label = None
    if job.target_type == "knowledge_file":
        kf = KnowledgeFile.objects.filter(id=job.target_id).values("original_filename").first()
        target_label = kf["original_filename"] if kf else None

    job.target_label = target_label
    return job
```

---

## 18.4 DELETE /api/v1/embeddings/vectors/{vector_id}

### Detail

Deletes a single `VectorDocument` record from the database **and** removes the corresponding vector from ChromaDB. `vector_id` here is the NeuralOps UUID of the `VectorDocument` DB record (not the ChromaDB vector ID string). Use this to surgically remove a specific chunk's vector without reprocessing the entire file — for example, after identifying a corrupt or sensitive chunk.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `VectorDocument` by `vector_id` scoped to `company`.
3. Return 404 if not found.
4. Call ChromaDB to delete the vector using `VectorDocument.collection_name` and `VectorDocument.vector_id`.
5. Delete the `VectorDocument` DB record (hard delete — vectors are not soft-deleted).
6. Return 204 No Content.

### Request JSON

```json
// No request body — vector_id is a path parameter
// DELETE /api/v1/embeddings/vectors/vd1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
// 204 No Content
```

### Pydantic for Django Ninja

```python
# No input or output schema required.
# Return HTTP 204 using Django Ninja's response={204: None} pattern.
```

### Models Involved

- `VectorDocument` — hard-deleted from DB
- `Company` — tenant scope (security gate)

### Django ORM Query (Proposed)

```python
from nucleus.models import VectorDocument
from ninja.errors import HttpError


def delete_vector_document(request, vector_id):
    company = request.auth.current_company

    try:
        vd = VectorDocument.objects.get(id=vector_id, company=company)
    except VectorDocument.DoesNotExist:
        raise HttpError(404, "Vector document not found.")

    # Delete from ChromaDB first — if this fails, DB record is preserved
    try:
        vector_service.delete_vector(
            collection_name=vd.collection_name,
            vector_id=vd.vector_id,
        )
    except Exception as exc:
        raise HttpError(502, f"Failed to delete vector from ChromaDB: {exc}")

    # Hard delete the DB record
    vd.delete()

    return None
```

---

## Part B — Permission / RBAC APIs

> **All models in this section are proposed.** `Role`, `Permission`, and `RolePermission` do not yet exist in the migration. See the Model Definitions section at the end of Part B.

---

## 19.1 GET /api/v1/permissions

### Detail

Returns the full catalogue of available permission codenames for the company — the atomic capabilities that can be assigned to roles. Permissions are read-only from the API perspective; they are seeded by the system and represent every action a user can perform on every resource type. Custom permissions are not supported in v1.

### Flow

1. Authenticate request; resolve `current_company`.
2. Query `Permission` records filtered by `company` (company-scoped) plus global system permissions.
3. Optionally filter by `resource_type`.
4. Return full list ordered by `resource_type`, `action`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/permissions?resource_type=agent
{
  "resource_type": "agent"   // optional filter
}
```

### Response JSON

```json
{
  "count": 8,
  "results": [
    {
      "id": "perm1b2c-e5f6-7890-abcd-ef1234567890",
      "codename": "agents.create",
      "name": "Create Agent",
      "description": "Allows creating a new AI agent in the company.",
      "resource_type": "agent",
      "action": "create"
    },
    {
      "id": "perm2b3c-e5f6-7890-abcd-ef1234567891",
      "codename": "agents.run",
      "name": "Run Agent",
      "description": "Allows triggering agent runs.",
      "resource_type": "agent",
      "action": "run"
    },
    {
      "id": "perm3b4c-e5f6-7890-abcd-ef1234567892",
      "codename": "agents.delete",
      "name": "Delete Agent",
      "description": "Allows soft-deleting an agent.",
      "resource_type": "agent",
      "action": "delete"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class PermissionFilterSchema(Schema):
    resource_type: Optional[str] = None


class PermissionOut(Schema):
    id: UUID
    codename: str
    name: str
    description: str
    resource_type: str
    action: str


class PermissionListOut(Schema):
    count: int
    results: list[PermissionOut]
```

### Models Involved

- `Permission` (**proposed**) — primary listing model
- `Company` — optional scope (system vs company-level perms)

### Django ORM Query (Proposed)

```python
from nucleus.models import Permission   # proposed model
from ninja.errors import HttpError


def list_permissions(request, filters: PermissionFilterSchema):
    qs = Permission.objects.filter(
        company=request.auth.current_company
    ).order_by("resource_type", "action")

    if filters.resource_type:
        qs = qs.filter(resource_type=filters.resource_type)

    return qs
```

---

## 19.2 GET /api/v1/roles

### Detail

Returns all `Role` records for the authenticated user's active company — including both system-seeded roles (`owner`, `admin`, `member`, `viewer`) and any custom roles created by admins. Each role includes its full list of assigned permissions. System roles are marked with `is_system_role=True` and cannot be modified or deleted.

### Flow

1. Authenticate request; resolve `current_company`.
2. Query `Role` filtered by `company`.
3. Prefetch `permissions` M2M.
4. Return list ordered by `is_system_role DESC`, then `name ASC`.

### Request JSON

```json
// No request body — GET with no filters
// GET /api/v1/roles
```

### Response JSON

```json
{
  "count": 5,
  "results": [
    {
      "id": "role1b2c-e5f6-7890-abcd-ef1234567890",
      "name": "owner",
      "description": "Full administrative access to all company resources.",
      "is_system_role": true,
      "permissions": [
        { "id": "perm1b2c", "codename": "agents.create", "name": "Create Agent" },
        { "id": "perm2b3c", "codename": "agents.run", "name": "Run Agent" }
      ],
      "member_count": 1,
      "created_at": "2026-04-01T00:00:00Z"
    },
    {
      "id": "role2b3c-e5f6-7890-abcd-ef1234567891",
      "name": "Support Lead",
      "description": "Custom role for support team leads with agent run access.",
      "is_system_role": false,
      "permissions": [
        { "id": "perm2b3c", "codename": "agents.run", "name": "Run Agent" },
        { "id": "perm5b6c", "codename": "messages.create", "name": "Send Message" }
      ],
      "member_count": 4,
      "created_at": "2026-05-10T09:00:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class PermissionBriefOut(Schema):
    id: UUID
    codename: str
    name: str


class RoleOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    is_system_role: bool
    permissions: list[PermissionBriefOut]
    member_count: int
    created_at: datetime


class RoleListOut(Schema):
    count: int
    results: list[RoleOut]
```

### Models Involved

- `Role` (**proposed**) — primary listing model
- `Permission` (**proposed**) — M2M prefetched
- `RolePermission` (**proposed**) — M2M through table
- `CompanyAccess` — annotated `member_count` (users with this role)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count
from nucleus.models import Role   # proposed model


def list_roles(request):
    return Role.objects.filter(
        company=request.auth.current_company,
    ).prefetch_related(
        "permissions"
    ).annotate(
        member_count=Count("company_access_assignments", distinct=True)
    ).order_by("-is_system_role", "name")
```

---

## 19.3 POST /api/v1/roles

### Detail

Creates a new custom `Role` in the authenticated user's active company. Requires a unique `name` within the company. Accepts a list of `permission_ids` to assign immediately. System roles cannot be replicated by name. The creating user must have the `roles.create` permission (i.e. must be an `owner` or `admin`).

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate caller has `roles.create` permission.
3. Validate `name` is unique within the company and does not match a system role name.
4. Create `Role` with `is_system_role=False`.
5. Validate all `permission_ids` belong to company or are global system permissions.
6. Set M2M permissions via `RolePermission`.
7. Return the created role with full permission list.

### Request JSON

```json
{
  "name": "Support Lead",
  "description": "Custom role for support team leads with agent run access.",
  "permission_ids": [
    "perm2b3c-e5f6-7890-abcd-ef1234567891",
    "perm5b6c-e5f6-7890-abcd-ef1234567895"
  ]
}
```

### Response JSON

```json
{
  "id": "role2b3c-e5f6-7890-abcd-ef1234567891",
  "name": "Support Lead",
  "description": "Custom role for support team leads with agent run access.",
  "is_system_role": false,
  "permissions": [
    { "id": "perm2b3c", "codename": "agents.run", "name": "Run Agent" },
    { "id": "perm5b6c", "codename": "messages.create", "name": "Send Message" }
  ],
  "member_count": 0,
  "created_at": "2026-05-22T12:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class RoleCreateIn(Schema):
    name: str
    description: Optional[str] = None
    permission_ids: list[UUID] = []
```

### Models Involved

- `Role` (**proposed**) — created record
- `Permission` (**proposed**) — validated and assigned
- `RolePermission` (**proposed**) — M2M through records created
- `Company` — tenant scope + uniqueness check

### Django ORM Query (Proposed)

```python
from nucleus.models import Role, Permission
from ninja.errors import HttpError

SYSTEM_ROLE_NAMES = {"owner", "admin", "member", "viewer"}


def create_role(request, payload: RoleCreateIn):
    company = request.auth.current_company

    if payload.name.lower() in SYSTEM_ROLE_NAMES:
        raise HttpError(409, f"'{payload.name}' is a reserved system role name.")

    if Role.objects.filter(company=company, name=payload.name).exists():
        raise HttpError(409, f"A role named '{payload.name}' already exists.")

    role = Role.objects.create(
        company=company,
        name=payload.name,
        description=payload.description,
        is_system_role=False,
    )

    if payload.permission_ids:
        permissions = Permission.objects.filter(
            id__in=payload.permission_ids,
            company=company,
        )
        role.permissions.set(permissions)

    return role
```

---

## 19.4 PATCH /api/v1/roles/{role_id}

### Detail

Partially updates a custom `Role`. Supports updating `name`, `description`, and the full set of assigned `permission_ids` (replaces the existing permission set). System roles (`is_system_role=True`) cannot be modified and will return 403. The `name` must remain unique within the company.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate caller has `roles.update` permission.
3. Fetch `Role` by `role_id` scoped to `company`.
4. Reject if `is_system_role=True`.
5. Validate new `name` uniqueness if changed.
6. Apply field updates; replace permissions M2M if `permission_ids` provided.
7. Return updated role.

### Request JSON

```json
{
  "name": "Support Lead v2",
  "description": "Updated role for senior support leads.",
  "permission_ids": [
    "perm2b3c-e5f6-7890-abcd-ef1234567891",
    "perm5b6c-e5f6-7890-abcd-ef1234567895",
    "perm7b8c-e5f6-7890-abcd-ef1234567897"
  ]
}
```

### Response JSON

```json
{
  "id": "role2b3c-e5f6-7890-abcd-ef1234567891",
  "name": "Support Lead v2",
  "description": "Updated role for senior support leads.",
  "is_system_role": false,
  "permissions": [
    { "id": "perm2b3c", "codename": "agents.run", "name": "Run Agent" },
    { "id": "perm5b6c", "codename": "messages.create", "name": "Send Message" },
    { "id": "perm7b8c", "codename": "knowledge.search", "name": "Search Knowledge" }
  ],
  "member_count": 4,
  "created_at": "2026-05-22T12:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class RoleUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[list[UUID]] = None   # None = do not change; [] = remove all
```

### Models Involved

- `Role` (**proposed**) — updated
- `Permission` (**proposed**) — M2M replaced
- `RolePermission` (**proposed**) — M2M through records updated
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import Role, Permission
from ninja.errors import HttpError


def update_role(request, role_id, payload: RoleUpdateIn):
    company = request.auth.current_company

    try:
        role = Role.objects.prefetch_related("permissions").get(
            id=role_id, company=company
        )
    except Role.DoesNotExist:
        raise HttpError(404, "Role not found.")

    if role.is_system_role:
        raise HttpError(403, "System roles cannot be modified.")

    update_fields = ["updated_at"]

    if payload.name is not None:
        if payload.name.lower() in SYSTEM_ROLE_NAMES:
            raise HttpError(409, f"'{payload.name}' is a reserved system role name.")
        if Role.objects.filter(company=company, name=payload.name).exclude(id=role_id).exists():
            raise HttpError(409, f"A role named '{payload.name}' already exists.")
        role.name = payload.name
        update_fields.append("name")

    if payload.description is not None:
        role.description = payload.description
        update_fields.append("description")

    role.save(update_fields=update_fields)

    if payload.permission_ids is not None:
        permissions = Permission.objects.filter(
            id__in=payload.permission_ids,
            company=company,
        )
        role.permissions.set(permissions)

    return role
```

---

## 19.5 DELETE /api/v1/roles/{role_id}

### Detail

Soft-deletes a custom `Role`. System roles cannot be deleted. Before deleting, the API checks whether any `CompanyAccess` records are currently assigned this role — if so, it returns a 409 Conflict unless `force=True` is passed, which reassigns affected members to the `member` system role before proceeding.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate caller has `roles.delete` permission.
3. Fetch `Role` by `role_id` scoped to `company`.
4. Reject if `is_system_role=True`.
5. Check for active `CompanyAccess` records with this role assignment.
6. If members exist and `force=False`, return 409.
7. If `force=True`, reassign affected members to `"member"` system role.
8. Soft-delete the role.
9. Return 204 No Content.

### Request JSON

```json
// Query Parameter
// DELETE /api/v1/roles/role2b3c-e5f6-7890-abcd-ef1234567891?force=true
{
  "force": false   // optional: if true, reassign members to "member" before deleting
}
```

### Response JSON

```json
// 204 No Content
```

### Pydantic for Django Ninja

```python
# No request body — force is a query parameter.
# Return HTTP 204 using Django Ninja's response={204: None} pattern.
```

### Models Involved

- `Role` (**proposed**) — soft-deleted
- `CompanyAccess` — checked and optionally reassigned
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from nucleus.models import Role, CompanyAccess
from ninja.errors import HttpError


@transaction.atomic
def delete_role(request, role_id, force: bool = False):
    company = request.auth.current_company

    try:
        role = Role.objects.get(id=role_id, company=company, is_active=True)
    except Role.DoesNotExist:
        raise HttpError(404, "Role not found.")

    if role.is_system_role:
        raise HttpError(403, "System roles cannot be deleted.")

    # Check for active member assignments (assumes CompanyAccess.role_obj FK to Role)
    affected = CompanyAccess.objects.filter(
        company=company,
        role_obj=role,
        is_active=True,
    )

    if affected.exists() and not force:
        raise HttpError(
            409,
            f"This role is assigned to {affected.count()} member(s). "
            "Use force=true to reassign them to 'member' before deletion."
        )

    if force:
        affected.update(role="member", role_obj=None)

    role.soft_delete()
    return None
```

---

### Proposed RBAC Model Definitions

Add the following to `nucleus/models/governance.py` and create a new migration:

```python
class Permission(BaseModel):
    """
    Atomic capability that can be granted to a role.
    Seeded by system; custom permissions not supported in v1.
    """
    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="%(class)s_items"
    )
    codename = models.CharField(
        max_length=120,
        help_text="e.g. 'agents.run', 'messages.create', 'knowledge.search'",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    resource_type = models.CharField(
        max_length=80,
        db_index=True,
        help_text="e.g. 'agent', 'message', 'knowledge_base'",
    )
    action = models.CharField(
        max_length=50,
        help_text="e.g. 'create', 'read', 'update', 'delete', 'run'",
    )

    class Meta:
        db_table = "governance_permission"
        constraints = [
            models.UniqueConstraint(
                fields=("company", "codename"),
                name="uniq_permission_codename_per_company",
            )
        ]


class Role(BaseModel):
    """
    Named collection of permissions assignable to company members.
    """
    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="%(class)s_items"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    is_system_role = models.BooleanField(
        default=False,
        help_text="System roles (owner, admin, member, viewer) cannot be modified.",
    )
    permissions = models.ManyToManyField(
        Permission,
        through="RolePermission",
        related_name="roles",
        blank=True,
    )

    class Meta:
        db_table = "governance_role"
        constraints = [
            models.UniqueConstraint(
                fields=("company", "name"),
                name="uniq_role_name_per_company",
            )
        ]


class RolePermission(BaseModel):
    """Through table for Role ↔ Permission M2M."""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")
    company = models.ForeignKey("Company", on_delete=models.CASCADE, related_name="%(class)s_items")

    class Meta:
        db_table = "governance_role_permission"
        constraints = [
            models.UniqueConstraint(
                fields=("role", "permission"),
                name="uniq_role_permission",
            )
        ]
```

Also add `role_obj` FK to `CompanyAccess` to link members to their custom role:

```python
# Add to CompanyAccess model
role_obj = models.ForeignKey(
    "Role",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="company_access_assignments",
    help_text="Custom role assignment. Takes precedence over the 'role' char field when set.",
)
```

---

## Part C — Audit / Activity APIs

---

## 20.1 GET /api/v1/audit/events

### Detail

Returns a paginated list of `AuditEvent` records for the authenticated user's active company. Supports rich filtering by actor, action, target type/ID, IP address, and date range. Designed for the admin audit log view — compliance teams reviewing who did what and when. Restricted to users with `audit.read` permission (owner or admin).

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate caller has `audit.read` permission.
3. Query `AuditEvent` filtered by `company`.
4. Apply optional filters (`actor_id`, `action`, `target_type`, `target_id`, `from_date`, `to_date`).
5. `select_related` on `actor`.
6. Return paginated list ordered by `created_at DESC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/audit/events?action=agent.run&from_date=2026-05-01&page=1
{
  "actor_id": null,
  "action": "agent.run",
  "target_type": "agent",
  "target_id": null,
  "from_date": "2026-05-01",
  "to_date": null,
  "page": 1,
  "page_size": 50
}
```

### Response JSON

```json
{
  "count": 24,
  "next": "http://api/v1/audit/events?page=2",
  "previous": null,
  "results": [
    {
      "id": "ae1b2c3d-e5f6-7890-abcd-ef1234567890",
      "action": "agent.run",
      "target_type": "agent",
      "target_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "payload": {
        "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "input_summary": "Research quantum computing..."
      },
      "actor": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "noaman@example.com"
      },
      "ip_address": "192.168.1.42",
      "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
      "created_at": "2026-05-22T09:00:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, date


class AuditEventFilterSchema(Schema):
    actor_id: Optional[UUID] = None
    action: Optional[str] = None        # e.g. "agent.run", "message.delete"
    target_type: Optional[str] = None   # e.g. "agent", "message", "knowledge_file"
    target_id: Optional[UUID] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class ActorBriefOut(Schema):
    id: UUID
    username: str


class AuditEventListItemOut(Schema):
    id: UUID
    action: str
    target_type: str
    target_id: Optional[UUID]
    payload: dict[str, Any]
    actor: Optional[ActorBriefOut]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime


class AuditEventListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[AuditEventListItemOut]
```

### Models Involved

- `AuditEvent` — primary listing model
- `User` — FK `actor` (nested brief)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AuditEvent


def list_audit_events(request, filters: AuditEventFilterSchema):
    company = request.auth.current_company

    qs = AuditEvent.objects.filter(
        company=company,
    ).select_related("actor")

    if filters.actor_id:
        qs = qs.filter(actor_id=filters.actor_id)

    if filters.action:
        qs = qs.filter(action=filters.action)

    if filters.target_type:
        qs = qs.filter(target_type=filters.target_type)

    if filters.target_id:
        qs = qs.filter(target_id=filters.target_id)

    if filters.from_date:
        qs = qs.filter(created_at__date__gte=filters.from_date)

    if filters.to_date:
        qs = qs.filter(created_at__date__lte=filters.to_date)

    return qs.order_by("-created_at")
```

---

## 20.2 GET /api/v1/audit/events/{event_id}

### Detail

Retrieves the full detail of a single `AuditEvent` by its UUID. Returns all fields including the full `payload` JSON (which may contain before/after diffs for update actions, full request context, or structured error info). Restricted to `audit.read` permission.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate caller has `audit.read` permission.
3. Fetch `AuditEvent` by `event_id` scoped to `company`.
4. Return 404 if not found.
5. Return full detail with actor nested.

### Request JSON

```json
// No request body — event_id is a path parameter
// GET /api/v1/audit/events/ae1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
{
  "id": "ae1b2c3d-e5f6-7890-abcd-ef1234567890",
  "action": "agent.run",
  "target_type": "agent",
  "target_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "payload": {
    "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "agent_name": "Research Agent v2",
    "input_summary": "Research quantum computing advancements...",
    "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status_after": "pending"
  },
  "actor": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "noaman@example.com",
    "email": "noaman@example.com"
  },
  "ip_address": "192.168.1.42",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
  "created_at": "2026-05-22T09:00:00Z",
  "updated_at": "2026-05-22T09:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class ActorDetailOut(Schema):
    id: UUID
    username: str
    email: Optional[str]


class AuditEventDetailOut(Schema):
    id: UUID
    action: str
    target_type: str
    target_id: Optional[UUID]
    payload: dict[str, Any]
    actor: Optional[ActorDetailOut]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AuditEvent` — primary record
- `User` — FK `actor` (nested detail)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AuditEvent
from ninja.errors import HttpError


def get_audit_event(request, event_id):
    try:
        return AuditEvent.objects.select_related("actor").get(
            id=event_id,
            company=request.auth.current_company,
        )
    except AuditEvent.DoesNotExist:
        raise HttpError(404, "Audit event not found.")
```

---

## 20.3 GET /api/v1/activity/feed

### Detail

Returns a user-facing activity feed — a curated, paginated list of `AuditEvent` records relevant to the authenticated user. Unlike the admin audit log (which shows all company events), the activity feed shows only events where the user was the actor **or** where the action affected a resource the user has access to (e.g. a topic they participate in, an agent run they triggered). Designed for the "Recent Activity" panel in the UI sidebar.

### Flow

1. Authenticate request; resolve `current_company` and `current_user`.
2. Build a compound filter: events where `actor=current_user` OR `target_id` is in a resource set the user owns/participates in.
3. Resolve user's accessible resource IDs (topic participations, project memberships, agent runs triggered).
4. Query `AuditEvent` with the compound filter, scoped to `company`.
5. Optionally filter by `action_group` (messages, agents, knowledge, etc.).
6. Return paginated feed ordered by `created_at DESC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/activity/feed?action_group=agents&page=1&page_size=20
{
  "action_group": "agents",   // optional: "agents" | "messages" | "knowledge" | "members"
  "from_date": null,
  "to_date": null,
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 42,
  "next": "http://api/v1/activity/feed?page=2",
  "previous": null,
  "results": [
    {
      "id": "ae1b2c3d-e5f6-7890-abcd-ef1234567890",
      "action": "agent.run",
      "action_label": "Started an agent run",
      "target_type": "agent",
      "target_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "target_label": "Research Agent v2",
      "actor": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "noaman@example.com"
      },
      "is_own_action": true,
      "summary": "You started a run on Research Agent v2",
      "created_at": "2026-05-22T09:00:00Z"
    },
    {
      "id": "ae2b3c4d-e5f6-7890-abcd-ef1234567891",
      "action": "message.create",
      "action_label": "Sent a message",
      "target_type": "topic",
      "target_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "target_label": "Research Discussion",
      "actor": {
        "id": "u2b3c4d5-e5f6-7890-abcd-ef1234567891",
        "username": "alice@example.com"
      },
      "is_own_action": false,
      "summary": "alice@example.com sent a message in Research Discussion",
      "created_at": "2026-05-22T08:55:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime, date


class ActivityFeedFilterSchema(Schema):
    action_group: Optional[str] = None   # "agents" | "messages" | "knowledge" | "members"
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class ActivityFeedItemOut(Schema):
    id: UUID
    action: str
    action_label: str
    target_type: str
    target_id: Optional[UUID]
    target_label: Optional[str]
    actor: Optional[ActorBriefOut]
    is_own_action: bool
    summary: str
    created_at: datetime


class ActivityFeedOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[ActivityFeedItemOut]
```

### Models Involved

- `AuditEvent` — primary feed source
- `User` — FK `actor` (nested); used to determine `is_own_action`
- `TopicParticipant` — resolves topics user participates in
- `ProjectMember` — resolves projects user is member of
- `AgentRun` — resolves runs triggered by user (for `target_id` matching)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Q
from nucleus.models import (
    AuditEvent, TopicParticipant, ProjectMember, AgentRun
)

# Action group → action prefix mapping
ACTION_GROUP_MAP = {
    "agents":    ["agent."],
    "messages":  ["message."],
    "knowledge": ["knowledge.", "embedding."],
    "members":   ["member.", "invitation.", "role."],
}


def get_activity_feed(request, filters: ActivityFeedFilterSchema):
    company = request.auth.current_company
    user = request.auth

    # Resolve resource IDs accessible to this user
    topic_ids = TopicParticipant.objects.filter(
        user=user, company=company, is_active=True
    ).values_list("topic_id", flat=True)

    project_ids = ProjectMember.objects.filter(
        user=user, company=company, is_active=True
    ).values_list("project_id", flat=True)

    run_ids = AgentRun.objects.filter(
        triggered_by=user, company=company
    ).values_list("id", flat=True)

    # Compound filter: own actions OR actions on accessible resources
    feed_filter = Q(actor=user) | Q(
        target_type="topic", target_id__in=topic_ids
    ) | Q(
        target_type="project", target_id__in=project_ids
    ) | Q(
        target_type="agent_run", target_id__in=run_ids
    )

    qs = AuditEvent.objects.filter(
        company=company,
    ).filter(feed_filter).select_related("actor").order_by("-created_at")

    # Apply action_group filter
    if filters.action_group:
        prefixes = ACTION_GROUP_MAP.get(filters.action_group, [])
        if prefixes:
            action_q = Q()
            for prefix in prefixes:
                action_q |= Q(action__startswith=prefix)
            qs = qs.filter(action_q)

    if filters.from_date:
        qs = qs.filter(created_at__date__gte=filters.from_date)

    if filters.to_date:
        qs = qs.filter(created_at__date__lte=filters.to_date)

    # Enrich results
    results = []
    for event in qs:
        is_own = event.actor_id == user.id
        results.append({
            **event.__dict__,
            "is_own_action": is_own,
            "action_label": _action_label(event.action),
            "target_label": event.payload.get("target_name"),
            "summary": _build_summary(event, is_own),
        })

    return results


def _action_label(action: str) -> str:
    labels = {
        "agent.run": "Started an agent run",
        "agent.cancel": "Cancelled an agent run",
        "message.create": "Sent a message",
        "message.delete": "Deleted a message",
        "knowledge.upload": "Uploaded a file",
        "member.invite": "Invited a member",
        "role.assign": "Assigned a role",
    }
    return labels.get(action, action.replace(".", " ").title())


def _build_summary(event, is_own: bool) -> str:
    actor = "You" if is_own else (event.actor.username if event.actor else "Someone")
    label = _action_label(event.action).lower()
    target = event.payload.get("target_name", "")
    return f"{actor} {label}{' in ' + target if target else ''}"
```

---

## Summary: Model Reference by Group

### Embedding / Vector

| Model | Table | Status | Used In |
| --- | --- | --- | --- |
| `EmbeddingJob` | `intelligence_embedding_job` | **Exists** (migration 0002) | 18.1, 18.2, 18.3 |
| `VectorDocument` | `intelligence_vector_document` | **Exists** (migration 0002) | 18.4 |
| `KnowledgeFile` | `intelligence_knowledge_file` | **Exists** (migration 0001) | 18.1, 18.2, 18.3 |

### Permission / RBAC

| Model | Table | Status | Used In |
| --- | --- | --- | --- |
| `Permission` | `governance_permission` | **Proposed** | 19.1, 19.2, 19.3, 19.4, 19.5 |
| `Role` | `governance_role` | **Proposed** | 19.2, 19.3, 19.4, 19.5 |
| `RolePermission` | `governance_role_permission` | **Proposed** | 19.2, 19.3, 19.4, 19.5 |
| `CompanyAccess` | `governance_company_access` | **Exists** — needs `role_obj` FK | 19.5 |

### Audit / Activity

| Model | Table | Status | Used In |
| --- | --- | --- | --- |
| `AuditEvent` | `governance_audit_event` | **Exists** (migration 0002) | 20.1, 20.2, 20.3 |
| `TopicParticipant` | `workspace_topic_participant` | **Exists** (migration 0002) | 20.3 |
| `ProjectMember` | `workspace_project_member` | **Exists** (migration 0002) | 20.3 |
| `AgentRun` | `intelligence_agent_run` | **Exists** (migration 0002) | 20.3 |

---

## AuditEvent Writing Convention

Every state-changing API endpoint should write an `AuditEvent` after completing successfully. Use a consistent `action` naming convention: `{resource}.{verb}`.

```python
# Recommended action codenames
# Agents
"agent.create"        "agent.update"        "agent.delete"
"agent.run"           "agent.cancel"        "agent.test"

# Messages
"message.create"      "message.update"      "message.delete"
"message.react"       "message.retry"

# Knowledge
"knowledge_base.create"   "knowledge_base.delete"   "knowledge_base.reindex"
"knowledge_file.upload"   "knowledge_file.delete"   "knowledge_file.reprocess"

# Members & Access
"member.invite"       "member.activate"     "member.deactivate"
"role.create"         "role.update"         "role.delete"   "role.assign"

# Embedding
"embedding.job_retry"   "embedding.vector_delete"
```

Write pattern (add to every relevant API view after success):

```python
AuditEvent.objects.create(
    company=company,
    actor=request.auth,
    action="agent.run",
    target_type="agent",
    target_id=agent.id,
    payload={
        "agent_name": agent.name,
        "run_id": str(run.id),
        "status_after": "pending",
    },
    ip_address=request.META.get("REMOTE_ADDR"),
    user_agent=request.META.get("HTTP_USER_AGENT"),
)
```
