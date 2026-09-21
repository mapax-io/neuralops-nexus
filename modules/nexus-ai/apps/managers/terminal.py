"""
Terminal (W21): a real shell session in the project's folder, on a PTY.

Nucleus signs a short-lived ticket for a person who holds project.terminal
(the same shared secret both services already authenticate with); the worker
verifies it, starts a shell in the project folder with a controlling
terminal, and bridges bytes both ways over a WebSocket (apps/routers/terminal.py).
Interactive programs, job control, colours and resizing all work because it IS
a terminal -- not a command runner.

What the shell can see is deliberately narrow: a sanitized environment (the
worker's own env holds secrets), HOME at the project folder, the container
user (uid 1000). The persona allow-list does not apply to a person's shell;
the Admin-tier right is the boundary, the container the hard one.
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import signal
import struct
import sys
import termios
from collections.abc import AsyncIterator
from typing import Any

from apps.core.config import settings
from apps.managers.tickets import TICKET_TTL_SECONDS, sign_ticket, verify_ticket as _verify

__all__ = ["TICKET_TTL_SECONDS", "TerminalSession", "sign_ticket", "verify_ticket"]

# What the shell inherits, and nothing else. The worker's env carries keys.
ENV_PASSTHROUGH = ("PATH", "LANG", "LC_ALL", "TZ")
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


# ── Tickets ──────────────────────────────────────────────────────────────────
# The ticket itself is generic and shared with the live browser; a terminal's
# ticket must also name the folder the shell opens in.
def verify_ticket(ticket: str | None, secret: str, now: float | None = None) -> dict[str, Any] | None:
    """The claims when the signature holds and the ticket is live; None otherwise."""
    return _verify(ticket, secret, require=("project_id", "cwd"), now=now)


# ── The session ──────────────────────────────────────────────────────────────
def _shell_env(cwd: str, project_name: str | None) -> dict[str, str]:
    env = {key: os.environ[key] for key in ENV_PASSTHROUGH if key in os.environ}
    env.setdefault("PATH", DEFAULT_PATH)
    env.setdefault("LANG", "C.UTF-8")
    env.update({
        "HOME": cwd,
        "TERM": "xterm-256color",
        "SHELL": settings.TERMINAL_SHELL,
        # A prompt that says where you are, without a hostname nobody chose.
        "PS1": r"\[\e[36m\]\W\[\e[0m\] $ ",
        "NEURALOPS_PROJECT": project_name or "",
    })
    return env


# Runs in the child AFTER exec, with the PTY slave already on its stdio: start a
# session (unless the loop did) and make that terminal the controlling one, so
# job control and ^C work, then become the shell. Not a preexec_fn: uvloop runs
# those before the child's stdio and session exist, asyncio after -- this way
# is the same under both.
_ADOPT_TERMINAL = (
    "import fcntl, os, sys, termios\n"
    "try:\n    os.setsid()\nexcept OSError:\n    pass\n"
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
    "os.execvp(sys.argv[1], sys.argv[1:])\n"
)


class TerminalSession:
    """One shell on one PTY: start, write, read, resize, close."""

    def __init__(self, cwd: str, project_name: str | None = None, cols: int = 80, rows: int = 24):
        self.cwd = cwd
        self.project_name = project_name
        self.cols, self.rows = cols, rows
        self.master: int | None = None
        self.process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if not os.path.isdir(self.cwd):
            raise FileNotFoundError(f"project folder missing: {self.cwd}")
        master, slave = os.openpty()
        self.master = master
        self._set_winsize(master)
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, "-I", "-c", _ADOPT_TERMINAL,
                settings.TERMINAL_SHELL, "--noprofile", "--norc", "-i",
                stdin=slave, stdout=slave, stderr=slave,
                cwd=self.cwd, env=_shell_env(self.cwd, self.project_name),
                start_new_session=True,
            )
        finally:
            os.close(slave)

    def _set_winsize(self, fd: int) -> None:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = max(2, min(int(cols), 500)), max(1, min(int(rows), 300))
        if self.master is not None:
            self._set_winsize(self.master)
            if self.process and self.process.returncode is None:
                os.killpg(self.process.pid, signal.SIGWINCH)

    def write(self, data: bytes) -> None:
        if self.master is not None:
            os.write(self.master, data)

    async def output(self) -> AsyncIterator[bytes]:
        """Bytes from the PTY as they come; ends when the shell exits."""
        assert self.master is not None
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        def on_readable() -> None:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                chunk = b""
            if chunk:
                queue.put_nowait(chunk)
            else:
                loop.remove_reader(self.master)
                queue.put_nowait(None)

        loop.add_reader(self.master, on_readable)
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    return
                yield chunk
        finally:
            try:
                loop.remove_reader(self.master)
            except (ValueError, OSError):
                pass

    async def close(self) -> None:
        """End the shell and everything it started: hang up, then kill what is left."""
        if self.process and self.process.returncode is None:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.killpg(self.process.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2)
                    break
                except asyncio.TimeoutError:
                    continue
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None
