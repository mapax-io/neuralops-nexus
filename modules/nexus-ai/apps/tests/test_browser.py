"""
The live browser: what it may open, and how a session's pieces behave. Chromium
itself is not driven here (the image may not carry it) -- these pin the rules
that decide what reaches it.
"""
import pytest

from apps.core.config import settings
from apps.managers.browser import (
    BLOCKED_SCHEME_MESSAGE, PRIVATE_MESSAGE, BrowserSession, check_url, is_available, is_private_host,
)


def test_a_bare_host_becomes_https_and_only_web_schemes_are_allowed(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_ALLOW_PRIVATE_NETWORK", True)
    assert check_url("example.com") == ("https://example.com", None)
    assert check_url("  https://google.com/search?q=a ") == ("https://google.com/search?q=a", None)
    assert check_url("http://example.com") == ("http://example.com", None)
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "data:text/html,<b>x", "chrome://settings"):
        url, why = check_url(bad)
        assert url is None and why == BLOCKED_SCHEME_MESSAGE, bad
    assert check_url("")[1] == "Nothing to open."


def test_the_private_network_is_out_of_reach_unless_the_server_says_otherwise(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_ALLOW_PRIVATE_NETWORK", False)
    # IPv6 keeps its brackets in a URL, as a browser writes it.
    for host in ("localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.4.4", "[::1]", "169.254.169.254", "metadata.google.internal", "db.internal", "printer.local"):
        url, why = check_url(f"http://{host}/")
        assert url is None, host
        assert why == PRIVATE_MESSAGE, host
    # A public name is fine, and the switch lets an operator open their own network.
    assert check_url("https://example.com")[0] == "https://example.com"
    monkeypatch.setattr(settings, "BROWSER_ALLOW_PRIVATE_NETWORK", True)
    assert check_url("http://192.168.1.1/")[0] == "http://192.168.1.1/"


def test_is_private_host_reads_literals_and_names():
    assert is_private_host("127.0.0.1") is True
    assert is_private_host("::1") is True
    assert is_private_host("0.0.0.0") is True
    assert is_private_host("") is True
    assert is_private_host("8.8.8.8") is False
    # A name this process cannot resolve is one it cannot vouch for: refused,
    # rather than handed to Chromium to resolve differently.
    assert is_private_host("no-such-host.invalid") is True
    # An over-long DNS label makes getaddrinfo raise UnicodeError, not OSError —
    # that used to escape the check entirely.
    assert is_private_host("a" * 64 + ".example.com") is True


def test_the_ranges_python_does_not_call_private_are_still_the_deployment_s():
    # Carrier-grade NAT is what Tailscale hands out, and 100.100.100.100 is
    # Alibaba's metadata endpoint inside it; neither is "private" to ipaddress.
    import ipaddress
    assert ipaddress.ip_address("100.64.1.5").is_private is False
    assert is_private_host("100.64.1.5") is True
    assert is_private_host("100.100.100.100") is True
    assert is_private_host("metadata.tencentyun.com") is True
    assert is_private_host("fd00::1") is True


@pytest.mark.asyncio
async def test_a_session_clamps_the_size_it_was_asked_for(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MAX_WIDTH", 1600)
    monkeypatch.setattr(settings, "BROWSER_MAX_HEIGHT", 1000)
    frames, states = [], []
    big = BrowserSession(on_frame=lambda b: frames.append(b), on_state=lambda s: states.append(s), width=9000, height=9000)
    assert (big.width, big.height) == (1600, 1000)
    small = BrowserSession(on_frame=lambda b: frames.append(b), on_state=lambda s: states.append(s), width=10, height=10)
    assert (small.width, small.height) == (320, 240)


class _StuckPage:
    """A page whose history calls fail, as Chromium's do on a page that cannot go back."""
    url = "https://example.com/a"

    async def go_back(self, timeout=None):
        raise RuntimeError("Timeout 30000ms exceeded")

    async def go_forward(self, timeout=None):
        raise RuntimeError("net::ERR_ABORTED")

    async def reload(self, timeout=None):
        raise RuntimeError("Timeout 30000ms exceeded")


@pytest.mark.asyncio
async def test_back_forward_and_reload_say_why_they_did_not_work():
    # They used to swallow the failure: no frame, no message, no change -- a
    # button that does nothing reads as a broken app, not a page that would not.
    from apps.managers.browser import BrowserError, Tab
    states = []
    session = BrowserSession(on_frame=lambda b: None, on_state=lambda s: states.append(s))

    async def push_state():
        states.append("pushed")
    session.push_state = push_state
    tab = Tab(_StuckPage(), tab_id="t1")
    session.tabs.append(tab)
    session.active = tab.id
    for step in (session.back, session.forward, session.reload):
        with pytest.raises(BrowserError) as raised:
            await step()
        assert str(raised.value)
    # The state still went out each time, failure or not.
    assert states.count("pushed") == 3


def test_availability_is_reported_not_assumed():
    # Whatever this image has, the answer is a bool and the router gates on it.
    assert isinstance(is_available(), bool)


def test_the_browser_is_launched_as_the_browser_people_use():
    # The full Chromium in its new headless mode, not the headless shell; and
    # without Playwright's automation flag, which a person browsing does not
    # carry. Nothing is spoofed: no user agent is set here.
    from apps.managers.browser import LAUNCH_ARGS, launch_options
    opts = launch_options()
    assert opts["channel"] == "chromium"
    assert "--enable-automation" in opts["ignore_default_args"]
    assert "--no-sandbox" in opts["args"] and opts["args"] == LAUNCH_ARGS
    assert "user_agent" not in opts
    assert "headless" not in opts          # no display: Playwright's default, headless
    # With a virtual display it runs windowed, on that display -- the ordinary browser.
    windowed = launch_options(":99")
    assert windowed["headless"] is False and windowed["env"]["DISPLAY"] == ":99"


def test_the_display_is_optional_and_never_a_failure(monkeypatch):
    # Windowed off, or an image without Xvfb: no display, and the browser runs headless.
    import apps.managers.browser as mod
    monkeypatch.setattr(settings, "BROWSER_WINDOWED", False)
    assert mod._ensure_display() is None
    monkeypatch.setattr(settings, "BROWSER_WINDOWED", True)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    assert mod._ensure_display() is None


def test_a_project_s_browser_state_lives_outside_the_project_folder_and_the_id_is_checked(monkeypatch, tmp_path):
    from apps.managers.browser import state_path
    monkeypatch.setattr(settings, "BROWSER_STATE_DIR", str(tmp_path / "state"))
    assert state_path("80b04b52-01ae-449d-9114-91c45eb674a1") == tmp_path / "state" / "80b04b52-01ae-449d-9114-91c45eb674a1.json"
    assert state_path(None) is None
    for bad in ("../../etc/passwd", "a/b", "", "x" * 65):
        assert state_path(bad) is None, bad


class _FakeContext:
    def __init__(self):
        self.closed = False

    async def storage_state(self, path):
        import json
        import pathlib
        pathlib.Path(path).write_text(json.dumps({"cookies": [{"name": "cf_clearance", "value": "ok"}], "origins": []}))

    async def route(self, *a, **k):
        pass

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self):
        self.context_kwargs = None

    async def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return _FakeContext()


@pytest.mark.asyncio
async def test_a_session_remembers_its_project_s_cookies_for_the_next_one(monkeypatch, tmp_path):
    # A browser that forgot everything at every session re-asked every login
    # and every challenge a person had already passed (2026-09-22).
    import apps.managers.browser as mod
    monkeypatch.setattr(settings, "BROWSER_STATE_DIR", str(tmp_path / "state"))
    fake = _FakeBrowser()

    async def shared():
        return fake
    monkeypatch.setattr(mod, "_shared_browser", shared)

    async def no_tab(url=None):
        return None

    first = BrowserSession(on_frame=lambda b: None, on_state=lambda s: None, project_id="p1")
    first.open_tab = no_tab
    await first.start()
    assert fake.context_kwargs["storage_state"] is None      # nothing remembered yet
    await first.close()
    kept = tmp_path / "state" / "p1.json"
    assert kept.exists() and "cf_clearance" in kept.read_text()
    assert oct(kept.stat().st_mode & 0o777) == "0o600"

    second = BrowserSession(on_frame=lambda b: None, on_state=lambda s: None, project_id="p1")
    second.open_tab = no_tab
    await second.start()
    assert fake.context_kwargs["storage_state"] == str(kept)   # the next session starts from it

    other = BrowserSession(on_frame=lambda b: None, on_state=lambda s: None, project_id="p2")
    other.open_tab = no_tab
    await other.start()
    assert fake.context_kwargs["storage_state"] is None       # another project shares nothing
