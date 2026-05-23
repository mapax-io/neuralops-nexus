# Topic / Chat APIs Documentation

## Table of Contents
1. [GET /api/v1/channels/{channel_id}/topics](#1-get-apiv1channelschannel_idtopics)
2. [POST /api/v1/channels/{channel_id}/topics](#2-post-apiv1channelschannel_idtopics)
3. [GET /api/v1/topics/{topic_id}](#3-get-apiv1topicstopic_id)
4. [PATCH /api/v1/topics/{topic_id}](#4-patch-apiv1topicstopic_id)
5. [DELETE /api/v1/topics/{topic_id}](#5-delete-apiv1topicstopic_id)
6. [POST /api/v1/topics/{topic_id}/archive](#6-post-apiv1topicstopic_idarchive)
7. [POST /api/v1/topics/{topic_id}/restore](#7-post-apiv1topicstopic_idrestore)
8. [POST /api/v1/topics/{topic_id}/read](#8-post-apiv1topicstopic_idread)
9. [POST /api/v1/topics/{topic_id}/pin](#9-post-apiv1topicstopic_idpin)
10. [POST /api/v1/topics/{topic_id}/unpin](#10-post-apiv1topicstopic_idunpin)
11. [GET /api/v1/topics/{topic_id}/history](#11-get-apiv1topicstopic_idhistory)

---

## 1. GET /api/v1/channels/{channel_id}/topics

### Detail
List all topics (chat threads/conversations) within a channel. Supports filtering by active/archived/pinned status and pagination.

### Flow
1. Authenticate user via JWT
2. Verify user has access to the channel
3. Query topics belonging to the channel
4. Apply filters (active/archived/pinned)
5. Return paginated list with message counts and last activity

### Request JSON
```json
// Query Parameters
{
  "is_active": true,           // Optional: filter by active status
  "include_archived": false,   // Optional: include archived topics
  "is_pinned": null,           // Optional: filter by pinned status
  "page": 1,                   // Optional: pagination
  "page_size": 20              // Optional: items per page
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "topics": [
      {
        "id": "450e8400-e29b-41d4-a716-446655440000",
        "title": "Feature Discussion: AI Agent Integration",
        "slug": "feature-discussion-ai-agent-integration",
        "channel_id": "550e8400-e29b-41d4-a716-446655440000",
        "project_id": "650e8400-e29b-41d4-a716-446655440000",
        "company_id": "750e8400-e29b-41d4-a716-446655440000",
        "is_active": true,
        "is_pinned": false,
        "message_count": 45,
        "participant_count": 5,
        "last_message_at": "2026-05-23T02:30:00Z",
        "created_at": "2026-05-20T10:30:00Z",
        "updated_at": "2026-05-23T02:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 15,
      "total_pages": 1
    }
  }
}
```

### Pydantic for Django Ninja
```python
from ninja import Schema, Query
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class TopicListFilters(Query):
    is_active: Optional[bool] = True
    include_archived: Optional[bool] = False
    is_pinned: Optional[bool] = None
    page: int = 1
    page_size: int = 20


class TopicOut(Schema):
    id: UUID
    title: str
    slug: str
    channel_id: UUID
    project_id: UUID
    company_id: UUID
    is_active: bool
    is_pinned: bool
    message_count: int
    participant_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PaginationOut(Schema):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class TopicListResponse(Schema):
    success: bool = True
    data: dict  # Contains 'topics' and 'pagination'


@router.get("/channels/{channel_id}/topics", response=TopicListResponse)
def list_topics(request, channel_id: UUID, filters: TopicListFilters = Query(...)):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `Channel`
- `Project`
- `Company`
- `ChatMessage` (for message count and last activity)
- `TopicParticipant` (for participant count)
- `User` (implicit via authentication)

### Django ORM Query (Proposed)
```python
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q

# Verify channel access
channel = Channel.objects.filter(
    Q(id=channel_id) &
    (
        Q(channelmember__user=request.user, channelmember__is_active=True) |
        Q(company__companyaccess__user=request.user)
    ),
    is_active=True
).select_related('project', 'company').first()

if not channel:
    raise HttpError(404, "Channel not found or access denied")

# Build query
topics_query = ChatTopic.objects.filter(
    channel=channel,
    company=channel.company,
    project=channel.project
)

# Apply filters
if filters.is_active is not None:
    topics_query = topics_query.filter(is_active=filters.is_active)

if not filters.include_archived:
    topics_query = topics_query.filter(deleted_at__isnull=True)

if filters.is_pinned is not None:
    topics_query = topics_query.filter(is_pinned=filters.is_pinned)

# Annotate with counts and last activity
topics_query = topics_query.annotate(
    message_count=Count('messages', filter=Q(messages__is_active=True)),
    participant_count=Count('topicparticipant', filter=Q(topicparticipant__is_active=True)),
    last_message_at=Max('messages__created_at')
).select_related('channel', 'project', 'company').order_by('-is_pinned', '-updated_at')

# Pagination
paginator = Paginator(topics_query, filters.page_size)
page_obj = paginator.get_page(filters.page)

topics_data = [
    {
        "id": topic.id,
        "title": topic.title,
        "slug": topic.slug,
        "channel_id": topic.channel_id,
        "project_id": topic.project_id,
        "company_id": topic.company_id,
        "is_active": topic.is_active,
        "is_pinned": getattr(topic, 'is_pinned', False),
        "message_count": topic.message_count,
        "participant_count": topic.participant_count,
        "last_message_at": topic.last_message_at,
        "created_at": topic.created_at,
        "updated_at": topic.updated_at,
    }
    for topic in page_obj
]

return {
    "success": True,
    "data": {
        "topics": topics_data,
        "pagination": {
            "page": filters.page,
            "page_size": filters.page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
        }
    }
}
```

---

## 2. POST /api/v1/channels/{channel_id}/topics

### Detail
Create a new topic (chat thread) within a channel. Auto-generates slug from title and adds creator as first participant.

### Flow
1. Authenticate user
2. Verify user is a member of the channel
3. Validate topic title
4. Generate unique slug
5. Create topic record
6. Add creator as participant
7. Return created topic

### Request JSON
```json
{
  "title": "New Feature Brainstorm Session",
  "is_active": true
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "New Feature Brainstorm Session",
      "slug": "new-feature-brainstorm-session",
      "channel_id": "550e8400-e29b-41d4-a716-446655440000",
      "project_id": "650e8400-e29b-41d4-a716-446655440000",
      "company_id": "750e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "is_pinned": false,
      "message_count": 0,
      "participant_count": 1,
      "created_at": "2026-05-23T03:14:00Z",
      "updated_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
from django.utils.text import slugify
from django.db import transaction


class TopicCreateIn(Schema):
    title: str
    is_active: bool = True


class TopicCreateResponse(Schema):
    success: bool = True
    data: dict  # Contains 'topic'


@router.post("/channels/{channel_id}/topics", response=TopicCreateResponse)
@transaction.atomic
def create_topic(request, channel_id: UUID, payload: TopicCreateIn):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `Channel`
- `Project`
- `Company`
- `TopicParticipant` (auto-created for creator)
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils.text import slugify
from django.db import transaction

# Verify channel access and membership
channel = Channel.objects.filter(
    id=channel_id,
    channelmember__user=request.user,
    channelmember__is_active=True,
    is_active=True
).select_related('project', 'company').first()

if not channel:
    raise HttpError(403, "Channel not found or access denied")

# Generate unique slug
base_slug = slugify(payload.title)
slug = base_slug
counter = 1

while ChatTopic.objects.filter(channel=channel, slug=slug).exists():
    slug = f"{base_slug}-{counter}"
    counter += 1

# Create topic
with transaction.atomic():
    topic = ChatTopic.objects.create(
        title=payload.title,
        slug=slug,
        channel=channel,
        project=channel.project,
        company=channel.company,
        is_active=payload.is_active
    )
    
    # Add creator as participant
    TopicParticipant.objects.create(
        topic=topic,
        user=request.user,
        is_active=True
    )

return {
    "success": True,
    "data": {
        "topic": {
            "id": topic.id,
            "title": topic.title,
            "slug": topic.slug,
            "channel_id": topic.channel_id,
            "project_id": topic.project_id,
            "company_id": topic.company_id,
            "is_active": topic.is_active,
            "is_pinned": False,
            "message_count": 0,
            "participant_count": 1,
            "created_at": topic.created_at,
            "updated_at": topic.updated_at,
        }
    }
}
```

---

## 3. GET /api/v1/topics/{topic_id}

### Detail
Retrieve detailed information about a specific topic including participants, message count, and read status.

### Flow
1. Authenticate user
2. Verify user has access to the topic
3. Fetch topic details with aggregated data
4. Include user's read status
5. Return topic data

### Request JSON
```json
// No request body - path parameter only
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Feature Discussion: AI Agent Integration",
      "slug": "feature-discussion-ai-agent-integration",
      "channel_id": "550e8400-e29b-41d4-a716-446655440000",
      "channel_name": "Development",
      "project_id": "650e8400-e29b-41d4-a716-446655440000",
      "project_name": "AI Platform",
      "company_id": "750e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "is_pinned": false,
      "message_count": 45,
      "participant_count": 5,
      "unread_count": 3,
      "last_message_at": "2026-05-23T02:30:00Z",
      "last_read_at": "2026-05-23T01:00:00Z",
      "created_at": "2026-05-20T10:30:00Z",
      "updated_at": "2026-05-23T02:30:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicDetailOut(Schema):
    id: UUID
    title: str
    slug: str
    channel_id: UUID
    channel_name: str
    project_id: UUID
    project_name: str
    company_id: UUID
    is_active: bool
    is_pinned: bool
    message_count: int
    participant_count: int
    unread_count: int
    last_message_at: Optional[datetime]
    last_read_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TopicDetailResponse(Schema):
    success: bool = True
    data: dict  # Contains 'topic'


@router.get("/topics/{topic_id}", response=TopicDetailResponse)
def get_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `Channel`
- `Project`
- `Company`
- `TopicParticipant`
- `ChatMessage`
- `ChatReadMarker` (for read status)

### Django ORM Query (Proposed)
```python
from django.db.models import Count, Max, Q

# Fetch topic with access check
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user, channel__channelmember__is_active=True) |
        Q(company__companyaccess__user=request.user)
    )
).select_related('channel', 'project', 'company').annotate(
    message_count=Count('messages', filter=Q(messages__is_active=True)),
    participant_count=Count('topicparticipant', filter=Q(topicparticipant__is_active=True)),
    last_message_at=Max('messages__created_at')
).first()

if not topic:
    raise HttpError(404, "Topic not found or access denied")

# Get user's read marker
read_marker = ChatReadMarker.objects.filter(
    topic=topic,
    user=request.user
).first()

last_read_at = read_marker.last_read_at if read_marker else None

# Calculate unread count
if last_read_at:
    unread_count = ChatMessage.objects.filter(
        topic=topic,
        is_active=True,
        created_at__gt=last_read_at
    ).count()
else:
    unread_count = topic.message_count

return {
    "success": True,
    "data": {
        "topic": {
            "id": topic.id,
            "title": topic.title,
            "slug": topic.slug,
            "channel_id": topic.channel_id,
            "channel_name": topic.channel.name,
            "project_id": topic.project_id,
            "project_name": topic.project.name,
            "company_id": topic.company_id,
            "is_active": topic.is_active,
            "is_pinned": getattr(topic, 'is_pinned', False),
            "message_count": topic.message_count,
            "participant_count": topic.participant_count,
            "unread_count": unread_count,
            "last_message_at": topic.last_message_at,
            "last_read_at": last_read_at,
            "created_at": topic.created_at,
            "updated_at": topic.updated_at,
        }
    }
}
```

---

## 4. PATCH /api/v1/topics/{topic_id}

### Detail
Update topic properties (title). Only participants or channel admins can modify topics.

### Flow
1. Authenticate user
2. Verify user is participant or channel admin
3. Validate update payload
4. Update topic fields
5. Regenerate slug if title changed
6. Return updated topic

### Request JSON
```json
{
  "title": "Updated Feature Discussion",
  "is_active": true
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Updated Feature Discussion",
      "slug": "updated-feature-discussion",
      "channel_id": "550e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "updated_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicUpdateIn(Schema):
    title: Optional[str] = None
    is_active: Optional[bool] = None


class TopicUpdateResponse(Schema):
    success: bool = True
    data: dict  # Contains 'topic'


@router.patch("/topics/{topic_id}", response=TopicUpdateResponse)
def update_topic(request, topic_id: UUID, payload: TopicUpdateIn):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `TopicParticipant` (permission check)
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils.text import slugify

# Verify access (participant or channel admin)
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user, 
          channel__channelmember__role__in=['admin', 'owner'],
          channel__channelmember__is_active=True)
    )
).select_related('channel', 'project').first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

# Update fields
update_fields = []

if payload.title is not None:
    new_slug = slugify(payload.title)
    
    # Check slug uniqueness if title changed
    if new_slug != topic.slug:
        counter = 1
        base_slug = new_slug
        
        while ChatTopic.objects.filter(
            channel=topic.channel, 
            slug=new_slug
        ).exclude(id=topic_id).exists():
            new_slug = f"{base_slug}-{counter}"
            counter += 1
    
    topic.title = payload.title
    topic.slug = new_slug
    update_fields.extend(['title', 'slug'])

if payload.is_active is not None:
    topic.is_active = payload.is_active
    update_fields.append('is_active')

if update_fields:
    update_fields.append('updated_at')
    topic.save(update_fields=update_fields)

return {
    "success": True,
    "data": {
        "topic": {
            "id": topic.id,
            "title": topic.title,
            "slug": topic.slug,
            "channel_id": topic.channel_id,
            "is_active": topic.is_active,
            "updated_at": topic.updated_at,
        }
    }
}
```

---

## 5. DELETE /api/v1/topics/{topic_id}

### Detail
Soft-delete a topic. Sets `deleted_at` timestamp and `is_active=False`. Only topic creator or channel admins can delete.

### Flow
1. Authenticate user
2. Verify user is creator or channel admin
3. Soft-delete topic
4. Optionally cascade to messages (mark as inactive)
5. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic deleted successfully",
  "data": {
    "topic_id": "450e8400-e29b-41d4-a716-446655440000",
    "deleted_at": "2026-05-23T03:14:00Z"
  }
}
```

### Pydantic for Django Ninja
```python
class TopicDeleteResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic_id' and 'deleted_at'


@router.delete("/topics/{topic_id}", response=TopicDeleteResponse)
def delete_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `TopicParticipant` (check creator)
- `ChannelMember` (permission check)
- `ChatMessage` (optional cascade)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils import timezone
from django.db import transaction

# Verify delete permission (creator or channel admin)
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user,
          channel__channelmember__role__in=['admin', 'owner'],
          channel__channelmember__is_active=True)
    ),
    deleted_at__isnull=True
).select_related('channel').first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

# Soft delete
with transaction.atomic():
    now = timezone.now()
    
    topic.deleted_at = now
    topic.is_active = False
    topic.save(update_fields=['deleted_at', 'is_active', 'updated_at'])
    
    # Optionally soft-delete all messages
    ChatMessage.objects.filter(topic=topic, deleted_at__isnull=True).update(
        deleted_at=now,
        is_active=False
    )

return {
    "success": True,
    "message": "Topic deleted successfully",
    "data": {
        "topic_id": str(topic.id),
        "deleted_at": topic.deleted_at.isoformat(),
    }
}
```

---

## 6. POST /api/v1/topics/{topic_id}/archive

### Detail
Archive a topic without deleting it. Sets `is_active=False` but keeps `deleted_at=None`.

### Flow
1. Authenticate user
2. Verify user has permission
3. Set `is_active=False`
4. Return archived status

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic archived successfully",
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Old Discussion",
      "is_active": false,
      "archived_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicArchiveResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic'


@router.post("/topics/{topic_id}/archive", response=TopicArchiveResponse)
def archive_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `TopicParticipant` (permission check)
- `ChannelMember` (permission check)

### Django ORM Query (Proposed)
```python
# Verify permission
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user,
          channel__channelmember__role__in=['admin', 'owner'])
    ),
    deleted_at__isnull=True
).first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

if not topic.is_active:
    raise HttpError(400, "Topic is already archived")

# Archive
topic.is_active = False
topic.save(update_fields=['is_active', 'updated_at'])

return {
    "success": True,
    "message": "Topic archived successfully",
    "data": {
        "topic": {
            "id": str(topic.id),
            "title": topic.title,
            "is_active": topic.is_active,
            "archived_at": topic.updated_at.isoformat(),
        }
    }
}
```

---

## 7. POST /api/v1/topics/{topic_id}/restore

### Detail
Restore an archived or soft-deleted topic. Sets `is_active=True` and clears `deleted_at`.

### Flow
1. Authenticate user
2. Verify user has permission
3. Set `is_active=True` and `deleted_at=None`
4. Return restored status

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic restored successfully",
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Restored Discussion",
      "is_active": true,
      "restored_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicRestoreResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic'


@router.post("/topics/{topic_id}/restore", response=TopicRestoreResponse)
def restore_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `ChannelMember` (permission check)

### Django ORM Query (Proposed)
```python
# Verify permission (including soft-deleted topics)
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user) |
        Q(channel__channelmember__user=request.user,
          channel__channelmember__role__in=['admin', 'owner'])
    )
).first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

if topic.is_active and not topic.deleted_at:
    raise HttpError(400, "Topic is already active")

# Restore
topic.is_active = True
topic.deleted_at = None
topic.save(update_fields=['is_active', 'deleted_at', 'updated_at'])

return {
    "success": True,
    "message": "Topic restored successfully",
    "data": {
        "topic": {
            "id": str(topic.id),
            "title": topic.title,
            "is_active": topic.is_active,
            "restored_at": topic.updated_at.isoformat(),
        }
    }
}
```

---

## 8. POST /api/v1/topics/{topic_id}/read

### Detail
Mark a topic as read for the current user. Updates or creates a `ChatReadMarker` with the current timestamp.

### Flow
1. Authenticate user
2. Verify user has access to topic
3. Update or create read marker with current timestamp
4. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic marked as read",
  "data": {
    "topic_id": "450e8400-e29b-41d4-a716-446655440000",
    "last_read_at": "2026-05-23T03:14:00Z",
    "unread_count": 0
  }
}
```

### Pydantic for Django Ninja
```python
class TopicReadResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic_id', 'last_read_at', 'unread_count'


@router.post("/topics/{topic_id}/read", response=TopicReadResponse)
def mark_topic_read(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `ChatReadMarker`
- `TopicParticipant` (access check)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils import timezone

# Verify access
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user, channel__channelmember__is_active=True)
    ),
    is_active=True
).first()

if not topic:
    raise HttpError(404, "Topic not found or access denied")

# Update or create read marker
now = timezone.now()

read_marker, created = ChatReadMarker.objects.update_or_create(
    topic=topic,
    user=request.user,
    defaults={
        'last_read_at': now,
        'is_active': True
    }
)

return {
    "success": True,
    "message": "Topic marked as read",
    "data": {
        "topic_id": str(topic.id),
        "last_read_at": now.isoformat(),
        "unread_count": 0,
    }
}
```

---

## 9. POST /api/v1/topics/{topic_id}/pin

### Detail
Pin a topic to the top of the channel's topic list. Only channel admins can pin topics.

### Flow
1. Authenticate user
2. Verify user is channel admin
3. Set `is_pinned=True` on topic
4. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic pinned successfully",
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Important Announcement",
      "is_pinned": true,
      "pinned_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicPinResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic'


@router.post("/topics/{topic_id}/pin", response=TopicPinResponse)
def pin_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
# Verify admin permission
topic = ChatTopic.objects.filter(
    id=topic_id,
    channel__channelmember__user=request.user,
    channel__channelmember__role__in=['admin', 'owner'],
    channel__channelmember__is_active=True,
    is_active=True
).first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

# Check if field exists (needs to be added to model)
if not hasattr(topic, 'is_pinned'):
    raise HttpError(500, "Pin feature not implemented in model")

if topic.is_pinned:
    raise HttpError(400, "Topic is already pinned")

# Pin
topic.is_pinned = True
topic.save(update_fields=['is_pinned', 'updated_at'])

return {
    "success": True,
    "message": "Topic pinned successfully",
    "data": {
        "topic": {
            "id": str(topic.id),
            "title": topic.title,
            "is_pinned": topic.is_pinned,
            "pinned_at": topic.updated_at.isoformat(),
        }
    }
}
```

---

## 10. POST /api/v1/topics/{topic_id}/unpin

### Detail
Unpin a topic. Only channel admins can unpin topics.

### Flow
1. Authenticate user
2. Verify user is channel admin
3. Set `is_pinned=False` on topic
4. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Topic unpinned successfully",
  "data": {
    "topic": {
      "id": "450e8400-e29b-41d4-a716-446655440000",
      "title": "Old Announcement",
      "is_pinned": false,
      "unpinned_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicUnpinResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'topic'


@router.post("/topics/{topic_id}/unpin", response=TopicUnpinResponse)
def unpin_topic(request, topic_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
# Verify admin permission
topic = ChatTopic.objects.filter(
    id=topic_id,
    channel__channelmember__user=request.user,
    channel__channelmember__role__in=['admin', 'owner'],
    channel__channelmember__is_active=True,
    is_active=True
).first()

if not topic:
    raise HttpError(403, "Topic not found or insufficient permissions")

if not hasattr(topic, 'is_pinned'):
    raise HttpError(500, "Pin feature not implemented in model")

if not topic.is_pinned:
    raise HttpError(400, "Topic is not pinned")

# Unpin
topic.is_pinned = False
topic.save(update_fields=['is_pinned', 'updated_at'])

return {
    "success": True,
    "message": "Topic unpinned successfully",
    "data": {
        "topic": {
            "id": str(topic.id),
            "title": topic.title,
            "is_pinned": topic.is_pinned,
            "unpinned_at": topic.updated_at.isoformat(),
        }
    }
}
```

---

## 11. GET /api/v1/topics/{topic_id}/history

### Detail
Retrieve paginated message history for a topic. Includes messages with attachments, reactions, and sender information.

### Flow
1. Authenticate user
2. Verify user has access to topic
3. Query messages with related data
4. Apply pagination (newest first or oldest first)
5. Update read marker
6. Return message list

### Request JSON
```json
// Query Parameters
{
  "page": 1,
  "page_size": 50,
  "order": "desc",              // desc (newest first) or asc (oldest first)
  "before_message_id": null,    // Optional: fetch messages before this ID
  "after_message_id": null      // Optional: fetch messages after this ID
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "350e8400-e29b-41d4-a716-446655440000",
        "content": "This is a sample message",
        "message_type": "text",
        "sender": {
          "id": "950e8400-e29b-41d4-a716-446655440000",
          "username": "john.doe",
          "full_name": "John Doe"
        },
        "attachments": [],
        "reactions": [
          {
            "emoji": "👍",
            "count": 3,
            "users": ["user1", "user2", "user3"]
          }
        ],
        "status": "completed",
        "created_at": "2026-05-23T02:30:00Z",
        "updated_at": "2026-05-23T02:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total_items": 45,
      "total_pages": 1,
      "has_more": false
    }
  }
}
```

### Pydantic for Django Ninja
```python
class TopicHistoryFilters(Query):
    page: int = 1
    page_size: int = 50
    order: str = "desc"  # desc or asc
    before_message_id: Optional[UUID] = None
    after_message_id: Optional[UUID] = None


class MessageSenderOut(Schema):
    id: UUID
    username: str
    full_name: Optional[str]


class MessageReactionOut(Schema):
    emoji: str
    count: int
    users: List[str]


class MessageOut(Schema):
    id: UUID
    content: str
    message_type: str
    sender: MessageSenderOut
    attachments: List[dict]
    reactions: List[MessageReactionOut]
    status: str
    created_at: datetime
    updated_at: datetime


class TopicHistoryResponse(Schema):
    success: bool = True
    data: dict  # Contains 'messages' and 'pagination'


@router.get("/topics/{topic_id}/history", response=TopicHistoryResponse)
def get_topic_history(request, topic_id: UUID, filters: TopicHistoryFilters = Query(...)):
    # Implementation
    pass
```

### Models Involved
- `ChatTopic`
- `ChatMessage`
- `User`
- `Human` (for sender full name)
- `ChatAttachment`
- `ChatReaction`
- `TopicParticipant` (access check)
- `ChatReadMarker` (update on read)

### Django ORM Query (Proposed)
```python
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
from django.utils import timezone

# Verify access
topic = ChatTopic.objects.filter(
    Q(id=topic_id) &
    (
        Q(topicparticipant__user=request.user, topicparticipant__is_active=True) |
        Q(channel__channelmember__user=request.user, channel__channelmember__is_active=True)
    ),
    is_active=True
).first()

if not topic:
    raise HttpError(404, "Topic not found or access denied")

# Build query
messages_query = ChatMessage.objects.filter(
    topic=topic,
    is_active=True,
    deleted_at__isnull=True
).select_related(
    'sender',
    'sender__human_profile'
).prefetch_related(
    'attachments',
    'reactions__user'
)

# Apply cursor-based filters
if filters.before_message_id:
    messages_query = messages_query.filter(id__lt=filters.before_message_id)

if filters.after_message_id:
    messages_query = messages_query.filter(id__gt=filters.after_message_id)

# Order
if filters.order == "asc":
    messages_query = messages_query.order_by('created_at')
else:
    messages_query = messages_query.order_by('-created_at')

# Pagination
paginator = Paginator(messages_query, filters.page_size)
page_obj = paginator.get_page(filters.page)

# Format messages
messages_data = []
for message in page_obj:
    # Group reactions by emoji
    reactions_dict = {}
    for reaction in message.reactions.all():
        if reaction.emoji not in reactions_dict:
            reactions_dict[reaction.emoji] = {
                'emoji': reaction.emoji,
                'count': 0,
                'users': []
            }
        reactions_dict[reaction.emoji]['count'] += 1
        reactions_dict[reaction.emoji]['users'].append(reaction.user.username)
    
    messages_data.append({
        "id": message.id,
        "content": message.content,
        "message_type": message.message_type,
        "sender": {
            "id": message.sender.id,
            "username": message.sender.username,
            "full_name": getattr(message.sender.human_profile, 'full_name', None) if hasattr(message.sender, 'human_profile') else None,
        },
        "attachments": [
            {
                "id": att.id,
                "type": att.attachment_type,
                "filename": att.original_filename,
                "url": att.file.url if att.file else None,
            }
            for att in message.attachments.all()
        ],
        "reactions": list(reactions_dict.values()),
        "status": message.status,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    })

# Update read marker
ChatReadMarker.objects.update_or_create(
    topic=topic,
    user=request.user,
    defaults={
        'last_read_at': timezone.now(),
        'is_active': True
    }
)

return {
    "success": True,
    "data": {
        "messages": messages_data,
        "pagination": {
            "page": filters.page,
            "page_size": filters.page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_more": page_obj.has_next(),
        }
    }
}
```

---

## Missing Models & Fields

### Models to Create

1. **TopicParticipant**
```python
class TopicParticipant(BaseModel):
    """
    Tracks users participating in a topic/thread.
    """
    topic = models.ForeignKey(
        'ChatTopic',
        on_delete=models.CASCADE,
        related_name='topicparticipant'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='topic_participations'
    )
    
    class Meta:
        db_table = 'workspace_topic_participant'
        constraints = [
            models.UniqueConstraint(
                fields=['topic', 'user'],
                name='uniq_topic_user_participant'
            )
        ]
```

2. **ChatReadMarker**
```python
class ChatReadMarker(BaseModel):
    """
    Tracks which messages a user has read in a topic.
    """
    topic = models.ForeignKey(
        'ChatTopic',
        on_delete=models.CASCADE,
        related_name='read_markers'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='chat_read_markers'
    )
    last_read_at = models.DateTimeField()
    last_read_message = models.ForeignKey(
        'ChatMessage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        db_table = 'workspace_chat_read_marker'
        constraints = [
            models.UniqueConstraconstraint(
                fields=['topic', 'user'],
                name='uniq_topic_user_read_marker'
            )
        ]
```

### Fields to Add to ChatTopic

```python
class ChatTopic(BaseModel, CompanyScoped, ProjectScoped):
    # Existing fields...
    
    # Add these:
    is_pinned = models.BooleanField(default=False, db_index=True)
    pinned_at = models.DateTimeField(null=True, blank=True)
    pinned_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pinned_topics'
    )
```

---

## Summary

This documentation covers all 11 Topic/Chat API endpoints with:
- Detailed descriptions
- Request/response flows
- JSON schemas
- Pydantic models for Django Ninja
- Involved database models
- Production-ready Django ORM queries
- Permission checks and validation logic
- Soft-delete patterns
- Pagination and cursor-based navigation
- Read tracking functionality
- Pin/unpin features

**Key patterns:**
- Participant-based access control
- Read marker tracking for unread counts
- Slug generation with collision handling
- Soft deletion with cascade options
- Pin/unpin for prioritization
- Cursor-based history pagination
