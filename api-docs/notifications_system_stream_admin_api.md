# NeuralOps — Notifications, System, Streaming & Admin API Documentation

> Sections 21–24 · 15 Endpoints
> Framework: Django 5.2 + Django Ninja · Auth: Supabase JWT · Transport: Centrifuge (nexus-transport)

---

## Table of Contents

1. [Notifications](#notifications)
   - GET /notifications
   - POST /notifications/read-all
   - POST /notifications/{notification_id}/read
2. [System & Health](#system--health)
   - GET /health
   - GET /version
   - GET /system/status
   - GET /system/features
3. [Streaming (Centrifuge)](#streaming-centrifuge)
   - GET /stream/topics/{topic_id}
   - GET /stream/messages/{message_id}
   - POST /stream/agents/{run_id}/cancel
4. [Admin](#admin)
   - GET /admin/users
   - GET /admin/companies
   - GET /admin/system-metrics
   - POST /admin/reindex-all
   - POST /admin/rebuild-search

---

## Notification Creation Convention

Notifications are created throughout the system using a helper utility:

```python
def create_notification(user, company, notification_type, title, body, metadata=None):
    Notification.objects.create(
        user=user,
        company=company,
        notification_type=notification_type,
        title=title,
        body=body,
        metadata=metadata or {},
    )
```

Common trigger points:
- Agent run completes/fails → `notification_type=AGENT`
- User invited to company → `notification_type=INVITATION`
- Embedding job fails → `notification_type=ERROR`
- Knowledge base reindex complete → `notification_type=INFO`

---

## Streaming Architecture — Channel Naming Convention

| Resource              | Centrifuge Channel          | Events Published                       |
|-----------------------|-----------------------------|----------------------------------------|
| ChatTopic             | `topic:{topic_id}`          | `message.created`, `message.updated`   |
| ChatMessage (stream)  | `message:{message_id}`      | `chunk`, `done`, `error`               |
| AgentRun              | `agent_run:{run_id}`        | `step`, `log`, `run.cancelled`, `done` |

Two-step handshake:
1. Client calls Django Ninja HTTP endpoint → receives a short-lived Centrifuge subscription JWT
2. Client connects directly to Centrifuge WebSocket using that token

---

## Access Control Matrix

| Endpoint Group     | Auth Required | Company Scope | Extra Guard                    |
|--------------------|--------------|---------------|--------------------------------|
| Notifications      | ✅ Supabase JWT | ✅ current_company | Own notifications only     |
| Health             | ❌ None        | ❌            | —                              |
| Version            | ❌ None        | ❌            | —                              |
| System Status      | ✅ Supabase JWT | ✅            | Any authenticated member       |
| System Features    | ✅ Supabase JWT | ✅            | Any authenticated member       |
| Streaming          | ✅ Supabase JWT | ✅            | Participant/run ownership check|
| Admin              | ✅ Supabase JWT | ❌ (global)   | `is_staff` or `is_superuser`   |

---

## Notifications

---

### GET /api/v1/notifications

#### Detail
Returns a paginated list of notifications for the authenticated user within the current company. The response envelope includes an `unread_count` field for badge rendering without a separate count call.

#### Flow
1. Extract authenticated user from Supabase JWT (`request.auth`)
2. Scope to `request.auth.current_company`
3. Filter `Notification` by `user=request.auth` and `company=current_company`
4. Apply optional `?is_read=false` filter
5. Order by `created_at DESC`
6. Compute `unread_count` via aggregate COUNT on unread records
7. Paginate and return wrapped in envelope

#### Request JSON
```json
// Query parameters only — no request body
// GET /api/v1/notifications?is_read=false&page=1&page_size=20
```

#### Response JSON
```json
{
  "unread_count": 5,
  "count": 42,
  "next": "/api/v1/notifications?page=2&page_size=20",
  "previous": null,
  "results": [
    {
      "id": "a1b2c3d4-0000-0000-0000-000000000001",
      "notification_type": "agent",
      "title": "Agent Run Completed",
      "body": "Your agent 'Data Extractor' finished successfully with 12 results.",
      "is_read": false,
      "read_at": null,
      "metadata": {
        "agent_run_id": "run-uuid-here",
        "agent_name": "Data Extractor"
      },
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

#### Pydantic for Django Ninja
```python
from ninja import Schema, FilterSchema
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class NotificationOut(Schema):
    id: UUID
    notification_type: str
    title: str
    body: str
    is_read: bool
    read_at: Optional[datetime]
    metadata: dict
    created_at: datetime
    updated_at: datetime

class NotificationListEnvelope(Schema):
    unread_count: int
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[NotificationOut]

class NotificationFilterSchema(FilterSchema):
    is_read: Optional[bool] = None
    notification_type: Optional[str] = None
```

#### List Model Involved
- `Notification` — primary model
- `User` — current authenticated user filter
- `Company` — tenant scope via `request.auth.current_company`

#### Django ORM Query (Proposed)
```python
from django.db.models import Count, Q

@router.get("/notifications", response=NotificationListEnvelope)
def list_notifications(
    request,
    filters: NotificationFilterSchema = Query(...),
    page: int = 1,
    page_size: int = 20,
):
    company = request.auth.current_company
    user = request.auth

    qs = Notification.objects.filter(
        user=user,
        company=company,
        is_active=True,
    ).order_by("-created_at")

    if filters.is_read is not None:
        qs = qs.filter(is_read=filters.is_read)
    if filters.notification_type:
        qs = qs.filter(notification_type=filters.notification_type)

    # Unread count always computed on the full (unfiltered) set
    unread_count = Notification.objects.filter(
        user=user,
        company=company,
        is_active=True,
        is_read=False,
    ).count()

    total = qs.count()
    offset = (page - 1) * page_size
    results = list(qs[offset : offset + page_size])

    return NotificationListEnvelope(
        unread_count=unread_count,
        count=total,
        next=f"/api/v1/notifications?page={page + 1}&page_size={page_size}" if offset + page_size < total else None,
        previous=f"/api/v1/notifications?page={page - 1}&page_size={page_size}" if page > 1 else None,
        results=results,
    )
```

---

### POST /api/v1/notifications/read-all

#### Detail
Marks all unread notifications for the authenticated user in the current company as read. Uses a bulk `UPDATE` for efficiency — no row-by-row save. Returns the count of records updated.

#### Flow
1. Authenticate via Supabase JWT
2. Scope to `request.auth.current_company`
3. Issue bulk `UPDATE` on `Notification` where `user=request.auth`, `company=current_company`, `is_read=False`
4. Set `is_read=True` and `read_at=now()`
5. Return `{"updated": N}`

#### Request JSON
```json
// No request body — POST with empty body
{}
```

#### Response JSON
```json
{
  "updated": 12,
  "message": "12 notifications marked as read."
}
```

#### Pydantic for Django Ninja
```python
class ReadAllOut(Schema):
    updated: int
    message: str
```

#### List Model Involved
- `Notification` — bulk updated

#### Django ORM Query (Proposed)
```python
from django.utils import timezone

@router.post("/notifications/read-all", response=ReadAllOut)
def read_all_notifications(request):
    company = request.auth.current_company
    now = timezone.now()

    updated_count = Notification.objects.filter(
        user=request.auth,
        company=company,
        is_read=False,
        is_active=True,
    ).update(
        is_read=True,
        read_at=now,
        updated_at=now,
    )

    return ReadAllOut(
        updated=updated_count,
        message=f"{updated_count} notifications marked as read.",
    )
```

---

### POST /api/v1/notifications/{notification_id}/read

#### Detail
Marks a single notification as read. Validates that the notification belongs to the authenticated user in the current company — prevents cross-user notification access. Returns the updated notification object. Idempotent: if already read, returns current state without modifying `read_at`.

#### Flow
1. Authenticate via Supabase JWT
2. Fetch `Notification` by `id=notification_id`, `user=request.auth`, `company=current_company`
3. Return 404 if not found or not owned by user
4. If already `is_read=True`, return the notification as-is (idempotent)
5. Set `is_read=True` and `read_at=now()`
6. Save and return updated notification

#### Request JSON
```json
// No request body
// POST /api/v1/notifications/a1b2c3d4-0000-0000-0000-000000000001/read
```

#### Response JSON
```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "notification_type": "agent",
  "title": "Agent Run Completed",
  "body": "Your agent 'Data Extractor' finished successfully with 12 results.",
  "is_read": true,
  "read_at": "2025-01-15T11:00:00Z",
  "metadata": {
    "agent_run_id": "run-uuid-here",
    "agent_name": "Data Extractor"
  },
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T11:00:00Z"
}
```

#### Pydantic for Django Ninja
```python
# Reuses NotificationOut defined in GET /notifications — no additional schema needed
```

#### List Model Involved
- `Notification` — fetched and updated

#### Django ORM Query (Proposed)
```python
from django.utils import timezone
from django.shortcuts import get_object_or_404

@router.post("/notifications/{notification_id}/read", response=NotificationOut)
def read_notification(request, notification_id: UUID):
    company = request.auth.current_company

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.auth,
        company=company,
        is_active=True,
    )

    if not notification.is_read:
        now = timezone.now()
        notification.is_read = True
        notification.read_at = now
        notification.save(update_fields=["is_read", "read_at", "updated_at"])

    return notification
```

---

## System & Health

---

### GET /api/v1/health

#### Detail
Lightweight liveness probe. No authentication required. Returns HTTP 200 with a fixed payload. Used by load balancers, container orchestration (Kubernetes readiness/liveness probes), and uptime monitors. Should never raise an exception — if the app can respond at all, this returns 200.

#### Flow
1. No auth check
2. No database queries
3. Return static `{"status": "ok"}` immediately

#### Request JSON
```json
// No auth, no body
// GET /api/v1/health
```

#### Response JSON
```json
{
  "status": "ok"
}
```

#### Pydantic for Django Ninja
```python
class HealthOut(Schema):
    status: str
```

#### List Model Involved
- None

#### Django ORM Query (Proposed)
```python
@router.get("/health", response=HealthOut, auth=None)
def health(request):
    return HealthOut(status="ok")
```

---

### GET /api/v1/version

#### Detail
Returns build metadata — application version, environment name, and build timestamp — read from environment variables. No authentication required. Useful for debugging deployments and confirming which build is running in staging vs. production.

#### Flow
1. No auth check
2. Read `APP_VERSION`, `APP_ENV`, `BUILD_TIMESTAMP` from `os.environ` (with safe defaults)
3. Return payload

#### Request JSON
```json
// No auth, no body
// GET /api/v1/version
```

#### Response JSON
```json
{
  "version": "1.4.2",
  "environment": "production",
  "build_at": "2025-01-10T08:00:00Z",
  "python_version": "3.12.2",
  "django_version": "5.2.0"
}
```

#### Pydantic for Django Ninja
```python
import os, sys, django

class VersionOut(Schema):
    version: str
    environment: str
    build_at: str
    python_version: str
    django_version: str
```

#### List Model Involved
- None

#### Django ORM Query (Proposed)
```python
@router.get("/version", response=VersionOut, auth=None)
def version(request):
    return VersionOut(
        version=os.getenv("APP_VERSION", "0.0.0"),
        environment=os.getenv("APP_ENV", "development"),
        build_at=os.getenv("BUILD_TIMESTAMP", "unknown"),
        python_version=sys.version.split(" ")[0],
        django_version=django.__version__,
    )
```

---

### GET /api/v1/system/status

#### Detail
Performs live health probes against all critical infrastructure dependencies: PostgreSQL (primary DB), Redis (cache/message broker), ChromaDB (vector store), and Centrifuge (real-time transport). Returns individual status per service plus an overall system status. Requires authentication — intended for admin dashboards and ops tooling.

#### Flow
1. Authenticate via Supabase JWT
2. Probe each service sequentially or concurrently:
   - **PostgreSQL**: Execute `SELECT 1` via Django ORM connection
   - **Redis**: `cache.set` + `cache.get` roundtrip
   - **ChromaDB**: `chroma_client.heartbeat()`
   - **Centrifuge**: HTTP GET to `CENTRIFUGE_API_URL/health`
3. Aggregate `overall: "healthy" | "degraded" | "down"`:
   - `healthy` = all probes pass
   - `degraded` = PostgreSQL up but ≥1 ancillary service down
   - `down` = PostgreSQL unreachable
4. Return per-service status with `latency_ms`

#### Request JSON
```json
// No body — GET request
// GET /api/v1/system/status
```

#### Response JSON
```json
{
  "overall": "healthy",
  "checked_at": "2025-01-15T12:00:00Z",
  "services": {
    "postgres": {
      "status": "healthy",
      "latency_ms": 2
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 1
    },
    "chromadb": {
      "status": "healthy",
      "latency_ms": 8
    },
    "centrifuge": {
      "status": "degraded",
      "latency_ms": null,
      "error": "Connection refused at centrifuge:8000"
    }
  }
}
```

#### Pydantic for Django Ninja
```python
from typing import Dict, Optional
from datetime import datetime

class ServiceStatus(Schema):
    status: str  # "healthy" | "degraded" | "down"
    latency_ms: Optional[int]
    error: Optional[str] = None

class SystemStatusOut(Schema):
    overall: str
    checked_at: datetime
    services: Dict[str, ServiceStatus]
```

#### List Model Involved
- None (infrastructure probe only — no ORM queries)

#### Django ORM Query (Proposed)
```python
import time
import requests as http_requests
from django.db import connections
from django.core.cache import cache
from django.utils import timezone

@router.get("/system/status", response=SystemStatusOut)
def system_status(request):
    services = {}
    now = timezone.now()

    # --- PostgreSQL ---
    t0 = time.monotonic()
    try:
        connections["default"].ensure_connection()
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        services["postgres"] = ServiceStatus(
            status="healthy",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:
        services["postgres"] = ServiceStatus(status="down", latency_ms=None, error=str(e))

    # --- Redis ---
    t0 = time.monotonic()
    try:
        cache.set("__health__", "1", timeout=5)
        assert cache.get("__health__") == "1"
        services["redis"] = ServiceStatus(
            status="healthy",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:
        services["redis"] = ServiceStatus(status="down", latency_ms=None, error=str(e))

    # --- ChromaDB ---
    t0 = time.monotonic()
    try:
        import chromadb
        client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        client.heartbeat()
        services["chromadb"] = ServiceStatus(
            status="healthy",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:
        services["chromadb"] = ServiceStatus(status="down", latency_ms=None, error=str(e))

    # --- Centrifuge ---
    t0 = time.monotonic()
    try:
        resp = http_requests.get(f"{settings.CENTRIFUGE_API_URL}/health", timeout=2)
        resp.raise_for_status()
        services["centrifuge"] = ServiceStatus(
            status="healthy",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:
        services["centrifuge"] = ServiceStatus(status="degraded", latency_ms=None, error=str(e))

    # --- Overall ---
    statuses = [s.status for s in services.values()]
    if services["postgres"].status == "down":
        overall = "down"
    elif any(s in ("down", "degraded") for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return SystemStatusOut(overall=overall, checked_at=now, services=services)
```

---

### GET /api/v1/system/features

#### Detail
Returns the feature flag state for the current company. Flags are resolved from two layers: global defaults in `settings.FEATURE_FLAGS` (base layer) and per-company overrides stored in `Company.metadata["feature_flags"]` (override layer). Company-level overrides take full precedence, enabling experimental features for specific tenants without a code deploy.

#### Flow
1. Authenticate via Supabase JWT
2. Load `FEATURE_FLAGS` dict from `settings.py` (global defaults)
3. Load `current_company.metadata.get("feature_flags", {})` (company overrides)
4. Merge: company values override global values
5. Track source of each flag (`"global"` vs `"company_override"`)
6. Return merged flags + source map

#### Request JSON
```json
// No body — GET request
// GET /api/v1/system/features
```

#### Response JSON
```json
{
  "features": {
    "semantic_search": true,
    "agent_runs": true,
    "mcp_servers": false,
    "streaming_responses": true,
    "knowledge_base_reindex": true,
    "rbac_v2": false,
    "admin_metrics": true
  },
  "source": {
    "semantic_search": "global",
    "mcp_servers": "company_override",
    "rbac_v2": "global"
  }
}
```

#### Pydantic for Django Ninja
```python
from typing import Dict

class SystemFeaturesOut(Schema):
    features: Dict[str, bool]
    source: Dict[str, str]  # "global" | "company_override"
```

#### List Model Involved
- `Company` — reads `metadata` JSON field for per-company overrides

#### Django ORM Query (Proposed)
```python
@router.get("/system/features", response=SystemFeaturesOut)
def system_features(request):
    company = request.auth.current_company

    global_flags: dict = getattr(settings, "FEATURE_FLAGS", {})
    company_overrides: dict = company.metadata.get("feature_flags", {})

    merged = {}
    sources = {}

    for key, value in global_flags.items():
        if key in company_overrides:
            merged[key] = company_overrides[key]
            sources[key] = "company_override"
        else:
            merged[key] = value
            sources[key] = "global"

    # Company-only flags not present in global defaults
    for key, value in company_overrides.items():
        if key not in merged:
            merged[key] = value
            sources[key] = "company_override"

    return SystemFeaturesOut(features=merged, source=sources)
```

---

## Streaming (Centrifuge)

---

### GET /api/v1/stream/topics/{topic_id}

#### Detail
Issues a short-lived Centrifuge subscription JWT for the channel `topic:{topic_id}`, confirming the requesting user is a participant in that topic. Also returns the last N messages as the initial state payload so the client can hydrate the UI before the WebSocket connection is established. The client then connects directly to the Centrifuge WebSocket server using this token.

#### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatTopic` by `id=topic_id`, `company=current_company`
3. Verify user is a participant (`TopicParticipant` — see proposed model below)
4. Fallback: check `ProjectMember` if `TopicParticipant` not present
5. Generate Centrifuge subscription JWT for channel `topic:{topic_id}` with TTL (300s)
6. Fetch last N messages (default 50) ordered `created_at ASC`
7. Return token + initial messages + Centrifuge WebSocket URL

#### Request JSON
```json
// Query parameter only: ?last_n=50
// GET /api/v1/stream/topics/3fa85f64-5717-4562-b3fc-2c963f66afa6?last_n=50
```

#### Response JSON
```json
{
  "channel": "topic:3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "ws_url": "wss://nexus.example.com/connection/websocket",
  "expires_in": 300,
  "initial_messages": [
    {
      "id": "msg-uuid-1",
      "content": "Hello, how can I help?",
      "message_type": "text",
      "status": "completed",
      "sender": {
        "id": "user-uuid",
        "username": "aria_persona",
        "user_type": "persona"
      },
      "created_at": "2025-01-15T09:55:00Z"
    }
  ]
}
```

#### Pydantic for Django Ninja
```python
from typing import List, Optional
import jwt as pyjwt
import time

class MessageSenderOut(Schema):
    id: UUID
    username: str
    user_type: str

class StreamMessageOut(Schema):
    id: UUID
    content: str
    message_type: str
    status: str
    sender: Optional[MessageSenderOut]
    created_at: datetime

class TopicStreamOut(Schema):
    channel: str
    token: str
    ws_url: str
    expires_in: int
    initial_messages: List[StreamMessageOut]
```

#### List Model Involved
- `ChatTopic` — fetched by ID, company scope
- `ChatMessage` — last N messages for initial hydration
- `User` — sender details per message
- `TopicParticipant` *(proposed)* — membership verification
- `ProjectMember` — fallback access check

#### Django ORM Query (Proposed)
```python
import jwt as pyjwt
import time

CENTRIFUGE_SECRET = settings.CENTRIFUGE_SECRET_KEY
CENTRIFUGE_WS_URL = settings.CENTRIFUGE_WS_URL

@router.get("/stream/topics/{topic_id}", response=TopicStreamOut)
def stream_topic(request, topic_id: UUID, last_n: int = 50):
    company = request.auth.current_company

    topic = get_object_or_404(
        ChatTopic,
        id=topic_id,
        company=company,
        is_active=True,
    )

    # Verify participation
    is_participant = TopicParticipant.objects.filter(
        topic=topic,
        user=request.auth,
        is_active=True,
    ).exists()

    if not is_participant:
        # Fallback: project membership grants implicit topic access
        is_participant = ProjectMember.objects.filter(
            project=topic.project,
            user=request.auth,
            is_active=True,
        ).exists()

    if not is_participant:
        raise HttpError(403, "Not a participant of this topic.")

    channel = f"topic:{topic_id}"
    now = int(time.time())
    expires_in = 300

    token = pyjwt.encode(
        {
            "sub": str(request.auth.id),
            "channel": channel,
            "iat": now,
            "exp": now + expires_in,
        },
        CENTRIFUGE_SECRET,
        algorithm="HS256",
    )

    messages = list(
        reversed(
            list(
                ChatMessage.objects.filter(
                    topic=topic,
                    is_active=True,
                )
                .select_related("sender")
                .order_by("-created_at")[:last_n]
            )
        )
    )

    return TopicStreamOut(
        channel=channel,
        token=token,
        ws_url=CENTRIFUGE_WS_URL,
        expires_in=expires_in,
        initial_messages=messages,
    )
```

---

### GET /api/v1/stream/messages/{message_id}

#### Detail
Issues a Centrifuge subscription JWT for channel `message:{message_id}`. Only valid when the message is in `pending` or `streaming` status — if already `completed`, `failed`, or `cancelled`, returns the final content directly without issuing a stream token. Used for real-time AI response streaming.

#### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`
3. Verify user has access to the message's topic (participant or project member)
4. If `status` is terminal (`completed`, `failed`, `cancelled`): return final content, `is_final=true`, no token
5. If `status` is `pending` or `streaming`: generate Centrifuge JWT for `message:{message_id}`
6. Return token + `content_so_far` + `is_final=false`

#### Request JSON
```json
// No body — GET request
// GET /api/v1/stream/messages/msg-uuid-here
```

#### Response JSON
```json
// Active streaming:
{
  "message_id": "msg-uuid-here",
  "status": "streaming",
  "channel": "message:msg-uuid-here",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "ws_url": "wss://nexus.example.com/connection/websocket",
  "expires_in": 300,
  "content_so_far": "Based on the knowledge base, I can see that...",
  "is_final": false
}

// Already completed:
{
  "message_id": "msg-uuid-here",
  "status": "completed",
  "channel": null,
  "token": null,
  "ws_url": null,
  "expires_in": null,
  "content_so_far": "Based on the knowledge base, the answer is...",
  "is_final": true
}
```

#### Pydantic for Django Ninja
```python
class MessageStreamOut(Schema):
    message_id: UUID
    status: str
    channel: Optional[str]
    token: Optional[str]
    ws_url: Optional[str]
    expires_in: Optional[int]
    content_so_far: str
    is_final: bool
```

#### List Model Involved
- `ChatMessage` — fetched by ID; status and content read
- `ChatTopic` — access check (via `message.topic`)
- `TopicParticipant` *(proposed)* — access validation
- `ProjectMember` — fallback access check

#### Django ORM Query (Proposed)
```python
@router.get("/stream/messages/{message_id}", response=MessageStreamOut)
def stream_message(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic", "topic__project"),
        id=message_id,
        company=company,
        is_active=True,
    )

    is_participant = TopicParticipant.objects.filter(
        topic=message.topic,
        user=request.auth,
        is_active=True,
    ).exists() or ProjectMember.objects.filter(
        project=message.topic.project,
        user=request.auth,
        is_active=True,
    ).exists()

    if not is_participant:
        raise HttpError(403, "Access denied.")

    TERMINAL = {
        ChatMessage.Status.COMPLETED,
        ChatMessage.Status.FAILED,
        ChatMessage.Status.CANCELLED,
    }

    if message.status in TERMINAL:
        return MessageStreamOut(
            message_id=message.id,
            status=message.status,
            channel=None, token=None, ws_url=None, expires_in=None,
            content_so_far=message.content,
            is_final=True,
        )

    channel = f"message:{message_id}"
    now = int(time.time())
    expires_in = 300

    token = pyjwt.encode(
        {
            "sub": str(request.auth.id),
            "channel": channel,
            "iat": now,
            "exp": now + expires_in,
        },
        CENTRIFUGE_SECRET,
        algorithm="HS256",
    )

    return MessageStreamOut(
        message_id=message.id,
        status=message.status,
        channel=channel,
        token=token,
        ws_url=CENTRIFUGE_WS_URL,
        expires_in=expires_in,
        content_so_far=message.content,
        is_final=False,
    )
```

---

### POST /api/v1/stream/agents/{run_id}/cancel

#### Detail
Cancels an active `AgentRun` and publishes a `run.cancelled` event to the Centrifuge channel `agent_run:{run_id}` so all connected clients know the stream has ended. Only works on runs in `pending` or `running` status. Authorization: run triggerer OR company `owner`/`admin`.

#### Flow
1. Authenticate via Supabase JWT
2. Fetch `AgentRun` by `id=run_id`, `company=current_company`
3. Validate: status must be `pending` or `running` — 409 otherwise
4. Validate: user is `triggered_by` OR has `role in [owner, admin]` — 403 otherwise
5. Update `AgentRun.status = "cancelled"`, `completed_at = now()`
6. Publish `run.cancelled` event to Centrifuge channel via HTTP API
7. Signal Celery worker via Redis cache key `cancel_run:{run_id}`
8. Write `AuditEvent(action="agent_run.cancelled")`
9. Return updated run

#### Request JSON
```json
{
  "reason": "User cancelled the run manually."
}
```

#### Response JSON
```json
{
  "id": "run-uuid-here",
  "status": "cancelled",
  "agent_id": "agent-uuid-here",
  "topic_id": "topic-uuid-here",
  "triggered_by": "user-uuid-here",
  "completed_at": "2025-01-15T12:05:00Z",
  "message": "Run cancelled and stream terminated."
}
```

#### Pydantic for Django Ninja
```python
class CancelRunIn(Schema):
    reason: Optional[str] = None

class CancelRunOut(Schema):
    id: UUID
    status: str
    agent_id: Optional[UUID]
    topic_id: Optional[UUID]
    triggered_by: Optional[UUID]
    completed_at: Optional[datetime]
    message: str
```

#### List Model Involved
- `AgentRun` — status updated to `cancelled`
- `CompanyAccess` — role check for non-triggering users
- `AuditEvent` — cancellation logged

#### Django ORM Query (Proposed)
```python
import requests as http_requests
from django.core.cache import cache

@router.post("/stream/agents/{run_id}/cancel", response=CancelRunOut)
def cancel_agent_run_stream(request, run_id: UUID, body: CancelRunIn = Body(...)):
    company = request.auth.current_company
    user = request.auth

    run = get_object_or_404(
        AgentRun,
        id=run_id,
        company=company,
        is_active=True,
    )

    CANCELLABLE = {AgentRun.Status.PENDING, AgentRun.Status.RUNNING}
    if run.status not in CANCELLABLE:
        raise HttpError(409, f"Cannot cancel a run in '{run.status}' state.")

    is_triggerer = run.triggered_by_id == user.id
    is_privileged = CompanyAccess.objects.filter(
        company=company,
        user=user,
        role__in=["owner", "admin"],
        is_active=True,
    ).exists()

    if not is_triggerer and not is_privileged:
        raise HttpError(403, "Not authorized to cancel this run.")

    now = timezone.now()
    run.status = AgentRun.Status.CANCELLED
    run.completed_at = now
    run.save(update_fields=["status", "completed_at", "updated_at"])

    # Publish run.cancelled to Centrifuge (non-fatal if Centrifuge is down)
    channel = f"agent_run:{run_id}"
    try:
        http_requests.post(
            f"{settings.CENTRIFUGE_API_URL}/api",
            json={
                "method": "publish",
                "params": {
                    "channel": channel,
                    "data": {
                        "type": "run.cancelled",
                        "run_id": str(run_id),
                        "reason": body.reason or "Cancelled by user",
                    },
                },
            },
            headers={"Authorization": f"apikey {settings.CENTRIFUGE_API_KEY}"},
            timeout=3,
        )
    except Exception:
        pass

    # Signal Celery worker to halt processing
    cache.set(f"cancel_run:{run_id}", "1", timeout=300)

    AuditEvent.objects.create(
        company=company,
        actor=user,
        action="agent_run.cancelled",
        target_type="agent_run",
        target_id=run.id,
        payload={"reason": body.reason, "previous_status": "running"},
    )

    return CancelRunOut(
        id=run.id,
        status=run.status,
        agent_id=run.agent_id,
        topic_id=run.topic_id,
        triggered_by=run.triggered_by_id,
        completed_at=run.completed_at,
        message="Run cancelled and stream terminated.",
    )
```

---

## Admin

> **All admin endpoints require `is_staff=True` or `is_superuser=True`. No company scope — these are cross-tenant views.**

---

### GET /api/v1/admin/users

#### Detail
Returns a paginated, cross-company list of all `User` records with annotations. Includes `company_count` (number of active company memberships per user). Supports filtering by `user_type`, `is_active`, and text search by `username` or `email`.

#### Flow
1. Authenticate via Supabase JWT
2. Validate `is_staff or is_superuser` — raise 403 otherwise
3. Query all `User` records (no company filter)
4. Annotate with `company_count` via `Count("company_access", filter=Q(is_active=True))`
5. Apply optional filters
6. Paginate and return

#### Request JSON
```json
// GET /api/v1/admin/users?user_type=human&is_active=true&search=john&page=1&page_size=50
```

#### Response JSON
```json
{
  "count": 124,
  "next": "/api/v1/admin/users?page=2",
  "previous": null,
  "results": [
    {
      "id": "user-uuid",
      "username": "john_doe",
      "email": "john@example.com",
      "user_type": "human",
      "is_active": true,
      "is_staff": false,
      "is_superuser": false,
      "company_count": 3,
      "date_joined": "2024-06-01T00:00:00Z",
      "last_login": "2025-01-14T18:22:00Z"
    }
  ]
}
```

#### Pydantic for Django Ninja
```python
class AdminUserOut(Schema):
    id: UUID
    username: str
    email: str
    user_type: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    company_count: int
    date_joined: Optional[datetime]
    last_login: Optional[datetime]

class AdminUserListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[AdminUserOut]
```

#### List Model Involved
- `User` — all users, cross-tenant
- `CompanyAccess` — annotated count of active memberships

#### Django ORM Query (Proposed)
```python
from django.db.models import Count, Q

def require_staff(request):
    if not (request.auth.is_staff or request.auth.is_superuser):
        raise HttpError(403, "Admin access required.")

@router.get("/admin/users", response=AdminUserListOut)
def admin_list_users(
    request,
    user_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    require_staff(request)

    qs = User.objects.annotate(
        company_count=Count(
            "company_access",
            filter=Q(company_access__is_active=True),
            distinct=True,
        )
    ).order_by("-date_joined")

    if user_type:
        qs = qs.filter(user_type=user_type)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    if search:
        qs = qs.filter(
            Q(username__icontains=search) | Q(email__icontains=search)
        )

    total = qs.count()
    offset = (page - 1) * page_size
    results = list(qs[offset : offset + page_size])

    return AdminUserListOut(
        count=total,
        next=f"/api/v1/admin/users?page={page + 1}" if offset + page_size < total else None,
        previous=f"/api/v1/admin/users?page={page - 1}" if page > 1 else None,
        results=results,
    )
```

---

### GET /api/v1/admin/companies

#### Detail
Returns a paginated, annotated list of all companies on the platform. Each company is annotated with live counts: members, active agents, knowledge bases, and active agent runs. Used for platform-wide monitoring and billing-related audits.

#### Flow
1. Authenticate + validate `is_staff` or `is_superuser`
2. Query all `Company` records
3. Annotate with `member_count`, `agent_count`, `kb_count`, `active_run_count`
4. Apply optional `is_active` filter and search by name/slug
5. Paginate and return

#### Request JSON
```json
// GET /api/v1/admin/companies?is_active=true&search=acme&page=1&page_size=20
```

#### Response JSON
```json
{
  "count": 38,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "company-uuid",
      "name": "Acme Corp",
      "slug": "acme-corp",
      "is_personal": false,
      "is_active": true,
      "member_count": 14,
      "agent_count": 5,
      "kb_count": 8,
      "active_run_count": 2,
      "created_at": "2024-03-10T00:00:00Z"
    }
  ]
}
```

#### Pydantic for Django Ninja
```python
class AdminCompanyOut(Schema):
    id: UUID
    name: str
    slug: str
    is_personal: bool
    is_active: bool
    member_count: int
    agent_count: int
    kb_count: int
    active_run_count: int
    created_at: datetime

class AdminCompanyListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[AdminCompanyOut]
```

#### List Model Involved
- `Company` — primary queryset
- `CompanyAccess` — `member_count` annotation
- `AIAgent` — `agent_count` annotation
- `KnowledgeBase` — `kb_count` annotation
- `AgentRun` — `active_run_count` annotation

#### Django ORM Query (Proposed)
```python
@router.get("/admin/companies", response=AdminCompanyListOut)
def admin_list_companies(
    request,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    require_staff(request)

    qs = Company.objects.annotate(
        member_count=Count(
            "access_list",
            filter=Q(access_list__is_active=True),
            distinct=True,
        ),
        agent_count=Count(
            "aiagent_items",
            filter=Q(aiagent_items__is_active=True),
            distinct=True,
        ),
        kb_count=Count(
            "knowledgebase_items",
            filter=Q(knowledgebase_items__is_active=True),
            distinct=True,
        ),
        active_run_count=Count(
            "agentrun_items",
            filter=Q(agentrun_items__status__in=["pending", "running"]),
            distinct=True,
        ),
    ).order_by("-created_at")

    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))

    total = qs.count()
    offset = (page - 1) * page_size
    results = list(qs[offset : offset + page_size])

    return AdminCompanyListOut(
        count=total,
        next=f"/api/v1/admin/companies?page={page + 1}" if offset + page_size < total else None,
        previous=f"/api/v1/admin/companies?page={page - 1}" if page > 1 else None,
        results=results,
    )
```

---

### GET /api/v1/admin/system-metrics

#### Detail
Returns platform-wide aggregate metrics: record counts across all major models (no company filter), plus live infrastructure stats from Redis and ChromaDB. Used for the ops dashboard, capacity planning, and SLA reporting.

#### Flow
1. Authenticate + validate `is_staff` or `is_superuser`
2. Run aggregate COUNT queries across all major models
3. Collect Redis info via `redis.info()`
4. Collect ChromaDB collection count + total vector count via `list_collections()`
5. Assemble and return

#### Request JSON
```json
// No body — GET request
// GET /api/v1/admin/system-metrics
```

#### Response JSON
```json
{
  "collected_at": "2025-01-15T12:00:00Z",
  "platform_totals": {
    "companies": 38,
    "users": 412,
    "projects": 195,
    "chat_topics": 1840,
    "chat_messages": 98340,
    "ai_agents": 88,
    "agent_runs_total": 12500,
    "agent_runs_active": 4,
    "agent_runs_completed": 11900,
    "agent_runs_failed": 596,
    "knowledge_bases": 72,
    "knowledge_files": 340,
    "embedding_jobs_total": 380,
    "embedding_jobs_pending": 5,
    "vector_documents": 24200,
    "notifications_unread": 1520,
    "audit_events": 48900
  },
  "infrastructure": {
    "redis": {
      "used_memory_mb": 128,
      "connected_clients": 14,
      "keyspace_hits": 48200,
      "keyspace_misses": 1800
    },
    "chromadb": {
      "collections": 72,
      "total_vectors": 24200
    }
  }
}
```

#### Pydantic for Django Ninja
```python
class PlatformTotalsOut(Schema):
    companies: int
    users: int
    projects: int
    chat_topics: int
    chat_messages: int
    ai_agents: int
    agent_runs_total: int
    agent_runs_active: int
    agent_runs_completed: int
    agent_runs_failed: int
    knowledge_bases: int
    knowledge_files: int
    embedding_jobs_total: int
    embedding_jobs_pending: int
    vector_documents: int
    notifications_unread: int
    audit_events: int

class RedisMetricsOut(Schema):
    used_memory_mb: int
    connected_clients: int
    keyspace_hits: int
    keyspace_misses: int

class ChromaMetricsOut(Schema):
    collections: int
    total_vectors: int

class InfraMetricsOut(Schema):
    redis: Optional[RedisMetricsOut]
    chromadb: Optional[ChromaMetricsOut]

class SystemMetricsOut(Schema):
    collected_at: datetime
    platform_totals: PlatformTotalsOut
    infrastructure: InfraMetricsOut
```

#### List Model Involved
- `Company`, `User`, `Project`, `ChatTopic`, `ChatMessage`
- `AIAgent`, `AgentRun`
- `KnowledgeBase`, `KnowledgeFile`
- `EmbeddingJob`, `VectorDocument`
- `Notification`, `AuditEvent`

#### Django ORM Query (Proposed)
```python
@router.get("/admin/system-metrics", response=SystemMetricsOut)
def admin_system_metrics(request):
    require_staff(request)

    totals = PlatformTotalsOut(
        companies=Company.objects.count(),
        users=User.objects.count(),
        projects=Project.objects.count(),
        chat_topics=ChatTopic.objects.count(),
        chat_messages=ChatMessage.objects.count(),
        ai_agents=AIAgent.objects.count(),
        agent_runs_total=AgentRun.objects.count(),
        agent_runs_active=AgentRun.objects.filter(
            status__in=["pending", "running"]
        ).count(),
        agent_runs_completed=AgentRun.objects.filter(status="completed").count(),
        agent_runs_failed=AgentRun.objects.filter(status="failed").count(),
        knowledge_bases=KnowledgeBase.objects.count(),
        knowledge_files=KnowledgeFile.objects.count(),
        embedding_jobs_total=EmbeddingJob.objects.count(),
        embedding_jobs_pending=EmbeddingJob.objects.filter(status="pending").count(),
        vector_documents=VectorDocument.objects.count(),
        notifications_unread=Notification.objects.filter(
            is_read=False, is_active=True
        ).count(),
        audit_events=AuditEvent.objects.count(),
    )

    # Redis
    redis_metrics = None
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(settings.CELERY_BROKER_URL)
        info = r.info()
        redis_metrics = RedisMetricsOut(
            used_memory_mb=info["used_memory"] // (1024 * 1024),
            connected_clients=info["connected_clients"],
            keyspace_hits=info.get("keyspace_hits", 0),
            keyspace_misses=info.get("keyspace_misses", 0),
        )
    except Exception:
        pass

    # ChromaDB
    chroma_metrics = None
    try:
        import chromadb
        client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        collections = client.list_collections()
        chroma_metrics = ChromaMetricsOut(
            collections=len(collections),
            total_vectors=sum(c.count() for c in collections),
        )
    except Exception:
        pass

    return SystemMetricsOut(
        collected_at=timezone.now(),
        platform_totals=totals,
        infrastructure=InfraMetricsOut(redis=redis_metrics, chromadb=chroma_metrics),
    )
```

---

### POST /api/v1/admin/reindex-all

#### Detail
Triggers a platform-wide re-embedding of all active `KnowledgeFile` records across all companies. Skips files that already have an active (`pending` or `running`) `EmbeddingJob`. Supports optional `dry_run` to preview scope. Supports `company_id` to scope reindex to a single tenant. Uses `bulk_create` for efficiency.

#### Flow
1. Authenticate + validate `is_staff` or `is_superuser`
2. If `dry_run=true`: count eligible files and return without creating jobs
3. Query all active `KnowledgeFile` records (optionally filtered by `company_id`)
4. Exclude files with an existing `pending` or `running` `EmbeddingJob`
5. Bulk create `EmbeddingJob` records (`batch_size=500`)
6. Dispatch `run_embedding_job.delay(job.id)` for each created job
7. Write `AuditEvent(action="admin.reindex_all")`
8. Return summary

#### Request JSON
```json
{
  "dry_run": false,
  "company_id": null
}
```

> `company_id` — optional UUID. If omitted, all companies are included.

#### Response JSON
```json
{
  "status": "dispatched",
  "jobs_created": 312,
  "files_skipped": 28,
  "dry_run": false,
  "company_filter": null,
  "message": "312 embedding jobs dispatched."
}
```

#### Pydantic for Django Ninja
```python
class ReindexAllIn(Schema):
    dry_run: bool = False
    company_id: Optional[UUID] = None

class ReindexAllOut(Schema):
    status: str
    jobs_created: int
    files_skipped: int
    dry_run: bool
    company_filter: Optional[UUID]
    message: str
```

#### List Model Involved
- `KnowledgeFile` — source records to re-embed
- `EmbeddingJob` — created for eligible files; existing active jobs checked
- `AuditEvent` — admin action logged

#### Django ORM Query (Proposed)
```python
@router.post("/admin/reindex-all", response=ReindexAllOut)
def admin_reindex_all(request, body: ReindexAllIn):
    require_staff(request)

    files_qs = KnowledgeFile.objects.filter(is_active=True)

    if body.company_id:
        files_qs = files_qs.filter(knowledge_base__company_id=body.company_id)

    # Files with an already-active embedding job
    active_file_ids = EmbeddingJob.objects.filter(
        target_type="knowledge_file",
        status__in=["pending", "running"],
    ).values_list("target_id", flat=True)

    eligible_files = files_qs.exclude(id__in=active_file_ids)
    skipped = files_qs.count() - eligible_files.count()

    if body.dry_run:
        return ReindexAllOut(
            status="dry_run",
            jobs_created=eligible_files.count(),
            files_skipped=skipped,
            dry_run=True,
            company_filter=body.company_id,
            message=f"Dry run: {eligible_files.count()} jobs would be created.",
        )

    jobs = [
        EmbeddingJob(
            company=f.knowledge_base.company,
            target_type="knowledge_file",
            target_id=f.id,
            status="pending",
        )
        for f in eligible_files.select_related("knowledge_base")
    ]

    created = EmbeddingJob.objects.bulk_create(jobs, batch_size=500)

    from celery_app.tasks import run_embedding_job
    for job in created:
        run_embedding_job.delay(str(job.id))

    AuditEvent.objects.create(
        company=request.auth.current_company,
        actor=request.auth,
        action="admin.reindex_all",
        target_type="platform",
        target_id=None,
        payload={
            "jobs_created": len(created),
            "files_skipped": skipped,
            "company_filter": str(body.company_id) if body.company_id else None,
        },
    )

    return ReindexAllOut(
        status="dispatched",
        jobs_created=len(created),
        files_skipped=skipped,
        dry_run=False,
        company_filter=body.company_id,
        message=f"{len(created)} embedding jobs dispatched.",
    )
```

---

### POST /api/v1/admin/rebuild-search

#### Detail
Rebuilds PostgreSQL GIN full-text search indexes using `REINDEX INDEX CONCURRENTLY` — which does not block reads during the rebuild. Targets all registered GIN indexes across `ChatMessage`, `KnowledgeFile`, `ChatTopic`, and `KnowledgeChunk` tables. Accepts an optional `tables` filter to limit scope. Returns per-index timing results.

#### Flow
1. Authenticate + validate `is_staff` or `is_superuser`
2. Resolve GIN index list from `GIN_INDEX_REGISTRY` (optionally filtered by `body.tables`)
3. Open a Django raw cursor
4. For each index, execute `REINDEX INDEX CONCURRENTLY {index_name}` and record duration
5. Write `AuditEvent(action="admin.rebuild_search")`
6. Return per-index results + total duration

#### Request JSON
```json
{
  "tables": ["chat_message", "knowledge_file"]
}
```

> `tables` — optional list. If omitted, all registered GIN indexes are rebuilt.

#### Response JSON
```json
{
  "status": "completed",
  "indexes_rebuilt": [
    {
      "index_name": "chat_message_content_gin",
      "table": "workspace_chat_message",
      "duration_ms": 4820
    },
    {
      "index_name": "knowledge_file_name_gin",
      "table": "intelligence_knowledge_file",
      "duration_ms": 1230
    }
  ],
  "total_duration_ms": 6050,
  "rebuilt_at": "2025-01-15T13:00:00Z"
}
```

#### Pydantic for Django Ninja
```python
class RebuildSearchIn(Schema):
    tables: Optional[List[str]] = None  # None = all registered tables

class IndexRebuildResult(Schema):
    index_name: str
    table: str
    duration_ms: int  # -1 = failed

class RebuildSearchOut(Schema):
    status: str
    indexes_rebuilt: List[IndexRebuildResult]
    total_duration_ms: int
    rebuilt_at: datetime
```

#### List Model Involved
- None (raw DDL SQL — no ORM models involved)
- `AuditEvent` — rebuild action logged

#### Django ORM Query (Proposed)
```python
import time as _time
from django.db import connection

GIN_INDEX_REGISTRY = [
    {"index_name": "chat_message_content_gin",   "table": "workspace_chat_message"},
    {"index_name": "knowledge_file_name_gin",     "table": "intelligence_knowledge_file"},
    {"index_name": "chat_topic_title_gin",        "table": "workspace_chat_topic"},
    {"index_name": "knowledge_chunk_text_gin",    "table": "intelligence_knowledge_chunk"},
]

@router.post("/admin/rebuild-search", response=RebuildSearchOut)
def admin_rebuild_search(request, body: RebuildSearchIn):
    require_staff(request)

    targets = GIN_INDEX_REGISTRY
    if body.tables:
        targets = [
            idx for idx in GIN_INDEX_REGISTRY
            if any(t in idx["table"] for t in body.tables)
        ]

    results = []
    overall_start = _time.monotonic()

    with connection.cursor() as cursor:
        for idx in targets:
            t0 = _time.monotonic()
            try:
                # CONCURRENTLY cannot run inside a transaction block;
                # ensure Django's autocommit is active for DDL statements
                cursor.execute(
                    f"REINDEX INDEX CONCURRENTLY {idx['index_name']}"
                )
                results.append(IndexRebuildResult(
                    index_name=idx["index_name"],
                    table=idx["table"],
                    duration_ms=int((_time.monotonic() - t0) * 1000),
                ))
            except Exception:
                results.append(IndexRebuildResult(
                    index_name=idx["index_name"],
                    table=idx["table"],
                    duration_ms=-1,
                ))

    total_ms = int((_time.monotonic() - overall_start) * 1000)
    now = timezone.now()

    AuditEvent.objects.create(
        company=request.auth.current_company,
        actor=request.auth,
        action="admin.rebuild_search",
        target_type="platform",
        target_id=None,
        payload={
            "indexes_rebuilt": [r.index_name for r in results],
            "total_duration_ms": total_ms,
        },
    )

    return RebuildSearchOut(
        status="completed",
        indexes_rebuilt=results,
        total_duration_ms=total_ms,
        rebuilt_at=now,
    )
```

---

## Model Reference Summary

| Model           | DB Table                        | Used In                              |
|-----------------|---------------------------------|--------------------------------------|
| `Notification`  | `governance_notification`       | Notifications (all three endpoints)  |
| `Company`       | `governance_company`            | System/Features, Admin               |
| `CompanyAccess` | `governance_company_access`     | Stream cancel auth, Admin users      |
| `User`          | `accounts_user`                 | All sections                         |
| `ChatTopic`     | `workspace_chat_topic`          | Streaming — topic subscription       |
| `ChatMessage`   | `workspace_chat_message`        | Streaming — message subscription     |
| `AgentRun`      | `intelligence_agent_run`        | Streaming — run cancel               |
| `AIAgent`       | `intelligence_ai_agent`         | Admin company annotation             |
| `KnowledgeBase` | `intelligence_knowledge_base`   | Admin company annotation             |
| `KnowledgeFile` | `intelligence_knowledge_file`   | Admin reindex-all                    |
| `EmbeddingJob`  | `intelligence_embedding_job`    | Admin reindex-all                    |
| `VectorDocument`| `intelligence_vector_document`  | Admin system-metrics                 |
| `AuditEvent`    | `governance_audit_event`        | Stream cancel, Admin actions         |
| `Project`       | `workspace_project`             | Admin system-metrics                 |

---

## Proposed Models (Not Yet Migrated)

### TopicParticipant *(required by streaming endpoints)*

```python
class TopicParticipant(ProjectBaseModel):
    """
    Tracks which users are active participants in a ChatTopic.
    Used for streaming access control and presence indicators.
    Falls back to ProjectMember if this table does not yet exist.
    """
    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_participations",
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workspace_topic_participant"
        constraints = [
            models.UniqueConstraint(
                fields=["topic", "user"],
                name="uniq_topic_participant",
            )
        ]
        indexes = [
            models.Index(fields=["topic", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]
```

> **Migration needed**: `python manage.py makemigrations nucleus --name add_topic_participant`

---

*End of Notifications, System, Streaming & Admin API Documentation*
