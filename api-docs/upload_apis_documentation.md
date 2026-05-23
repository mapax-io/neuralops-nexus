# Upload APIs Documentation

## Table of Contents
1. [POST /api/v1/uploads](#post-apiv1uploads)
2. [GET /api/v1/uploads/{upload_id}](#get-apiv1uploadsuploaded)
3. [DELETE /api/v1/uploads/{upload_id}](#delete-apiv1uploadsuploaded)
4. [POST /api/v1/uploads/{upload_id}/complete](#post-apiv1uploadsuploaded_complete)
5. [POST /api/v1/uploads/multipart/start](#post-apiv1uploadsmultipartstart)
6. [POST /api/v1/uploads/multipart/{upload_id}/part](#post-apiv1uploadsmultipartuploaded_part)
7. [POST /api/v1/uploads/multipart/{upload_id}/finish](#post-apiv1uploadsmultipartuploaded_finish)
8. [POST /api/v1/uploads/multipart/{upload_id}/abort](#post-apiv1uploadsmultipartuploaded_abort)

---

## POST /api/v1/uploads

### Detail
Creates a new upload session for a single file upload. This endpoint initializes the upload process and returns an upload ID that can be used to track the upload status.

### Flow
1. Client sends upload metadata (filename, size, content type)
2. Server validates the request
3. Server creates an Upload record in the database
4. Server generates a presigned URL for direct upload (if using cloud storage)
5. Server returns upload ID and upload URL
6. Client uploads file to the provided URL
7. Client calls complete endpoint when upload finishes

### Request JSON
```json
{
  "filename": "document.pdf",
  "file_size": 1048576,
  "content_type": "application/pdf",
  "metadata": {
    "description": "Project documentation",
    "tags": ["project", "documentation"]
  }
}
```

### Response JSON
```json
{
  "upload_id": "upl_7d8f9e0a1b2c3d4e",
  "upload_url": "https://storage.example.com/presigned-url",
  "expires_at": "2026-05-23T05:28:00Z",
  "status": "pending",
  "created_at": "2026-05-23T04:28:00Z"
}
```

### Pydantic for Django Ninja
```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime

class UploadCreateRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=5368709120)  # Max 5GB
    content_type: str = Field(..., max_length=100)
    metadata: Optional[Dict[str, Any]] = None

    @validator('filename')
    def validate_filename(cls, v):
        if '..' in v or '/' in v:
            raise ValueError('Invalid filename')
        return v

class UploadCreateResponse(BaseModel):
    upload_id: str
    upload_url: str
    expires_at: datetime
    status: str
    created_at: datetime
```

### List Model Involved
- **Upload**: Main model storing upload metadata
- **User**: Owner of the upload
- **File**: Final file record after upload completion

### Django ORM Query (Proposed)
```python
from django.utils import timezone
from datetime import timedelta

# Create upload record
upload = Upload.objects.create(
    user=request.user,
    filename=data.filename,
    file_size=data.file_size,
    content_type=data.content_type,
    metadata=data.metadata,
    status='pending',
    expires_at=timezone.now() + timedelta(hours=1)
)

# Generate presigned URL (example with S3)
upload_url = storage_service.generate_presigned_url(
    key=f"uploads/{upload.id}/{upload.filename}",
    expires_in=3600
)
```

---

## GET /api/v1/uploads/{upload_id}

### Detail
Retrieves the status and metadata of an existing upload session. Useful for tracking upload progress and checking completion status.

### Flow
1. Client sends GET request with upload_id
2. Server validates upload_id and user permissions
3. Server retrieves Upload record from database
4. Server returns upload status and metadata

### Request JSON
No request body (GET request with URL parameter)

### Response JSON
```json
{
  "upload_id": "upl_7d8f9e0a1b2c3d4e",
  "filename": "document.pdf",
  "file_size": 1048576,
  "content_type": "application/pdf",
  "status": "completed",
  "progress": 100,
  "metadata": {
    "description": "Project documentation",
    "tags": ["project", "documentation"]
  },
  "created_at": "2026-05-23T04:28:00Z",
  "completed_at": "2026-05-23T04:30:00Z",
  "file_url": "https://cdn.example.com/files/document.pdf"
}
```

### Pydantic for Django Ninja
```python
class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    file_size: int
    content_type: str
    status: str  # pending, uploading, completed, failed, aborted
    progress: int = Field(ge=0, le=100)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    file_url: Optional[str] = None
    error_message: Optional[str] = None
```

### List Model Involved
- **Upload**: Main upload record
- **User**: Owner verification
- **File**: Associated file if upload is completed

### Django ORM Query (Proposed)
```python
from django.shortcuts import get_object_or_404

# Retrieve upload with user permission check
upload = get_object_or_404(
    Upload.objects.select_related('file'),
    id=upload_id,
    user=request.user
)

# Calculate progress if multipart
if upload.is_multipart:
    total_parts = upload.multipart_parts.count()
    completed_parts = upload.multipart_parts.filter(status='completed').count()
    progress = (completed_parts / total_parts * 100) if total_parts > 0 else 0
else:
    progress = 100 if upload.status == 'completed' else 0
```

---

## DELETE /api/v1/uploads/{upload_id}

### Detail
Cancels and deletes an upload session. Cleans up any partial uploads and associated resources.

### Flow
1. Client sends DELETE request with upload_id
2. Server validates upload_id and user permissions
3. Server checks if upload can be deleted (not already completed)
4. Server deletes uploaded files from storage
5. Server marks upload as deleted or removes record
6. Server returns confirmation

### Request JSON
No request body (DELETE request with URL parameter)

### Response JSON
```json
{
  "success": true,
  "message": "Upload deleted successfully",
  "upload_id": "upl_7d8f9e0a1b2c3d4e"
}
```

### Pydantic for Django Ninja
```python
class UploadDeleteResponse(BaseModel):
    success: bool
    message: str
    upload_id: str
```

### List Model Involved
- **Upload**: Upload record to be deleted
- **MultipartPart**: Parts to be cleaned up (if multipart)
- **User**: Owner verification

### Django ORM Query (Proposed)
```python
from django.db import transaction

with transaction.atomic():
    # Get upload with lock
    upload = Upload.objects.select_for_update().get(
        id=upload_id,
        user=request.user
    )
    
    # Only allow deletion if not completed
    if upload.status == 'completed':
        raise ValueError("Cannot delete completed upload")
    
    # Delete from storage
    if upload.storage_key:
        storage_service.delete(upload.storage_key)
    
    # Delete multipart parts if applicable
    if upload.is_multipart:
        for part in upload.multipart_parts.all():
            if part.storage_key:
                storage_service.delete(part.storage_key)
        upload.multipart_parts.all().delete()
    
    # Delete upload record
    upload.delete()
```

---

## POST /api/v1/uploads/{upload_id}/complete

### Detail
Marks a single-file upload as complete and triggers post-processing. This endpoint is called after the file has been successfully uploaded to the presigned URL.

### Flow
1. Client completes file upload to storage
2. Client sends POST request to complete endpoint
3. Server validates upload completion in storage
4. Server updates upload status to 'completed'
5. Server creates File record
6. Server triggers any post-processing (virus scan, thumbnail generation, etc.)
7. Server returns completion confirmation with file URL

### Request JSON
```json
{
  "etag": "d41d8cd98f00b204e9800998ecf8427e",
  "checksum": "sha256:abcdef123456..."
}
```

### Response JSON
```json
{
  "success": true,
  "upload_id": "upl_7d8f9e0a1b2c3d4e",
  "file_id": "fil_9a8b7c6d5e4f3g2h",
  "file_url": "https://cdn.example.com/files/document.pdf",
  "status": "completed",
  "completed_at": "2026-05-23T04:30:00Z"
}
```

### Pydantic for Django Ninja
```python
class UploadCompleteRequest(BaseModel):
    etag: Optional[str] = None
    checksum: Optional[str] = None

class UploadCompleteResponse(BaseModel):
    success: bool
    upload_id: str
    file_id: str
    file_url: str
    status: str
    completed_at: datetime
```

### List Model Involved
- **Upload**: Upload record to be completed
- **File**: New file record created
- **User**: Owner of the file

### Django ORM Query (Proposed)
```python
from django.db import transaction
from django.utils import timezone

with transaction.atomic():
    # Get upload with lock
    upload = Upload.objects.select_for_update().get(
        id=upload_id,
        user=request.user,
        status='pending'
    )
    
    # Verify file exists in storage
    if not storage_service.exists(upload.storage_key):
        raise ValueError("File not found in storage")
    
    # Create File record
    file = File.objects.create(
        user=request.user,
        filename=upload.filename,
        file_size=upload.file_size,
        content_type=upload.content_type,
        storage_key=upload.storage_key,
        metadata=upload.metadata,
        etag=request.etag,
        checksum=request.checksum
    )
    
    # Update upload status
    upload.status = 'completed'
    upload.completed_at = timezone.now()
    upload.file = file
    upload.save()
    
    # Trigger post-processing tasks
    process_file_task.delay(file.id)
```

---

## POST /api/v1/uploads/multipart/start

### Detail
Initiates a multipart upload session for large files. Allows files to be uploaded in chunks, which is more reliable for large files and enables resume functionality.

### Flow
1. Client sends multipart upload request with file metadata
2. Server creates Upload record with multipart flag
3. Server initiates multipart upload in storage backend
4. Server calculates number of parts based on file size
5. Server returns upload_id and part count
6. Client uploads each part separately

### Request JSON
```json
{
  "filename": "large-video.mp4",
  "file_size": 524288000,
  "content_type": "video/mp4",
  "part_size": 5242880,
  "metadata": {
    "title": "Training Video",
    "category": "education"
  }
}
```

### Response JSON
```json
{
  "upload_id": "upl_multipart_1a2b3c4d",
  "part_count": 100,
  "part_size": 5242880,
  "status": "initiated",
  "created_at": "2026-05-23T04:28:00Z",
  "expires_at": "2026-05-24T04:28:00Z"
}
```

### Pydantic for Django Ninja
```python
class MultipartUploadStartRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=107374182400)  # Max 100GB
    content_type: str = Field(..., max_length=100)
    part_size: int = Field(default=5242880, ge=5242880, le=104857600)  # 5MB to 100MB
    metadata: Optional[Dict[str, Any]] = None

class MultipartUploadStartResponse(BaseModel):
    upload_id: str
    part_count: int
    part_size: int
    status: str
    created_at: datetime
    expires_at: datetime
```

### List Model Involved
- **Upload**: Main upload record with multipart flag
- **MultipartPart**: Individual part records
- **User**: Owner of the upload

### Django ORM Query (Proposed)
```python
from django.utils import timezone
from datetime import timedelta
import math

with transaction.atomic():
    # Calculate part count
    part_count = math.ceil(file_size / part_size)
    
    # Create multipart upload
    upload = Upload.objects.create(
        user=request.user,
        filename=data.filename,
        file_size=data.file_size,
        content_type=data.content_type,
        metadata=data.metadata,
        is_multipart=True,
        part_size=data.part_size,
        part_count=part_count,
        status='initiated',
        expires_at=timezone.now() + timedelta(days=1)
    )
    
    # Initiate multipart upload in storage
    multipart_upload_id = storage_service.create_multipart_upload(
        key=f"uploads/{upload.id}/{upload.filename}"
    )
    
    upload.storage_multipart_id = multipart_upload_id
    upload.save()
    
    # Create part records
    MultipartPart.objects.bulk_create([
        MultipartPart(
            upload=upload,
            part_number=i,
            status='pending'
        )
        for i in range(1, part_count + 1)
    ])
```

---

## POST /api/v1/uploads/multipart/{upload_id}/part

### Detail
Uploads a single part of a multipart upload. Each part is uploaded separately and can be retried independently.

### Flow
1. Client sends request for a specific part number
2. Server validates upload session and part number
3. Server generates presigned URL for that specific part
4. Server returns presigned URL
5. Client uploads part data to presigned URL
6. Client confirms part upload with ETag
7. Server updates part status

### Request JSON
```json
{
  "part_number": 1,
  "etag": "d41d8cd98f00b204e9800998ecf8427e"
}
```

### Response JSON
```json
{
  "upload_id": "upl_multipart_1a2b3c4d",
  "part_number": 1,
  "upload_url": "https://storage.example.com/presigned-part-url",
  "expires_at": "2026-05-23T05:28:00Z",
  "status": "uploading"
}
```

### Pydantic for Django Ninja
```python
class MultipartPartUploadRequest(BaseModel):
    part_number: int = Field(..., ge=1, le=10000)
    etag: Optional[str] = None  # Provided after upload completion

class MultipartPartUploadResponse(BaseModel):
    upload_id: str
    part_number: int
    upload_url: str
    expires_at: datetime
    status: str
```

### List Model Involved
- **Upload**: Parent multipart upload
- **MultipartPart**: Specific part being uploaded
- **User**: Owner verification

### Django ORM Query (Proposed)
```python
# Get upload and verify ownership
upload = Upload.objects.get(
    id=upload_id,
    user=request.user,
    is_multipart=True,
    status='initiated'
)

# Get or update part
part = MultipartPart.objects.get(
    upload=upload,
    part_number=part_number
)

# If ETag provided, update part completion
if request.etag:
    part.etag = request.etag
    part.status = 'completed'
    part.completed_at = timezone.now()
    part.save()
else:
    # Generate presigned URL for part upload
    upload_url = storage_service.generate_multipart_presigned_url(
        upload_id=upload.storage_multipart_id,
        part_number=part_number,
        expires_in=3600
    )
    
    part.status = 'uploading'
    part.save()
```

---

## POST /api/v1/uploads/multipart/{upload_id}/finish

### Detail
Completes a multipart upload by combining all uploaded parts into a single file. This endpoint verifies all parts are uploaded and finalizes the upload.

### Flow
1. Client sends finish request with all part ETags
2. Server validates all parts are uploaded
3. Server sends complete-multipart request to storage
4. Storage combines all parts into final file
5. Server creates File record
6. Server updates Upload status to 'completed'
7. Server triggers post-processing
8. Server returns file URL

### Request JSON
```json
{
  "parts": [
    {"part_number": 1, "etag": "etag1"},
    {"part_number": 2, "etag": "etag2"},
    {"part_number": 3, "etag": "etag3"}
  ]
}
```

### Response JSON
```json
{
  "success": true,
  "upload_id": "upl_multipart_1a2b3c4d",
  "file_id": "fil_9a8b7c6d5e4f3g2h",
  "file_url": "https://cdn.example.com/files/large-video.mp4",
  "status": "completed",
  "completed_at": "2026-05-23T04:35:00Z",
  "file_size": 524288000
}
```

### Pydantic for Django Ninja
```python
class MultipartPartInfo(BaseModel):
    part_number: int = Field(..., ge=1)
    etag: str

class MultipartUploadFinishRequest(BaseModel):
    parts: List[MultipartPartInfo]

class MultipartUploadFinishResponse(BaseModel):
    success: bool
    upload_id: str
    file_id: str
    file_url: str
    status: str
    completed_at: datetime
    file_size: int
```

### List Model Involved
- **Upload**: Multipart upload to be completed
- **MultipartPart**: All parts to be verified
- **File**: New file record created
- **User**: Owner of the file

### Django ORM Query (Proposed)
```python
from django.db import transaction

with transaction.atomic():
    # Get upload with lock
    upload = Upload.objects.select_for_update().select_related('user').get(
        id=upload_id,
        user=request.user,
        is_multipart=True,
        status='initiated'
    )
    
    # Verify all parts are completed
    parts = upload.multipart_parts.all().order_by('part_number')
    
    if parts.count() != upload.part_count:
        raise ValueError("Not all parts uploaded")
    
    if parts.filter(status__ne='completed').exists():
        raise ValueError("Some parts are not completed")
    
    # Complete multipart upload in storage
    storage_service.complete_multipart_upload(
        upload_id=upload.storage_multipart_id,
        parts=[{"PartNumber": p.part_number, "ETag": p.etag} for p in parts]
    )
    
    # Create File record
    file = File.objects.create(
        user=request.user,
        filename=upload.filename,
        file_size=upload.file_size,
        content_type=upload.content_type,
        storage_key=f"uploads/{upload.id}/{upload.filename}",
        metadata=upload.metadata
    )
    
    # Update upload
    upload.status = 'completed'
    upload.completed_at = timezone.now()
    upload.file = file
    upload.save()
    
    # Trigger post-processing
    process_file_task.delay(file.id)
```

---

## POST /api/v1/uploads/multipart/{upload_id}/abort

### Detail
Aborts a multipart upload session and cleans up all uploaded parts. Used when the client decides to cancel the upload.

### Flow
1. Client sends abort request
2. Server validates upload session
3. Server aborts multipart upload in storage
4. Storage deletes all uploaded parts
5. Server updates upload status to 'aborted'
6. Server returns confirmation

### Request JSON
```json
{
  "reason": "User cancelled upload"
}
```

### Response JSON
```json
{
  "success": true,
  "upload_id": "upl_multipart_1a2b3c4d",
  "status": "aborted",
  "message": "Multipart upload aborted successfully",
  "parts_deleted": 25
}
```

### Pydantic for Django Ninja
```python
class MultipartUploadAbortRequest(BaseModel):
    reason: Optional[str] = None

class MultipartUploadAbortResponse(BaseModel):
    success: bool
    upload_id: str
    status: str
    message: str
    parts_deleted: int
```

### List Model Involved
- **Upload**: Multipart upload to be aborted
- **MultipartPart**: Parts to be deleted
- **User**: Owner verification

### Django ORM Query (Proposed)
```python
from django.db import transaction

with transaction.atomic():
    # Get upload with lock
    upload = Upload.objects.select_for_update().get(
        id=upload_id,
        user=request.user,
        is_multipart=True
    )
    
    # Only allow abort if not completed
    if upload.status == 'completed':
        raise ValueError("Cannot abort completed upload")
    
    # Count parts for response
    parts_count = upload.multipart_parts.count()
    
    # Abort multipart upload in storage
    if upload.storage_multipart_id:
        storage_service.abort_multipart_upload(
            upload_id=upload.storage_multipart_id
        )
    
    # Delete part records
    upload.multipart_parts.all().delete()
    
    # Update upload status
    upload.status = 'aborted'
    upload.aborted_at = timezone.now()
    upload.abort_reason = request.reason
    upload.save()
```

---

## Models Schema (Django)

```python
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Upload(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('initiated', 'Initiated'),
        ('uploading', 'Uploading'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted'),
    ]
    
    id = models.CharField(max_length=50, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploads')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100)
    metadata = models.JSONField(null=True, blank=True)
    
    # Multipart specific fields
    is_multipart = models.BooleanField(default=False)
    part_size = models.IntegerField(null=True, blank=True)
    part_count = models.IntegerField(null=True, blank=True)
    storage_multipart_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Storage
    storage_key = models.CharField(max_length=500, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    aborted_at = models.DateTimeField(null=True, blank=True)
    abort_reason = models.TextField(null=True, blank=True)
    
    # Relations
    file = models.ForeignKey('File', on_delete=models.SET_NULL, null=True, blank=True, related_name='upload_session')
    
    class Meta:
        db_table = 'uploads'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
        ]

class MultipartPart(models.Model):
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='multipart_parts')
    part_number = models.IntegerField()
    etag = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')
    storage_key = models.CharField(max_length=500, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'multipart_parts'
        unique_together = [['upload', 'part_number']]
        indexes = [
            models.Index(fields=['upload', 'part_number']),
            models.Index(fields=['status']),
        ]

class File(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='files')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100)
    storage_key = models.CharField(max_length=500)
    metadata = models.JSONField(null=True, blank=True)
    etag = models.CharField(max_length=255, null=True, blank=True)
    checksum = models.CharField(max_length=255, null=True, blank=True)
    
    # URLs
    file_url = models.URLField(max_length=1000)
    thumbnail_url = models.URLField(max_length=1000, null=True, blank=True)
    
    # Processing
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'files'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['content_type']),
        ]
```

---

## Summary

This documentation covers all 8 upload API endpoints with:
- Detailed explanations of each endpoint's purpose
- Complete request/response flows
- JSON schemas for requests and responses
- Pydantic models for Django Ninja validation
- Database models involved
- Proposed Django ORM queries with transaction handling

The upload system supports both single-file uploads (for smaller files) and multipart uploads (for large files), with proper status tracking, cleanup, and error handling.
