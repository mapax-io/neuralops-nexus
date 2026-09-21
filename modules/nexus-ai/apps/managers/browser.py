"""
The live browser: a real Chromium running on the server, streamed to the app.

An iframe cannot show most of the web — google.com, github.com and most large
sites send X-Frame-Options or frame-ancestors, and the browser enforces that,
so no amount of client code can embed them. The only way to put the real web
beside a chat is to run a real browser somewhere and stream it. That is this:
one Chromium per server, one isolated context per session, one Playwright page
per tab, frames pushed out as JPEG through Chromium's own screencast, and mouse
and keyboard pushed back in. Tabs, history, forms, logins and JavaScript all
work because it IS a browser.

What it is allowed to reach matters more than usual, because the browser sits
INSIDE the deployment: by default it may not open a private address, so nobody
can point the team's browser at the database or a cloud metadata endpoint. The
Admin-tier right nucleus checks is the first boundary, this is the second.

Playwright is imported lazily so the worker (and these tests) still run on an
image built without Chromium; is_available() says which it is.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import re
import socket
import uuid
from typing import Any, Callable, Awaitable
from urllib.parse import urlparse

from apps.core.config import settings

log = logging.getLogger(__name__)

# Chromium is launched once and shared; each session gets its own context, which
# is its own cookie jar, storage and cache.
_browser: Any = None
_playwright: Any = None
_launch_lock: asyncio.Lock | None = None

BLOCKED_SCHEME_MESSAGE = "Only http and https pages can be opened here."
PRIVATE_MESSAGE = "That address is inside the server's own network, which this browser may not open."

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
# Metadata services are the classic target of a server-side browser.
_ALWAYS_BLOCKED_HOSTS = {
    "metadata.google.internal", "metadata.goog", "instance-data",
    "metadata.tencentyun.com",
}
# Ranges Python's own flags do not call private, but a deployment's network very
# much does: carrier-grade NAT is what Tailscale hands out, and 100.100.100.100
# is Alibaba's metadata endpoint inside it.
_EXTRA_PRIVATE_NETS = tuple(
    ipaddress.ip_network(cidr) for cidr in ("100.64.0.0/10", "fc00::/7", "2001:db8::/32")
)


def is_available() -> bool:
    """Whether this image has Playwright and a Chromium to drive."""
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _lock() -> asyncio.Lock:
    global _launch_lock
    if _launch_lock is None:
        _launch_lock = asyncio.Lock()
    return _launch_lock


async def _shared_browser():
    """The one Chromium, launched on first use."""
    global _browser, _playwright
    async with _lock():
        if _browser is not None and _browser.is_connected():
            return _browser
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            args=[
                "--no-sandbox",  # the container is the sandbox; Chromium's needs privileges we do not grant
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        log.info("[browser] chromium launched")
        return _browser


async def shutdown() -> None:
    """Close the shared Chromium — called when the worker stops."""
    global _browser, _playwright
    try:
        if _browser is not None:
            await _browser.close()
    finally:
        _browser = None
        if _playwright is not None:
            try:
                await _playwright.stop()
            finally:
                _playwright = None


# ── What the browser may open ────────────────────────────────────────────────

def is_private_host(host: str) -> bool:
    """True when a hostname or literal points inside the deployment's own network."""
    name = (host or "").strip().strip(".").lower()
    if not name:
        return True
    if name in _ALWAYS_BLOCKED_HOSTS or name == "localhost" or name.endswith(".localhost") or name.endswith(".local") or name.endswith(".internal"):
        return True
    candidates: list[str] = []
    try:
        ipaddress.ip_address(name)
        candidates.append(name)
    except ValueError:
        try:
            for info in socket.getaddrinfo(name, None):
                candidates.append(info[4][0])
        except Exception:  # noqa: BLE001
            # getaddrinfo raises UnicodeError (not OSError) for an over-long
            # label, which used to escape this check entirely. A name this
            # process cannot resolve is a name it cannot vouch for, so it is
            # refused rather than waved through (audit, 2026-09-21).
            return True
    for address in candidates:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return True
        if any(ip in net for net in _EXTRA_PRIVATE_NETS if ip.version == net.version):
            return True
    return False


def check_url(raw: str) -> tuple[str | None, str | None]:
    """(url, None) when it may be opened, else (None, why not)."""
    url = (raw or "").strip()
    if not url:
        return None, "Nothing to open."
    # A scheme of any kind is judged as written: "javascript:alert(1)" has no
    # "://", and gluing https:// in front of it would quietly make it look fine.
    scheme = _SCHEME_RE.match(url)
    if scheme:
        if scheme.group(1).lower() not in ("http", "https"):
            return None, BLOCKED_SCHEME_MESSAGE
    else:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None, BLOCKED_SCHEME_MESSAGE
    if not parsed.hostname:
        return None, "That address has no site in it."
    if not settings.BROWSER_ALLOW_PRIVATE_NETWORK and is_private_host(parsed.hostname):
        return None, PRIVATE_MESSAGE
    return url, None


# ── A tab ────────────────────────────────────────────────────────────────────

class Tab:
    """One page, its own history — what a tab is."""

    def __init__(self, page: Any, tab_id: str | None = None):
        self.id = tab_id or uuid.uuid4().hex[:8]
        self.page = page
        self.loading = False
        self._cdp: Any = None
        self._casting = False

    @property
    def url(self) -> str:
        try:
            return self.page.url or ""
        except Exception:  # noqa: BLE001
            return ""

    async def title(self) -> str:
        try:
            return (await self.page.title()) or self.url or "New tab"
        except Exception:  # noqa: BLE001
            return self.url or "New tab"

    async def can_go(self) -> tuple[bool, bool]:
        """(back, forward) — read from the page's own history length."""
        try:
            return (
                bool(await self.page.evaluate("history.length > 1")),
                False,  # Chromium does not expose "can go forward"; the app enables it after a back
            )
        except Exception:  # noqa: BLE001
            return False, False


# ── A session ────────────────────────────────────────────────────────────────

class BrowserSession:
    """
    One person's browser: an isolated context, its tabs, and a screencast of
    whichever tab is in front. Frames are handed to `on_frame` as JPEG bytes;
    every change to the tab strip is handed to `on_state`.
    """

    def __init__(
        self,
        *,
        on_frame: Callable[[bytes], Awaitable[None]],
        on_state: Callable[[dict], Awaitable[None]],
        width: int = 1280,
        height: int = 800,
    ):
        self.on_frame = on_frame
        self.on_state = on_state
        self.width = max(320, min(width, settings.BROWSER_MAX_WIDTH))
        self.height = max(240, min(height, settings.BROWSER_MAX_HEIGHT))
        self.context: Any = None
        self.tabs: list[Tab] = []
        self.active: str | None = None
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self, url: str | None = None) -> None:
        browser = await _shared_browser()
        self.context = await browser.new_context(
            viewport={"width": self.width, "height": self.height},
            user_agent=settings.BROWSER_USER_AGENT or None,
            locale="en-US",
            # A service worker's requests do not pass through context.route, so
            # it would be a way round the guard below; downloads would write to
            # the worker's own disk. Neither is wanted here.
            service_workers="block",
            accept_downloads=False,
        )
        if not settings.BROWSER_ALLOW_PRIVATE_NETWORK:
            await self.context.route("**/*", self._guard)
        await self.open_tab(url or settings.BROWSER_HOME)

    async def _guard(self, route: Any, request: Any) -> None:
        """
        Every request, not just the address bar: a page may not fetch the private
        network either. If the check itself fails, the request is refused -- a
        guard that opens when it breaks is not a guard (audit, 2026-09-21).
        """
        try:
            host = urlparse(request.url).hostname or ""
            allowed = not is_private_host(host)
        except Exception:  # noqa: BLE001
            allowed = False
        try:
            await (route.continue_() if allowed else route.abort("blockedbyclient"))
        except Exception:  # noqa: BLE001
            pass

    async def close(self) -> None:
        self._closed = True
        for tab in self.tabs:
            await self._stop_cast(tab)
        try:
            if self.context is not None:
                await self.context.close()
        except Exception:  # noqa: BLE001
            pass
        self.context = None
        self.tabs = []
        self.active = None

    # ── tabs ─────────────────────────────────────────────────────────────────

    def tab(self, tab_id: str | None) -> Tab | None:
        return next((t for t in self.tabs if t.id == tab_id), None)

    @property
    def current(self) -> Tab | None:
        return self.tab(self.active)

    async def open_tab(self, url: str | None = None) -> Tab:
        if len(self.tabs) >= settings.BROWSER_MAX_TABS:
            raise BrowserError(f"That is {settings.BROWSER_MAX_TABS} tabs — close one first.")
        page = await self.context.new_page()
        tab = Tab(page)
        self.tabs.append(tab)
        self._watch(tab)
        await self.activate(tab.id, push_state=False)
        if url:
            await self.navigate(url, tab=tab, push_state=False)
        await self.push_state()
        return tab

    def _watch(self, tab: Tab) -> None:
        """A page that opens a popup opens a tab, as a browser does."""
        def on_popup(page: Any) -> None:
            if self._closed or len(self.tabs) >= settings.BROWSER_MAX_TABS:
                # Left open it would still be a live renderer nobody can see or
                # close — a page calling window.open in a loop would fill the
                # container with them.
                asyncio.create_task(_close_quietly(page))
                return
            popup = Tab(page)
            self.tabs.append(popup)
            self._watch(popup)
            asyncio.create_task(self._popup_opened(popup))

        tab.page.on("popup", on_popup)
        tab.page.on("framenavigated", lambda frame: asyncio.create_task(self._maybe_state(tab, frame)))
        tab.page.on("close", lambda _page=None: asyncio.create_task(self._page_closed(tab)))

    async def _popup_opened(self, tab: Tab) -> None:
        await self.activate(tab.id)

    async def _maybe_state(self, tab: Tab, frame: Any) -> None:
        # Only the main frame changes what the tab strip says.
        try:
            if frame is not tab.page.main_frame:
                return
        except Exception:  # noqa: BLE001
            return
        await self.push_state()

    async def _page_closed(self, tab: Tab) -> None:
        if self._closed:
            return
        if tab in self.tabs:
            self.tabs.remove(tab)
        if self.active == tab.id:
            self.active = self.tabs[-1].id if self.tabs else None
            if self.current:
                await self._start_cast(self.current)
        await self.push_state()

    async def close_tab(self, tab_id: str) -> None:
        tab = self.tab(tab_id)
        if tab is None:
            return
        await self._stop_cast(tab)
        try:
            await tab.page.close()
        except Exception:  # noqa: BLE001
            await self._page_closed(tab)

    async def activate(self, tab_id: str, *, push_state: bool = True) -> None:
        tab = self.tab(tab_id)
        if tab is None:
            return
        if self.current and self.current is not tab:
            await self._stop_cast(self.current)
        self.active = tab.id
        try:
            await tab.page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass
        await self._start_cast(tab)
        if push_state:
            await self.push_state()

    # ── the screencast ───────────────────────────────────────────────────────

    async def _start_cast(self, tab: Tab) -> None:
        if tab._casting or self._closed:
            return
        try:
            tab._cdp = await self.context.new_cdp_session(tab.page)
        except Exception as exc:  # noqa: BLE001
            log.warning("[browser] no cdp session: %s", exc)
            return

        def on_frame(event: dict) -> None:
            asyncio.create_task(self._frame(tab, event))

        tab._cdp.on("Page.screencastFrame", on_frame)
        await tab._cdp.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": settings.BROWSER_FRAME_QUALITY,
            "maxWidth": self.width,
            "maxHeight": self.height,
            "everyNthFrame": 1,
        })
        tab._casting = True

    async def _stop_cast(self, tab: Tab) -> None:
        if not tab._casting:
            return
        tab._casting = False
        try:
            await tab._cdp.send("Page.stopScreencast")
            await tab._cdp.detach()
        except Exception:  # noqa: BLE001
            pass
        tab._cdp = None

    async def _frame(self, tab: Tab, event: dict) -> None:
        """
        One painted frame. Chromium sends the next only after the ack, so the ack
        goes first: a frame that arrives just after its tab stopped being the one
        in front would otherwise wedge that tab's screencast until it is switched
        to again.
        """
        try:
            await tab._cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
        except Exception:  # noqa: BLE001
            pass
        if self._closed or tab.id != self.active:
            return
        try:
            await self.on_frame(base64.b64decode(event["data"]))
        except Exception:  # noqa: BLE001
            pass

    async def push_state(self) -> None:
        if self._closed:
            return
        tabs = []
        for tab in list(self.tabs):
            tabs.append({"id": tab.id, "title": await tab.title(), "url": tab.url, "loading": tab.loading})
        back, forward = (await self.current.can_go()) if self.current else (False, False)
        await self.on_state({
            "type": "state",
            "tabs": tabs,
            "active": self.active,
            "canBack": back,
            "canForward": forward,
            "width": self.width,
            "height": self.height,
        })

    # ── what a person does ───────────────────────────────────────────────────

    async def navigate(self, raw: str, *, tab: Tab | None = None, push_state: bool = True) -> None:
        target = tab or self.current
        if target is None:
            return
        url, problem = check_url(raw)
        if problem:
            raise BrowserError(problem)
        target.loading = True
        if push_state:
            await self.push_state()
        try:
            await target.page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_NAV_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(_readable(exc, url)) from exc
        finally:
            target.loading = False
            if push_state:
                await self.push_state()

    # These three say why they did not work, as navigate does: a button that
    # produces no frame, no message and no change reads as a broken app rather
    # than a page that would not go there (audit, 2026-09-21).
    async def back(self) -> None:
        await self._history_step("go_back")

    async def forward(self) -> None:
        await self._history_step("go_forward")

    async def reload(self) -> None:
        await self._history_step("reload")

    async def _history_step(self, method: str) -> None:
        if not self.current:
            return
        page, url = self.current.page, self.current.url
        try:
            await getattr(page, method)(timeout=settings.BROWSER_NAV_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(_readable(exc, url)) from exc
        finally:
            await self.push_state()

    async def resize(self, width: int, height: int) -> None:
        self.width = max(320, min(int(width), settings.BROWSER_MAX_WIDTH))
        self.height = max(240, min(int(height), settings.BROWSER_MAX_HEIGHT))
        for tab in self.tabs:
            try:
                await tab.page.set_viewport_size({"width": self.width, "height": self.height})
            except Exception:  # noqa: BLE001
                pass
        # The cast is sized at start, so it restarts at the new size.
        if self.current:
            await self._stop_cast(self.current)
            await self._start_cast(self.current)
        await self.push_state()

    async def mouse(self, action: str, x: float, y: float, button: str = "left") -> None:
        page = self.current.page if self.current else None
        if page is None:
            return
        x, y = float(x), float(y)
        if action == "move":
            await page.mouse.move(x, y)
        elif action == "down":
            await page.mouse.move(x, y)
            await page.mouse.down(button=button)
        elif action == "up":
            await page.mouse.move(x, y)
            await page.mouse.up(button=button)
        elif action == "click":
            await page.mouse.click(x, y, button=button)
        elif action == "dblclick":
            await page.mouse.dblclick(x, y, button=button)

    async def wheel(self, dx: float, dy: float) -> None:
        if self.current:
            await self.current.page.mouse.wheel(float(dx), float(dy))

    async def key(self, action: str, key: str) -> None:
        page = self.current.page if self.current else None
        if page is None or not key:
            return
        if action == "down":
            await page.keyboard.down(key)
        elif action == "up":
            await page.keyboard.up(key)
        else:
            await page.keyboard.press(key)

    async def text(self, value: str) -> None:
        """Typed characters, IME and paste all arrive as text to insert."""
        if self.current and value:
            await self.current.page.keyboard.insert_text(value)


async def _close_quietly(page: Any) -> None:
    try:
        await page.close()
    except Exception:  # noqa: BLE001
        pass


class BrowserError(Exception):
    """Something the person should be told, in their words."""


def _readable(exc: Exception, url: str) -> str:
    text = str(exc) or exc.__class__.__name__
    host = urlparse(url).hostname or url
    if "ERR_NAME_NOT_RESOLVED" in text:
        return f"{host} could not be found."
    if "ERR_CONNECTION_REFUSED" in text:
        return f"{host} refused the connection."
    if "ERR_CERT" in text or "SSL" in text:
        return f"{host} has a certificate this browser does not trust."
    if "Timeout" in text or "timeout" in text:
        return f"{host} took too long to answer."
    if "blockedbyclient" in text or "ERR_BLOCKED_BY_CLIENT" in text:
        return PRIVATE_MESSAGE
    return f"{host} could not be opened."
