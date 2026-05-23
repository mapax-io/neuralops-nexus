# NeuralOps — Message API Documentation

> Section 9 · 12 Endpoints
> Framework: Django 5.2 + Django Ninja · Auth: Supabase JWT · Real-time: Centrifuge (nexus-transport)

---

## Table of Contents

1. [GET /topics/{topic_id}/messages](#get-apiv1topicstopic_idmessages)
2. [POST /topics/{topic_id}/messages](#post-apiv1topicstopic_idmessages)
3. [GET /messages/{message_id}](#get-apiv1messagesmessage_id)
4. [PATCH /messages/{message_id}](#patch-apiv1messagesmessage_id)
5. [DELETE /messages/{message_id}](#delete-apiv1messagesmessage_id)
6. [POST /messages/{message_id}/truncate](#post-apiv1messagesmessage_idtruncate)
7. [POST /messages/{message_id}/retry](#post-apiv1messagesmessage_idretry)
8. [POST /messages/{message_id}/cancel](#post-apiv1messagesmessage_idcancel)
9. [POST /messages/{message_id}/forms/{block_key}/submit](#post-apiv1messagesmessage_idformsblock_keysubmit)
10. [GET /messages/{message_id}/blocks](#get-apiv1messagesmessage_idblocks)
11. [POST /messages/{message_id}/reactions](#post-apiv1messagesmessage_idreactions)
12. [DELETE /messages/{message_id}/reactions/{reaction_id}](#delete-apiv1messagesmessage_idreactionsreaction_id)

---

## Key Conventions

### Access Control
All message endpoints require Supabase JWT auth scoped to `request.auth.current_company`. A user must be either a `TopicParticipant` in the target topic **or** a `ProjectMember` in the parent project to read or write messages.

### Centrifuge Publishing
On every write mutation (create, edit, delete, react), the endpoint publishes an event to the Centrifuge channel `topic:{topic_id}` so all connected WebSocket clients receive the update in real-time.

```python
# Shared publish helper
def publish_to_topic(topic_id, event_type, payload):
    import requests as http_req
    try:
        http_req.post(
            f"{settings.CENTRIFUGE_API_URL}/api",
            json={
                "method": "publish",
                "params": {
                    "channel": f"topic:{topic_id}",
                    "data": {"type": event_type, **payload},
                },
            },
            headers={"Authorization": f"apikey {settings.CENTRIFUGE_API_KEY}"},
            timeout=2,
        )
    except Exception:
        pass  # Non-fatal
```

### Soft Delete
Messages are soft-deleted via `SoftDeleteModel.soft_delete()` — `is_active=False`, `deleted_at=now()`. Soft-deleted messages are excluded from all list queries but their reactions and attachments are preserved for audit purposes.

### MessageBlock (Proposed Model)
The `content_json` field on `ChatMessage` stores structured blocks (forms, graphs, tool outputs). For the `/blocks` and `/forms/{block_key}/submit` endpoints a dedicated `MessageBlock` model is proposed — see the [Proposed Models](#proposed-models-not-yet-migrated) section.

---

## GET /api/v1/topics/{topic_id}/messages

### Detail
Returns a paginated, chronological list of all active messages in a topic. Supports cursor-based pagination (via `before` / `after` message ID) and standard page/offset pagination. Also returns an `unread_count` based on the requesting user's `ChatReadMarker`. Updates the user's read marker to the latest returned message on each successful fetch.

### Flow
1. Authenticate via Supabase JWT; scope to `current_company`
2. Fetch `ChatTopic` by `topic_id`, `company=current_company`
3. Verify user is `TopicParticipant` or `ProjectMember` — 403 otherwise
4. Build queryset: `ChatMessage` where `topic=topic`, `is_active=True`
5. Apply cursor filter if `before` / `after` query params provided
6. `select_related("sender")`, `prefetch_related("reactions", "attachments")`
7. Order by `sequence ASC` (fallback: `created_at ASC`)
8. Compute `unread_count` from `ChatReadMarker`
9. Upsert `ChatReadMarker` to latest message in result
10. Return paginated envelope

### Request JSON
```json
// Query params only — no body
// GET /api/v1/topics/uuid/messages?page=1&page_size=50&before=msg-uuid
```

### Response JSON
```json
{
  "count": 310,
  "unread_count": 4,
  "next": "/api/v1/topics/uuid/messages?page=2&page_size=50",
  "previous": null,
  "results": [
    {
      "id": "msg-uuid-1",
      "topic_id": "topic-uuid",
      "message_type": "text",
      "content": "Hello! How can I help you today?",
      "content_json": {},
      "language": "en",
      "status": "completed",
      "sequence": 1,
      "parent_id": null,
      "retry_of_id": null,
      "is_deleted_from_context": false,
      "sender": {
        "id": "user-uuid",
        "username": "aria_persona",
        "user_type": "persona"
      },
      "reactions": [
        {"id": "rxn-uuid", "emoji": "👍", "user_id": "user-uuid-2"}
      ],
      "attachments": [],
      "metadata": {},
      "created_at": "2025-01-15T09:00:00Z",
      "updated_at": "2025-01-15T09:00:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja
```python
from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class SenderOut(Schema):
    id: UUID
    username: str
    user_type: str

class ReactionOut(Schema):
    id: UUID
    emoji: str
    user_id: UUID

class AttachmentOut(Schema):
    id: UUID
    attachment_type: str
    original_filename: str
    mime_type: str
    file_size: int
    file_url: str

class MessageOut(Schema):
    id: UUID
    topic_id: UUID
    message_type: str
    content: str
    content_json: dict
    language: Optional[str]
    status: str
    sequence: int
    parent_id: Optional[UUID]
    retry_of_id: Optional[UUID]
    is_deleted_from_context: bool
    sender: Optional[SenderOut]
    reactions: List[ReactionOut]
    attachments: List[AttachmentOut]
    metadata: dict
    created_at: datetime
    updated_at: datetime

class MessageListOut(Schema):
    count: int
    unread_count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[MessageOut]
```

### List Model Involved
- `ChatTopic` — parent topic, fetched and validated
- `ChatMessage` — primary queryset
- `User` — sender details via `select_related`
- `ChatReaction` — prefetched per message
- `ChatAttachment` — prefetched per message
- `TopicParticipant` — access check
- `ProjectMember` — fallback access check
- `ChatReadMarker` — unread count computation + upsert

### Django ORM Query (Proposed)
```python
from django.utils import timezone
from django.shortcuts import get_object_or_404

@router.get("/topics/{topic_id}/messages", response=MessageListOut)
def list_messages(
    request,
    topic_id: UUID,
    page: int = 1,
    page_size: int = 50,
    before: Optional[UUID] = None,
    after: Optional[UUID] = None,
):
    company = request.auth.current_company

    topic = get_object_or_404(ChatTopic, id=topic_id, company=company, is_active=True)

    # Access check
    has_access = (
        TopicParticipant.objects.filter(topic=topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Not a participant of this topic.")

    qs = (
        ChatMessage.objects.filter(topic=topic, is_active=True)
        .select_related("sender")
        .prefetch_related("reactions", "attachments")
        .order_by("sequence", "created_at")
    )

    # Cursor pagination
    if before:
        pivot = get_object_or_404(ChatMessage, id=before, topic=topic)
        qs = qs.filter(sequence__lt=pivot.sequence)
    if after:
        pivot = get_object_or_404(ChatMessage, id=after, topic=topic)
        qs = qs.filter(sequence__gt=pivot.sequence)

    # Unread count
    marker = ChatReadMarker.objects.filter(user=request.auth, topic=topic).first()
    if marker and marker.last_read_message_id:
        unread_count = ChatMessage.objects.filter(
            topic=topic,
            is_active=True,
            sequence__gt=marker.last_read_message.sequence,
        ).count()
    else:
        unread_count = qs.count()

    total = qs.count()
    offset = (page - 1) * page_size
    results = list(qs[offset : offset + page_size])

    # Update read marker to latest message in results
    if results:
        ChatReadMarker.objects.update_or_create(
            user=request.auth,
            topic=topic,
            defaults={"last_read_message": results[-1]},
        )

    return MessageListOut(
        count=total,
        unread_count=unread_count,
        next=f"/api/v1/topics/{topic_id}/messages?page={page + 1}&page_size={page_size}" if offset + page_size < total else None,
        previous=f"/api/v1/topics/{topic_id}/messages?page={page - 1}&page_size={page_size}" if page > 1 else None,
        results=results,
    )
```

---

## POST /api/v1/topics/{topic_id}/messages

### Detail
Creates a new message in a topic. Supports human text messages and AI-triggered messages. When `message_type` is `text` or `markdown`, the message is immediately `completed`. When the sender is an AI agent or persona, or when `trigger_agent=true`, the message is created with `status=pending` and an `AgentRun` is dispatched to the Celery worker. The new message is published to `topic:{topic_id}` via Centrifuge.

### Flow
1. Authenticate via Supabase JWT; scope to `current_company`
2. Fetch `ChatTopic` by `topic_id`; verify access
3. Compute next `sequence` number via `MAX(sequence) + 1`
4. Create `ChatMessage` with `sender=request.auth`, `status=completed` (human) or `status=pending` (AI trigger)
5. If `attachments` provided, create `ChatAttachment` records linked to the message
6. If `trigger_agent=true` or topic has an assigned agent: create `AgentRun` and dispatch `run_agent_task.delay(run_id)`
7. Publish `message.created` to Centrifuge channel `topic:{topic_id}`
8. Update `ChatReadMarker` for sender to this new message
9. Return created message

### Request JSON
```json
{
  "content": "Can you summarize the latest sales report?",
  "message_type": "text",
  "parent_id": null,
  "language": "en",
  "trigger_agent": true,
  "attachment_ids": ["upload-uuid-1"],
  "metadata": {}
}
```

### Response JSON
```json
{
  "id": "msg-uuid-new",
  "topic_id": "topic-uuid",
  "message_type": "text",
  "content": "Can you summarize the latest sales report?",
  "content_json": {},
  "language": "en",
  "status": "completed",
  "sequence": 15,
  "parent_id": null,
  "retry_of_id": null,
  "is_deleted_from_context": false,
  "sender": {
    "id": "user-uuid",
    "username": "john_doe",
    "user_type": "human"
  },
  "reactions": [],
  "attachments": [
    {
      "id": "att-uuid",
      "attachment_type": "document",
      "original_filename": "sales_report.pdf",
      "mime_type": "application/pdf",
      "file_size": 204800,
      "file_url": "/media/chat_attachments/2025/01/15/sales_report.pdf"
    }
  ],
  "agent_run_id": "run-uuid-or-null",
  "metadata": {},
  "created_at": "2025-01-15T09:10:00Z",
  "updated_at": "2025-01-15T09:10:00Z"
}
```

### Pydantic for Django Ninja
```python
from ninja import Schema
from uuid import UUID
from typing import Optional, List

class MessageCreateIn(Schema):
    content: str
    message_type: str = "text"
    parent_id: Optional[UUID] = None
    language: Optional[str] = None
    trigger_agent: bool = False
    attachment_ids: List[UUID] = []
    metadata: dict = {}

class MessageCreateOut(MessageOut):
    agent_run_id: Optional[UUID]
```

### List Model Involved
- `ChatTopic` — parent topic; fetched and validated
- `ChatMessage` — created
- `ChatAttachment` — created for each `attachment_id`
- `Upload` — resolved from `attachment_ids` to get file info
- `AgentRun` — created if AI agent triggered
- `TopicParticipant` / `ProjectMember` — access check
- `ChatReadMarker` — upserted to new message

### Django ORM Query (Proposed)
```python
from django.db.models import Max
from django.db import transaction

@router.post("/topics/{topic_id}/messages", response=MessageCreateOut)
def create_message(request, topic_id: UUID, body: MessageCreateIn):
    company = request.auth.current_company

    topic = get_object_or_404(ChatTopic, id=topic_id, company=company, is_active=True)

    has_access = (
        TopicParticipant.objects.filter(topic=topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Not a participant of this topic.")

    with transaction.atomic():
        # Thread-safe sequence increment
        last_seq = (
            ChatMessage.objects.filter(topic=topic)
            .aggregate(max_seq=Max("sequence"))["max_seq"] or 0
        )

        message = ChatMessage.objects.create(
            company=company,
            project=topic.project,
            topic=topic,
            sender=request.auth,
            message_type=body.message_type,
            content=body.content,
            language=body.language,
            parent_id=body.parent_id,
            sequence=last_seq + 1,
            status=ChatMessage.Status.COMPLETED,
            metadata=body.metadata,
        )

        # Attachments from pre-uploaded files
        attachments = []
        for upload_id in body.attachment_ids:
            upload = get_object_or_404(Upload, id=upload_id, company=company)
            att = ChatAttachment.objects.create(
                message=message,
                attachment_type=_infer_attachment_type(upload.mime_type),
                file=upload.file,
                original_filename=upload.original_filename,
                mime_type=upload.mime_type,
                file_size=upload.file_size,
            )
            attachments.append(att)

        # Agent trigger
        agent_run = None
        if body.trigger_agent:
            agent_run = AgentRun.objects.create(
                company=company,
                project=topic.project,
                topic=topic,
                triggered_by=request.auth,
                status=AgentRun.Status.PENDING,
                input_payload={"message_id": str(message.id), "content": body.content},
            )
            from celery_app.tasks import run_agent_task
            run_agent_task.delay(str(agent_run.id))

        # Update read marker
        ChatReadMarker.objects.update_or_create(
            user=request.auth,
            topic=topic,
            defaults={"last_read_message": message},
        )

    # Publish real-time event
    publish_to_topic(topic_id, "message.created", {"message_id": str(message.id)})

    return {**message.__dict__, "agent_run_id": agent_run.id if agent_run else None}
```

---

## GET /api/v1/messages/{message_id}

### Detail
Retrieves a single message by ID with full detail: sender, reactions, attachments, and blocks. Validates that the message belongs to the current company and that the requesting user has access to its topic.

### Flow
1. Authenticate via Supabase JWT; scope to `current_company`
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify user access via `TopicParticipant` or `ProjectMember`
4. `select_related("sender", "topic", "parent", "retry_of")`
5. `prefetch_related("reactions__user", "attachments", "blocks")`
6. Return full message detail

### Request JSON
```json
// No body — GET request
// GET /api/v1/messages/msg-uuid
```

### Response JSON
```json
{
  "id": "msg-uuid",
  "topic_id": "topic-uuid",
  "message_type": "form",
  "content": "Please fill out the following form:",
  "content_json": {
    "blocks": [
      {
        "key": "customer_info",
        "type": "form",
        "schema": {
          "fields": [
            {"name": "name", "type": "text", "label": "Customer Name"},
            {"name": "priority", "type": "select", "options": ["low", "medium", "high"]}
          ]
        },
        "submitted": false
      }
    ]
  },
  "language": "en",
  "status": "completed",
  "sequence": 7,
  "parent_id": null,
  "retry_of_id": null,
  "is_deleted_from_context": false,
  "sender": {
    "id": "persona-user-uuid",
    "username": "aria_persona",
    "user_type": "persona"
  },
  "reactions": [],
  "attachments": [],
  "metadata": {
    "model_used": "gpt-4o",
    "token_usage": {"prompt": 120, "completion": 85}
  },
  "created_at": "2025-01-15T09:05:00Z",
  "updated_at": "2025-01-15T09:05:00Z"
}
```

### Pydantic for Django Ninja
```python
# Reuses MessageOut defined in GET /topics/{topic_id}/messages
# No additional schema needed
```

### List Model Involved
- `ChatMessage` — fetched by ID
- `User` — sender via `select_related`
- `ChatReaction` — prefetched
- `ChatAttachment` — prefetched
- `TopicParticipant` / `ProjectMember` — access check

### Django ORM Query (Proposed)
```python
@router.get("/messages/{message_id}", response=MessageOut)
def get_message(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("sender", "topic", "topic__project", "parent", "retry_of")
        .prefetch_related("reactions__user", "attachments"),
        id=message_id,
        company=company,
        is_active=True,
    )

    has_access = (
        TopicParticipant.objects.filter(topic=message.topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=message.topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Access denied.")

    return message
```

---

## PATCH /api/v1/messages/{message_id}

### Detail
Edits the `content` of an existing message. Only the original sender may edit their own message. AI-generated messages (`sender.user_type=persona`) cannot be edited by human users. Only `completed` messages can be edited — editing a `streaming` or `pending` message is rejected with 409. Publishes `message.updated` to Centrifuge after save.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify `request.auth == message.sender` — 403 otherwise
4. Verify `message.status == completed` — 409 if pending/streaming
5. Update `content` and/or `metadata` fields
6. Save with `update_fields`
7. Publish `message.updated` to Centrifuge `topic:{topic_id}`
8. Return updated message

### Request JSON
```json
{
  "content": "Updated: Can you summarize the Q4 sales report instead?",
  "metadata": {}
}
```

### Response JSON
```json
{
  "id": "msg-uuid",
  "topic_id": "topic-uuid",
  "message_type": "text",
  "content": "Updated: Can you summarize the Q4 sales report instead?",
  "content_json": {},
  "language": "en",
  "status": "completed",
  "sequence": 15,
  "sender": {
    "id": "user-uuid",
    "username": "john_doe",
    "user_type": "human"
  },
  "reactions": [],
  "attachments": [],
  "metadata": {},
  "created_at": "2025-01-15T09:10:00Z",
  "updated_at": "2025-01-15T09:15:00Z"
}
```

### Pydantic for Django Ninja
```python
class MessageUpdateIn(Schema):
    content: Optional[str] = None
    metadata: Optional[dict] = None
```

### List Model Involved
- `ChatMessage` — updated

### Django ORM Query (Proposed)
```python
@router.patch("/messages/{message_id}", response=MessageOut)
def update_message(request, message_id: UUID, body: MessageUpdateIn):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("sender", "topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    if message.sender_id != request.auth.id:
        raise HttpError(403, "You can only edit your own messages.")

    if message.status != ChatMessage.Status.COMPLETED:
        raise HttpError(409, f"Cannot edit a message in '{message.status}' state.")

    update_fields = ["updated_at"]

    if body.content is not None:
        message.content = body.content
        update_fields.append("content")

    if body.metadata is not None:
        message.metadata = body.metadata
        update_fields.append("metadata")

    message.save(update_fields=update_fields)

    publish_to_topic(message.topic_id, "message.updated", {"message_id": str(message.id)})

    return message
```

---

## DELETE /api/v1/messages/{message_id}

### Detail
Soft-deletes a message. The sender may delete their own messages; `owner` and `admin` role members may delete any message in their company. Soft-delete sets `is_active=False` and `deleted_at=now()`. Publishes `message.deleted` to Centrifuge so clients can remove the message from their UI. Reactions and attachments are preserved in the database for audit purposes.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify: user is sender, OR has `role in [owner, admin]` in `CompanyAccess`
4. Call `message.soft_delete()`
5. Publish `message.deleted` to Centrifuge `topic:{topic_id}`
6. Return `{"deleted": true}`

### Request JSON
```json
// No body — DELETE request
// DELETE /api/v1/messages/msg-uuid
```

### Response JSON
```json
{
  "deleted": true,
  "message_id": "msg-uuid"
}
```

### Pydantic for Django Ninja
```python
class MessageDeleteOut(Schema):
    deleted: bool
    message_id: UUID
```

### List Model Involved
- `ChatMessage` — soft deleted
- `CompanyAccess` — role check for non-sender deletions

### Django ORM Query (Proposed)
```python
@router.delete("/messages/{message_id}", response=MessageDeleteOut)
def delete_message(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    is_sender = message.sender_id == request.auth.id
    is_privileged = CompanyAccess.objects.filter(
        company=company,
        user=request.auth,
        role__in=["owner", "admin"],
        is_active=True,
    ).exists()

    if not is_sender and not is_privileged:
        raise HttpError(403, "Cannot delete this message.")

    message.soft_delete()

    publish_to_topic(message.topic_id, "message.deleted", {"message_id": str(message.id)})

    return MessageDeleteOut(deleted=True, message_id=message.id)
```

---

## POST /api/v1/messages/{message_id}/truncate

### Detail
Truncates the conversation at the specified message — soft-deletes the target message **and all messages that follow it** (higher `sequence` number) in the same topic. Used to restart a conversation from a specific point. Only `owner`, `admin`, or the topic's `OWNER`-role `TopicParticipant` may truncate. Publishes `topic.truncated` to Centrifuge with the cutoff sequence number.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify user has `owner`/`admin` company role or `OWNER` topic participant role
4. Soft-delete all messages with `topic=topic` and `sequence >= message.sequence`
5. Count records deleted for response
6. Publish `topic.truncated` to Centrifuge with `cutoff_sequence`
7. Return summary

### Request JSON
```json
// No body — POST request
// POST /api/v1/messages/msg-uuid/truncate
```

### Response JSON
```json
{
  "truncated_from_sequence": 12,
  "messages_removed": 8,
  "topic_id": "topic-uuid"
}
```

### Pydantic for Django Ninja
```python
class TruncateOut(Schema):
    truncated_from_sequence: int
    messages_removed: int
    topic_id: UUID
```

### List Model Involved
- `ChatMessage` — bulk soft-deleted (target + all after)
- `TopicParticipant` — role check
- `CompanyAccess` — fallback role check

### Django ORM Query (Proposed)
```python
from django.utils import timezone

@router.post("/messages/{message_id}/truncate", response=TruncateOut)
def truncate_messages(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    topic = message.topic

    # Authorization: company owner/admin OR topic OWNER participant
    is_topic_owner = TopicParticipant.objects.filter(
        topic=topic,
        user=request.auth,
        role=TopicParticipant.Role.OWNER,
        is_active=True,
    ).exists()

    is_company_admin = CompanyAccess.objects.filter(
        company=company,
        user=request.auth,
        role__in=["owner", "admin"],
        is_active=True,
    ).exists()

    if not is_topic_owner and not is_company_admin:
        raise HttpError(403, "Insufficient permissions to truncate this topic.")

    now = timezone.now()
    affected = ChatMessage.objects.filter(
        topic=topic,
        is_active=True,
        sequence__gte=message.sequence,
    )
    count = affected.count()
    affected.update(is_active=False, deleted_at=now, updated_at=now)

    publish_to_topic(
        topic.id,
        "topic.truncated",
        {"cutoff_sequence": message.sequence, "messages_removed": count},
    )

    return TruncateOut(
        truncated_from_sequence=message.sequence,
        messages_removed=count,
        topic_id=topic.id,
    )
```

---

## POST /api/v1/messages/{message_id}/retry

### Detail
Retries a failed or cancelled AI-generated message. Creates a new `ChatMessage` with `retry_of=original_message`, `status=pending`, and dispatches a new `AgentRun` to the Celery worker. The original message is marked `is_deleted_from_context=True` so it is excluded from the AI context window on the retry run. Only works on messages with `status in [failed, cancelled]`.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify `message.status in [failed, cancelled]` — 409 otherwise
4. Verify user access (participant or project member)
5. Mark original message `is_deleted_from_context=True`
6. Create new `ChatMessage(retry_of=original, status=pending, sequence=MAX+1)`
7. Create new `AgentRun` linked to the topic and dispatch to Celery
8. Publish `message.created` to Centrifuge `topic:{topic_id}`
9. Return new message

### Request JSON
```json
// No body or optional override:
{
  "content_override": null
}
```

### Response JSON
```json
{
  "id": "new-msg-uuid",
  "topic_id": "topic-uuid",
  "message_type": "text",
  "content": "",
  "content_json": {},
  "status": "pending",
  "sequence": 16,
  "retry_of_id": "original-msg-uuid",
  "sender": null,
  "reactions": [],
  "attachments": [],
  "agent_run_id": "new-run-uuid",
  "metadata": {},
  "created_at": "2025-01-15T09:20:00Z",
  "updated_at": "2025-01-15T09:20:00Z"
}
```

### Pydantic for Django Ninja
```python
class RetryMessageIn(Schema):
    content_override: Optional[str] = None

class RetryMessageOut(MessageOut):
    agent_run_id: Optional[UUID]
```

### List Model Involved
- `ChatMessage` — original updated (`is_deleted_from_context=True`); new message created
- `AgentRun` — new run created and dispatched
- `TopicParticipant` / `ProjectMember` — access check

### Django ORM Query (Proposed)
```python
from django.db import transaction
from django.db.models import Max

@router.post("/messages/{message_id}/retry", response=RetryMessageOut)
def retry_message(request, message_id: UUID, body: RetryMessageIn):
    company = request.auth.current_company

    original = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    RETRYABLE = {ChatMessage.Status.FAILED, ChatMessage.Status.CANCELLED}
    if original.status not in RETRYABLE:
        raise HttpError(409, f"Cannot retry a message in '{original.status}' state.")

    has_access = (
        TopicParticipant.objects.filter(topic=original.topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=original.topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Access denied.")

    with transaction.atomic():
        # Exclude original from context window
        original.is_deleted_from_context = True
        original.save(update_fields=["is_deleted_from_context", "updated_at"])

        last_seq = (
            ChatMessage.objects.filter(topic=original.topic)
            .aggregate(max_seq=Max("sequence"))["max_seq"] or 0
        )

        new_message = ChatMessage.objects.create(
            company=company,
            project=original.topic.project,
            topic=original.topic,
            sender=None,  # will be set by agent
            message_type=original.message_type,
            content=body.content_override or "",
            status=ChatMessage.Status.PENDING,
            retry_of=original,
            sequence=last_seq + 1,
        )

        agent_run = AgentRun.objects.create(
            company=company,
            project=original.topic.project,
            topic=original.topic,
            triggered_by=request.auth,
            status=AgentRun.Status.PENDING,
            input_payload={
                "retry_message_id": str(new_message.id),
                "original_message_id": str(original.id),
            },
        )

        from celery_app.tasks import run_agent_task
        run_agent_task.delay(str(agent_run.id))

    publish_to_topic(original.topic_id, "message.created", {"message_id": str(new_message.id)})

    return {**new_message.__dict__, "agent_run_id": agent_run.id}
```

---

## POST /api/v1/messages/{message_id}/cancel

### Detail
Cancels a message that is currently `pending` or `streaming`. Finds the associated `AgentRun` (if any) for this message and cancels it. Sets `ChatMessage.status = cancelled`. Publishes `message.cancelled` to Centrifuge. Used when the user wants to stop a long-running AI response mid-stream.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify `message.status in [pending, streaming]` — 409 otherwise
4. Verify user is sender or has `owner`/`admin` role
5. Set `message.status = cancelled`, save
6. Find linked `AgentRun` (via `topic` + matching `status in [pending, running]`) and cancel it
7. Signal Celery worker via Redis cache key `cancel_run:{run_id}`
8. Publish `message.cancelled` to Centrifuge `topic:{topic_id}` and `message:{message_id}`
9. Return updated message

### Request JSON
```json
// No body — POST request
// POST /api/v1/messages/msg-uuid/cancel
```

### Response JSON
```json
{
  "id": "msg-uuid",
  "status": "cancelled",
  "topic_id": "topic-uuid",
  "message": "Message cancelled."
}
```

### Pydantic for Django Ninja
```python
class CancelMessageOut(Schema):
    id: UUID
    status: str
    topic_id: UUID
    message: str
```

### List Model Involved
- `ChatMessage` — status updated to `cancelled`
- `AgentRun` — associated run also cancelled
- `CompanyAccess` — role check

### Django ORM Query (Proposed)
```python
from django.core.cache import cache

@router.post("/messages/{message_id}/cancel", response=CancelMessageOut)
def cancel_message(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    CANCELLABLE = {ChatMessage.Status.PENDING, ChatMessage.Status.STREAMING}
    if message.status not in CANCELLABLE:
        raise HttpError(409, f"Cannot cancel a message in '{message.status}' state.")

    is_sender = message.sender_id == request.auth.id
    is_privileged = CompanyAccess.objects.filter(
        company=company, user=request.auth, role__in=["owner", "admin"], is_active=True
    ).exists()
    if not is_sender and not is_privileged:
        raise HttpError(403, "Cannot cancel this message.")

    now = timezone.now()
    message.status = ChatMessage.Status.CANCELLED
    message.save(update_fields=["status", "updated_at"])

    # Cancel linked AgentRun
    active_run = AgentRun.objects.filter(
        topic=message.topic,
        status__in=[AgentRun.Status.PENDING, AgentRun.Status.RUNNING],
    ).first()

    if active_run:
        active_run.status = AgentRun.Status.CANCELLED
        active_run.completed_at = now
        active_run.save(update_fields=["status", "completed_at", "updated_at"])
        cache.set(f"cancel_run:{active_run.id}", "1", timeout=300)

    # Publish to both channels
    publish_to_topic(message.topic_id, "message.cancelled", {"message_id": str(message.id)})

    import requests as http_req
    try:
        http_req.post(
            f"{settings.CENTRIFUGE_API_URL}/api",
            json={
                "method": "publish",
                "params": {
                    "channel": f"message:{message_id}",
                    "data": {"type": "message.cancelled"},
                },
            },
            headers={"Authorization": f"apikey {settings.CENTRIFUGE_API_KEY}"},
            timeout=2,
        )
    except Exception:
        pass

    return CancelMessageOut(
        id=message.id,
        status=message.status,
        topic_id=message.topic_id,
        message="Message cancelled.",
    )
```

---

## POST /api/v1/messages/{message_id}/forms/{block_key}/submit

### Detail
Submits data for a form block embedded within an AI message. Form blocks are stored in `ChatMessage.content_json["blocks"]` as a list of block objects — each with a `key`, `type`, and `schema`. On submission, the form data is validated against the block's schema, the block's `submitted=true` flag is set, the response is stored, and the submission may trigger an `AgentRun` continuation (e.g., the agent was waiting for human input via a form).

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify `message.message_type == "form"` and block with `key=block_key` exists in `content_json`
4. Verify user has topic access
5. Validate submitted `data` against block schema (basic key presence check or JSON Schema)
6. Update `content_json["blocks"][block_key].submitted = true`, store `submission_data`
7. Save message with `update_fields=["content_json", "updated_at"]`
8. If an `AgentRun` with `status=waiting_approval` is linked to this topic, resume it by updating to `running` and dispatching continuation task
9. Publish `message.form_submitted` to Centrifuge `topic:{topic_id}`
10. Return updated block state

### Request JSON
```json
{
  "data": {
    "name": "Acme Corp",
    "priority": "high"
  }
}
```

### Response JSON
```json
{
  "message_id": "msg-uuid",
  "block_key": "customer_info",
  "submitted": true,
  "submission_data": {
    "name": "Acme Corp",
    "priority": "high"
  },
  "agent_run_resumed": true,
  "agent_run_id": "run-uuid"
}
```

### Pydantic for Django Ninja
```python
class FormSubmitIn(Schema):
    data: dict

class FormSubmitOut(Schema):
    message_id: UUID
    block_key: str
    submitted: bool
    submission_data: dict
    agent_run_resumed: bool
    agent_run_id: Optional[UUID]
```

### List Model Involved
- `ChatMessage` — `content_json` updated
- `AgentRun` — waiting run resumed if applicable
- `TopicParticipant` / `ProjectMember` — access check

### Django ORM Query (Proposed)
```python
@router.post("/messages/{message_id}/forms/{block_key}/submit", response=FormSubmitOut)
def submit_form_block(request, message_id: UUID, block_key: str, body: FormSubmitIn):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    if message.message_type != ChatMessage.MessageType.FORM:
        raise HttpError(400, "This message does not contain form blocks.")

    # Find block by key in content_json
    blocks = message.content_json.get("blocks", [])
    target_block = next((b for b in blocks if b.get("key") == block_key), None)

    if target_block is None:
        raise HttpError(404, f"Block '{block_key}' not found in message.")

    if target_block.get("submitted"):
        raise HttpError(409, "This form block has already been submitted.")

    has_access = (
        TopicParticipant.objects.filter(topic=message.topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=message.topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Access denied.")

    # Mark block as submitted
    target_block["submitted"] = True
    target_block["submission_data"] = body.data
    target_block["submitted_by"] = str(request.auth.id)
    target_block["submitted_at"] = timezone.now().isoformat()

    message.content_json["blocks"] = blocks
    message.save(update_fields=["content_json", "updated_at"])

    # Resume waiting AgentRun
    waiting_run = AgentRun.objects.filter(
        topic=message.topic,
        status=AgentRun.Status.WAITING_APPROVAL,
        is_active=True,
    ).first()

    agent_run_resumed = False
    if waiting_run:
        waiting_run.status = AgentRun.Status.RUNNING
        waiting_run.input_payload["form_submission"] = {
            "block_key": block_key,
            "data": body.data,
        }
        waiting_run.save(update_fields=["status", "input_payload", "updated_at"])
        from celery_app.tasks import resume_agent_task
        resume_agent_task.delay(str(waiting_run.id))
        agent_run_resumed = True

    publish_to_topic(
        message.topic_id,
        "message.form_submitted",
        {"message_id": str(message.id), "block_key": block_key},
    )

    return FormSubmitOut(
        message_id=message.id,
        block_key=block_key,
        submitted=True,
        submission_data=body.data,
        agent_run_resumed=agent_run_resumed,
        agent_run_id=waiting_run.id if waiting_run else None,
    )
```

---

## GET /api/v1/messages/{message_id}/blocks

### Detail
Returns all content blocks for a message, parsed from `content_json["blocks"]`. Each block has a `key`, `type` (form, graph, code, tool_output, etc.), and type-specific `data`. This endpoint provides a structured view of rich AI message content — avoiding the need for clients to parse `content_json` themselves. If the proposed `MessageBlock` model exists, it queries that table instead of parsing `content_json`.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify user topic access
4. If `MessageBlock` model is available: query `MessageBlock.objects.filter(message=message)`
5. Else: parse `message.content_json.get("blocks", [])` and serialize
6. Return list of blocks

### Request JSON
```json
// No body — GET request
// GET /api/v1/messages/msg-uuid/blocks
```

### Response JSON
```json
{
  "message_id": "msg-uuid",
  "blocks": [
    {
      "key": "customer_info",
      "type": "form",
      "order": 0,
      "data": {
        "schema": {
          "fields": [
            {"name": "name", "type": "text", "label": "Customer Name"},
            {"name": "priority", "type": "select", "options": ["low", "medium", "high"]}
          ]
        },
        "submitted": true,
        "submission_data": {"name": "Acme Corp", "priority": "high"}
      }
    },
    {
      "key": "analysis_result",
      "type": "graph",
      "order": 1,
      "data": {
        "chart_type": "bar",
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "datasets": [{"label": "Revenue", "data": [120, 145, 132, 198]}]
      }
    }
  ]
}
```

### Pydantic for Django Ninja
```python
class BlockOut(Schema):
    key: str
    type: str
    order: int
    data: dict

class MessageBlocksOut(Schema):
    message_id: UUID
    blocks: List[BlockOut]
```

### List Model Involved
- `ChatMessage` — `content_json` read
- `MessageBlock` *(proposed)* — queried if model exists

### Django ORM Query (Proposed)
```python
@router.get("/messages/{message_id}/blocks", response=MessageBlocksOut)
def get_message_blocks(request, message_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    has_access = (
        TopicParticipant.objects.filter(topic=message.topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=message.topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Access denied.")

    # Once MessageBlock model is migrated, prefer DB query:
    # blocks = list(MessageBlock.objects.filter(message=message).order_by("order"))

    # Fallback: parse from content_json
    raw_blocks = message.content_json.get("blocks", [])
    blocks = [
        BlockOut(
            key=b.get("key", f"block_{i}"),
            type=b.get("type", "unknown"),
            order=i,
            data={k: v for k, v in b.items() if k not in ("key", "type")},
        )
        for i, b in enumerate(raw_blocks)
    ]

    return MessageBlocksOut(message_id=message.id, blocks=blocks)
```

---

## POST /api/v1/messages/{message_id}/reactions

### Detail
Adds an emoji reaction to a message. Enforces uniqueness per `(message, user, emoji)` combination via a database constraint — if the same emoji from the same user already exists, returns the existing reaction (idempotent). Publishes `reaction.added` to Centrifuge `topic:{topic_id}`.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Verify user has topic access
4. `get_or_create` `ChatReaction(message=message, user=request.auth, emoji=body.emoji)`
5. If created: publish `reaction.added` to Centrifuge
6. Return reaction

### Request JSON
```json
{
  "emoji": "👍"
}
```

### Response JSON
```json
{
  "id": "rxn-uuid",
  "message_id": "msg-uuid",
  "emoji": "👍",
  "user": {
    "id": "user-uuid",
    "username": "john_doe",
    "user_type": "human"
  },
  "created_at": "2025-01-15T09:30:00Z",
  "created": true
}
```

### Pydantic for Django Ninja
```python
class ReactionCreateIn(Schema):
    emoji: str

class ReactionCreateOut(Schema):
    id: UUID
    message_id: UUID
    emoji: str
    user: SenderOut
    created_at: datetime
    created: bool  # false if reaction already existed (idempotent)
```

### List Model Involved
- `ChatMessage` — parent message, validated
- `ChatReaction` — created or fetched
- `TopicParticipant` / `ProjectMember` — access check

### Django ORM Query (Proposed)
```python
@router.post("/messages/{message_id}/reactions", response=ReactionCreateOut)
def add_reaction(request, message_id: UUID, body: ReactionCreateIn):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    has_access = (
        TopicParticipant.objects.filter(topic=message.topic, user=request.auth, is_active=True).exists()
        or ProjectMember.objects.filter(project=message.topic.project, user=request.auth, is_active=True).exists()
    )
    if not has_access:
        raise HttpError(403, "Access denied.")

    reaction, created = ChatReaction.objects.get_or_create(
        message=message,
        user=request.auth,
        emoji=body.emoji,
    )

    if created:
        publish_to_topic(
            message.topic_id,
            "reaction.added",
            {
                "message_id": str(message.id),
                "reaction_id": str(reaction.id),
                "emoji": body.emoji,
                "user_id": str(request.auth.id),
            },
        )

    return ReactionCreateOut(
        id=reaction.id,
        message_id=message.id,
        emoji=reaction.emoji,
        user=request.auth,
        created_at=reaction.created_at,
        created=created,
    )
```

---

## DELETE /api/v1/messages/{message_id}/reactions/{reaction_id}

### Detail
Removes an emoji reaction. A user may only remove their own reaction. `owner` and `admin` company members may remove any reaction. Hard-deletes the `ChatReaction` row — reactions do not use soft delete. Publishes `reaction.removed` to Centrifuge `topic:{topic_id}`.

### Flow
1. Authenticate via Supabase JWT
2. Fetch `ChatMessage` by `id=message_id`, `company=current_company`, `is_active=True`
3. Fetch `ChatReaction` by `id=reaction_id`, `message=message`
4. Verify: user is `reaction.user` OR has `owner`/`admin` role
5. Hard-delete `reaction.delete()`
6. Publish `reaction.removed` to Centrifuge `topic:{topic_id}`
7. Return `{"deleted": true}`

### Request JSON
```json
// No body — DELETE request
// DELETE /api/v1/messages/msg-uuid/reactions/rxn-uuid
```

### Response JSON
```json
{
  "deleted": true,
  "reaction_id": "rxn-uuid",
  "message_id": "msg-uuid"
}
```

### Pydantic for Django Ninja
```python
class ReactionDeleteOut(Schema):
    deleted: bool
    reaction_id: UUID
    message_id: UUID
```

### List Model Involved
- `ChatMessage` — parent, validated
- `ChatReaction` — hard deleted
- `CompanyAccess` — role check for non-owner deletions

### Django ORM Query (Proposed)
```python
@router.delete("/messages/{message_id}/reactions/{reaction_id}", response=ReactionDeleteOut)
def delete_reaction(request, message_id: UUID, reaction_id: UUID):
    company = request.auth.current_company

    message = get_object_or_404(
        ChatMessage.objects.select_related("topic"),
        id=message_id,
        company=company,
        is_active=True,
    )

    reaction = get_object_or_404(
        ChatReaction,
        id=reaction_id,
        message=message,
    )

    is_owner = reaction.user_id == request.auth.id
    is_privileged = CompanyAccess.objects.filter(
        company=company,
        user=request.auth,
        role__in=["owner", "admin"],
        is_active=True,
    ).exists()

    if not is_owner and not is_privileged:
        raise HttpError(403, "Cannot remove this reaction.")

    reaction.delete()

    publish_to_topic(
        message.topic_id,
        "reaction.removed",
        {
            "message_id": str(message.id),
            "reaction_id": str(reaction_id),
        },
    )

    return ReactionDeleteOut(
        deleted=True,
        reaction_id=reaction_id,
        message_id=message.id,
    )
```

---

## Model Reference Summary

| Model              | DB Table                        | Used In                                          |
|--------------------|---------------------------------|--------------------------------------------------|
| `ChatMessage`      | `workspace_chat_message`        | All endpoints — primary model                    |
| `ChatTopic`        | `workspace_chat_topic`          | All endpoints — parent topic                     |
| `ChatReaction`     | `workspace_chat_reaction`       | Reactions add/delete                             |
| `ChatAttachment`   | `workspace_chat_attachment`     | Message create (attach files)                    |
| `ChatReadMarker`   | `workspace_chat_read_marker`    | List messages (unread count + upsert)            |
| `TopicParticipant` | `workspace_topic_participant`   | Access check (all endpoints)                     |
| `ProjectMember`    | `workspace_project_member`      | Fallback access check (all endpoints)            |
| `CompanyAccess`    | `governance_company_access`     | Privilege check (delete, truncate, cancel)       |
| `AgentRun`         | `intelligence_agent_run`        | Create (trigger), retry, cancel, form submit     |
| `Upload`           | `storage_upload`                | Message create (resolve attachment file info)    |
| `Channel`          | `workspace_channel`             | Topic parent (via `topic.channel`)               |
| `Project`          | `workspace_project`             | Topic parent (via `topic.project`)               |

---

## Proposed Models (Not Yet Migrated)

### MessageBlock *(required by /blocks and /forms/{block_key}/submit)*

```python
class MessageBlock(BaseModel):
    """
    Persisted representation of a structured content block within a ChatMessage.
    Provides indexed, queryable access to blocks without parsing content_json.
    
    Types: form, graph, code, tool_output, image, table, approval
    """
    class BlockType(models.TextChoices):
        FORM        = "form",        "Form"
        GRAPH       = "graph",       "Graph"
        CODE        = "code",        "Code"
        TOOL_OUTPUT = "tool_output", "Tool Output"
        IMAGE       = "image",       "Image"
        TABLE       = "table",       "Table"
        APPROVAL    = "approval",    "Approval"

    message = models.ForeignKey(
        "nucleus.ChatMessage",
        on_delete=models.CASCADE,
        related_name="blocks",
    )

    key = models.CharField(max_length=100)           # Stable identifier within message
    block_type = models.CharField(
        max_length=30,
        choices=BlockType.choices,
        db_index=True,
    )
    order = models.PositiveSmallIntegerField(default=0)
    data = models.JSONField(default=dict)             # Type-specific content

    # Form-specific tracking
    submitted = models.BooleanField(default=False, db_index=True)
    submission_data = models.JSONField(default=dict, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_blocks",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workspace_message_block"
        constraints = [
            models.UniqueConstraint(
                fields=["message", "key"],
                name="uniq_message_block_key",
            )
        ]
        indexes = [
            models.Index(fields=["message", "order"]),
            models.Index(fields=["block_type", "submitted"]),
        ]
```

> **Migration needed**: `python manage.py makemigrations nucleus --name add_message_block`

---

*End of Message API Documentation*
