"""
W21 Terminal: a shell session on a PTY in the project folder, reached over a
WebSocket with a ticket nucleus signed. A real terminal: interactive, with a
controlling terminal, resizable, ended when the socket goes.
"""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from apps.core.config import settings
from apps.managers.terminal import TerminalSession, sign_ticket, verify_ticket

SECRET = settings.INTERNAL_API_KEY


def claims(tmp_path, **over):
    base = {"project_id": "p1", "project_name": "Alpha", "user_id": "u1", "cwd": str(tmp_path)}
    base.update(over)
    return base


# ── tickets ──────────────────────────────────────────────────────────────────
def test_a_ticket_round_trips_and_carries_its_claims(tmp_path):
    ticket = sign_ticket(claims(tmp_path), SECRET)
    out = verify_ticket(ticket, SECRET)
    assert out["cwd"] == str(tmp_path) and out["project_id"] == "p1" and out["exp"] > time.time()


def test_a_tampered_expired_or_foreign_ticket_is_refused(tmp_path):
    ticket = sign_ticket(claims(tmp_path), SECRET)
    payload, signature = ticket.rsplit(".", 1)
    assert verify_ticket(payload + "." + signature[:-1] + ("0" if signature[-1] != "0" else "1"), SECRET) is None
    assert verify_ticket(ticket, "another-secret") is None
    assert verify_ticket(sign_ticket(claims(tmp_path), SECRET, ttl=-1), SECRET) is None
    assert verify_ticket(None, SECRET) is None and verify_ticket("garbage", SECRET) is None
    assert verify_ticket(sign_ticket({"project_id": "p1"}, SECRET), SECRET) is None  # no cwd


# ── the session ──────────────────────────────────────────────────────────────
async def read_until(session, needle: bytes, timeout: float = 8.0) -> bytes:
    """Output until `needle` shows -- typed text is echoed back, so callers split their markers when typing."""
    seen = b""
    async def collect():
        nonlocal seen
        async for chunk in session.output():
            seen += chunk
            if needle in seen:
                return
    await asyncio.wait_for(collect(), timeout=timeout)
    return seen


@pytest.mark.asyncio
async def test_a_shell_starts_in_the_project_folder_answers_and_keeps_its_cwd(tmp_path):
    (tmp_path / "sub").mkdir()
    session = TerminalSession(cwd=str(tmp_path), project_name="Alpha")
    await session.start()
    try:
        session.write(b"pwd; echo MARK\"\"-1\n")
        out = await read_until(session, b"MARK-1")
        assert str(tmp_path).encode() in out
        session.write(b"cd sub && pwd; echo MARK\"\"-2\n")
        out = await read_until(session, b"MARK-2")
        assert (str(tmp_path) + "/sub").encode() in out  # a real shell: cd sticks
        session.write(b"env | sort; echo MARK\"\"-3\n")
        out = await read_until(session, b"MARK-3")
        assert b"INTERNAL_API_KEY" not in out and b"NEURALOPS_PROJECT=Alpha" in out  # sanitized env
        session.resize(120, 40)
        session.write(b"tput cols; echo MARK\"\"-4\n")
        out = await read_until(session, b"MARK-4")
        assert b"120" in out
    finally:
        await session.close()
    assert session.process.returncode is not None  # nothing left running


def test_the_shell_gets_its_terminal_under_uvloop_too(tmp_path):
    """The server runs uvloop, whose child setup differs from asyncio's (2026-09-21: a preexec_fn ioctl failed there)."""
    uvloop = pytest.importorskip("uvloop")

    async def scenario():
        session = TerminalSession(cwd=str(tmp_path))
        await session.start()
        try:
            session.write(b"tty; echo MARK\"\"-U\n")
            out = await read_until(session, b"MARK-U")
            assert b"/dev/pts/" in out  # a controlling terminal, not "not a tty"
            session.write(b"sleep 30 &\nkill %1 && echo JOB\"\"-OK\n")
            out = await read_until(session, b"JOB-OK")  # job control works
        finally:
            await session.close()

    uvloop.run(scenario())


@pytest.mark.asyncio
async def test_a_missing_folder_does_not_start_a_shell(tmp_path):
    session = TerminalSession(cwd=str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError):
        await session.start()


# ── the socket ───────────────────────────────────────────────────────────────
def test_the_socket_needs_a_valid_ticket(tmp_path):
    from apps.main import app
    client = TestClient(app)
    # Accepted, then closed with a code the app can read (a refusal before the
    # handshake would reach the browser as a bare 403 with no code).
    with client.websocket_connect("/api/v1/terminal/ws?ticket=nope") as ws:
        message = ws.receive()
    assert (message["type"], message["code"]) == ("websocket.close", 4401)


def test_the_socket_carries_a_shell_and_resizes_it(tmp_path):
    from apps.main import app
    client = TestClient(app)
    ticket = sign_ticket(claims(tmp_path), SECRET)
    with client.websocket_connect(f"/api/v1/terminal/ws?ticket={ticket}") as ws:
        ws.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
        ws.send_bytes(b"tput cols; echo MARK\"\"-WS\n")
        seen = b""
        for _ in range(50):
            message = ws.receive()
            if message.get("bytes"):
                seen += message["bytes"]
            if b"MARK-WS" in seen:
                break
        assert b"100" in seen
