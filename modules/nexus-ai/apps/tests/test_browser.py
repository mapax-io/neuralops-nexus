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
    # A name nobody can resolve is left to Chromium to fail on, not blocked here.
    assert is_private_host("no-such-host.invalid") is False


@pytest.mark.asyncio
async def test_a_session_clamps_the_size_it_was_asked_for(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_MAX_WIDTH", 1600)
    monkeypatch.setattr(settings, "BROWSER_MAX_HEIGHT", 1000)
    frames, states = [], []
    big = BrowserSession(on_frame=lambda b: frames.append(b), on_state=lambda s: states.append(s), width=9000, height=9000)
    assert (big.width, big.height) == (1600, 1000)
    small = BrowserSession(on_frame=lambda b: frames.append(b), on_state=lambda s: states.append(s), width=10, height=10)
    assert (small.width, small.height) == (320, 240)


def test_availability_is_reported_not_assumed():
    # Whatever this image has, the answer is a bool and the router gates on it.
    assert isinstance(is_available(), bool)
