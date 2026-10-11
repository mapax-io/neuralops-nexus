"""
Terminal (W21): the WebSocket that carries a shell session.

`GET /api/v1/terminal/ws?ticket=…` -- nginx exposes it as /terminal/ws. Binary
frames are the terminal's bytes in both directions; text frames are small
JSON control messages: from the app `{"type": "resize", "cols", "rows"}`, to
the app `{"type": "exit" | "error" | "idle", "message"}` before the close.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.core.config import settings
from apps.managers.terminal import TerminalSession, verify_ticket

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["terminal"])

# Close codes the app can tell apart.
CLOSE_BAD_TICKET = 4401
CLOSE_TOO_MANY = 4429
CLOSE_IDLE = 4408

_open_sessions = 0


async def _say(ws: WebSocket, kind: str, message: str) -> None:
    try:
        await ws.send_text(json.dumps({"type": kind, "message": message}))
    except Exception:
        pass


@router.websocket("/terminal/ws")
async def terminal_ws(ws: WebSocket) -> None:
    global _open_sessions
    # Accept before refusing: a close before the handshake reaches the browser
    # as a bare HTTP 403 (code 1006), and the app could not say why.
    await ws.accept()
    claims = verify_ticket(ws.query_params.get("ticket"), settings.INTERNAL_API_KEY)
    if not claims:
        await ws.close(code=CLOSE_BAD_TICKET)
        return
    if _open_sessions >= settings.TERMINAL_MAX_SESSIONS:
        await ws.close(code=CLOSE_TOO_MANY)
        return
    _open_sessions += 1
    session = TerminalSession(cwd=claims["cwd"], project_name=claims.get("project_name"))
    log.info("[terminal] open user=%s project=%s cwd=%s", claims.get("user_id"), claims.get("project_id"), claims["cwd"])
    try:
        try:
            await session.start()
        except Exception as exc:
            await _say(ws, "error", f"The shell could not start: {exc}")
            await ws.close()
            return

        async def pump_output() -> None:
            async for chunk in session.output():
                await ws.send_bytes(chunk)
            await _say(ws, "exit", "The shell exited.")
            await ws.close()

        pump = asyncio.create_task(pump_output())
        try:
            while True:
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=settings.TERMINAL_IDLE_SECONDS)
                except asyncio.TimeoutError:
                    await _say(ws, "idle", f"Closed after {settings.TERMINAL_IDLE_SECONDS // 60} minutes without input.")
                    await ws.close(code=CLOSE_IDLE)
                    break
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    session.write(message["bytes"])
                elif message.get("text"):
                    try:
                        control = json.loads(message["text"])
                    except ValueError:
                        continue
                    if control.get("type") == "resize":
                        session.resize(control.get("cols", 80), control.get("rows", 24))
        except WebSocketDisconnect:
            pass
        finally:
            pump.cancel()
            try:
                await pump
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        await session.close()
        _open_sessions -= 1
        log.info("[terminal] closed user=%s project=%s", claims.get("user_id"), claims.get("project_id"))
