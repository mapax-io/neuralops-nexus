"""
The live browser's WebSocket: `GET /api/v1/browser/ws?ticket=…`.

Binary frames out are JPEG paints of whichever tab is in front — nothing else
goes over the wire as binary, so the app can treat every binary frame as an
image. Text frames are small JSON messages both ways: in, what a person did
(navigate, click, type, switch tab); out, the tab strip and any refusal.

The ticket is nucleus's word that this person holds the right; the worker
re-checks nothing about the person, only the signature and the expiry.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.core.config import settings
from apps.managers.browser import BrowserError, BrowserSession, is_available
from apps.managers.tickets import verify_ticket

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["browser"])

CLOSE_BAD_TICKET = 4401
CLOSE_TOO_MANY = 4429
CLOSE_IDLE = 4408
CLOSE_UNAVAILABLE = 4503

_open_sessions = 0


async def _say(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:  # noqa: BLE001
        pass


@router.websocket("/browser/ws")
async def browser_ws(ws: WebSocket) -> None:
    global _open_sessions
    # Accept first: a close before the handshake reaches the app as a bare 1006
    # and it could not say why.
    await ws.accept()
    # kind is required here: a terminal's ticket carries the same signature, and
    # the two rights are separate, so one must not open the other.
    claims = verify_ticket(ws.query_params.get("ticket"), settings.INTERNAL_API_KEY, require=("project_id", "kind"))
    if not claims or claims.get("kind") != "browser":
        await ws.close(code=CLOSE_BAD_TICKET)
        return
    if not (settings.BROWSER_ENABLED and is_available()):
        await _say(ws, {"type": "error", "message": "This server was not built with the live browser."})
        await ws.close(code=CLOSE_UNAVAILABLE)
        return
    if _open_sessions >= settings.BROWSER_MAX_SESSIONS:
        await ws.close(code=CLOSE_TOO_MANY)
        return

    # Built before the slot is taken, so nothing between the two can leak one.
    session = BrowserSession(
        on_frame=ws.send_bytes,
        on_state=lambda state: _say(ws, state),
        width=int(claims.get("width") or 1280),
        height=int(claims.get("height") or 800),
    )
    _open_sessions += 1
    log.info("[browser] open user=%s project=%s", claims.get("user_id"), claims.get("project_id"))
    # Two clocks: `idle` moves with every message and drives the timeout, so it
    # cannot also measure how long the session lasted (audit, 2026-09-21).
    started = idle = asyncio.get_event_loop().time()
    try:
        try:
            await session.start(claims.get("url") or None)
        except Exception as exc:  # noqa: BLE001
            log.warning("[browser] could not start: %s", exc)
            await _say(ws, {"type": "error", "message": "The browser could not start on the server."})
            await ws.close()
            return

        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.BROWSER_IDLE_SECONDS)
            except asyncio.TimeoutError:
                await _say(ws, {"type": "error", "message": "Closed after a while with nothing happening."})
                await ws.close(code=CLOSE_IDLE)
                return
            idle = asyncio.get_event_loop().time()
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            try:
                await _handle(session, message)
            except BrowserError as exc:
                await _say(ws, {"type": "error", "message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                log.warning("[browser] %s failed: %s", message.get("type"), exc)
                await _say(ws, {"type": "error", "message": "That did not work."})
    except WebSocketDisconnect:
        pass
    finally:
        _open_sessions -= 1
        await session.close()
        log.info("[browser] closed project=%s after %.0fs", claims.get("project_id"), asyncio.get_event_loop().time() - idle)


async def _handle(session: BrowserSession, message: dict) -> None:
    kind = message.get("type")
    if kind == "navigate":
        await session.navigate(str(message.get("url") or ""))
    elif kind == "open":
        await session.open_tab(str(message.get("url") or "") or None)
    elif kind == "close":
        await session.close_tab(str(message.get("tab") or ""))
    elif kind == "activate":
        await session.activate(str(message.get("tab") or ""))
    elif kind == "back":
        await session.back()
    elif kind == "forward":
        await session.forward()
    elif kind == "reload":
        await session.reload()
    elif kind == "resize":
        await session.resize(message.get("width") or 1280, message.get("height") or 800)
    elif kind == "mouse":
        await session.mouse(str(message.get("action") or "move"), message.get("x") or 0, message.get("y") or 0, str(message.get("button") or "left"))
    elif kind == "wheel":
        await session.wheel(message.get("dx") or 0, message.get("dy") or 0)
    elif kind == "key":
        await session.key(str(message.get("action") or "press"), str(message.get("key") or ""))
    elif kind == "text":
        await session.text(str(message.get("text") or ""))
