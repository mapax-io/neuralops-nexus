"""
The Layer 0 acceptance harness: model calls go to a fake server that answers
like OpenAI / Anthropic streaming; nucleus is a fake too; the module under
test runs as a real uvicorn service, so disconnects and keepalives behave as
they do in production.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from fake_nucleus import FakeNucleus, make_app as make_nucleus_app  # noqa: E402
from fake_provider import FakeProvider, ServedApp, make_app as make_provider_app  # noqa: E402

INTERNAL_KEY = "test-internal-key"


@pytest.fixture(scope="session")
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture(scope="session")
def nucleus() -> FakeNucleus:
    return FakeNucleus()


@pytest.fixture(scope="session")
def servers(provider: FakeProvider, nucleus: FakeNucleus):
    provider_srv = ServedApp(make_provider_app(provider)).start()
    nucleus_srv = ServedApp(make_nucleus_app(nucleus)).start()

    os.environ["NEXUS_NUCLEUS_URL"] = nucleus_srv.url
    os.environ["INTERNAL_API_KEY"] = INTERNAL_KEY
    os.environ["HISTORY_DEPTH"] = "10"
    os.environ["KEEPALIVE_SECONDS"] = "30"

    from fastapi_app.main import create_app
    app_srv = ServedApp(create_app()).start()

    yield {"provider": provider_srv, "nucleus": nucleus_srv, "app": app_srv}

    app_srv.stop()
    nucleus_srv.stop()
    provider_srv.stop()


class Harness:
    def __init__(self, servers: dict, provider: FakeProvider, nucleus: FakeNucleus) -> None:
        self.provider = provider
        self.nucleus = nucleus
        self.app_url = servers["app"].url
        self.provider_url = servers["provider"].url

    def job(self, **overrides) -> dict:
        base = {
            "job_id": "job-1", "msg_id": "msg-1", "persona_id": "p1",
            "topic_id": "t1", "user_message_id": "um1",
            "message": "current question",
            "company_id": "c1", "project_id": "pr1", "user_id": "u1",
        }
        base.update(overrides)
        return base

    async def trigger(self, job: dict | None = None, timeout: float = 60.0) -> list[dict]:
        """POST the job and return every SSE event, parsed."""
        events: list[dict] = []
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.app_url}/api/v1/trigger/",
                json=job or self.job(), headers={"X-Internal-Key": INTERNAL_KEY},
            ) as response:
                assert response.status_code == 200, await response.aread()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[len("data: "):]))
        return events

    def usage_records(self) -> list[dict]:
        return [r for post in self.nucleus.usage_posts for r in post["records"]]

    async def wait_for_usage(self, n: int = 1, timeout: float = 8.0) -> list[dict]:
        import asyncio
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            records = self.usage_records()
            if len(records) >= n:
                return records
            await asyncio.sleep(0.05)
        raise AssertionError(f"usage records did not reach {n}: {self.usage_records()}")


# ── Test report: title + elaborated result per test ─────────────────────────────────
# Every test's docstring is its report entry: first line = title, the rest =
# what it verifies. Every `python -m pytest` run prints the report and rewrites
# tests/REPORT.md — run after every change; the diff is the regression record.


def pytest_itemcollected(item):
    titles = getattr(item.config, "_nexus_titles", None)
    if titles is None:
        titles = item.config._nexus_titles = {}
    titles[item.nodeid] = (item.function.__doc__ or "").strip()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    from datetime import datetime, timezone

    titles = getattr(config, "_nexus_titles", {})
    rows = []
    for outcome in ("passed", "failed", "error"):
        for rep in terminalreporter.stats.get(outcome, []):
            if getattr(rep, "when", "call") != "call":
                continue  # one row per test: the call phase only
            doc = titles.get(rep.nodeid, "")
            title, _, detail = doc.partition("\n")
            rows.append({
                "nodeid": rep.nodeid,
                "outcome": "PASS" if outcome == "passed" else outcome.upper(),
                "duration": getattr(rep, "duration", 0.0),
                "title": title.strip() or rep.nodeid.split("::")[-1],
                "detail": " ".join(detail.split()),
            })
    if not rows:
        return
    rows.sort(key=lambda r: r["nodeid"])

    terminalreporter.section("nexus-ai Layer 0 — test report")
    for r in rows:
        terminalreporter.write_line(f"[{r['outcome']:>5}] {r['title']}  ({r['duration']:.2f}s)")
        if r["detail"]:
            terminalreporter.write_line(f"        {r['detail']}")
        terminalreporter.write_line(f"        {r['nodeid']}")

    passed = sum(1 for r in rows if r["outcome"] == "PASS")
    lines = [
        "# nexus-ai — Layer 0 acceptance test report",
        "",
        f"Run: {datetime.now(timezone.utc).isoformat(timespec='seconds')} — "
        f"**{passed}/{len(rows)} passed**. Regenerated by every `python -m pytest` run.",
        "",
        "| Result | Test | Title and what it verifies | Time |",
        "|---|---|---|---|",
    ]
    for r in rows:
        name = r["nodeid"].split("::", 1)[-1]
        detail = f" — {r['detail']}" if r["detail"] else ""
        lines.append(f"| {r['outcome']} | `{name}` | **{r['title']}**{detail} | {r['duration']:.2f}s |")
    report_path = Path(__file__).parent / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    terminalreporter.write_line(f"report written: {report_path}")


@pytest.fixture
def harness(servers, provider: FakeProvider, nucleus: FakeNucleus) -> Harness:
    provider.reset()
    nucleus.reset()
    os.environ["KEEPALIVE_SECONDS"] = "30"
    from fake_nucleus import make_model, make_persona
    # default: an OpenAI-shaped persona pointing at the fake provider
    nucleus.persona = make_persona(make_model("openai", servers["provider"].url + "/v1"))
    nucleus.history = []
    return Harness(servers, provider, nucleus)


def openai_model(h: Harness, **kw) -> dict:
    from fake_nucleus import make_model
    return make_model("openai", h.provider_url + "/v1", **kw)


def anthropic_model(h: Harness, **kw) -> dict:
    from fake_nucleus import make_model
    return make_model("anthropic", h.provider_url, **kw)
