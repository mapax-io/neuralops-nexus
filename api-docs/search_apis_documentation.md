# 17. Search APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/search |
| POST | /api/v1/knowledge/search |
| POST | /api/v1/topics/{topic_id}/search |
| POST | /api/v1/search/messages |
| POST | /api/v1/search/files |
| POST | /api/v1/search/semantic |

---

## Background

NeuralOps supports two distinct search paradigms:

**Keyword / Full-text Search** — PostgreSQL `ILIKE` or `tsvector`-based search over structured records (messages, files, topics). Fast, exact, deterministic. Results are ranked by recency or relevance score.

**Semantic / Vector Search** — Embedding-based similarity search over `VectorDocument` records stored in ChromaDB. Slow, fuzzy, meaning-aware. Used for knowledge retrieval during AI inference and user-facing "find similar" features.

Every search call logs a `SearchLog` record for analytics and audit. The `SavedSearch` model allows users to persist named queries for later reuse (managed separately).

**Models touched across all search endpoints:**

| Model | Table | Role |
| --- | --- | --- |
| `ChatMessage` | `workspace_chat_message` | Message content search |
| `ChatTopic` | `workspace_chat_topic` | Topic-scoped search |
| `ChatAttachment` | `workspace_chat_attachment` | File attachment search |
| `KnowledgeFile` | `intelligence_knowledge_file` | Document search |
| `KnowledgeChunk` | `intelligence_knowledge_chunk` | Chunk-level content |
| `KnowledgeBase` | `intelligence_knowledge_base` | KB filter scope |
| `VectorDocument` | `intelligence_vector_document` | Semantic vector lookup |
| `Project` | `workspace_project` | Scope filter |
| `Channel` | `workspace_channel` | Scope filter |
| `SearchLog` | `search_log` | All searches logged here |
| `Company` | `governance_company` | Tenant scope |

---

## 17.1 GET /api/v1/search

### Detail

Global federated search across all company resources — messages, topics, channels, projects, knowledge files, and personas. Returns a unified result list grouped by resource type. Designed for the top-level search bar in the UI. Accepts a single `q` query parameter. Results are capped per type to keep the response fast and bounded. All results are scoped to `current_company`.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `q` is non-empty (min 2 chars).
3. Run parallel `ILIKE` / `tsvector` queries across:
   - `ChatMessage.content`
   - `ChatTopic.title`
   - `Channel.name`
   - `Project.name`
   - `KnowledgeFile.original_filename`
4. Cap each result set (e.g. top 5 per type).
5. Log `SearchLog` record (`search_type="global"`).
6. Return unified grouped response.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/search?q=quantum+computing&limit=5
{
  "q": "quantum computing",   // required: search query
  "limit": 5                  // optional: max results per type (default 5)
}
```

### Response JSON

```json
{
  "query": "quantum computing",
  "total_hits": 17,
  "results": {
    "messages": [
      {
        "id": "msg1b2c3-e5f6-7890-abcd-ef1234567890",
        "content_preview": "...latest advancements in **quantum computing** suggest...",
        "topic": { "id": "t1b2c3d4", "title": "Research Discussion" },
        "channel": { "id": "ch1b2c3d", "name": "research" },
        "project": { "id": "p1b2c3d4", "name": "Product Team" },
        "sender": { "id": "u1b2c3d4", "username": "noaman@example.com" },
        "created_at": "2026-05-20T10:00:00Z",
        "resource_type": "message"
      }
    ],
    "topics": [
      {
        "id": "t2b2c3d4-e5f6-7890-abcd-ef1234567891",
        "title": "Quantum Computing Research",
        "channel": { "id": "ch1b2c3d", "name": "research" },
        "project": { "id": "p1b2c3d4", "name": "Product Team" },
        "created_at": "2026-05-18T09:00:00Z",
        "resource_type": "topic"
      }
    ],
    "knowledge_files": [
      {
        "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
        "original_filename": "quantum_computing_primer.pdf",
        "knowledge_base": { "id": "kb1b2c3d", "name": "Research Library" },
        "embedding_status": "completed",
        "resource_type": "knowledge_file"
      }
    ],
    "channels": [],
    "projects": []
  },
  "latency_ms": 48
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class SearchMessageHitOut(Schema):
    id: UUID
    content_preview: str
    topic: dict
    channel: dict
    project: dict
    sender: Optional[dict]
    created_at: datetime
    resource_type: str = "message"


class SearchTopicHitOut(Schema):
    id: UUID
    title: str
    channel: dict
    project: dict
    created_at: datetime
    resource_type: str = "topic"


class SearchKnowledgeFileHitOut(Schema):
    id: UUID
    original_filename: str
    knowledge_base: dict
    embedding_status: str
    resource_type: str = "knowledge_file"


class GlobalSearchResultsOut(Schema):
    messages: list[SearchMessageHitOut]
    topics: list[SearchTopicHitOut]
    knowledge_files: list[SearchKnowledgeFileHitOut]
    channels: list[dict]
    projects: list[dict]


class GlobalSearchOut(Schema):
    query: str
    total_hits: int
    results: GlobalSearchResultsOut
    latency_ms: int
```

### Models Involved

- `ChatMessage` — keyword search on `content`
- `ChatTopic` — keyword search on `title`
- `Channel` — keyword search on `name`
- `Project` — keyword search on `name`
- `KnowledgeFile` — keyword search on `original_filename`
- `SearchLog` — result logged after search
- `Company` — tenant scope on all queries

### Django ORM Query (Proposed)

```python
import time
from django.db.models import Q
from nucleus.models import (
    ChatMessage, ChatTopic, Channel, Project, KnowledgeFile, SearchLog
)
from ninja.errors import HttpError


def global_search(request, q: str, limit: int = 5):
    if not q or len(q.strip()) < 2:
        raise HttpError(422, "Query must be at least 2 characters.")

    company = request.auth.current_company
    start = time.time()

    messages = ChatMessage.objects.filter(
        company=company,
        is_active=True,
        content__icontains=q,
    ).select_related(
        "topic", "topic__channel", "topic__project", "sender"
    ).order_by("-created_at")[:limit]

    topics = ChatTopic.objects.filter(
        company=company,
        is_active=True,
        title__icontains=q,
    ).select_related("channel", "project").order_by("-created_at")[:limit]

    channels = Channel.objects.filter(
        company=company,
        is_active=True,
        name__icontains=q,
    ).select_related("project").order_by("name")[:limit]

    projects = Project.objects.filter(
        company=company,
        is_active=True,
        name__icontains=q,
    ).order_by("name")[:limit]

    knowledge_files = KnowledgeFile.objects.filter(
        knowledge_base__company=company,
        is_active=True,
        original_filename__icontains=q,
    ).select_related("knowledge_base").order_by("-created_at")[:limit]

    latency_ms = int((time.time() - start) * 1000)

    total_hits = (
        len(messages) + len(topics) + len(channels)
        + len(projects) + len(knowledge_files)
    )

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=q,
        search_type="global",
        filters={},
        result_count=total_hits,
        latency_ms=latency_ms,
    )

    return {
        "query": q,
        "total_hits": total_hits,
        "results": {
            "messages": list(messages),
            "topics": list(topics),
            "knowledge_files": list(knowledge_files),
            "channels": list(channels),
            "projects": list(projects),
        },
        "latency_ms": latency_ms,
    }
```

---

## 17.2 POST /api/v1/knowledge/search

### Detail

Performs a semantic similarity search across one or more Knowledge Bases using vector embeddings. The query string is embedded on-the-fly using the company's configured embedding model, then matched against stored `VectorDocument` records in ChromaDB. Returns the top-K most similar `KnowledgeChunk` passages with their similarity scores. Supports filtering by `kb_ids` and `project_ids`. This is the primary retrieval mechanism used by AI agents during RAG (Retrieval-Augmented Generation).

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate KB IDs belong to company (if provided).
3. Embed the `query` string via the configured embedding model.
4. Query ChromaDB collections for the specified KBs using the query vector.
5. Retrieve top-K results; resolve `KnowledgeChunk` records from DB using `source_id`.
6. Log `SearchLog` record (`search_type="knowledge_semantic"`).
7. Return ranked chunk results with scores and source metadata.

### Request JSON

```json
{
  "query": "What are the system requirements for NeuralOps installation?",
  "kb_ids": ["kb1b2c3d-e5f6-7890-abcd-ef1234567890"],
  "project_ids": [],
  "top_k": 5,
  "score_threshold": 0.7
}
```

### Response JSON

```json
{
  "query": "What are the system requirements for NeuralOps installation?",
  "top_k": 5,
  "results": [
    {
      "chunk_id": "ch1b2c3d-e5f6-7890-abcd-ef1234567890",
      "chunk_index": 12,
      "text": "System Requirements\nNeuralOps requires a minimum of 4 CPU cores, 8GB RAM, and 20GB disk space. Docker 24+ and PostgreSQL 15+ are required...",
      "token_count": 487,
      "similarity_score": 0.94,
      "knowledge_file": {
        "id": "kf1b2c3d-e5f6-7890-abcd-ef1234567890",
        "original_filename": "installation_guide.pdf",
        "knowledge_base": {
          "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
          "name": "Product Documentation"
        }
      },
      "vector_document": {
        "id": "vd1b2c3d-e5f6-7890-abcd-ef1234567890",
        "vector_db": "chroma",
        "collection_name": "kb_kb1b2c3d",
        "vector_id": "kf1b2c3d_chunk_12"
      }
    }
  ],
  "latency_ms": 312
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class KnowledgeSearchIn(Schema):
    query: str
    kb_ids: list[UUID] = []
    project_ids: list[UUID] = []
    top_k: int = 5
    score_threshold: float = 0.0


class VectorDocumentBriefOut(Schema):
    id: UUID
    vector_db: str
    collection_name: str
    vector_id: str


class KnowledgeFileBriefOut(Schema):
    id: UUID
    original_filename: str
    knowledge_base: dict


class KnowledgeSearchHitOut(Schema):
    chunk_id: UUID
    chunk_index: int
    text: str
    token_count: int
    similarity_score: float
    knowledge_file: KnowledgeFileBriefOut
    vector_document: VectorDocumentBriefOut


class KnowledgeSearchOut(Schema):
    query: str
    top_k: int
    results: list[KnowledgeSearchHitOut]
    latency_ms: int
```

### Models Involved

- `KnowledgeBase` — filter scope and collection resolution
- `KnowledgeChunk` — resolved from vector results by `source_id`
- `KnowledgeFile` — parent of matched chunks
- `VectorDocument` — queried in ChromaDB; record resolved from DB
- `SearchLog` — logged after search
- `Project` — optional scope filter (KBs attached to specific projects)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
import time
from nucleus.models import (
    KnowledgeBase, KnowledgeChunk, KnowledgeFile, VectorDocument, SearchLog
)
from ninja.errors import HttpError


def knowledge_search(request, payload: KnowledgeSearchIn):
    if not payload.query.strip():
        raise HttpError(422, "Query cannot be empty.")

    company = request.auth.current_company
    start = time.time()

    # Resolve which KBs to search
    kb_qs = KnowledgeBase.objects.filter(company=company, is_active=True)
    if payload.kb_ids:
        kb_qs = kb_qs.filter(id__in=payload.kb_ids)
    if payload.project_ids:
        kb_qs = kb_qs.filter(projects__id__in=payload.project_ids)

    if not kb_qs.exists():
        raise HttpError(404, "No matching knowledge bases found.")

    # Resolve ChromaDB collection names for targeted KBs
    file_ids = KnowledgeFile.objects.filter(
        knowledge_base__in=kb_qs,
        is_active=True,
        embedding_status="completed",
    ).values_list("id", flat=True)

    collection_names = VectorDocument.objects.filter(
        company=company,
        source_type="knowledge_file",
        source_id__in=file_ids,
    ).values_list("collection_name", flat=True).distinct()

    # Query ChromaDB — vector search is handled by the AI service layer
    # chroma_results: list of (vector_id, score, metadata)
    chroma_results = vector_service.query(
        collections=list(collection_names),
        query_text=payload.query,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
    )

    # Resolve vector_ids back to DB records
    vector_ids = [r["vector_id"] for r in chroma_results]
    score_map = {r["vector_id"]: r["score"] for r in chroma_results}

    vector_docs = VectorDocument.objects.filter(
        company=company,
        vector_id__in=vector_ids,
    ).select_related()

    # Match chunks from source_ids
    chunk_ids = [vd.source_id for vd in vector_docs if vd.source_type == "knowledge_file"]
    chunks = KnowledgeChunk.objects.filter(
        id__in=chunk_ids,
    ).select_related(
        "knowledge_file", "knowledge_file__knowledge_base"
    )
    chunk_map = {str(c.id): c for c in chunks}
    vd_map = {str(vd.source_id): vd for vd in vector_docs}

    results = []
    for chunk_id in chunk_ids:
        chunk = chunk_map.get(str(chunk_id))
        vd = vd_map.get(str(chunk_id))
        if chunk and vd:
            results.append({
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "similarity_score": score_map.get(vd.vector_id, 0.0),
                "knowledge_file": chunk.knowledge_file,
                "vector_document": vd,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)

    latency_ms = int((time.time() - start) * 1000)

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=payload.query,
        search_type="knowledge_semantic",
        filters={"kb_ids": [str(i) for i in payload.kb_ids]},
        result_count=len(results),
        latency_ms=latency_ms,
    )

    return {
        "query": payload.query,
        "top_k": payload.top_k,
        "results": results,
        "latency_ms": latency_ms,
    }
```

---

## 17.3 POST /api/v1/topics/{topic_id}/search

### Detail

Performs a full-text keyword search scoped to a single chat topic — searching only the messages within that topic. Useful for the in-topic search bar ("find in this conversation"). Supports filtering by sender, date range, and message type. Results are ordered by relevance and recency.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `ChatTopic` by `topic_id` scoped to `company`.
3. Apply keyword search on `ChatMessage.content` filtered to this topic.
4. Apply optional filters (sender, date range, message_type).
5. Log `SearchLog` record (`search_type="topic_messages"`).
6. Return paginated message hits with highlighted preview.

### Request JSON

```json
{
  "query": "quarterly revenue forecast",
  "sender_ids": [],
  "message_type": null,
  "from_date": "2026-05-01",
  "to_date": "2026-05-22",
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "query": "quarterly revenue forecast",
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "msg1b2c3-e5f6-7890-abcd-ef1234567890",
      "content_preview": "...the **quarterly revenue forecast** indicates a 22% growth...",
      "message_type": "text",
      "status": "completed",
      "sender": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "noaman@example.com"
      },
      "created_at": "2026-05-15T11:30:00Z"
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


class TopicSearchIn(Schema):
    query: str
    sender_ids: list[UUID] = []
    message_type: Optional[str] = None   # "text" | "markdown" | "code" | etc.
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    page: int = 1
    page_size: int = 20


class TopicMessageHitOut(Schema):
    id: UUID
    content_preview: str
    message_type: str
    status: str
    sender: Optional[dict]
    created_at: datetime


class TopicSearchOut(Schema):
    topic_id: UUID
    query: str
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[TopicMessageHitOut]
```

### Models Involved

- `ChatTopic` — parent scope and company validation
- `ChatMessage` — full-text search on `content`
- `User` — optional `sender_ids` filter; nested in results
- `SearchLog` — logged after search
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
import time
from django.db.models import Q
from nucleus.models import ChatTopic, ChatMessage, SearchLog
from ninja.errors import HttpError


def search_topic_messages(request, topic_id, payload: TopicSearchIn):
    if not payload.query.strip():
        raise HttpError(422, "Query cannot be empty.")

    company = request.auth.current_company
    start = time.time()

    try:
        topic = ChatTopic.objects.get(
            id=topic_id, company=company, is_active=True
        )
    except ChatTopic.DoesNotExist:
        raise HttpError(404, "Topic not found.")

    qs = ChatMessage.objects.filter(
        topic=topic,
        company=company,
        is_active=True,
        content__icontains=payload.query,
    ).select_related("sender")

    if payload.sender_ids:
        qs = qs.filter(sender_id__in=payload.sender_ids)

    if payload.message_type:
        qs = qs.filter(message_type=payload.message_type)

    if payload.from_date:
        qs = qs.filter(created_at__date__gte=payload.from_date)

    if payload.to_date:
        qs = qs.filter(created_at__date__lte=payload.to_date)

    qs = qs.order_by("-created_at")
    total = qs.count()

    latency_ms = int((time.time() - start) * 1000)

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=payload.query,
        search_type="topic_messages",
        filters={"topic_id": str(topic_id)},
        result_count=total,
        latency_ms=latency_ms,
    )

    return {
        "topic_id": topic.id,
        "query": payload.query,
        "count": total,
        "results": qs,
    }
```

---

## 17.4 POST /api/v1/search/messages

### Detail

Performs a full-text keyword search across all `ChatMessage` records in the company. Supports rich filtering by project, channel, topic, sender, date range, and message type. Returns paginated message hits with sender and topic context. Results are ordered by recency (newest first) unless a relevance sort is requested.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `query` is non-empty.
3. Build a `ChatMessage` queryset with `content__icontains` + all filters.
4. Apply `select_related` for sender, topic, topic's channel and project.
5. Log `SearchLog` (`search_type="messages"`).
6. Return paginated results.

### Request JSON

```json
{
  "query": "deployment pipeline failed",
  "project_ids": ["p1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "channel_ids": [],
  "topic_ids": [],
  "sender_ids": [],
  "message_type": null,
  "from_date": "2026-05-01",
  "to_date": null,
  "sort": "recency",
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "query": "deployment pipeline failed",
  "count": 7,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "msg2b3c4d-e5f6-7890-abcd-ef1234567890",
      "content_preview": "The **deployment pipeline failed** on step 3 — Docker build timeout.",
      "message_type": "text",
      "status": "completed",
      "topic": {
        "id": "t2b2c3d4-e5f6-7890-abcd-ef1234567891",
        "title": "Infrastructure Issues"
      },
      "channel": {
        "id": "ch1b2c3d-e5f6-7890-abcd-ef1234567890",
        "name": "engineering"
      },
      "project": {
        "id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Product Team"
      },
      "sender": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "noaman@example.com"
      },
      "created_at": "2026-05-20T14:22:00Z"
    }
  ],
  "latency_ms": 34
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime, date


class MessageSearchIn(Schema):
    query: str
    project_ids: list[UUID] = []
    channel_ids: list[UUID] = []
    topic_ids: list[UUID] = []
    sender_ids: list[UUID] = []
    message_type: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    sort: str = "recency"       # "recency" | "relevance"
    page: int = 1
    page_size: int = 20


class MessageSearchHitOut(Schema):
    id: UUID
    content_preview: str
    message_type: str
    status: str
    topic: dict
    channel: dict
    project: dict
    sender: Optional[dict]
    created_at: datetime


class MessageSearchOut(Schema):
    query: str
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[MessageSearchHitOut]
    latency_ms: int
```

### Models Involved

- `ChatMessage` — primary search target (`content__icontains`)
- `ChatTopic` — FK join for context; optional filter scope
- `Channel` — FK join for context; optional filter scope
- `Project` — optional filter scope
- `User` — optional sender filter; nested in results
- `SearchLog` — logged after search
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
import time
from nucleus.models import ChatMessage, SearchLog
from ninja.errors import HttpError


def search_messages(request, payload: MessageSearchIn):
    if not payload.query.strip():
        raise HttpError(422, "Query cannot be empty.")

    company = request.auth.current_company
    start = time.time()

    qs = ChatMessage.objects.filter(
        company=company,
        is_active=True,
        content__icontains=payload.query,
    ).select_related(
        "sender",
        "topic",
        "topic__channel",
        "topic__project",
    )

    if payload.project_ids:
        qs = qs.filter(project_id__in=payload.project_ids)

    if payload.channel_ids:
        qs = qs.filter(topic__channel_id__in=payload.channel_ids)

    if payload.topic_ids:
        qs = qs.filter(topic_id__in=payload.topic_ids)

    if payload.sender_ids:
        qs = qs.filter(sender_id__in=payload.sender_ids)

    if payload.message_type:
        qs = qs.filter(message_type=payload.message_type)

    if payload.from_date:
        qs = qs.filter(created_at__date__gte=payload.from_date)

    if payload.to_date:
        qs = qs.filter(created_at__date__lte=payload.to_date)

    qs = qs.order_by("-created_at")
    total = qs.count()

    latency_ms = int((time.time() - start) * 1000)

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=payload.query,
        search_type="messages",
        filters={
            "project_ids": [str(i) for i in payload.project_ids],
            "channel_ids": [str(i) for i in payload.channel_ids],
        },
        result_count=total,
        latency_ms=latency_ms,
    )

    return {
        "query": payload.query,
        "count": total,
        "results": qs,
        "latency_ms": latency_ms,
    }
```

---

## 17.5 POST /api/v1/search/files

### Detail

Searches across all file-type resources in the company — both `KnowledgeFile` records (documents ingested into knowledge bases) and `ChatAttachment` records (files uploaded directly in chat messages). Supports filtering by MIME type, knowledge base, project, date range, and file size. Returns a unified result list tagged by `file_source` (`knowledge` or `chat`).

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `query` is non-empty.
3. Search `KnowledgeFile.original_filename` with `icontains`.
4. Search `ChatAttachment.original_filename` with `icontains`.
5. Apply optional filters independently to each queryset.
6. Merge and sort unified results by `created_at DESC`.
7. Log `SearchLog` (`search_type="files"`).
8. Return paginated unified file results.

### Request JSON

```json
{
  "query": "quarterly report",
  "file_source": null,
  "mime_types": ["application/pdf", "application/vnd.ms-excel"],
  "kb_ids": [],
  "project_ids": [],
  "from_date": "2026-01-01",
  "to_date": null,
  "min_size_bytes": null,
  "max_size_bytes": null,
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "query": "quarterly report",
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "kf2b3c4d-e5f6-7890-abcd-ef1234567891",
      "original_filename": "Q1_2026_quarterly_report.pdf",
      "mime_type": "application/pdf",
      "file_size": 1548290,
      "file_source": "knowledge",
      "knowledge_base": {
        "id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
        "name": "Finance Documents"
      },
      "embedding_status": "completed",
      "created_at": "2026-04-05T08:00:00Z"
    },
    {
      "id": "att1b2c3-e5f6-7890-abcd-ef1234567890",
      "original_filename": "Q2_2026_quarterly_report_draft.xlsx",
      "mime_type": "application/vnd.ms-excel",
      "file_size": 204800,
      "file_source": "chat",
      "message": {
        "id": "msg3b4c5d-e5f6-7890-abcd-ef1234567890",
        "topic": { "id": "t3b4c5d4", "title": "Finance Review" }
      },
      "created_at": "2026-05-10T15:00:00Z"
    }
  ],
  "latency_ms": 52
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime, date


class FileSearchIn(Schema):
    query: str
    file_source: Optional[str] = None      # "knowledge" | "chat" | null (both)
    mime_types: list[str] = []
    kb_ids: list[UUID] = []
    project_ids: list[UUID] = []
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    min_size_bytes: Optional[int] = None
    max_size_bytes: Optional[int] = None
    page: int = 1
    page_size: int = 20


class KnowledgeFileHitOut(Schema):
    id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    file_source: str = "knowledge"
    knowledge_base: dict
    embedding_status: str
    created_at: datetime


class ChatAttachmentHitOut(Schema):
    id: UUID
    original_filename: str
    mime_type: str
    file_size: int
    file_source: str = "chat"
    message: dict
    created_at: datetime


class FileSearchOut(Schema):
    query: str
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[dict]   # mixed KnowledgeFileHitOut | ChatAttachmentHitOut
    latency_ms: int
```

### Models Involved

- `KnowledgeFile` — searched by `original_filename`
- `ChatAttachment` — searched by `original_filename`
- `KnowledgeBase` — FK join for context; optional `kb_ids` filter
- `ChatMessage` — FK join from ChatAttachment for topic context
- `ChatTopic` — nested context from message
- `Project` — optional scope filter
- `SearchLog` — logged after search
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
import time
from nucleus.models import KnowledgeFile, ChatAttachment, SearchLog
from ninja.errors import HttpError


def search_files(request, payload: FileSearchIn):
    if not payload.query.strip():
        raise HttpError(422, "Query cannot be empty.")

    company = request.auth.current_company
    start = time.time()
    results = []

    # --- Knowledge Files ---
    if payload.file_source in (None, "knowledge"):
        kf_qs = KnowledgeFile.objects.filter(
            knowledge_base__company=company,
            is_active=True,
            original_filename__icontains=payload.query,
        ).select_related("knowledge_base")

        if payload.mime_types:
            kf_qs = kf_qs.filter(mime_type__in=payload.mime_types)
        if payload.kb_ids:
            kf_qs = kf_qs.filter(knowledge_base_id__in=payload.kb_ids)
        if payload.project_ids:
            kf_qs = kf_qs.filter(knowledge_base__projects__id__in=payload.project_ids)
        if payload.from_date:
            kf_qs = kf_qs.filter(created_at__date__gte=payload.from_date)
        if payload.to_date:
            kf_qs = kf_qs.filter(created_at__date__lte=payload.to_date)
        if payload.min_size_bytes:
            kf_qs = kf_qs.filter(file_size__gte=payload.min_size_bytes)
        if payload.max_size_bytes:
            kf_qs = kf_qs.filter(file_size__lte=payload.max_size_bytes)

        for kf in kf_qs.order_by("-created_at"):
            results.append({**kf.__dict__, "file_source": "knowledge", "knowledge_base": kf.knowledge_base})

    # --- Chat Attachments ---
    if payload.file_source in (None, "chat"):
        att_qs = ChatAttachment.objects.filter(
            message__company=company,
            is_active=True,
            original_filename__icontains=payload.query,
        ).select_related("message", "message__topic")

        if payload.mime_types:
            att_qs = att_qs.filter(mime_type__in=payload.mime_types)
        if payload.project_ids:
            att_qs = att_qs.filter(message__project_id__in=payload.project_ids)
        if payload.from_date:
            att_qs = att_qs.filter(created_at__date__gte=payload.from_date)
        if payload.to_date:
            att_qs = att_qs.filter(created_at__date__lte=payload.to_date)
        if payload.min_size_bytes:
            att_qs = att_qs.filter(file_size__gte=payload.min_size_bytes)
        if payload.max_size_bytes:
            att_qs = att_qs.filter(file_size__lte=payload.max_size_bytes)

        for att in att_qs.order_by("-created_at"):
            results.append({**att.__dict__, "file_source": "chat", "message": att.message})

    # Merge sort by created_at desc
    results.sort(key=lambda x: x["created_at"], reverse=True)

    latency_ms = int((time.time() - start) * 1000)

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=payload.query,
        search_type="files",
        filters={"mime_types": payload.mime_types, "file_source": payload.file_source},
        result_count=len(results),
        latency_ms=latency_ms,
    )

    return {
        "query": payload.query,
        "count": len(results),
        "results": results,
        "latency_ms": latency_ms,
    }
```

---

## 17.6 POST /api/v1/search/semantic

### Detail

Performs a broad semantic (vector embedding) search across all indexed content in the company — or a scoped subset defined by `project_ids`, `kb_ids`, or `source_types`. Unlike the knowledge-specific endpoint (17.2), this endpoint can search across multiple content types (`knowledge_file`, `message`) if those have been vectorised. Returns top-K `VectorDocument` hits with similarity scores and resolved source content. This is the most powerful and flexible retrieval endpoint, used by the AI inference pipeline.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `query` is non-empty.
3. Resolve target collections from `VectorDocument` based on scope filters.
4. Embed `query` string via the configured embedding model.
5. Run vector similarity query in ChromaDB against resolved collections.
6. For each result, resolve source content from DB (`KnowledgeChunk` or `ChatMessage`).
7. Apply `score_threshold` filter.
8. Log `SearchLog` (`search_type="semantic"`).
9. Return ranked hits with resolved content and scores.

### Request JSON

```json
{
  "query": "how to configure SMTP for email notifications",
  "source_types": ["knowledge_file"],
  "kb_ids": [],
  "project_ids": ["p1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "top_k": 8,
  "score_threshold": 0.65,
  "include_content": true
}
```

### Response JSON

```json
{
  "query": "how to configure SMTP for email notifications",
  "source_types": ["knowledge_file"],
  "top_k": 8,
  "score_threshold": 0.65,
  "results": [
    {
      "rank": 1,
      "similarity_score": 0.91,
      "source_type": "knowledge_file",
      "source_id": "ch4b5c6d-e5f6-7890-abcd-ef1234567890",
      "content": "Email Notifications\nTo configure SMTP, navigate to Settings → Notifications → Email. Enter your SMTP host, port (587 for TLS), username, and password...",
      "token_count": 312,
      "vector_document": {
        "id": "vd2b3c4d-e5f6-7890-abcd-ef1234567891",
        "vector_db": "chroma",
        "collection_name": "kb_kb1b2c3d",
        "vector_id": "kf2b3c4d_chunk_8"
      },
      "source_metadata": {
        "knowledge_file_id": "kf2b3c4d-e5f6-7890-abcd-ef1234567891",
        "original_filename": "admin_guide.pdf",
        "knowledge_base_id": "kb1b2c3d-e5f6-7890-abcd-ef1234567890",
        "knowledge_base_name": "Product Documentation",
        "chunk_index": 8
      }
    }
  ],
  "latency_ms": 284
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class SemanticSearchIn(Schema):
    query: str
    source_types: list[str] = ["knowledge_file"]   # "knowledge_file" | "message"
    kb_ids: list[UUID] = []
    project_ids: list[UUID] = []
    top_k: int = 5
    score_threshold: float = 0.0
    include_content: bool = True


class SemanticSearchHitOut(Schema):
    rank: int
    similarity_score: float
    source_type: str
    source_id: UUID
    content: Optional[str]
    token_count: Optional[int]
    vector_document: VectorDocumentBriefOut
    source_metadata: dict[str, Any]


class SemanticSearchOut(Schema):
    query: str
    source_types: list[str]
    top_k: int
    score_threshold: float
    results: list[SemanticSearchHitOut]
    latency_ms: int
```

### Models Involved

- `VectorDocument` — collection resolution and vector ID lookup
- `KnowledgeChunk` — resolved source content for `source_type=knowledge_file`
- `KnowledgeFile` — parent metadata for knowledge chunks
- `KnowledgeBase` — scope filter; metadata enrichment
- `ChatMessage` — resolved source content for `source_type=message` (if vectorised)
- `Project` — optional scope filter for KB resolution
- `SearchLog` — logged after search
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
import time
from nucleus.models import (
    VectorDocument, KnowledgeChunk, KnowledgeFile,
    KnowledgeBase, ChatMessage, SearchLog
)
from ninja.errors import HttpError


def semantic_search(request, payload: SemanticSearchIn):
    if not payload.query.strip():
        raise HttpError(422, "Query cannot be empty.")

    company = request.auth.current_company
    start = time.time()

    # Resolve target collections from VectorDocument scope
    vd_qs = VectorDocument.objects.filter(
        company=company,
        source_type__in=payload.source_types,
    )

    if payload.kb_ids or payload.project_ids:
        # Restrict to file IDs within scoped KBs
        kb_qs = KnowledgeBase.objects.filter(company=company, is_active=True)
        if payload.kb_ids:
            kb_qs = kb_qs.filter(id__in=payload.kb_ids)
        if payload.project_ids:
            kb_qs = kb_qs.filter(projects__id__in=payload.project_ids)

        scoped_file_ids = KnowledgeFile.objects.filter(
            knowledge_base__in=kb_qs, is_active=True
        ).values_list("id", flat=True)

        vd_qs = vd_qs.filter(source_id__in=scoped_file_ids)

    collection_names = list(vd_qs.values_list("collection_name", flat=True).distinct())

    if not collection_names:
        return {
            "query": payload.query,
            "source_types": payload.source_types,
            "top_k": payload.top_k,
            "score_threshold": payload.score_threshold,
            "results": [],
            "latency_ms": 0,
        }

    # Vector search via ChromaDB service layer
    chroma_results = vector_service.query(
        collections=collection_names,
        query_text=payload.query,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
    )

    # Resolve source records from DB
    vector_ids = [r["vector_id"] for r in chroma_results]
    score_map = {r["vector_id"]: r["score"] for r in chroma_results}

    resolved_vds = VectorDocument.objects.filter(
        company=company, vector_id__in=vector_ids
    )
    vd_by_vector_id = {vd.vector_id: vd for vd in resolved_vds}

    # Resolve content for each result
    chunk_ids = [
        vd.source_id for vd in resolved_vds
        if vd.source_type == "knowledge_file"
    ]
    chunks = KnowledgeChunk.objects.filter(
        id__in=chunk_ids
    ).select_related("knowledge_file", "knowledge_file__knowledge_base")
    chunk_by_id = {str(c.id): c for c in chunks}

    results = []
    for rank, cr in enumerate(chroma_results, start=1):
        vd = vd_by_vector_id.get(cr["vector_id"])
        if not vd:
            continue

        score = score_map.get(cr["vector_id"], 0.0)
        hit = {
            "rank": rank,
            "similarity_score": score,
            "source_type": vd.source_type,
            "source_id": vd.source_id,
            "vector_document": vd,
            "content": None,
            "token_count": None,
            "source_metadata": {},
        }

        if vd.source_type == "knowledge_file":
            chunk = chunk_by_id.get(str(vd.source_id))
            if chunk:
                hit["content"] = chunk.text if payload.include_content else None
                hit["token_count"] = chunk.token_count
                hit["source_metadata"] = {
                    "knowledge_file_id": str(chunk.knowledge_file.id),
                    "original_filename": chunk.knowledge_file.original_filename,
                    "knowledge_base_id": str(chunk.knowledge_file.knowledge_base.id),
                    "knowledge_base_name": chunk.knowledge_file.knowledge_base.name,
                    "chunk_index": chunk.chunk_index,
                }

        results.append(hit)

    latency_ms = int((time.time() - start) * 1000)

    SearchLog.objects.create(
        company=company,
        user=request.auth,
        query=payload.query,
        search_type="semantic",
        filters={
            "source_types": payload.source_types,
            "kb_ids": [str(i) for i in payload.kb_ids],
            "score_threshold": payload.score_threshold,
        },
        result_count=len(results),
        latency_ms=latency_ms,
    )

    return {
        "query": payload.query,
        "source_types": payload.source_types,
        "top_k": payload.top_k,
        "score_threshold": payload.score_threshold,
        "results": results,
        "latency_ms": latency_ms,
    }
```

---

## Summary: Search Endpoint Comparison

| Endpoint | Search Type | Scope | Primary Model Queried | Logged As |
| --- | --- | --- | --- | --- |
| GET /api/v1/search | Keyword, federated | Company-wide, all types | `ChatMessage`, `ChatTopic`, `Channel`, `Project`, `KnowledgeFile` | `global` |
| POST /api/v1/knowledge/search | Semantic (vector) | KB-scoped | `VectorDocument` → `KnowledgeChunk` | `knowledge_semantic` |
| POST /api/v1/topics/{id}/search | Keyword | Single topic | `ChatMessage` | `topic_messages` |
| POST /api/v1/search/messages | Keyword, filtered | Company-wide messages | `ChatMessage` | `messages` |
| POST /api/v1/search/files | Keyword, unified | Company-wide files | `KnowledgeFile` + `ChatAttachment` | `files` |
| POST /api/v1/search/semantic | Semantic (vector) | Flexible scope | `VectorDocument` → `KnowledgeChunk` / `ChatMessage` | `semantic` |

## SearchLog: What Gets Recorded

Every endpoint writes a `SearchLog` after execution:

```python
SearchLog.objects.create(
    company=company,
    user=request.auth,        # nullable — anonymous allowed in future
    query=payload.query,
    search_type="...",        # one of the values in the table above
    filters={...},            # serialized filter dict
    result_count=N,
    latency_ms=N,
)
```

This powers search analytics dashboards and allows you to identify the most common queries, failed searches, and slow-running patterns.

## PostgreSQL Full-Text Search Upgrade Path

The current ORM queries use `icontains` (simple `ILIKE '%query%'`). For production scale, upgrade to PostgreSQL full-text search using `SearchVector` and `SearchQuery`:

```python
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import F

qs = ChatMessage.objects.annotate(
    search=SearchVector("content"),
    rank=SearchRank(F("search"), SearchQuery(payload.query)),
).filter(
    company=company,
    is_active=True,
    search=SearchQuery(payload.query),
).order_by("-rank")
```

Add a `GinIndex` on the `content` field in a migration for significant performance gains on large message tables.
