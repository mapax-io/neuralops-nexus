# 15. Knowledge Base APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/knowledge-bases |
| POST | /api/v1/knowledge-bases |
| GET | /api/v1/knowledge-bases/{kb_id} |
| PATCH | /api/v1/knowledge-bases/{kb_id} |
| DELETE | /api/v1/knowledge-bases/{kb_id} |
| POST | /api/v1/knowledge-bases/{kb_id}/attach |
| POST | /api/v1/knowledge-bases/{kb_id}/detach |
| POST | /api/v1/knowledge-bases/{kb_id}/reindex |
| GET | /api/v1/knowledge-bases/{kb_id}/status |
| GET | /api/v1/knowledge-bases/{kb_id}/stats |
| GET | /api/v1/knowledge-bases/{kb_id}/files |
| POST | /api/v1/knowledge-bases/{kb_id}/files |
| GET | /api/v1/knowledge-files/{file_id} |
| DELETE | /api/v1/knowledge-files/{file_id} |
| POST | /api/v1/knowledge-files/{file_id}/reprocess |
| GET | /api/v1/knowledge-files/{file_id}/chunks |
| GET | /api/v1/knowledge-files/{file_id}/status |
| GET | /api/v1/knowledge-files/{file_id}/embeddings |

---

## Background

A **KnowledgeBase** is a named collection of documents scoped to a company. It can be attached to one or more **Projects** or **ChatTopics** so AI agents and personas can retrieve relevant context during inference. Files ingested into a KnowledgeBase are chunked, embedded, and stored in a vector database (ChromaDB by default). The pipeline is:

```
File Upload → KnowledgeFile → EmbeddingJob (async) → KnowledgeChunk + VectorDocument → Searchable
```

**Key models:**

| Model | Table | Purpose |
| --- | --- | --- |
| `KnowledgeBase` | `intelligence_knowledge_base` | Named container; M2M to projects/topics |
| `KnowledgeFile` | `intelligence_knowledge_file` | A single ingested file inside a KB |
| `KnowledgeChunk` | `intelligence_knowledge_chunk` | Text chunks split from a file |
| `EmbeddingJob` | `intelligence_embedding_job` | Async job tracking chunking + embedding |
| `VectorDocument` | `intelligence_vector_document` | Record of each vector stored in the vector DB |

---

## 15.1 GET /api/v1/knowledge-bases

### Detail

Returns a paginated list of all Knowledge Bases belonging to the authenticated user's active company. Supports optional filtering by name search and active status. Returns summary counts of files per KB for display in the UI listing.

### Flow

1. Authenticate request; resolve `current_company`.
2. Query `KnowledgeBase` filtered by `company` and `is_active=True`.
3. Apply optional `search` filter on `name`.
4. Annotate with `file_count` using a subquery or `Count`.
5. Return paginated list ordered by `name ASC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/knowledge-bases?search=product&page=1&page_size=20
{
  "search": "product",   // optional: name search
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
      "name": "Product Documentation",
      "description": "All product manuals, release notes, and FAQs",
      "is_active": true,
      "file_count": 14,
      "projects": [
        { "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Product Team" }
      ],
      "chat_topics": [],
      "created_at": "2026-04-10T08:00:00Z",
      "updated_at": "2026-05-20T14:00:00Z"
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


class ProjectBriefOut(Schema):
    id: UUID
    name: str


class ChatTopicBriefOut(Schema):
    id: UUID
    title: str


class KBListItemOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    file_count: int
    projects: list[ProjectBriefOut]
    chat_topics: list[ChatTopicBriefOut]
    created_at: datetime
    updated_at: datetime


class KBListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[KBListItemOut]


class KBFilterSchema(Schema):
    search: Optional[str] = None
```

### Models Involved

- `KnowledgeBase` — primary listing model
- `KnowledgeFile` — annotated count
- `Project` — M2M `projects` (prefetched)
- `ChatTopic` — M2M `chat_topics` (prefetched)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count
from nucleus.models import KnowledgeBase


def list_knowledge_bases(request, filters):
    qs = KnowledgeBase.objects.filter(
        company=request.auth.current_company,
        is_active=True,
    ).prefetch_related(
        "projects", "chat_topics"
    ).annotate(
        file_count=Count("files", filter=models.Q(files__is_active=True))
    )

    if filters.search:
        qs = qs.filter(name__icontains=filters.search)

    return qs.order_by("name")
```

---

## 15.2 POST /api/v1/knowledge-bases

### Detail

Creates a new Knowledge Base in the authenticated user's active company. Name must be unique within the company (`uniq_knowledge_base_name_per_company`). Optionally accepts initial project and topic attachments at creation time. No files are ingested at this stage.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `name` is unique within the company.
3. Create the `KnowledgeBase` record.
4. If `project_ids` provided, validate each project belongs to the company and set the M2M.
5. If `topic_ids` provided, validate each topic belongs to the company and set the M2M.
6. Return the created KB detail.

### Request JSON

```json
{
  "name": "Product Documentation",
  "description": "All product manuals, release notes, and FAQs",
  "project_ids": ["p1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "topic_ids": []
}
```

### Response JSON

```json
{
  "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Product Documentation",
  "description": "All product manuals, release notes, and FAQs",
  "is_active": true,
  "file_count": 0,
  "projects": [
    { "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Product Team" }
  ],
  "chat_topics": [],
  "created_at": "2026-05-22T08:00:00Z",
  "updated_at": "2026-05-22T08:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class KBCreateIn(Schema):
    name: str
    description: Optional[str] = None
    project_ids: list[UUID] = []
    topic_ids: list[UUID] = []


class KBDetailOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    file_count: int
    projects: list[ProjectBriefOut]
    chat_topics: list[ChatTopicBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `KnowledgeBase` — created record
- `Project` — M2M validated and set
- `ChatTopic` — M2M validated and set
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeBase, Project, ChatTopic
from ninja.errors import HttpError


def create_knowledge_base(request, payload: KBCreateIn):
    company = request.auth.current_company

    if KnowledgeBase.objects.filter(company=company, name=payload.name, is_active=True).exists():
        raise HttpError(409, f"A knowledge base named '{payload.name}' already exists.")

    kb = KnowledgeBase.objects.create(
        company=company,
        name=payload.name,
        description=payload.description,
    )

    if payload.project_ids:
        projects = Project.objects.filter(id__in=payload.project_ids, company=company, is_active=True)
        kb.projects.set(projects)

    if payload.topic_ids:
        topics = ChatTopic.objects.filter(id__in=payload.topic_ids, company=company, is_active=True)
        kb.chat_topics.set(topics)

    return kb
```

---

## 15.3 GET /api/v1/knowledge-bases/{kb_id}

### Detail

Retrieves the full detail of a single Knowledge Base. Returns all metadata, attached projects and topics, file count, and current indexing state summary. Scoped to the authenticated user's active company.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` by `kb_id` scoped to `company` and `is_active=True`.
3. Prefetch related `projects`, `chat_topics`, annotate `file_count`.
4. Return 404 if not found or soft-deleted.

### Request JSON

```json
// No request body — kb_id is a path parameter
// GET /api/v1/knowledge-bases/kb1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
{
  "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Product Documentation",
  "description": "All product manuals, release notes, and FAQs",
  "is_active": true,
  "file_count": 14,
  "projects": [
    { "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Product Team" }
  ],
  "chat_topics": [
    { "id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Q3 Product Review" }
  ],
  "created_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-05-20T14:00:00Z"
}
```

### Pydantic for Django Ninja

```python
# Reuses KBDetailOut from 15.2
```

### Models Involved

- `KnowledgeBase` — primary record
- `KnowledgeFile` — annotated count
- `Project` — M2M prefetched
- `ChatTopic` — M2M prefetched
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count, Q
from nucleus.models import KnowledgeBase
from ninja.errors import HttpError


def get_knowledge_base(request, kb_id):
    try:
        return KnowledgeBase.objects.prefetch_related(
            "projects", "chat_topics"
        ).annotate(
            file_count=Count("files", filter=Q(files__is_active=True))
        ).get(
            id=kb_id,
            company=request.auth.current_company,
            is_active=True,
        )
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")
```

---

## 15.4 PATCH /api/v1/knowledge-bases/{kb_id}

### Detail

Partially updates a Knowledge Base's metadata. Supports updating `name`, `description`, and `is_active`. Does not manage project/topic attachments — use the dedicated `/attach` and `/detach` endpoints for that. Name must remain unique within the company if changed.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` by `kb_id` scoped to `company`.
3. If `name` is changing, validate uniqueness within company.
4. Apply provided fields and save.
5. Return updated KB detail.

### Request JSON

```json
{
  "name": "Product Docs — v2",
  "description": "Updated product documentation including v2 release notes"
}
```

### Response JSON

```json
{
  "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Product Docs — v2",
  "description": "Updated product documentation including v2 release notes",
  "is_active": true,
  "file_count": 14,
  "projects": [
    { "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Product Team" }
  ],
  "chat_topics": [],
  "created_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional


class KBUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
```

### Models Involved

- `KnowledgeBase` — updated record
- `Company` — tenant scope (uniqueness check)

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeBase
from ninja.errors import HttpError


def update_knowledge_base(request, kb_id, payload: KBUpdateIn):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    if payload.name and payload.name != kb.name:
        if KnowledgeBase.objects.filter(company=company, name=payload.name, is_active=True).exists():
            raise HttpError(409, f"A knowledge base named '{payload.name}' already exists.")
        kb.name = payload.name

    update_fields = ["updated_at"]

    if payload.description is not None:
        kb.description = payload.description
        update_fields.append("description")

    if payload.name is not None:
        kb.name = payload.name
        update_fields.append("name")

    if payload.is_active is not None:
        kb.is_active = payload.is_active
        update_fields.append("is_active")

    kb.save(update_fields=update_fields)
    return kb
```

---

## 15.5 DELETE /api/v1/knowledge-bases/{kb_id}

### Detail

Soft-deletes a Knowledge Base and all its associated `KnowledgeFile` records. Detaches the KB from all linked projects and topics. Does not delete vector embeddings from ChromaDB immediately — that is handled by a background cleanup job. Returns 204 No Content.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` by `kb_id` scoped to `company`.
3. Clear all M2M attachments (`projects`, `chat_topics`).
4. Soft-delete all active `KnowledgeFile` records belonging to this KB.
5. Soft-delete the `KnowledgeBase` record.
6. Optionally dispatch a background job to purge vectors from ChromaDB.
7. Return 204 No Content.

### Request JSON

```json
// No request body — kb_id is a path parameter
// DELETE /api/v1/knowledge-bases/kb1b2c3d-e5f6-7890-abcd-ef1234567890
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

- `KnowledgeBase` — soft-deleted
- `KnowledgeFile` — bulk soft-deleted
- `Project` — M2M cleared
- `ChatTopic` — M2M cleared
- `EmbeddingJob` — background cleanup dispatched
- `VectorDocument` — async purge via background worker
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils import timezone
from nucleus.models import KnowledgeBase, KnowledgeFile
from ninja.errors import HttpError


@transaction.atomic
def delete_knowledge_base(request, kb_id):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    # Clear M2M relationships
    kb.projects.clear()
    kb.chat_topics.clear()

    # Bulk soft-delete all active files
    KnowledgeFile.objects.filter(
        knowledge_base=kb,
        is_active=True,
    ).update(
        is_active=False,
        deleted_at=timezone.now(),
    )

    # Soft-delete the KB itself
    kb.soft_delete()

    # Dispatch background vector cleanup
    purge_kb_vectors.delay(str(kb.id))

    return None
```

---

## 15.6 POST /api/v1/knowledge-bases/{kb_id}/attach

### Detail

Attaches a Knowledge Base to one or more Projects or ChatTopics so that AI agents and personas can query it during inference in those scopes. Multiple targets can be attached in a single request. Already-attached targets are silently ignored (idempotent).

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` by `kb_id` scoped to `company`.
3. Validate all provided `project_ids` and `topic_ids` belong to the same company.
4. Add them to the M2M sets (idempotently).
5. Return updated KB detail.

### Request JSON

```json
{
  "project_ids": ["p1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "topic_ids": ["t1b2c3d4-e5f6-7890-abcd-ef1234567890"]
}
```

### Response JSON

```json
{
  "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Product Docs — v2",
  "projects": [
    { "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890", "name": "Product Team" }
  ],
  "chat_topics": [
    { "id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Q3 Product Review" }
  ],
  "attached_projects_count": 1,
  "attached_topics_count": 1
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class KBAttachIn(Schema):
    project_ids: list[UUID] = []
    topic_ids: list[UUID] = []


class KBAttachOut(Schema):
    id: UUID
    name: str
    projects: list[ProjectBriefOut]
    chat_topics: list[ChatTopicBriefOut]
    attached_projects_count: int
    attached_topics_count: int
```

### Models Involved

- `KnowledgeBase` — M2M updated
- `Project` — validated and added to M2M
- `ChatTopic` — validated and added to M2M
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeBase, Project, ChatTopic
from ninja.errors import HttpError


def attach_knowledge_base(request, kb_id, payload: KBAttachIn):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.prefetch_related(
            "projects", "chat_topics"
        ).get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    if payload.project_ids:
        projects = Project.objects.filter(
            id__in=payload.project_ids, company=company, is_active=True
        )
        kb.projects.add(*projects)

    if payload.topic_ids:
        topics = ChatTopic.objects.filter(
            id__in=payload.topic_ids, company=company, is_active=True
        )
        kb.chat_topics.add(*topics)

    kb.refresh_from_db()
    return {
        "id": kb.id,
        "name": kb.name,
        "projects": list(kb.projects.all()),
        "chat_topics": list(kb.chat_topics.all()),
        "attached_projects_count": kb.projects.count(),
        "attached_topics_count": kb.chat_topics.count(),
    }
```

---

## 15.7 POST /api/v1/knowledge-bases/{kb_id}/detach

### Detail

Detaches a Knowledge Base from one or more Projects or ChatTopics. The KB itself and its files are not deleted — only the association is removed. Targets not currently attached are silently ignored (idempotent).

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` by `kb_id` scoped to `company`.
3. Remove provided `project_ids` and `topic_ids` from the M2M sets.
4. Return updated KB attachment state.

### Request JSON

```json
{
  "project_ids": ["p1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "topic_ids": []
}
```

### Response JSON

```json
{
  "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Product Docs — v2",
  "projects": [],
  "chat_topics": [
    { "id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Q3 Product Review" }
  ],
  "attached_projects_count": 0,
  "attached_topics_count": 1
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID


class KBDetachIn(Schema):
    project_ids: list[UUID] = []
    topic_ids: list[UUID] = []


# Reuses KBAttachOut for response
```

### Models Involved

- `KnowledgeBase` — M2M updated
- `Project` — removed from M2M
- `ChatTopic` — removed from M2M
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeBase, Project, ChatTopic
from ninja.errors import HttpError


def detach_knowledge_base(request, kb_id, payload: KBDetachIn):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    if payload.project_ids:
        kb.projects.remove(*Project.objects.filter(id__in=payload.project_ids))

    if payload.topic_ids:
        kb.chat_topics.remove(*ChatTopic.objects.filter(id__in=payload.topic_ids))

    kb.refresh_from_db()
    return {
        "id": kb.id,
        "name": kb.name,
        "projects": list(kb.projects.all()),
        "chat_topics": list(kb.chat_topics.all()),
        "attached_projects_count": kb.projects.count(),
        "attached_topics_count": kb.chat_topics.count(),
    }
```

---

## 15.8 POST /api/v1/knowledge-bases/{kb_id}/reindex

### Detail

Triggers a full re-embedding and re-indexing of all files in the Knowledge Base. Useful when the embedding model changes, a corruption is detected, or after bulk file updates. Creates a new `EmbeddingJob` for each active file in the KB with `target_type=knowledge_file`. Existing vector documents for the KB may be purged and rebuilt.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` scoped to `company`.
3. Fetch all active `KnowledgeFile` records for this KB.
4. For each file, set `embedding_status = "pending"` and create an `EmbeddingJob`.
5. Dispatch async workers to process each job.
6. Return summary of jobs enqueued.

### Request JSON

```json
// No request body required
// POST /api/v1/knowledge-bases/{kb_id}/reindex
{
  "force": true   // optional: force reindex even for already-completed files
}
```

### Response JSON

```json
{
  "kb_id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "kb_name": "Product Docs — v2",
  "jobs_enqueued": 14,
  "message": "Reindex started. 14 embedding jobs have been queued.",
  "started_at": "2026-05-22T10:30:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class KBReindexIn(Schema):
    force: bool = False


class KBReindexOut(Schema):
    kb_id: UUID
    kb_name: str
    jobs_enqueued: int
    message: str
    started_at: datetime
```

### Models Involved

- `KnowledgeBase` — source of file list
- `KnowledgeFile` — `embedding_status` reset to `pending`
- `EmbeddingJob` — one record created per file
- `VectorDocument` — optionally purged before re-embedding
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.utils import timezone
from nucleus.models import KnowledgeBase, KnowledgeFile, EmbeddingJob
from ninja.errors import HttpError


def reindex_knowledge_base(request, kb_id, payload: KBReindexIn):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    file_qs = KnowledgeFile.objects.filter(
        knowledge_base=kb,
        is_active=True,
    )

    if not payload.force:
        file_qs = file_qs.exclude(embedding_status="completed")

    jobs = []
    for kf in file_qs:
        kf.embedding_status = "pending"
        kf.save(update_fields=["embedding_status", "updated_at"])

        job = EmbeddingJob(
            company=company,
            target_type="knowledge_file",
            target_id=kf.id,
            status="pending",
        )
        jobs.append(job)

    EmbeddingJob.objects.bulk_create(jobs)

    # Dispatch async workers
    for job in EmbeddingJob.objects.filter(
        company=company,
        target_type="knowledge_file",
        status="pending",
    ).values_list("id", flat=True):
        process_embedding_job.delay(str(job))

    return {
        "kb_id": kb.id,
        "kb_name": kb.name,
        "jobs_enqueued": len(jobs),
        "message": f"Reindex started. {len(jobs)} embedding jobs have been queued.",
        "started_at": timezone.now(),
    }
```

---

## 15.9 GET /api/v1/knowledge-bases/{kb_id}/status

### Detail

Returns the current indexing status of the Knowledge Base — a summary of how many files are in each `embedding_status` state and whether any `EmbeddingJob` records are actively running. Used by the UI to show a progress indicator during ingestion or reindexing.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` scoped to `company`.
3. Aggregate `KnowledgeFile` counts grouped by `embedding_status`.
4. Check for any active `EmbeddingJob` records for this KB's files.
5. Return status summary.

### Request JSON

```json
// No request body — kb_id is a path parameter
// GET /api/v1/knowledge-bases/{kb_id}/status
```

### Response JSON

```json
{
  "kb_id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "kb_name": "Product Docs — v2",
  "overall_status": "indexing",
  "file_counts": {
    "pending": 2,
    "processing": 1,
    "completed": 11,
    "failed": 0,
    "total": 14
  },
  "active_jobs": 1,
  "last_indexed_at": "2026-05-22T10:35:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class KBFileCountsOut(Schema):
    pending: int
    processing: int
    completed: int
    failed: int
    total: int


class KBStatusOut(Schema):
    kb_id: UUID
    kb_name: str
    overall_status: str   # "idle" | "indexing" | "completed" | "failed" | "partial"
    file_counts: KBFileCountsOut
    active_jobs: int
    last_indexed_at: Optional[datetime]
```

### Models Involved

- `KnowledgeBase` — primary record
- `KnowledgeFile` — aggregated by `embedding_status`
- `EmbeddingJob` — checked for active jobs
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count, Q
from nucleus.models import KnowledgeBase, KnowledgeFile, EmbeddingJob
from ninja.errors import HttpError


def get_knowledge_base_status(request, kb_id):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    file_ids = KnowledgeFile.objects.filter(
        knowledge_base=kb, is_active=True
    ).values_list("id", flat=True)

    counts = KnowledgeFile.objects.filter(
        knowledge_base=kb, is_active=True
    ).aggregate(
        pending=Count("id", filter=Q(embedding_status="pending")),
        processing=Count("id", filter=Q(embedding_status="processing")),
        completed=Count("id", filter=Q(embedding_status="completed")),
        failed=Count("id", filter=Q(embedding_status="failed")),
        total=Count("id"),
    )

    active_jobs = EmbeddingJob.objects.filter(
        company=company,
        target_type="knowledge_file",
        target_id__in=file_ids,
        status__in=["pending", "running"],
    ).count()

    # Determine overall status
    if active_jobs > 0 or counts["processing"] > 0:
        overall = "indexing"
    elif counts["failed"] > 0 and counts["completed"] == 0:
        overall = "failed"
    elif counts["failed"] > 0:
        overall = "partial"
    elif counts["pending"] == 0 and counts["total"] > 0:
        overall = "completed"
    else:
        overall = "idle"

    # Last indexed = most recent completed file
    last_indexed = KnowledgeFile.objects.filter(
        knowledge_base=kb,
        embedding_status="completed",
    ).order_by("-updated_at").values_list("updated_at", flat=True).first()

    return {
        "kb_id": kb.id,
        "kb_name": kb.name,
        "overall_status": overall,
        "file_counts": counts,
        "active_jobs": active_jobs,
        "last_indexed_at": last_indexed,
    }
```

---

## 15.10 GET /api/v1/knowledge-bases/{kb_id}/stats

### Detail

Returns aggregate statistics for a Knowledge Base — total files, total chunks, total tokens, and total vector documents stored. Designed for display in the KB detail view and analytics dashboards.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeBase` scoped to `company`.
3. Aggregate across `KnowledgeFile`, `KnowledgeChunk`, and `VectorDocument`.
4. Return stats object.

### Request JSON

```json
// No request body — kb_id is a path parameter
// GET /api/v1/knowledge-bases/{kb_id}/stats
```

### Response JSON

```json
{
  "kb_id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "kb_name": "Product Docs — v2",
  "total_files": 14,
  "total_size_bytes": 48234512,
  "total_chunks": 832,
  "total_tokens": 1204500,
  "total_vector_documents": 832,
  "vector_db": "chroma",
  "chroma_collection": "kb_kb1b2c3d_e5f6_7890"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class KBStatsOut(Schema):
    kb_id: UUID
    kb_name: str
    total_files: int
    total_size_bytes: int
    total_chunks: int
    total_tokens: int
    total_vector_documents: int
    vector_db: str
    chroma_collection: Optional[str]
```

### Models Involved

- `KnowledgeBase` — primary record
- `KnowledgeFile` — aggregated for file count + size
- `KnowledgeChunk` — aggregated for chunk count + token count
- `VectorDocument` — aggregated for vector count
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count, Sum, Q
from nucleus.models import KnowledgeBase, KnowledgeFile, KnowledgeChunk, VectorDocument
from ninja.errors import HttpError


def get_knowledge_base_stats(request, kb_id):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    file_stats = KnowledgeFile.objects.filter(
        knowledge_base=kb, is_active=True
    ).aggregate(
        total_files=Count("id"),
        total_size_bytes=Sum("file_size"),
    )

    file_ids = KnowledgeFile.objects.filter(
        knowledge_base=kb, is_active=True
    ).values_list("id", flat=True)

    chunk_stats = KnowledgeChunk.objects.filter(
        knowledge_file__in=file_ids
    ).aggregate(
        total_chunks=Count("id"),
        total_tokens=Sum("token_count"),
    )

    vector_count = VectorDocument.objects.filter(
        company=company,
        source_type="knowledge_file",
        source_id__in=file_ids,
    ).count()

    # Chroma collection name from first file (all files in KB share collection prefix)
    sample_file = KnowledgeFile.objects.filter(
        knowledge_base=kb, is_active=True
    ).values("chroma_collection").first()

    return {
        "kb_id": kb.id,
        "kb_name": kb.name,
        "total_files": file_stats["total_files"] or 0,
        "total_size_bytes": file_stats["total_size_bytes"] or 0,
        "total_chunks": chunk_stats["total_chunks"] or 0,
        "total_tokens": chunk_stats["total_tokens"] or 0,
        "total_vector_documents": vector_count,
        "vector_db": "chroma",
        "chroma_collection": sample_file["chroma_collection"] if sample_file else None,
    }
```

---

## 15.11 GET /api/v1/knowledge-bases/{kb_id}/files

### Detail

Returns a paginated list of all `KnowledgeFile` records belonging to the given Knowledge Base. Supports optional filtering by `embedding_status` and MIME type. Returns metadata for each file including processing status, size, and chunk count.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `kb_id` belongs to company.
3. Query `KnowledgeFile` filtered by `knowledge_base` and `is_active=True`.
4. Apply optional filters (`embedding_status`, `mime_type`).
5. Annotate with `chunk_count` per file.
6. Return paginated list ordered by `created_at DESC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/knowledge-bases/{kb_id}/files?embedding_status=completed&page=1
{
  "embedding_status": "completed",   // optional: "pending" | "processing" | "completed" | "failed"
  "mime_type": "application/pdf",    // optional
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 11,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
      "original_filename": "product_manual_v2.pdf",
      "mime_type": "application/pdf",
      "file_size": 2048512,
      "embedding_status": "completed",
      "chunk_count": 64,
      "chroma_collection": "kb_kb1b2c3d",
      "created_at": "2026-05-01T09:00:00Z",
      "updated_at": "2026-05-01T09:05:30Z"
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


class KnowledgeFileListItemOut(Schema):
    id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    embedding_status: str
    chunk_count: int
    chroma_collection: Optional[str]
    created_at: datetime
    updated_at: datetime


class KnowledgeFileListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[KnowledgeFileListItemOut]


class KnowledgeFileFilterSchema(Schema):
    embedding_status: Optional[str] = None
    mime_type: Optional[str] = None
```

### Models Involved

- `KnowledgeFile` — primary listing model
- `KnowledgeChunk` — annotated count
- `KnowledgeBase` — parent validation
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db.models import Count
from nucleus.models import KnowledgeBase, KnowledgeFile
from ninja.errors import HttpError


def list_knowledge_files(request, kb_id, filters):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    qs = KnowledgeFile.objects.filter(
        knowledge_base=kb,
        is_active=True,
    ).annotate(
        chunk_count=Count("chunks")
    )

    if filters.embedding_status:
        qs = qs.filter(embedding_status=filters.embedding_status)

    if filters.mime_type:
        qs = qs.filter(mime_type=filters.mime_type)

    return qs.order_by("-created_at")
```

---

## 15.12 POST /api/v1/knowledge-bases/{kb_id}/files

### Detail

Uploads a new file into a Knowledge Base and immediately enqueues it for chunking and embedding. Accepts `multipart/form-data` with the file binary. Creates a `KnowledgeFile` record with `embedding_status=pending` and dispatches an `EmbeddingJob` to the background worker. The file is stored in Django's configured file storage backend (e.g. S3, local).

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `kb_id` belongs to company.
3. Receive `multipart/form-data` with file binary.
4. Save file to storage backend; create `KnowledgeFile` record with `embedding_status=pending`.
5. Create an `EmbeddingJob` record for this file.
6. Dispatch async embedding worker.
7. Return the created `KnowledgeFile` detail.

### Request JSON

```json
// Content-Type: multipart/form-data
{
  "file": "<binary file data>",
  "original_filename": "product_manual_v2.pdf"   // optional override; defaults to actual filename
}
```

### Response JSON

```json
{
  "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "original_filename": "product_manual_v2.pdf",
  "mime_type": "application/pdf",
  "file_size": 2048512,
  "embedding_status": "pending",
  "chunk_count": 0,
  "chroma_collection": null,
  "knowledge_base_id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-05-22T11:00:00Z",
  "updated_at": "2026-05-22T11:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema, File
from ninja.files import UploadedFile
from typing import Optional
from uuid import UUID
from datetime import datetime


class KnowledgeFileUploadOut(Schema):
    id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    embedding_status: str
    chunk_count: int
    chroma_collection: Optional[str]
    knowledge_base_id: UUID
    created_at: datetime
    updated_at: datetime

# In the router:
# @router.post("/{kb_id}/files", response=KnowledgeFileUploadOut)
# def upload_file(request, kb_id: UUID, file: UploadedFile = File(...)):
```

### Models Involved

- `KnowledgeFile` — created record
- `KnowledgeBase` — parent validated
- `EmbeddingJob` — created to track async processing
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeBase, KnowledgeFile, EmbeddingJob
from ninja.errors import HttpError


def upload_knowledge_file(request, kb_id, file):
    company = request.auth.current_company

    try:
        kb = KnowledgeBase.objects.get(id=kb_id, company=company, is_active=True)
    except KnowledgeBase.DoesNotExist:
        raise HttpError(404, "Knowledge base not found.")

    kf = KnowledgeFile.objects.create(
        knowledge_base=kb,
        file=file,
        original_filename=file.name,
        mime_type=file.content_type or "application/octet-stream",
        file_size=file.size,
        embedding_status="pending",
    )

    job = EmbeddingJob.objects.create(
        company=company,
        target_type="knowledge_file",
        target_id=kf.id,
        status="pending",
    )

    # Dispatch async worker
    process_embedding_job.delay(str(job.id))

    return kf
```

---

## 15.13 GET /api/v1/knowledge-files/{file_id}

### Detail

Retrieves the full detail of a single `KnowledgeFile` record. Includes metadata, embedding status, chunk count, and a reference to the parent Knowledge Base. The file must belong to the authenticated user's active company (validated via the parent KB's company FK).

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` by `file_id`, joining to `knowledge_base__company`.
3. Validate `knowledge_base.company == current_company`.
4. Return 404 if not found or soft-deleted.
5. Return file detail with chunk count annotation.

### Request JSON

```json
// No request body — file_id is a path parameter
// GET /api/v1/knowledge-files/kf1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
{
  "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "original_filename": "product_manual_v2.pdf",
  "mime_type": "application/pdf",
  "file_size": 2048512,
  "embedding_status": "completed",
  "chunk_count": 64,
  "chroma_collection": "kb_kb1b2c3d",
  "knowledge_base": {
    "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
    "name": "Product Docs — v2"
  },
  "created_at": "2026-05-01T09:00:00Z",
  "updated_at": "2026-05-01T09:05:30Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class KBBriefOut(Schema):
    id: UUID
    name: str


class KnowledgeFileDetailOut(Schema):
    id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    embedding_status: str
    chunk_count: int
    chroma_collection: Optional[str]
    knowledge_base: KBBriefOut
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `KnowledgeFile` — primary record
- `KnowledgeBase` — parent nested brief + company scope validation
- `KnowledgeChunk` — annotated count

### Django ORM Query (Proposed)

```python
from django.db.models import Count
from nucleus.models import KnowledgeFile
from ninja.errors import HttpError


def get_knowledge_file(request, file_id):
    try:
        return KnowledgeFile.objects.select_related(
            "knowledge_base"
        ).annotate(
            chunk_count=Count("chunks")
        ).get(
            id=file_id,
            is_active=True,
            knowledge_base__company=request.auth.current_company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")
```

---

## 15.14 DELETE /api/v1/knowledge-files/{file_id}

### Detail

Soft-deletes a single `KnowledgeFile` and all its associated `KnowledgeChunk` records. Also deletes the corresponding `VectorDocument` records from ChromaDB asynchronously. The file's physical storage object is not immediately removed — a background cleanup job handles that. Returns 204 No Content.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` scoped via `knowledge_base__company`.
3. Bulk soft-delete all `KnowledgeChunk` records for this file.
4. Soft-delete the `KnowledgeFile` record.
5. Dispatch background job to delete vectors from ChromaDB and physical file from storage.
6. Return 204 No Content.

### Request JSON

```json
// No request body — file_id is a path parameter
// DELETE /api/v1/knowledge-files/kf1b2c3d-e5f6-7890-abcd-ef1234567890
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

- `KnowledgeFile` — soft-deleted
- `KnowledgeChunk` — bulk soft-deleted
- `VectorDocument` — async purge
- `EmbeddingJob` — pending jobs cancelled
- `KnowledgeBase` — company scope validation

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils import timezone
from nucleus.models import KnowledgeFile, KnowledgeChunk, EmbeddingJob
from ninja.errors import HttpError


@transaction.atomic
def delete_knowledge_file(request, file_id):
    company = request.auth.current_company

    try:
        kf = KnowledgeFile.objects.select_related("knowledge_base").get(
            id=file_id,
            is_active=True,
            knowledge_base__company=company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")

    # Cancel any pending/running embedding jobs for this file
    EmbeddingJob.objects.filter(
        company=company,
        target_type="knowledge_file",
        target_id=kf.id,
        status__in=["pending", "running"],
    ).update(status="failed", error="File deleted by user.")

    # Bulk soft-delete chunks
    KnowledgeChunk.objects.filter(knowledge_file=kf).update(
        is_active=False,
        deleted_at=timezone.now(),
    )

    # Soft-delete the file itself
    kf.soft_delete()

    # Dispatch async cleanup (vector DB + physical storage)
    purge_file_vectors.delay(str(kf.id))

    return None
```

---

## 15.15 POST /api/v1/knowledge-files/{file_id}/reprocess

### Detail

Re-triggers the chunking and embedding pipeline for a single file. Useful after a failed embedding job or when chunk parameters change (e.g. chunk size, overlap). Resets `embedding_status` to `pending`, deletes existing chunks and vector documents, and enqueues a fresh `EmbeddingJob`.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` scoped via `knowledge_base__company`.
3. Delete existing `KnowledgeChunk` records for this file.
4. Delete existing `VectorDocument` records for this file (async or sync).
5. Reset `embedding_status = "pending"`.
6. Create a new `EmbeddingJob` and dispatch the worker.
7. Return the updated `KnowledgeFile` detail.

### Request JSON

```json
// No required body — optionally override processing parameters
{
  "chunk_size": 512,       // optional: token count per chunk (default from settings)
  "chunk_overlap": 64      // optional: token overlap between chunks
}
```

### Response JSON

```json
{
  "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "original_filename": "product_manual_v2.pdf",
  "embedding_status": "pending",
  "chunk_count": 0,
  "job_id": "ej1b2c3d-e5f6-7890-abcd-ef1234567890",
  "message": "File queued for reprocessing.",
  "queued_at": "2026-05-22T12:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class KnowledgeFileReprocessIn(Schema):
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


class KnowledgeFileReprocessOut(Schema):
    id: UUID
    original_filename: str
    embedding_status: str
    chunk_count: int
    job_id: UUID
    message: str
    queued_at: datetime
```

### Models Involved

- `KnowledgeFile` — `embedding_status` reset
- `KnowledgeChunk` — deleted (hard or soft)
- `EmbeddingJob` — new job created
- `VectorDocument` — async purge of old vectors
- `KnowledgeBase` — company scope validation

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils import timezone
from nucleus.models import KnowledgeFile, KnowledgeChunk, EmbeddingJob
from ninja.errors import HttpError


@transaction.atomic
def reprocess_knowledge_file(request, file_id, payload: KnowledgeFileReprocessIn):
    company = request.auth.current_company

    try:
        kf = KnowledgeFile.objects.get(
            id=file_id,
            is_active=True,
            knowledge_base__company=company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")

    # Remove existing chunks
    KnowledgeChunk.objects.filter(knowledge_file=kf).delete()

    # Async purge of existing vector documents
    purge_file_vectors.delay(str(kf.id))

    # Reset embedding status
    kf.embedding_status = "pending"
    kf.save(update_fields=["embedding_status", "updated_at"])

    # Create new embedding job with optional chunk settings in metadata
    job = EmbeddingJob.objects.create(
        company=company,
        target_type="knowledge_file",
        target_id=kf.id,
        status="pending",
        metadata={
            "chunk_size": payload.chunk_size,
            "chunk_overlap": payload.chunk_overlap,
        } if payload.chunk_size else {},
    )

    process_embedding_job.delay(str(job.id))

    return {
        "id": kf.id,
        "original_filename": kf.original_filename,
        "embedding_status": kf.embedding_status,
        "chunk_count": 0,
        "job_id": job.id,
        "message": "File queued for reprocessing.",
        "queued_at": timezone.now(),
    }
```

---

## 15.16 GET /api/v1/knowledge-files/{file_id}/chunks

### Detail

Returns a paginated list of `KnowledgeChunk` records for a given file. Each chunk is a text segment produced during the splitting phase. Useful for inspecting how a file was segmented, debugging chunking quality, or building a chunk browser in the UI.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` scoped via `knowledge_base__company`.
3. Query `KnowledgeChunk` filtered by `knowledge_file`, ordered by `chunk_index ASC`.
4. Return paginated list.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/knowledge-files/{file_id}/chunks?page=1&page_size=50
{
  "page": 1,
  "page_size": 50
}
```

### Response JSON

```json
{
  "count": 64,
  "next": "http://api/v1/knowledge-files/{file_id}/chunks?page=2",
  "previous": null,
  "results": [
    {
      "id": "ch1b2c3d-e5f6-7890-abcd-ef1234567890",
      "chunk_index": 0,
      "text": "NeuralOps Product Manual v2.0\nTable of Contents\n1. Introduction...",
      "token_count": 512,
      "metadata": {
        "page": 1,
        "section": "Table of Contents"
      }
    },
    {
      "id": "ch2b2c3d-e5f6-7890-abcd-ef1234567891",
      "chunk_index": 1,
      "text": "1. Introduction\nNeuralOps is an AI-powered workspace platform...",
      "token_count": 498,
      "metadata": {
        "page": 2,
        "section": "Introduction"
      }
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID


class KnowledgeChunkOut(Schema):
    id: UUID
    chunk_index: int
    text: str
    token_count: int
    metadata: dict[str, Any]


class KnowledgeChunkListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[KnowledgeChunkOut]
```

### Models Involved

- `KnowledgeChunk` — primary listing model
- `KnowledgeFile` — parent validated
- `KnowledgeBase` — company scope validation (via file → KB)

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeFile, KnowledgeChunk
from ninja.errors import HttpError


def list_knowledge_chunks(request, file_id):
    company = request.auth.current_company

    try:
        kf = KnowledgeFile.objects.get(
            id=file_id,
            is_active=True,
            knowledge_base__company=company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")

    return KnowledgeChunk.objects.filter(
        knowledge_file=kf,
    ).order_by("chunk_index")
```

---

## 15.17 GET /api/v1/knowledge-files/{file_id}/status

### Detail

Returns the processing status of a single `KnowledgeFile` — its `embedding_status`, the most recent `EmbeddingJob` state, error messages if any, and timing details. Designed for polling during file upload flows to show a real-time progress indicator.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` scoped via `knowledge_base__company`.
3. Fetch the most recent `EmbeddingJob` for this file.
4. Return status object with file + job details.

### Request JSON

```json
// No request body — file_id is a path parameter
// GET /api/v1/knowledge-files/{file_id}/status
```

### Response JSON

```json
{
  "file_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "original_filename": "product_manual_v2.pdf",
  "embedding_status": "completed",
  "chunk_count": 64,
  "latest_job": {
    "id": "ej1b2c3d-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "error": null,
    "started_at": "2026-05-01T09:00:10Z",
    "completed_at": "2026-05-01T09:05:30Z"
  }
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class EmbeddingJobBriefOut(Schema):
    id: UUID
    status: str
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class KnowledgeFileStatusOut(Schema):
    file_id: UUID
    original_filename: str
    embedding_status: str
    chunk_count: int
    latest_job: Optional[EmbeddingJobBriefOut]
```

### Models Involved

- `KnowledgeFile` — primary record
- `KnowledgeChunk` — counted
- `EmbeddingJob` — most recent job fetched
- `KnowledgeBase` — company scope validation

### Django ORM Query (Proposed)

```python
from django.db.models import Count
from nucleus.models import KnowledgeFile, EmbeddingJob
from ninja.errors import HttpError


def get_knowledge_file_status(request, file_id):
    company = request.auth.current_company

    try:
        kf = KnowledgeFile.objects.annotate(
            chunk_count=Count("chunks")
        ).get(
            id=file_id,
            is_active=True,
            knowledge_base__company=company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")

    latest_job = EmbeddingJob.objects.filter(
        company=company,
        target_type="knowledge_file",
        target_id=kf.id,
    ).order_by("-created_at").first()

    return {
        "file_id": kf.id,
        "original_filename": kf.original_filename,
        "embedding_status": kf.embedding_status,
        "chunk_count": kf.chunk_count,
        "latest_job": latest_job,
    }
```

---

## 15.18 GET /api/v1/knowledge-files/{file_id}/embeddings

### Detail

Returns the `VectorDocument` records associated with a given `KnowledgeFile`. Each record represents one stored vector in the vector database (one per chunk). Useful for auditing which vectors exist in ChromaDB, inspecting collection names, and debugging embedding pipeline issues.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `KnowledgeFile` scoped via `knowledge_base__company`.
3. Query `VectorDocument` filtered by `source_type=knowledge_file` and `source_id=file_id`.
4. Return paginated list of vector document records.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/knowledge-files/{file_id}/embeddings?page=1&page_size=50
{
  "page": 1,
  "page_size": 50
}
```

### Response JSON

```json
{
  "count": 64,
  "next": null,
  "previous": null,
  "file_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
  "vector_db": "chroma",
  "collection_name": "kb_kb1b2c3d",
  "results": [
    {
      "id": "vd1b2c3d-e5f6-7890-abcd-ef1234567890",
      "vector_db": "chroma",
      "collection_name": "kb_kb1b2c3d",
      "vector_id": "kf1b2c3d_chunk_0",
      "source_type": "knowledge_file",
      "source_id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
      "metadata": {
        "chunk_index": 0,
        "token_count": 512
      },
      "created_at": "2026-05-01T09:04:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class VectorDocumentOut(Schema):
    id: UUID
    vector_db: str
    collection_name: str
    vector_id: str
    source_type: str
    source_id: UUID
    metadata: dict[str, Any]
    created_at: datetime


class KnowledgeFileEmbeddingsOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    file_id: UUID
    vector_db: str
    collection_name: Optional[str]
    results: list[VectorDocumentOut]
```

### Models Involved

- `VectorDocument` — primary listing model
- `KnowledgeFile` — source validation + company scope
- `KnowledgeBase` — company scope validation (via file → KB)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import KnowledgeFile, VectorDocument
from ninja.errors import HttpError


def list_file_embeddings(request, file_id):
    company = request.auth.current_company

    try:
        kf = KnowledgeFile.objects.get(
            id=file_id,
            is_active=True,
            knowledge_base__company=company,
        )
    except KnowledgeFile.DoesNotExist:
        raise HttpError(404, "Knowledge file not found.")

    vectors = VectorDocument.objects.filter(
        company=company,
        source_type="knowledge_file",
        source_id=kf.id,
    ).order_by("created_at")

    # Infer collection name from first result
    collection_name = vectors.values_list(
        "collection_name", flat=True
    ).first()

    return {
        "file_id": kf.id,
        "vector_db": "chroma",
        "collection_name": collection_name,
        "vectors": vectors,
    }
```

---

## Summary: Model Reference

| Model | Table | Used In |
| --- | --- | --- |
| `KnowledgeBase` | `intelligence_knowledge_base` | 15.1 – 15.10 |
| `KnowledgeFile` | `intelligence_knowledge_file` | 15.11 – 15.18 |
| `KnowledgeChunk` | `intelligence_knowledge_chunk` | 15.10, 15.16, 15.17 |
| `EmbeddingJob` | `intelligence_embedding_job` | 15.8, 15.9, 15.12, 15.15, 15.17 |
| `VectorDocument` | `intelligence_vector_document` | 15.10, 15.14, 15.15, 15.18 |
| `Project` | `workspace_project` | 15.1 – 15.7 |
| `ChatTopic` | `workspace_chat_topic` | 15.1 – 15.7 |
| `Company` | `governance_company` | All endpoints (tenant scope) |

## Embedding Status Values

| Value | Meaning |
| --- | --- |
| `pending` | File uploaded, job not yet started |
| `processing` | Chunking and embedding in progress |
| `completed` | All chunks embedded and stored in vector DB |
| `failed` | Job encountered an unrecoverable error |

## Background Jobs

Two Celery (or equivalent) tasks are referenced throughout:

- `process_embedding_job(job_id)` — picks up an `EmbeddingJob`, chunks the file, embeds each chunk, writes `KnowledgeChunk` + `VectorDocument` records, updates `embedding_status`.
- `purge_file_vectors(file_id)` — removes `VectorDocument` records from ChromaDB and optionally deletes the physical file from storage.
- `purge_kb_vectors(kb_id)` — bulk purge of all vectors for a deleted KB.
