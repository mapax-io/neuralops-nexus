"""
Step 5 — the project file viewer (docs/NUCLEUS-REVAMP.md §3).

Browse, download and view-as-HTML over the project's folder on the server —
the same /nexus/projects/<slug>-<id8> folder the personas' filesystem tools
write into (workspace/services.get_project_folder_name; both containers
bind-mount ./projects there, verified in Step 0).

Safety, in plain words:
- Every path is resolved (symlinks followed) and must land INSIDE the
  project's folder — `..`, absolute paths and symlinks pointing out are all
  refused with a 400. The project folder is the wall.
- Rendered views have a size cap (big files are download-only).
- Rendered HTML is served with `Content-Security-Policy: sandbox`, which
  makes the browser run NO scripts from it — a file a persona (or anyone)
  wrote can't act in the viewer's browser.
- Who may look: the endpoints in workspace/api.py resolve the project the
  same way every other read does (project.view, with the topic-reach
  fallback).

Markdown rendering and code highlighting use the `markdown` and `Pygments`
packages WHEN the image has them (added to docker/dev/requirements.txt in
this step — an image built before that shows the same content as escaped,
readable plain text instead; nothing breaks).
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from datetime import datetime, timezone as dt_timezone
from html import escape
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Render caps — a view is for READING; anything bigger is download-only.
RENDER_MAX_BYTES = 2 * 1024 * 1024          # text/markdown/code shown as HTML
IMAGE_RENDER_MAX_BYTES = 8 * 1024 * 1024    # images are embedded as data URIs
LIST_MAX_ENTRIES = 500

MARKDOWN_EXTS = {".md", ".markdown", ".mdown"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}

# Optional renderers — present once the image is rebuilt with this step's
# requirements.txt; everything degrades to escaped plain text without them.
try:  # pragma: no cover - depends on the installed image
    import markdown as _markdown
except ImportError:  # pragma: no cover
    _markdown = None
try:  # pragma: no cover
    from pygments import highlight as _pyg_highlight
    from pygments.formatters import HtmlFormatter as _PygFormatter
    from pygments.lexers import get_lexer_for_filename as _pyg_lexer_for
    from pygments.util import ClassNotFound as _PygClassNotFound
except ImportError:  # pragma: no cover
    _pyg_highlight = None


class FileViewerError(Exception):
    """A refused file request; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# ── The wall ──────────────────────────────────────────────────────────────────

def project_root(project) -> Path:
    from .services import get_project_folder_name

    return (Path(settings.PROJECTS_ROOT) / get_project_folder_name(project)).resolve()


def resolve_path(project, rel: str | None) -> tuple[Path, Path]:
    """
    (root, target) with the target resolved (symlinks followed) and proven to
    be the root itself or inside it. Everything else is a 400 — `..`, an
    absolute path, a symlink pointing out, a null byte.
    """
    root = project_root(project)
    if not root.is_dir():
        raise FileViewerError(409, "This project has no folder on the server yet.")

    rel = (rel or "").strip()
    if "\x00" in rel:
        raise FileViewerError(400, "That path isn't valid.")
    rel = rel.lstrip("/")

    try:
        target = (root / rel).resolve() if rel else root
    except OSError:
        raise FileViewerError(400, "That path isn't valid.")

    if target != root and root not in target.parents:
        raise FileViewerError(400, "That path points outside the project's folder.")
    return root, target


# ── Browse ────────────────────────────────────────────────────────────────────

def list_folder(project, rel: str | None) -> dict:
    """The folder's entries, folders first then by name, capped and flagged."""
    root, target = resolve_path(project, rel)
    if not target.exists():
        raise FileViewerError(404, "No such folder in this project.")
    if not target.is_dir():
        raise FileViewerError(400, "That's a file — fetch it from files/content/ instead.")

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise FileViewerError(400, f"That folder can't be read: {exc.__class__.__name__}.")

    truncated = False
    for child in children:
        if len(entries) >= LIST_MAX_ENTRIES:
            truncated = True
            break
        try:
            stat = child.stat()
            is_dir = child.is_dir()
        except OSError:
            continue  # a broken symlink or a vanished file is just skipped
        entries.append({
            "name": child.name,
            "type": "dir" if is_dir else "file",
            "size": None if is_dir else stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
        })

    return {
        "path": str(target.relative_to(root)) if target != root else "",
        "entries": entries,
        "truncated": truncated,
    }


# ── Download ──────────────────────────────────────────────────────────────────

def open_for_download(project, rel: str | None) -> tuple[Path, str]:
    """(path, content_type) for a plain download — no size cap, streamed."""
    root, target = resolve_path(project, rel)
    if not target.exists():
        raise FileViewerError(404, "No such file in this project.")
    if target.is_dir():
        raise FileViewerError(400, "That's a folder — list it from files/ instead.")
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target, content_type


# ── View as HTML ──────────────────────────────────────────────────────────────

def render_html(project, rel: str | None) -> str:
    """
    One self-contained HTML page for the file: markdown rendered, code
    highlighted, text and images shown directly — all inside the size caps.
    Served with CSP `sandbox` by the endpoint, so nothing in it can run.
    """
    root, target = resolve_path(project, rel)
    if not target.exists():
        raise FileViewerError(404, "No such file in this project.")
    if target.is_dir():
        raise FileViewerError(400, "That's a folder — list it from files/ instead.")

    ext = target.suffix.lower()
    size = target.stat().st_size

    if ext in IMAGE_EXTS:
        if size > IMAGE_RENDER_MAX_BYTES:
            raise FileViewerError(413, "This image is too big to view — download it instead.")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = base64.b64encode(target.read_bytes()).decode()
        body = f'<img src="data:{content_type};base64,{data}" alt="{escape(target.name)}">'
        return _page(target.name, body)

    if size > RENDER_MAX_BYTES:
        raise FileViewerError(413, "This file is too big to view — download it instead.")

    raw = target.read_bytes()
    if b"\x00" in raw[:8192]:
        raise FileViewerError(415, "This file isn't text — download it instead.")
    text = raw.decode("utf-8", errors="replace")

    if ext in MARKDOWN_EXTS and _markdown is not None:
        body = _markdown.markdown(text, extensions=["fenced_code", "tables"])
    elif _pyg_highlight is not None and ext not in MARKDOWN_EXTS and ext not in (".txt", ""):
        try:
            lexer = _pyg_lexer_for(target.name)
            body = _pyg_highlight(text, lexer, _PygFormatter(noclasses=True))
        except _PygClassNotFound:
            body = f"<pre>{escape(text)}</pre>"
    else:
        # No renderer installed (or plain text): readable, escaped, safe.
        body = f"<pre>{escape(text)}</pre>"

    return _page(target.name, body)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  body {{ margin: 0; padding: 24px; font: 15px/1.6 -apple-system, system-ui, sans-serif;
         color: #1a1a1a; background: #ffffff; max-width: 920px; }}
  pre {{ padding: 12px; background: #f6f6f6; border-radius: 6px; overflow-x: auto;
        font: 13px/1.5 ui-monospace, monospace; white-space: pre-wrap; word-break: break-word; }}
  img {{ max-width: 100%; height: auto; }}
  table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e8e8e8; background: #141414; }}
    pre {{ background: #1f1f1f; }} td, th {{ border-color: #444; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
