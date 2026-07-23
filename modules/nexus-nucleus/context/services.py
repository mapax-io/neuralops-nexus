"""
Context services — attach / detach / list ContextSources for a topic.

Flow for file attach:
    1. Save ContextSource (status=pending)
    2. Extract text content from the file
    3. POST to nexus-ai /embed/ → get collection_id back
    4. Update ContextSource (collection_id, status=ready)

Flow for web attach:
    1. Save ContextSource (status=pending)
    2. Fetch URL content with httpx
    3. POST to nexus-ai /embed/ → get collection_id back
    4. Update ContextSource (collection_id, status=ready)

Flow for detach:
    1. DELETE nexus-ai /embed/context-source/{collection_id}/ (if embedded)
    2. Delete file from disk (if file source)
    3. Delete ContextSource record
"""
from __future__ import annotations

import hashlib
import logging
from typing import IO

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def list_context_sources(topic_id: str) -> list:
    from nucleus.models import ContextSource
    return list(
        ContextSource.objects.filter(topic_id=topic_id, is_active=True)
        .order_by("created_at")
    )


# ---------------------------------------------------------------------------
# Attach — file
# ---------------------------------------------------------------------------

def attach_file(
    *,
    company,
    topic,
    uploaded_file,
    name: str | None = None,
) -> object:
    """
    Save a file context source and embed it via nexus-ai.
    Returns the saved ContextSource instance.
    """
    from nucleus.models import ContextSource

    source_name = name or uploaded_file.name

    # Compute SHA-256 checksum to detect duplicates
    checksum = _compute_checksum(uploaded_file)

    # Return existing ready source if same file already embedded in this topic
    existing = ContextSource.objects.filter(
        topic=topic,
        checksum=checksum,
        status=ContextSource.Status.READY,
        is_active=True,
    ).first()
    if existing:
        logger.info("[context] duplicate file skipped (checksum=%s, source=%s)", checksum, existing.id)
        return existing

    source = ContextSource.objects.create(
        company=company,
        topic=topic,
        type=ContextSource.Type.FILE,
        name=source_name,
        file=uploaded_file,
        file_size=uploaded_file.size,
        mime_type=getattr(uploaded_file, "content_type", ""),
        checksum=checksum,
        status=ContextSource.Status.PENDING,
    )

    # Extract text and embed
    try:
        content = _extract_file_content(source.file, source_name)
        collection_id = _embed(
            source_id=str(source.id),
            label=source_name,
            content=content,
            source_type="file",
            topic_id=str(topic.id),
            channel_id=str(topic.channel_id),
            project_id=str(topic.project_id),
            company_id=str(company.id),
        )
        source.collection_id = collection_id
        source.status = ContextSource.Status.READY
        source.error = None
    except Exception as exc:
        logger.error("[context] embed failed for source %s: %s", source.id, exc)
        source.status = ContextSource.Status.ERROR
        source.error = str(exc)

    source.save(update_fields=["collection_id", "status", "error"])
    return source


# ---------------------------------------------------------------------------
# Attach — web
# ---------------------------------------------------------------------------

def attach_web(
    *,
    company,
    topic,
    url: str,
    name: str | None = None,
) -> object:
    """
    Fetch a web URL, embed its content via nexus-ai, return ContextSource.
    """
    from nucleus.models import ContextSource

    source_name = name or url
    source = ContextSource.objects.create(
        company=company,
        topic=topic,
        type=ContextSource.Type.WEB,
        name=source_name,
        url=url,
        status=ContextSource.Status.PENDING,
    )

    try:
        content = _fetch_url(url)
        collection_id = _embed(
            source_id=str(source.id),
            label=source_name,
            content=content,
            source_type="file",
            topic_id=str(topic.id),
            channel_id=str(topic.channel_id),
            project_id=str(topic.project_id),
            company_id=str(company.id),
        )
        source.collection_id = collection_id
        source.status = ContextSource.Status.READY
        source.error = None
    except Exception as exc:
        logger.error("[context] web embed failed for source %s: %s", source.id, exc)
        source.status = ContextSource.Status.ERROR
        source.error = str(exc)

    source.save(update_fields=["collection_id", "status", "error"])
    return source


# ---------------------------------------------------------------------------
# Detach
# ---------------------------------------------------------------------------

def detach_context_source(source_id: str) -> bool:
    """
    Remove a context source — delete vectors from nexus-ai and the DB record.
    Returns True if found and deleted, False if not found.
    """
    from nucleus.models import ContextSource

    try:
        source = ContextSource.objects.get(id=source_id, is_active=True)
    except ContextSource.DoesNotExist:
        return False

    # Delete vectors from ChromaDB via nexus-ai
    if source.collection_id:
        _delete_collection(source.collection_id)

    # Delete the file from disk
    if source.file:
        try:
            source.file.delete(save=False)
        except Exception as exc:
            logger.warning("[context] could not delete file for source %s: %s", source_id, exc)

    source.delete()
    return True


# ---------------------------------------------------------------------------
# Helpers — nexus-ai calls
# ---------------------------------------------------------------------------

def _embed(
    *,
    source_id: str,
    label: str,
    content: str,
    source_type: str = "file",
    topic_id: str = "",
    channel_id: str = "",
    project_id: str = "",
    company_id: str = "",
) -> str:
    """POST to nexus-ai /embed/ and return the collection_id."""
    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")

    if not nexus_ai_url:
        raise RuntimeError("NEXUS_AI_URL not configured")

    resp = httpx.post(
        f"{nexus_ai_url}/api/v1/embed/",
        json={
            "source_id": source_id,
            "type": source_type,
            "label": label,
            "content": content,
            "topic_id": topic_id,
            "channel_id": channel_id,
            "project_id": project_id,
            "company_id": company_id,
        },
        headers={"X-Internal-Key": internal_key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["collection_id"]


def _delete_collection(collection_id: str) -> None:
    """DELETE nexus-ai /embed/context-source/{collection_id}/."""
    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")

    if not nexus_ai_url:
        return

    try:
        httpx.delete(
            f"{nexus_ai_url}/api/v1/embed/context-source/{collection_id}/",
            headers={"X-Internal-Key": internal_key},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("[context] failed to delete collection %s: %s", collection_id, exc)


# ---------------------------------------------------------------------------
# Helpers — content extraction
# ---------------------------------------------------------------------------

def _extract_file_content(file_field, filename: str) -> str:
    """Extract plain text from a file (txt, pdf, docx, or any code file)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    file_field.open("rb")
    try:
        if ext == "pdf":
            return _extract_pdf(file_field)
        elif ext == "docx":
            return _extract_docx(file_field)
        else:
            # Plain text, source code, markdown, etc.
            raw = file_field.read()
            return raw.decode("utf-8", errors="replace")
    finally:
        file_field.close()


def _extract_pdf(file_obj) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(file_obj)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        raise RuntimeError("pypdf not installed — cannot extract PDF content")


def _extract_docx(file_obj) -> str:
    try:
        import docx
        doc = docx.Document(file_obj)
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise RuntimeError("python-docx not installed — cannot extract DOCX content")


def _fetch_url(url: str) -> str:
    """Fetch a web page and return its text content."""
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        # Strip HTML tags with a simple approach
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            return _strip_html(resp.text)
        return resp.text
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch URL {url}: {exc}")


def _compute_checksum(uploaded_file) -> str:
    """Return SHA-256 hex digest of an uploaded file's bytes."""
    h = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        h.update(chunk)
    uploaded_file.seek(0)  # reset so the file can still be saved by Django
    return h.hexdigest()


def _strip_html(html: str) -> str:
    """Very basic HTML-to-text stripping."""
    import re
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html).strip()
    return html
