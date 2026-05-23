# Channel APIs Documentation

## Table of Contents
1. [GET /api/v1/projects/{project_id}/channels](#1-get-apiv1projectsproject_idchannels)
2. [POST /api/v1/projects/{project_id}/channels](#2-post-apiv1projectsproject_idchannels)
3. [GET /api/v1/channels/{channel_id}](#3-get-apiv1channelschannel_id)
4. [PATCH /api/v1/channels/{channel_id}](#4-patch-apiv1channelschannel_id)
5. [DELETE /api/v1/channels/{channel_id}](#5-delete-apiv1channelschannel_id)
6. [POST /api/v1/channels/{channel_id}/archive](#6-post-apiv1channelschannel_idarchive)
7. [POST /api/v1/channels/{channel_id}/restore](#7-post-apiv1channelschannel_idrestore)
8. [GET /api/v1/channels/{channel_id}/members](#8-get-apiv1channelschannel_idmembers)
9. [POST /api/v1/channels/{channel_id}/members](#9-post-apiv1channelschannel_idmembers)
10. [PATCH /api/v1/channels/{channel_id}/members/{user_id}](#10-patch-apiv1channelschannel_idmembersuser_id)
11. [DELETE /api/v1/channels/{channel_id}/members/{user_id}](#11-delete-apiv1channelschannel_idmembersuser_id)

---

## 1. GET /api/v1/projects/{project_id}/channels

### Detail
List all channels within a specific project. Supports filtering by active/archived status and pagination.

### Flow
1. Authenticate user via JWT
2. Verify user has access to the project
3. Query channels belonging to the project
4. Apply filters (active/archived)
5. Return paginated list with member counts

### Request JSON
```json
// Query Parameters
{
  "is_active": true,           // Optional: filter by active status
  "include_archived": false,   // Optional: include soft-deleted
  "page": 1,                   // Optional: pagination
  "page_size": 20              // Optional: items per page
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "channels": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "General",
        "slug": "general",
        "description": "Main project discussion channel",
        "project_id": "650e8400-e29b-41d4-a716-446655440000",
        "company_id": "750e8400-e29b-41d4-a716-446655440000",
        "is_active": true,
        "member_count": 12,
        "created_at": "2026-05-20T10:30:00Z",
        "updated_at": "2026-05-22T14:45:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 5,
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


class ChannelListFilters(Query):
    is_active: Optional[bool] = True
    include_archived: Optional[bool] = False
    page: int = 1
    page_size: int = 20


class ChannelOut(Schema):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    project_id: UUID
    company_id: UUID
    is_active: bool
    member_count: int
    created_at: datetime
    updated_at: datetime


class PaginationOut(Schema):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ChannelListResponse(Schema):
    success: bool = True
    data: dict  # Contains 'channels' and 'pagination'


@router.get("/projects/{project_id}/channels", response=ChannelListResponse)
def list_channels(request, project_id: UUID, filters: ChannelListFilters = Query(...)):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `Project`
- `Company`
- `ChannelMember` (for member count)
- `User` (implicit via authentication)

### Django ORM Query (Proposed)
```python
from django.core.paginator import Paginator
from django.db.models import Count, Q

# Verify project access
project = Project.objects.filter(
    id=project_id,
    company__members=request.user,
    is_active=True
).first()

if not project:
    raise HttpError(404, "Project not found or access denied")

# Build query
channels_query = Channel.objects.filter(
    project=project,
    company=project.company
)

# Apply filters
if filters.is_active is not None:
    channels_query = channels_query.filter(is_active=filters.is_active)

if not filters.include_archived:
    channels_query = channels_query.filter(deleted_at__isnull=True)

# Annotate with member count
channels_query = channels_query.annotate(
    member_count=Count('channelmember', filter=Q(channelmember__is_active=True))
).select_related('project', 'company')

# Pagination
paginator = Paginator(channels_query, filters.page_size)
page_obj = paginator.get_page(filters.page)

channels_data = [
    {
        "id": channel.id,
        "name": channel.name,
        "slug": channel.slug,
        "description": channel.description,
        "project_id": channel.project_id,
        "company_id": channel.company_id,
        "is_active": channel.is_active,
        "member_count": channel.member_count,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }
    for channel in page_obj
]

return {
    "success": True,
    "data": {
        "channels": channels_data,
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

## 2. POST /api/v1/projects/{project_id}/channels

### Detail
Create a new channel within a project. Auto-generates slug from name and adds creator as first member.

### Flow
1. Authenticate user
2. Verify user has permission to create channels in project (admin/owner)
3. Validate channel name uniqueness within project
4. Generate slug
5. Create channel record
6. Add creator as channel admin
7. Return created channel

### Request JSON
```json
{
  "name": "Backend Development",
  "description": "Discussion for backend API work",
  "is_active": true
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "channel": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Backend Development",
      "slug": "backend-development",
      "description": "Discussion for backend API work",
      "project_id": "650e8400-e29b-41d4-a716-446655440000",
      "company_id": "750e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "member_count": 1,
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


class ChannelCreateIn(Schema):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class ChannelCreateResponse(Schema):
    success: bool = True
    data: dict  # Contains 'channel'


@router.post("/projects/{project_id}/channels", response=ChannelCreateResponse)
@transaction.atomic
def create_channel(request, project_id: UUID, payload: ChannelCreateIn):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `Project`
- `Company`
- `ChannelMember` (auto-created for creator)
- `User`
- `CompanyAccess` (permission check)

### Django ORM Query (Proposed)
```python
from django.utils.text import slugify
from django.db import transaction

# Verify project access and permission
project = Project.objects.filter(
    id=project_id,
    company__companyaccess__user=request.user,
    company__companyaccess__role__in=['owner', 'admin'],
    is_active=True
).select_related('company').first()

if not project:
    raise HttpError(403, "Insufficient permissions or project not found")

# Check name uniqueness
slug = slugify(payload.name)
if Channel.objects.filter(project=project, slug=slug).exists():
    raise HttpError(400, "Channel with this name already exists in project")

# Create channel
with transaction.atomic():
    channel = Channel.objects.create(
        name=payload.name,
        slug=slug,
        description=payload.description,
        project=project,
        company=project.company,
        is_active=payload.is_active
    )
    
    # Add creator as admin member
    ChannelMember.objects.create(
        channel=channel,
        user=request.user,
        role='admin',
        is_active=True
    )

return {
    "success": True,
    "data": {
        "channel": {
            "id": channel.id,
            "name": channel.name,
            "slug": channel.slug,
            "description": channel.description,
            "project_id": channel.project_id,
            "company_id": channel.company_id,
            "is_active": channel.is_active,
            "member_count": 1,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }
    }
}
```

---

## 3. GET /api/v1/channels/{channel_id}

### Detail
Retrieve detailed information about a specific channel including member count, recent activity, and metadata.

### Flow
1. Authenticate user
2. Verify user is a member of the channel or has company-level access
3. Fetch channel details
4. Include member count, topic count, last activity
5. Return channel data

### Request JSON
```json
// No request body - path parameter only
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "channel": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "General",
      "slug": "general",
      "description": "Main project discussion channel",
      "project_id": "650e8400-e29b-41d4-a716-446655440000",
      "project_name": "AI Platform",
      "company_id": "750e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "member_count": 12,
      "topic_count": 45,
      "last_activity_at": "2026-05-23T02:30:00Z",
      "created_at": "2026-05-20T10:30:00Z",
      "updated_at": "2026-05-22T14:45:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelDetailOut(Schema):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    project_id: UUID
    project_name: str
    company_id: UUID
    is_active: bool
    member_count: int
    topic_count: int
    last_activity_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ChannelDetailResponse(Schema):
    success: bool = True
    data: dict  # Contains 'channel'


@router.get("/channels/{channel_id}", response=ChannelDetailResponse)
def get_channel(request, channel_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `Project`
- `Company`
- `ChannelMember`
- `ChatTopic`
- `ChatMessage` (for last activity)

### Django ORM Query (Proposed)
```python
from django.db.models import Count, Max, Q

# Fetch channel with access check
channel = Channel.objects.filter(
    Q(id=channel_id) &
    (
        Q(channelmember__user=request.user, channelmember__is_active=True) |
        Q(company__companyaccess__user=request.user)
    )
).select_related('project', 'company').annotate(
    member_count=Count('channelmember', filter=Q(channelmember__is_active=True)),
    topic_count=Count('topics', filter=Q(topics__is_active=True)),
    last_activity_at=Max('topics__messages__created_at')
).first()

if not channel:
    raise HttpError(404, "Channel not found or access denied")

return {
    "success": True,
    "data": {
        "channel": {
            "id": channel.id,
            "name": channel.name,
            "slug": channel.slug,
            "description": channel.description,
            "project_id": channel.project_id,
            "project_name": channel.project.name,
            "company_id": channel.company_id,
            "is_active": channel.is_active,
            "member_count": channel.member_count,
            "topic_count": channel.topic_count,
            "last_activity_at": channel.last_activity_at,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }
    }
}
```

---

## 4. PATCH /api/v1/channels/{channel_id}

### Detail
Update channel properties. Only admins/owners can modify channel settings.

### Flow
1. Authenticate user
2. Verify user has admin/owner role in channel
3. Validate update payload
4. Update channel fields
5. Regenerate slug if name changed
6. Return updated channel

### Request JSON
```json
{
  "name": "General Discussion",
  "description": "Updated channel description",
  "is_active": true
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "channel": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "General Discussion",
      "slug": "general-discussion",
      "description": "Updated channel description",
      "project_id": "650e8400-e29b-41d4-a716-446655440000",
      "company_id": "750e8400-e29b-41d4-a716-446655440000",
      "is_active": true,
      "member_count": 12,
      "created_at": "2026-05-20T10:30:00Z",
      "updated_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ChannelUpdateResponse(Schema):
    success: bool = True
    data: dict  # Contains 'channel'


@router.patch("/channels/{channel_id}", response=ChannelUpdateResponse)
def update_channel(request, channel_id: UUID, payload: ChannelUpdateIn):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils.text import slugify
from django.db.models import Count, Q

# Verify channel access and admin permission
channel = Channel.objects.filter(
    id=channel_id,
    channelmember__user=request.user,
    channelmember__role__in=['admin', 'owner'],
    channelmember__is_active=True
).select_related('project', 'company').first()

if not channel:
    raise HttpError(403, "Channel not found or insufficient permissions")

# Update fields
update_fields = []

if payload.name is not None:
    new_slug = slugify(payload.name)
    
    # Check slug uniqueness if name changed
    if new_slug != channel.slug:
        if Channel.objects.filter(
            project=channel.project, 
            slug=new_slug
        ).exclude(id=channel_id).exists():
            raise HttpError(400, "Channel with this name already exists in project")
    
    channel.name = payload.name
    channel.slug = new_slug
    update_fields.extend(['name', 'slug'])

if payload.description is not None:
    channel.description = payload.description
    update_fields.append('description')

if payload.is_active is not None:
    channel.is_active = payload.is_active
    update_fields.append('is_active')

if update_fields:
    update_fields.append('updated_at')
    channel.save(update_fields=update_fields)

# Get member count
member_count = ChannelMember.objects.filter(
    channel=channel, 
    is_active=True
).count()

return {
    "success": True,
    "data": {
        "channel": {
            "id": channel.id,
            "name": channel.name,
            "slug": channel.slug,
            "description": channel.description,
            "project_id": channel.project_id,
            "company_id": channel.company_id,
            "is_active": channel.is_active,
            "member_count": member_count,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }
    }
}
```

---

## 5. DELETE /api/v1/channels/{channel_id}

### Detail
Soft-delete a channel. Sets `deleted_at` timestamp and marks `is_active=False`. Only owners can delete channels.

### Flow
1. Authenticate user
2. Verify user is channel owner or company owner
3. Check if channel can be deleted (not default/required channel)
4. Soft-delete channel (set deleted_at, is_active=False)
5. Optionally cascade soft-delete to topics
6. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Channel deleted successfully",
  "data": {
    "channel_id": "550e8400-e29b-41d4-a716-446655440000",
    "deleted_at": "2026-05-23T03:14:00Z"
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelDeleteResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'channel_id' and 'deleted_at'


@router.delete("/channels/{channel_id}", response=ChannelDeleteResponse)
def delete_channel(request, channel_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `ChannelMember` (permission check)
- `ChatTopic` (cascade soft-delete)
- `User`

### Django ORM Query (Proposed)
```python
from django.utils import timezone
from django.db import transaction

# Verify ownership
channel = Channel.objects.filter(
    Q(id=channel_id) &
    (
        Q(channelmember__user=request.user, channelmember__role='owner') |
        Q(company__companyaccess__user=request.user, company__companyaccess__role='owner')
    ),
    deleted_at__isnull=True
).select_related('company', 'project').first()

if not channel:
    raise HttpError(403, "Channel not found or insufficient permissions")

# Check if it's a protected channel (e.g., 'general')
if channel.slug == 'general':
    raise HttpError(400, "Cannot delete the default 'general' channel")

# Soft delete
with transaction.atomic():
    now = timezone.now()
    
    channel.deleted_at = now
    channel.is_active = False
    channel.save(update_fields=['deleted_at', 'is_active', 'updated_at'])
    
    # Optionally soft-delete all topics
    ChatTopic.objects.filter(channel=channel, deleted_at__isnull=True).update(
        deleted_at=now,
        is_active=False
    )

return {
    "success": True,
    "message": "Channel deleted successfully",
    "data": {
        "channel_id": str(channel.id),
        "deleted_at": channel.deleted_at.isoformat(),
    }
}
```

---

## 6. POST /api/v1/channels/{channel_id}/archive

### Detail
Archive a channel without deleting it. Sets `is_active=False` but keeps `deleted_at=None`. Archived channels are hidden from default views but can be restored.

### Flow
1. Authenticate user
2. Verify user has admin/owner permission
3. Set `is_active=False`
4. Keep channel data intact
5. Return archived channel status

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Channel archived successfully",
  "data": {
    "channel": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Old Backend Channel",
      "is_active": false,
      "archived_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelArchiveResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'channel'


@router.post("/channels/{channel_id}/archive", response=ChannelArchiveResponse)
def archive_channel(request, channel_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
# Verify admin access
channel = Channel.objects.filter(
    id=channel_id,
    channelmember__user=request.user,
    channelmember__role__in=['admin', 'owner'],
    channelmember__is_active=True,
    deleted_at__isnull=True
).first()

if not channel:
    raise HttpError(403, "Channel not found or insufficient permissions")

if not channel.is_active:
    raise HttpError(400, "Channel is already archived")

# Archive
channel.is_active = False
channel.save(update_fields=['is_active', 'updated_at'])

return {
    "success": True,
    "message": "Channel archived successfully",
    "data": {
        "channel": {
            "id": str(channel.id),
            "name": channel.name,
            "is_active": channel.is_active,
            "archived_at": channel.updated_at.isoformat(),
        }
    }
}
```

---

## 7. POST /api/v1/channels/{channel_id}/restore

### Detail
Restore an archived or soft-deleted channel. Sets `is_active=True` and clears `deleted_at`.

### Flow
1. Authenticate user
2. Verify user has admin/owner permission
3. Set `is_active=True` and `deleted_at=None`
4. Return restored channel status

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Channel restored successfully",
  "data": {
    "channel": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Backend Channel",
      "is_active": true,
      "restored_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelRestoreResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'channel'


@router.post("/channels/{channel_id}/restore", response=ChannelRestoreResponse)
def restore_channel(request, channel_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `Channel`
- `ChannelMember` (permission check)
- `User`

### Django ORM Query (Proposed)
```python
# Verify admin access (including soft-deleted channels)
channel = Channel.objects.filter(
    Q(id=channel_id) &
    (
        Q(channelmember__user=request.user, channelmember__role__in=['admin', 'owner']) |
        Q(company__companyaccess__user=request.user, company__companyaccess__role='owner')
    )
).first()

if not channel:
    raise HttpError(403, "Channel not found or insufficient permissions")

if channel.is_active and not channel.deleted_at:
    raise HttpError(400, "Channel is already active")

# Restore
channel.is_active = True
channel.deleted_at = None
channel.save(update_fields=['is_active', 'deleted_at', 'updated_at'])

return {
    "success": True,
    "message": "Channel restored successfully",
    "data": {
        "channel": {
            "id": str(channel.id),
            "name": channel.name,
            "is_active": channel.is_active,
            "restored_at": channel.updated_at.isoformat(),
        }
    }
}
```

---

## 8. GET /api/v1/channels/{channel_id}/members

### Detail
List all members of a channel with their roles and activity status. Supports pagination and filtering.

### Flow
1. Authenticate user
2. Verify user is a channel member or has company admin access
3. Query channel members
4. Include user details and roles
5. Return paginated member list

### Request JSON
```json
// Query Parameters
{
  "is_active": true,      // Optional: filter by active status
  "role": "member",       // Optional: filter by role
  "page": 1,
  "page_size": 20
}
```

### Response JSON
```json
{
  "success": true,
  "data": {
    "members": [
      {
        "id": "850e8400-e29b-41d4-a716-446655440000",
        "user_id": "950e8400-e29b-41d4-a716-446655440000",
        "username": "john.doe",
        "email": "john@example.com",
        "full_name": "John Doe",
        "role": "admin",
        "is_active": true,
        "joined_at": "2026-05-20T10:30:00Z",
        "last_seen_at": "2026-05-23T02:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 12,
      "total_pages": 1
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelMemberFilters(Query):
    is_active: Optional[bool] = True
    role: Optional[str] = None
    page: int = 1
    page_size: int = 20


class ChannelMemberOut(Schema):
    id: UUID
    user_id: UUID
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    joined_at: datetime
    last_seen_at: Optional[datetime]


class ChannelMembersResponse(Schema):
    success: bool = True
    data: dict  # Contains 'members' and 'pagination'


@router.get("/channels/{channel_id}/members", response=ChannelMembersResponse)
def list_channel_members(request, channel_id: UUID, filters: ChannelMemberFilters = Query(...)):
    # Implementation
    pass
```

### Models Involved
- `ChannelMember`
- `Channel`
- `User`
- `Human` (for full_name, profile data)

### Django ORM Query (Proposed)
```python
from django.core.paginator import Paginator

# Verify channel access
channel = Channel.objects.filter(
    Q(id=channel_id) &
    (
        Q(channelmember__user=request.user) |
        Q(company__companyaccess__user=request.user)
    ),
    is_active=True
).first()

if not channel:
    raise HttpError(404, "Channel not found or access denied")

# Query members
members_query = ChannelMember.objects.filter(
    channel=channel
).select_related('user', 'user__human_profile')

# Apply filters
if filters.is_active is not None:
    members_query = members_query.filter(is_active=filters.is_active)

if filters.role:
    members_query = members_query.filter(role=filters.role)

# Pagination
paginator = Paginator(members_query, filters.page_size)
page_obj = paginator.get_page(filters.page)

members_data = [
    {
        "id": member.id,
        "user_id": member.user_id,
        "username": member.user.username,
        "email": member.user.email,
        "full_name": getattr(member.user.human_profile, 'full_name', None),
        "role": member.role,
        "is_active": member.is_active,
        "joined_at": member.created_at,
        "last_seen_at": getattr(member, 'last_seen_at', None),
    }
    for member in page_obj
]

return {
    "success": True,
    "data": {
        "members": members_data,
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

## 9. POST /api/v1/channels/{channel_id}/members

### Detail
Add a new member to a channel. Only admins/owners can add members. User must be a member of the parent company.

### Flow
1. Authenticate user
2. Verify user has admin/owner permission in channel
3. Validate target user exists and is company member
4. Check if user is already a channel member
5. Add user with specified role
6. Return new member details

### Request JSON
```json
{
  "user_id": "950e8400-e29b-41d4-a716-446655440000",
  "role": "member"
}
```

### Response JSON
```json
{
  "success": true,
  "message": "Member added successfully",
  "data": {
    "member": {
      "id": "850e8400-e29b-41d4-a716-446655440000",
      "user_id": "950e8400-e29b-41d4-a716-446655440000",
      "username": "jane.smith",
      "email": "jane@example.com",
      "role": "member",
      "is_active": true,
      "joined_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelMemberAddIn(Schema):
    user_id: UUID
    role: str = "member"  # member, admin, owner


class ChannelMemberAddResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'member'


@router.post("/channels/{channel_id}/members", response=ChannelMemberAddResponse)
def add_channel_member(request, channel_id: UUID, payload: ChannelMemberAddIn):
    # Implementation
    pass
```

### Models Involved
- `ChannelMember`
- `Channel`
- `User`
- `CompanyAccess` (verify user is company member)

### Django ORM Query (Proposed)
```python
from django.db import transaction

# Verify channel admin access
channel = Channel.objects.filter(
    id=channel_id,
    channelmember__user=request.user,
    channelmember__role__in=['admin', 'owner'],
    channelmember__is_active=True,
    is_active=True
).select_related('company').first()

if not channel:
    raise HttpError(403, "Channel not found or insufficient permissions")

# Verify target user exists and is company member
target_user = User.objects.filter(
    id=payload.user_id,
    company_access__company=channel.company,
    company_access__is_active=True,
    is_active=True
).first()

if not target_user:
    raise HttpError(404, "User not found or not a member of the company")

# Check if already a member
existing_member = ChannelMember.objects.filter(
    channel=channel,
    user=target_user
).first()

if existing_member:
    if existing_member.is_active:
        raise HttpError(400, "User is already a member of this channel")
    else:
        # Reactivate
        existing_member.is_active = True
        existing_member.role = payload.role
        existing_member.save(update_fields=['is_active', 'role', 'updated_at'])
        member = existing_member
else:
    # Create new member
    member = ChannelMember.objects.create(
        channel=channel,
        user=target_user,
        role=payload.role,
        is_active=True
    )

return {
    "success": True,
    "message": "Member added successfully",
    "data": {
        "member": {
            "id": str(member.id),
            "user_id": str(member.user_id),
            "username": target_user.username,
            "email": target_user.email,
            "role": member.role,
            "is_active": member.is_active,
            "joined_at": member.created_at.isoformat(),
        }
    }
}
```

---

## 10. PATCH /api/v1/channels/{channel_id}/members/{user_id}

### Detail
Update a channel member's role or status. Only admins/owners can modify member roles.

### Flow
1. Authenticate user
2. Verify user has admin/owner permission
3. Validate target member exists
4. Prevent self-demotion if last owner
5. Update member role/status
6. Return updated member details

### Request JSON
```json
{
  "role": "admin",
  "is_active": true
}
```

### Response JSON
```json
{
  "success": true,
  "message": "Member updated successfully",
  "data": {
    "member": {
      "id": "850e8400-e29b-41d4-a716-446655440000",
      "user_id": "950e8400-e29b-41d4-a716-446655440000",
      "username": "jane.smith",
      "role": "admin",
      "is_active": true,
      "updated_at": "2026-05-23T03:14:00Z"
    }
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelMemberUpdateIn(Schema):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ChannelMemberUpdateResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'member'


@router.patch("/channels/{channel_id}/members/{user_id}", response=ChannelMemberUpdateResponse)
def update_channel_member(request, channel_id: UUID, user_id: UUID, payload: ChannelMemberUpdateIn):
    # Implementation
    pass
```

### Models Involved
- `ChannelMember`
- `Channel`
- `User`

### Django ORM Query (Proposed)
```python
# Verify channel admin access
is_admin = ChannelMember.objects.filter(
    channel_id=channel_id,
    user=request.user,
    role__in=['admin', 'owner'],
    is_active=True
).exists()

if not is_admin:
    raise HttpError(403, "Insufficient permissions")

# Get target member
member = ChannelMember.objects.filter(
    channel_id=channel_id,
    user_id=user_id
).select_related('user', 'channel').first()

if not member:
    raise HttpError(404, "Member not found")

# Prevent self-demotion if last owner
if payload.role and payload.role != 'owner' and member.user_id == request.user.id:
    owner_count = ChannelMember.objects.filter(
        channel_id=channel_id,
        role='owner',
        is_active=True
    ).count()
    
    if owner_count == 1:
        raise HttpError(400, "Cannot demote the last owner")

# Update member
update_fields = []

if payload.role is not None:
    member.role = payload.role
    update_fields.append('role')

if payload.is_active is not None:
    member.is_active = payload.is_active
    update_fields.append('is_active')

if update_fields:
    update_fields.append('updated_at')
    member.save(update_fields=update_fields)

return {
    "success": True,
    "message": "Member updated successfully",
    "data": {
        "member": {
            "id": str(member.id),
            "user_id": str(member.user_id),
            "username": member.user.username,
            "role": member.role,
            "is_active": member.is_active,
            "updated_at": member.updated_at.isoformat(),
        }
    }
}
```

---

## 11. DELETE /api/v1/channels/{channel_id}/members/{user_id}

### Detail
Remove a member from a channel. Sets `is_active=False` on the ChannelMember record. Only admins/owners can remove members.

### Flow
1. Authenticate user
2. Verify user has admin/owner permission
3. Validate target member exists
4. Prevent removal of last owner
5. Deactivate member (soft delete)
6. Return success confirmation

### Request JSON
```json
// No request body
```

### Response JSON
```json
{
  "success": true,
  "message": "Member removed successfully",
  "data": {
    "channel_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "950e8400-e29b-41d4-a716-446655440000",
    "removed_at": "2026-05-23T03:14:00Z"
  }
}
```

### Pydantic for Django Ninja
```python
class ChannelMemberRemoveResponse(Schema):
    success: bool = True
    message: str
    data: dict  # Contains 'channel_id', 'user_id', 'removed_at'


@router.delete("/channels/{channel_id}/members/{user_id}", response=ChannelMemberRemoveResponse)
def remove_channel_member(request, channel_id: UUID, user_id: UUID):
    # Implementation
    pass
```

### Models Involved
- `ChannelMember`
- `Channel`
- `User`

### Django ORM Query (Proposed)
```python
from django.utils import timezone

# Verify admin access
is_admin = ChannelMember.objects.filter(
    channel_id=channel_id,
    user=request.user,
    role__in=['admin', 'owner'],
    is_active=True
).exists()

if not is_admin:
    raise HttpError(403, "Insufficient permissions")

# Get target member
member = ChannelMember.objects.filter(
    channel_id=channel_id,
    user_id=user_id,
    is_active=True
).first()

if not member:
    raise HttpError(404, "Active member not found")

# Prevent removal of last owner
if member.role == 'owner':
    owner_count = ChannelMember.objects.filter(
        channel_id=channel_id,
        role='owner',
        is_active=True
    ).count()
    
    if owner_count == 1:
        raise HttpError(400, "Cannot remove the last owner")

# Soft delete
member.is_active = False
member.deleted_at = timezone.now()
member.save(update_fields=['is_active', 'deleted_at', 'updated_at'])

return {
    "success": True,
    "message": "Member removed successfully",
    "data": {
        "channel_id": str(channel_id),
        "user_id": str(user_id),
        "removed_at": member.deleted_at.isoformat(),
    }
}
```

---

## Missing Model: ChannelMember

**Note:** The `ChannelMember` model is referenced throughout this documentation but does not exist in the provided migrations. It needs to be created:

```python
class ChannelMember(BaseModel, CompanyScoped):
    """
    Represents membership in a channel with role-based access.
    """
    channel = models.ForeignKey(
        'Channel',
        on_delete=models.CASCADE,
        related_name='channelmember'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='channel_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=[
            ('owner', 'Owner'),
            ('admin', 'Admin'),
            ('member', 'Member'),
            ('viewer', 'Viewer'),
        ],
        default='member',
        db_index=True
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'workspace_channel_member'
        constraints = [
            models.UniqueConstraint(
                fields=['channel', 'user'],
                name='uniq_channel_user_member'
            )
        ]
        indexes = [
            models.Index(fields=['channel', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
```

---

## Summary

This documentation covers all 11 Channel API endpoints with:
- Detailed descriptions
- Request/response flows
- JSON schemas
- Pydantic models for Django Ninja
- Involved database models
- Production-ready Django ORM queries
- Permission checks and validation logic
- Soft-delete patterns
- Pagination support

**Key patterns:**
- Role-based access control (owner > admin > member > viewer)
- Soft deletion with `deleted_at` timestamps
- Slug generation from names
- Pagination on list endpoints
- Proper permission checks at query level
- Atomic transactions for multi-step operations
