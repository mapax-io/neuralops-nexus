"""
Unit tests for the realtime event contract (chat/events.py).

Pure payload construction -- no DB, no HTTP. The relay in services.py decides
when to publish; these pin what it publishes.
"""
from django.test import SimpleTestCase

from chat.events import TOOL_ACTIVITY_LABELS, tool_activity_end_event, tool_activity_event


def call(name):
    """A worker tool_call_start event carrying `name`."""
    return {"type": "tool_call_start", "tool_call": {"name": name, "args": {}}}


class ToolActivityEventTests(SimpleTestCase):
    def test_built_in_tools_get_their_own_wording(self):
        event = tool_activity_event("m1", call("web_search"))
        self.assertEqual(event, {
            "type": "tool_activity",
            "id": "m1",
            "tool": "web_search",
            "label": "Searching the web",
        })

    def test_every_labelled_tool_round_trips(self):
        for name, label in TOOL_ACTIVITY_LABELS.items():
            with self.subTest(tool=name):
                self.assertEqual(tool_activity_event("m1", call(name))["label"], label)

    def test_an_unknown_tool_falls_back_to_its_name(self):
        # An MCP server's own tool -- must still read as a sentence.
        event = tool_activity_event("m1", call("search_warehouse"))
        self.assertEqual(event["label"], "Using search warehouse")
        self.assertEqual(event["tool"], "search_warehouse")

    def test_the_message_id_is_carried_through(self):
        # The swarm path passes the ACTIVE message id, not the first one.
        self.assertEqual(tool_activity_event("m9", call("shell"))["id"], "m9")

    def test_nothing_is_published_without_a_tool_name(self):
        # Publishing an empty cue would be worse than staying quiet.
        self.assertIsNone(tool_activity_event("m1", call("")))
        self.assertIsNone(tool_activity_event("m1", call("   ")))
        self.assertIsNone(tool_activity_event("m1", {"type": "tool_call_start"}))
        self.assertIsNone(tool_activity_event("m1", {"type": "tool_call_start", "tool_call": None}))

    def test_a_surrounding_whitespace_name_is_trimmed(self):
        self.assertEqual(tool_activity_event("m1", call("  shell  "))["tool"], "shell")

    def test_the_payload_type_is_what_the_web_app_parses(self):
        # lib/realtime/events.ts switches on this string; a rename here is a
        # silent break there.
        self.assertEqual(tool_activity_event("m1", call("shell"))["type"], "tool_activity")

    def test_label_is_always_present_and_non_empty(self):
        # The client renders label verbatim, so an empty one would show a blank cue.
        for name in ("web_search", "filesystem", "some_unmapped_tool"):
            with self.subTest(tool=name):
                self.assertTrue(tool_activity_event("m1", call(name))["label"].strip())


# ── persona.mention on the send path ─────────────────────────────────────────

from unittest.mock import AsyncMock, patch  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

from authn.permissions.checker import PermissionChecker  # noqa: E402
from authn.permissions.models import Role, RoleAssignment  # noqa: E402
from nucleus.models import ChatMessage, CompanyAccess, ModelConfig, Persona  # noqa: E402
from workspace.tests import InviteGrantsFixture  # noqa: E402

User = get_user_model()


class MentionRightFixture(InviteGrantsFixture):
    """
    The invite fixture plus two personas in Alpha (Sara, Bob) and Vera, a
    company-wide Viewer -- the one default role without persona.mention.
    """

    def setUp(self):
        super().setUp()
        self.model_config = ModelConfig.objects.create(
            company=self.company, name="GPT Test", provider="openai", model_id="gpt-test", supports_tools=True,
        )
        self.model_config.projects.add(self.p1)
        self.persona_sara = self.persona("Sara")
        self.persona_bob = self.persona("Bob")
        self.vera = User.objects.create_user(username="vera", email="vera@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=self.vera, role="viewer", invited_by=self.owner)
        self.assign(self.vera, "Viewer")

    def persona(self, name: str):
        shadow = User.objects.create(username=f"persona_{name.lower()}", user_type="persona", is_active=True)
        return Persona.objects.create(company=self.company, project=self.p1, identity_user=shadow, name=name, model=self.model_config)

    def assign(self, user, role_name: str):
        PermissionChecker.assign_role(user, Role.objects.get(company=self.company, name=role_name), self.company, granted_by=self.owner)

    def demote_to_viewer(self, user):
        RoleAssignment.objects.filter(user=user).delete()
        self.assign(user, "Viewer")

    def send(self, user, content: str):
        """POST a message as `user` with every fire-and-forget side effect mocked; returns (response, trigger, swarm, publish)."""
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/messages/"
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}), \
             patch("chat.api.chat_svc.trigger_ai_response_async", new_callable=AsyncMock) as trigger, \
             patch("chat.api.chat_svc.trigger_ai_swarm_response_async", new_callable=AsyncMock) as swarm, \
             patch("chat.api.chat_svc.publish_async", new_callable=AsyncMock) as publish, \
             patch("chat.api.chat_svc.embed_message_async", new_callable=AsyncMock):
            r = Client().post(path, data={"content": content}, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")
        return r, trigger, swarm, publish

    def call(self, method, path, user, body=None):
        """One authenticated HTTP call as `user`; the Supabase check is patched away."""
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}):
            return getattr(Client(), method)(path, data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")

    @staticmethod
    def refused_events(publish) -> list:
        return [c.args[1] for c in publish.call_args_list if isinstance(c.args[1], dict) and c.args[1].get("type") == "mention_refused"]


class MentionRightTests(MentionRightFixture):
    """The right exists and the app hides the picker on it; the server must refuse too."""

    def test_a_member_mention_triggers_and_reports_no_refusal(self):
        r, trigger, swarm, publish = self.send(self.sara, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["refusals"], [])
        self.assertEqual(trigger.call_count, 1)
        self.assertEqual(trigger.call_args.kwargs["persona"].id, self.persona_sara.id)
        self.assertEqual(self.refused_events(publish), [])

    def test_a_viewer_mention_posts_the_message_but_never_triggers(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["refusals"], [{
            "persona_id": str(self.persona_sara.id), "name": "Sara", "code": "no_right",
            "message": "You can't call personas in this topic.", "resets_at": None,
        }])
        self.assertTrue(ChatMessage.objects.filter(id=body["message"]["id"], sender=self.vera).exists())
        trigger.assert_not_called()
        swarm.assert_not_called()
        events = self.refused_events(publish)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], body["message"]["id"])
        self.assertEqual(events[0]["actor_user_id"], str(self.vera.id))
        self.assertEqual(events[0]["refusals"], body["refusals"])

    def test_a_viewer_cannot_open_a_session_by_mentioning(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara @session let's talk")
        self.assertEqual([x["name"] for x in r.json()["refusals"]], ["Sara"])
        trigger.assert_not_called()
        self.assertFalse(ChatMessage.objects.filter(topic=self.t1, message_type="system", content__icontains="Session with").exists())

    def test_a_viewer_swarm_never_starts(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara @Bob compare notes /swarm")
        self.assertEqual(sorted(x["name"] for x in r.json()["refusals"]), ["Bob", "Sara"])
        swarm.assert_not_called()
        trigger.assert_not_called()

    def test_a_member_swarm_still_starts(self):
        r, trigger, swarm, publish = self.send(self.sara, "@Sara @Bob compare notes /swarm")
        self.assertEqual(r.json()["refusals"], [])
        self.assertEqual(swarm.call_count, 1)

    def test_a_session_auto_trigger_is_refused_once_the_right_is_gone(self):
        r, trigger, _, _ = self.send(self.sara, "@Sara @session hi there")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(trigger.call_count, 1)
        self.demote_to_viewer(self.sara)
        r, trigger, _, publish = self.send(self.sara, "and another thing")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([x["name"] for x in r.json()["refusals"]], ["Sara"])
        trigger.assert_not_called()
        self.assertEqual(len(self.refused_events(publish)), 1)

    def test_a_plain_message_carries_no_refusals(self):
        r, trigger, _, publish = self.send(self.vera, "just reading along")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["refusals"], [])
        trigger.assert_not_called()
        self.assertEqual(self.refused_events(publish), [])


# ── stopping a run ────────────────────────────────────────────────────────────
# The user could not stop a persona mid-reply. A stop is a signal keyed by the
# AI message id that the relay polls between events; Redis-backed so it works
# across nucleus workers, with an in-memory store for tests and single-process
# use.
import asyncio
import json

from chat.stop_signals import MemoryStore, StopRequested, StopSignals, stoppable, stoppable_lines


class StopSignalTests(SimpleTestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_a_requested_stop_is_seen_then_cleared(self):
        signals = StopSignals(MemoryStore())

        async def scenario():
            self.assertFalse(await signals.is_stop_requested("m1"))
            await signals.request_stop("m1")
            self.assertTrue(await signals.is_stop_requested("m1"))
            self.assertFalse(await signals.is_stop_requested("m2"))
            await signals.clear("m1")
            self.assertFalse(await signals.is_stop_requested("m1"))

        self.run_async(scenario())

    def test_a_stop_request_expires_so_a_stale_click_cannot_kill_a_later_run(self):
        store = MemoryStore(now=lambda: 1000.0)
        signals = StopSignals(store, ttl_seconds=600)

        async def scenario():
            await signals.request_stop("m1")
            store.now = lambda: 1000.0 + 599
            self.assertTrue(await signals.is_stop_requested("m1"))
            store.now = lambda: 1000.0 + 601
            self.assertFalse(await signals.is_stop_requested("m1"))

        self.run_async(scenario())


# The relay used to look for a stop only when the worker sent a line, so a
# click during a silent stretch (model thinking, a tool running) waited for the
# next token. The iterator polls on its own clock as well.
class StoppableLinesTests(SimpleTestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    async def collect(self, source, should_stop, poll=0.02):
        seen = []
        try:
            async for line in stoppable_lines(source, should_stop, poll_seconds=poll):
                seen.append(line)
        except StopRequested:
            return seen, True
        return seen, False

    def test_lines_pass_through_in_order_and_the_end_of_the_source_ends_it(self):
        async def source():
            for line in ("a", "b", "c"):
                yield line

        async def never():
            return False

        seen, stopped = self.run_async(self.collect(source(), never))
        self.assertEqual(seen, ["a", "b", "c"])
        self.assertFalse(stopped)

    def test_a_stop_is_seen_while_the_source_is_silent(self):
        signals = StopSignals(MemoryStore())

        async def source():
            yield "first"
            await asyncio.sleep(10)  # the worker has gone quiet
            yield "never"

        async def scenario():
            asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(signals.request_stop("m1")))
            started = asyncio.get_running_loop().time()
            seen, stopped = await self.collect(source(), lambda: signals.is_stop_requested("m1"))
            return seen, stopped, asyncio.get_running_loop().time() - started

        seen, stopped, took = self.run_async(scenario())
        self.assertEqual(seen, ["first"])
        self.assertTrue(stopped)
        self.assertLess(took, 1.0)

    def test_a_stop_is_seen_between_fast_lines_too(self):
        signals = StopSignals(MemoryStore())

        async def source():
            for i in range(10_000):
                if i == 5:
                    await signals.request_stop("m1")
                yield str(i)

        seen, stopped = self.run_async(self.collect(source(), lambda: signals.is_stop_requested("m1"), poll=0))
        self.assertTrue(stopped)
        self.assertLess(len(seen), 10_000)

    def test_opening_the_stream_is_stoppable_too_and_the_open_is_cancelled(self):
        signals = StopSignals(MemoryStore())
        state = {"cancelled": False}

        async def slow_open():
            try:
                await asyncio.sleep(10)  # the worker is still setting up
            except asyncio.CancelledError:
                state["cancelled"] = True
                raise
            return "response"

        async def scenario():
            asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(signals.request_stop("m1")))
            with self.assertRaises(StopRequested):
                await stoppable(slow_open(), lambda: signals.is_stop_requested("m1"), poll_seconds=0.02)

        self.run_async(scenario())
        self.assertTrue(state["cancelled"])

    def test_a_quick_open_returns_its_result(self):
        async def quick_open():
            return "response"

        async def never():
            return False

        self.assertEqual(self.run_async(stoppable(quick_open(), never)), "response")

    def test_a_source_error_still_reaches_the_caller(self):
        async def source():
            yield "a"
            raise RuntimeError("connection dropped")

        async def never():
            return False

        with self.assertRaises(RuntimeError):
            self.run_async(self.collect(source(), never))


# ── why a reply failed ────────────────────────────────────────────────────────
# The reader used to get "something went wrong" or a bubble that went quiet.
# Raw error text never leaves the server (it can carry keys and internals); a
# categorised sentence does.
from chat.reasons import explain_ai_error, ORPHANED_RUN_REASON


class ExplainAiErrorTests(SimpleTestCase):
    def test_a_rejected_key_names_the_provider_problem_not_the_key(self):
        raw = "status_code: 401, model_name: gpt-4o-mini, body: {'message': 'Incorrect API key provided: sk-proj-abc...A94A', 'code': 'invalid_api_key'}"
        reason = explain_ai_error(raw)
        self.assertIn("API key", reason)
        self.assertNotIn("sk-proj", reason)
        self.assertNotIn("A94A", reason)

    def test_rate_limits_quota_and_timeouts_are_told_apart(self):
        self.assertIn("rate", explain_ai_error("Error code: 429 - {'error': {'type': 'rate_limit_error'}}").lower())
        self.assertIn("credit", explain_ai_error("status_code: 402 insufficient_quota").lower())
        self.assertIn("too long", explain_ai_error("httpx.ReadTimeout: timed out").lower())

    def test_a_worker_that_vanished_is_said_plainly(self):
        self.assertIn("worker", explain_ai_error("peer closed connection without sending complete message body").lower())
        self.assertIn("worker", explain_ai_error("All connection attempts failed").lower())

    def test_a_refused_connection_is_a_worker_problem_not_a_content_refusal(self):
        self.assertIn("worker", explain_ai_error("httpx.ConnectError: [Errno 111] Connection refused").lower())
        self.assertIn("declined", explain_ai_error("The model returned a refusal for this content").lower())

    def test_a_tool_problem_is_a_tool_problem(self):
        self.assertIn("tool", explain_ai_error("MCP server 'Github' returned 500 during call_tool").lower())

    def test_unknown_errors_get_the_generic_sentence_and_never_the_raw_text(self):
        reason = explain_ai_error("ZeroDivisionError: division by zero at /nexus/ai/apps/x.py:42")
        self.assertNotIn("ZeroDivision", reason)
        self.assertNotIn("/nexus/", reason)
        self.assertTrue(reason.endswith("."))

    def test_our_own_bugs_are_named_as_ours(self):
        reason = explain_ai_error("streaming error: name 'time' is not defined")
        self.assertIn("internal error", reason)
        self.assertIn("bug", reason)
        self.assertNotIn("time", reason)

    def test_an_orphaned_run_has_its_own_reason(self):
        self.assertIn("restart", ORPHANED_RUN_REASON.lower())


# ── the relay, driven by a fake worker ───────────────────────────────────────
# What nucleus does with a worker's SSE stream: save the finished reply with
# its type, keep a stopped partial, fail a broken run with a reason. The swarm
# path had no test at all -- it once raised on its first line.
import json as _json  # noqa: E402

from asgiref.sync import sync_to_async  # noqa: E402
from django.test import override_settings  # noqa: E402

from chat.reasons import WORKER_ENDED_EARLY_REASON  # noqa: E402
from chat.services import _serialise, trigger_ai_response_async, trigger_ai_swarm_response_async  # noqa: E402


def sse(*events: dict) -> list[str]:
    return [f"data: {_json.dumps(e)}" for e in events]


class FakeResponse:
    """The worker's side: SSE lines, then the end, silence, or a broken pipe."""

    def __init__(self, lines, status_code=200, hang=False, boom: Exception | None = None):
        self.lines, self.status_code, self.hang, self.boom = lines, status_code, hang, boom
        self.closed = False

    async def aiter_lines(self):
        for line in self.lines:
            yield line
        if self.boom:
            raise self.boom
        if self.hang:
            await asyncio.sleep(30)

    async def aread(self):
        return b"worker said no"

    async def aclose(self):
        self.closed = True


class FakeClient:
    response: FakeResponse
    posted: list = []  # every job nucleus sent, oldest first

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def build_request(self, method, url, **kwargs):
        FakeClient.posted.append(kwargs.get("json"))
        return (method, url)

    async def send(self, request, stream=True):
        return FakeClient.response


@override_settings(NEXUS_AI_URL="http://worker.test", INTERNAL_API_KEY="k")
class RelayFixture(MentionRightFixture):
    def setUp(self):
        super().setUp()
        self.signals = StopSignals(MemoryStore())
        self.published: list[dict] = []

        async def publish(channel, data):
            self.published.append(data)

        for target, value in (
            ("chat.services.httpx.AsyncClient", FakeClient),
            ("chat.services.publish_async", publish),
            ("chat.services.embed_message_async", AsyncMock()),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("chat.services.stop_signals", return_value=self.signals)
        patcher.start()
        self.addCleanup(patcher.stop)

    def events(self, kind: str) -> list[dict]:
        return [e for e in self.published if e.get("type") == kind]

    def reply_rows(self) -> list:
        return list(ChatMessage.objects.filter(topic=self.t1, metadata__has_key="persona_id").order_by("sequence"))

    async def run_single(self, response: FakeResponse):
        FakeClient.response = response
        await trigger_ai_response_async(
            company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
            user_message="chart please", user_message_id="u1", topic_id=str(self.t1.id),
        )

    async def run_swarm(self, response: FakeResponse):
        FakeClient.response = response
        await trigger_ai_swarm_response_async(
            company=self.company, project=self.p1, topic=self.t1, personas=[self.persona_sara, self.persona_bob],
            user_message="chart please", user_message_id="u1", topic_id=str(self.t1.id),
        )

    async def stop_the_pending_reply_soon(self, after=0.05):
        await asyncio.sleep(after)
        pending = await sync_to_async(lambda: ChatMessage.objects.filter(topic=self.t1, status="pending").order_by("-sequence").first())()
        await self.signals.request_stop(str(pending.id))
        return pending


class RelayTests(RelayFixture):
    async def test_a_finished_reply_is_saved_with_its_type_and_announced(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_delta", "delta": "{\"type\""},
            {"type": "message_delta", "delta": ": \"bar\"}"},
            {"type": "message_done", "content": "{\"type\": \"bar\"}", "output_type": "chart", "render_as": "chart"},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "completed")
        self.assertEqual(row.content, "{\"type\": \"bar\"}")
        self.assertEqual(row.metadata["render_as"], "chart")
        self.assertNotIn("stopped", row.metadata)
        self.assertEqual(len(self.events("message_delta")), 2)
        done = self.events("message_done")[0]
        self.assertEqual((done["render_as"], done["output_type"], done["stopped"]), ("chart", "chart", False))

    async def test_a_stop_keeps_what_streamed_and_says_so(self):
        stopper = asyncio.ensure_future(self.stop_the_pending_reply_soon())
        response = FakeResponse(sse({"type": "message_delta", "delta": "Canada's GDP "}), hang=True)
        await self.run_single(response)
        pending = await stopper
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(str(row.id), str(pending.id))
        self.assertEqual((row.status, row.content, row.metadata.get("stopped")), ("completed", "Canada's GDP ", True))
        done = self.events("message_done")[0]
        self.assertEqual((done["id"], done["content"], done["stopped"]), (str(row.id), "Canada's GDP ", True))
        self.assertTrue(response.closed)  # the worker's run is cut, not left running
        self.assertFalse(await self.signals.is_stop_requested(str(row.id)))

    async def test_a_worker_error_fails_the_reply_with_a_reason_and_keeps_the_raw_text_private(self):
        await self.run_single(FakeResponse(sse({"type": "message_error", "error": "httpx.ConnectError: [Errno 111] Connection refused"})))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "failed")
        self.assertIn("worker", row.content.lower())
        self.assertNotIn("Errno", row.content)
        self.assertIn("Errno 111", row.metadata["error_detail"])
        self.assertEqual(self.events("message_error")[0]["content"], row.content)

    async def test_a_stream_that_breaks_mid_reply_is_a_failure_not_a_finished_reply(self):
        boom = RuntimeError("peer closed connection without sending complete message body")
        await self.run_single(FakeResponse(sse({"type": "message_delta", "delta": "half"}), boom=boom))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "failed")
        self.assertIn("worker", row.content.lower())

    async def test_a_transport_error_with_no_text_is_still_a_worker_problem(self):
        import httpx
        await self.run_single(FakeResponse(sse({"type": "message_delta", "delta": "half"}), boom=httpx.ReadError("")))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "failed")
        self.assertIn("worker", row.content.lower())
        self.assertIn("ReadError", row.metadata["error_detail"])

    async def test_a_stream_that_ends_without_done_is_the_worker_ending_early(self):
        await self.run_single(FakeResponse(sse({"type": "message_delta", "delta": "half"})))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual((row.status, row.content), ("failed", WORKER_ENDED_EARLY_REASON))

    async def test_a_worker_that_refuses_the_job_fails_the_reply(self):
        await self.run_single(FakeResponse([], status_code=500))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "failed")
        self.assertIn("500", row.metadata["error_detail"])

    async def test_a_swarm_relays_a_delegate_as_its_own_message(self):
        await self.run_swarm(FakeResponse(sse(
            {"type": "message_delta", "delta": "over to Bob"},
            {"type": "message_done", "content": "over to Bob", "output_type": "text", "render_as": "text"},
            {"type": "message_start", "id": "sub-1", "persona_id": str(self.persona_bob.id)},
            {"type": "message_delta", "delta": "Bob here"},
            {"type": "message_done", "content": "Bob here", "output_type": "text", "render_as": "text"},
        )))
        rows = await sync_to_async(self.reply_rows)()
        self.assertEqual([(r.content, r.status, r.sender_id) for r in rows], [
            ("over to Bob", "completed", self.persona_sara.identity_user_id),
            ("Bob here", "completed", self.persona_bob.identity_user_id),
        ])
        # the delegate's start event is republished under the DB message id
        starts = self.events("message_start")
        self.assertEqual(starts[1]["id"], str(rows[1].id))
        self.assertEqual(len(self.events("message_done")), 2)

    async def test_a_swarm_stop_ends_the_delegate_that_is_streaming(self):
        stopper = asyncio.ensure_future(self.stop_the_pending_reply_soon(after=0.1))
        await self.run_swarm(FakeResponse(sse(
            {"type": "message_delta", "delta": "over to Bob"},
            {"type": "message_done", "content": "over to Bob", "output_type": "text", "render_as": "text"},
            {"type": "message_start", "id": "sub-1", "persona_id": str(self.persona_bob.id)},
            {"type": "message_delta", "delta": "Bob was saying"},
        ), hang=True))
        pending = await stopper
        rows = await sync_to_async(self.reply_rows)()
        root, sub = rows
        self.assertEqual(str(sub.id), str(pending.id))
        self.assertEqual((root.status, root.metadata.get("stopped")), ("completed", None))
        self.assertEqual((sub.status, sub.content, sub.metadata.get("stopped")), ("completed", "Bob was saying", True))
        done = [e for e in self.events("message_done") if e["id"] == str(sub.id)][0]
        self.assertTrue(done["stopped"])


# ── reserved wire fields for the team AI operations work ─────────────────────
# Present with defaults from day one, so an app can ship its parsers before
# the capabilities that fill them. Additive only.
from chat.services import _serialise  # noqa: E402


class WireFieldDefaultsTests(MentionRightFixture):
    def message(self, **metadata):
        return ChatMessage.objects.create(
            company=self.company, project=self.p1, topic=self.t1, sender=self.persona_sara.identity_user,
            content="hi", sequence=1, metadata={"persona_id": str(self.persona_sara.id), **metadata},
        )

    def test_defaults_when_nothing_has_filled_them(self):
        out = _serialise(self.message())
        self.assertEqual(out["activity_trail"], [])
        self.assertEqual(out["approvals"], [])
        self.assertIsNone(out["preflight"])
        self.assertIsNone(out["answered_by_model"])
        self.assertIsNone(out["usage"])

    def test_values_pass_through_from_metadata(self):
        out = _serialise(self.message(
            activity_trail=[{"tool": "web_search", "ok": True, "duration_ms": 120, "preview": "…"}],
            preflight={"status": "proposed"}, answered_by_model="gpt-4o-mini (fallback)",
            usage={"prompt_tokens": 900, "output_tokens": 12, "context_window": 200000},
        ))
        self.assertEqual(out["activity_trail"][0]["tool"], "web_search")
        self.assertEqual(out["preflight"]["status"], "proposed")
        self.assertEqual(_serialise(self.message(approvals=[{"call_id": "c1", "tool": "run_command", "status": "denied"}]))["approvals"][0]["status"], "denied")
        self.assertEqual(out["answered_by_model"], "gpt-4o-mini (fallback)")
        self.assertEqual(out["usage"]["context_window"], 200000)
        self.assertEqual(_serialise(self.message(recalled=2))["recalled"], 2)
        self.assertEqual(out["recalled"], 0)
        self.assertEqual(_serialise(self.message(nudges=["and cite it"]))["nudges"], ["and cite it"])
        self.assertEqual(out["nudges"], [])


class RelayUsageTests(RelayFixture):
    """The worker's usage on message_done is kept on the row and republished."""

    async def test_usage_on_done_is_stored_and_republished(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_delta", "delta": "hi"},
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text",
             "prompt_tokens": 7366, "output_tokens": 104, "context_window": 1000000},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["usage"], {"prompt_tokens": 7366, "output_tokens": 104, "context_window": 1000000})
        done = self.events("message_done")[0]
        self.assertEqual((done["prompt_tokens"], done["output_tokens"], done["context_window"]), (7366, 104, 1000000))

    async def test_the_fallback_that_answered_is_kept_and_republished(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_delta", "delta": "hi"},
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text", "answered_by_model": "Small (fallback)"},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["answered_by_model"], "Small (fallback)")
        self.assertEqual(self.events("message_done")[0]["answered_by_model"], "Small (fallback)")
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"},
        )))
        row = (await sync_to_async(self.reply_rows)())[-1]
        self.assertNotIn("answered_by_model", row.metadata)
        self.assertIsNone(self.events("message_done")[-1]["answered_by_model"])

    async def test_what_the_reply_recorded_is_kept_and_republished(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text", "recalled": 2},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["recalled"], 2)
        self.assertEqual(self.events("message_done")[0]["recalled"], 2)
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"})))
        self.assertEqual(self.events("message_done")[-1]["recalled"], 0)

    async def test_a_done_without_usage_stores_none(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertNotIn("usage", row.metadata)
        self.assertIsNone(self.events("message_done")[0]["prompt_tokens"])


# ── the activity trail: every tool call, closed, on the wire and on the row ──
class ToolActivityEndEventTests(SimpleTestCase):
    def test_carries_outcome_duration_and_preview(self):
        ev = tool_activity_end_event("m1", {"tool_result": {"name": "web_search", "ok": True, "duration_ms": 412, "preview": "Canada …", "error": None, "url": "https://www.bing.com/search?q=canada"}})
        self.assertEqual(ev, {"type": "tool_activity_end", "id": "m1", "tool": "web_search", "ok": True, "duration_ms": 412, "preview": "Canada …", "error": None, "url": "https://www.bing.com/search?q=canada"})
        self.assertIsNone(tool_activity_end_event("m1", {"tool_result": {"name": "shell", "ok": True, "duration_ms": 1}})["url"])  # no page for a shell call

    def test_nothing_to_show_publishes_nothing(self):
        self.assertIsNone(tool_activity_end_event("m1", {"tool_result": {"name": "", "ok": True, "duration_ms": 1}}))
        self.assertIsNone(tool_activity_end_event("m1", {}))


def tool_pair(name, ok=True, duration_ms=100, preview="…", error=None, url=None):
    return [
        {"type": "tool_call_start", "tool_call": {"name": name, "args": {}}},
        {"type": "tool_call_end", "tool_result": {"name": name, "ok": ok, "duration_ms": duration_ms, "preview": preview if ok else None, "error": error, "url": url}},
    ]


class RelayActivityTrailTests(RelayFixture):
    async def test_each_call_is_published_as_it_ends_and_kept_on_the_row(self):
        await self.run_single(FakeResponse(sse(
            *tool_pair("web_search", preview="Canada GDP …"),
            *tool_pair("shell", ok=False, duration_ms=30, error="command not allowed"),
            {"type": "message_done", "content": "done", "output_type": "text", "render_as": "text"},
        )))
        ends = self.events("tool_activity_end")
        self.assertEqual([(e["tool"], e["ok"], e["duration_ms"]) for e in ends], [("web_search", True, 100), ("shell", False, 30)])
        self.assertEqual(ends[1]["error"], "command not allowed")
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["activity_trail"], [
            {"tool": "web_search", "ok": True, "duration_ms": 100, "preview": "Canada GDP …", "error": None, "url": None},
            {"tool": "shell", "ok": False, "duration_ms": 30, "preview": None, "error": "command not allowed", "url": None},
        ])
        # and the start events still drive the activity label as before
        self.assertEqual([e["tool"] for e in self.events("tool_activity")], ["web_search", "shell"])

    async def test_the_trail_is_capped_keeping_the_newest(self):
        calls = []
        for i in range(55):
            calls += tool_pair(f"t{i}")
        await self.run_single(FakeResponse(sse(*calls, {"type": "message_done", "content": "done", "output_type": "text", "render_as": "text"})))
        row = (await sync_to_async(self.reply_rows)())[0]
        trail = row.metadata["activity_trail"]
        self.assertEqual(len(trail), 50)
        self.assertEqual((trail[0]["tool"], trail[-1]["tool"]), ("t5", "t54"))

    async def test_a_stopped_run_keeps_its_trail(self):
        stopper = asyncio.ensure_future(self.stop_the_pending_reply_soon())
        await self.run_single(FakeResponse(sse(*tool_pair("web_search"), {"type": "message_delta", "delta": "partial"}), hang=True))
        await stopper
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertTrue(row.metadata.get("stopped"))
        self.assertEqual([t["tool"] for t in row.metadata["activity_trail"]], ["web_search"])

    async def test_a_failed_run_keeps_its_trail(self):
        await self.run_single(FakeResponse(sse(*tool_pair("web_search"), {"type": "message_error", "error": "status_code: 429 rate_limit_error"})))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.status, "failed")
        self.assertEqual([t["tool"] for t in row.metadata["activity_trail"]], ["web_search"])

    async def test_a_swarm_delegate_gets_its_own_trail(self):
        await self.run_swarm(FakeResponse(sse(
            *tool_pair("web_search"),
            {"type": "message_done", "content": "over to Bob", "output_type": "text", "render_as": "text"},
            {"type": "message_start", "id": "sub-1", "persona_id": str(self.persona_bob.id)},
            *tool_pair("shell"),
            {"type": "message_done", "content": "Bob here", "output_type": "text", "render_as": "text"},
        )))
        root, sub = await sync_to_async(self.reply_rows)()
        self.assertEqual([t["tool"] for t in root.metadata["activity_trail"]], ["web_search"])
        self.assertEqual([t["tool"] for t in sub.metadata["activity_trail"]], ["shell"])
        ends = self.events("tool_activity_end")
        self.assertEqual([(e["id"] == str(sub.id), e["tool"]) for e in ends], [(False, "web_search"), (True, "shell")])


PLAN = {"summary": "Read the CSV and write the report.", "steps": [{"title": "Read sales.csv", "tools": ["filesystem"], "writes": False}, {"title": "Write report.md", "tools": ["filesystem"], "writes": True}], "risks": ["Overwrites report.md"]}


class PreflightRelayTests(RelayFixture):
    """A gated persona plans first; the plan lands on the row for a person to decide."""

    def setUp(self):
        super().setUp()
        FakeClient.posted = []

    def gate(self):
        self.persona_sara.acts_after_approval = True
        self.persona_sara.save(update_fields=["acts_after_approval"])

    async def test_a_gated_persona_is_flagged_for_the_worker_and_an_ungated_one_is_not(self):
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"})))
        self.assertFalse(FakeClient.posted[-1]["preflight"])
        await sync_to_async(self.gate)()
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"})))
        self.assertTrue(FakeClient.posted[-1]["preflight"])
        self.assertIsNone(FakeClient.posted[-1]["approved_plan"])

    async def test_a_preflight_reply_stores_the_proposal_with_what_was_asked(self):
        await sync_to_async(self.gate)()
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": json.dumps(PLAN), "output_type": "preflight", "render_as": "preflight"},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["preflight"], {"status": "proposed", "plan": PLAN, "user_message": "chart please", "user_message_id": "u1"})
        done = self.events("message_done")[0]
        self.assertEqual(done["render_as"], "preflight")
        self.assertEqual(done["preflight"]["status"], "proposed")  # live cards decide without a reload

    async def test_a_plan_that_is_not_json_is_kept_as_text_with_no_proposal(self):
        await sync_to_async(self.gate)()
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": "I would read the file then write it.", "output_type": "preflight", "render_as": "preflight"},
        )))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertNotIn("preflight", row.metadata)
        self.assertEqual(row.metadata["render_as"], "text")


class PreflightDecisionTests(RelayFixture):
    """Approve, adjust or decline a proposal, under persona.approve_run at the topic."""

    def setUp(self):
        super().setUp()
        FakeClient.posted = []
        self.persona_sara.acts_after_approval = True
        self.persona_sara.save(update_fields=["acts_after_approval"])

    async def propose(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_done", "content": json.dumps(PLAN), "output_type": "preflight", "render_as": "preflight"},
        )))
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": "done", "output_type": "text", "render_as": "text"}))
        return (await sync_to_async(self.reply_rows)())[0]

    async def decide(self, row, user, decision, note=None):
        from chat.services import decide_preflight
        outcome = await decide_preflight(topic=self.t1, message_id=str(row.id), user=user, decision=decision, note=note)
        # The re-trigger is fire-and-forget (the HTTP reply never waits on AI);
        # let it run to its end before looking at what was posted.
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending)
        return outcome

    async def test_approve_records_who_and_runs_the_plan_with_the_tools_back_on(self):
        row = await self.propose()
        outcome = await self.decide(row, self.owner, "approve")
        self.assertEqual(outcome["status"], "approved")
        await sync_to_async(row.refresh_from_db)()
        pf = row.metadata["preflight"]
        self.assertEqual((pf["status"], pf["decided_by_name"]), ("approved", "owner"))
        self.assertIn("decided_at", pf)
        posted = FakeClient.posted[-1]
        self.assertFalse(posted["preflight"])
        self.assertIn("Read sales.csv", posted["approved_plan"])
        self.assertEqual((posted["message"], posted["user_message_id"]), ("chart please", "u1"))
        self.assertEqual(len(self.events("preflight_decided")), 1)

    async def test_adjust_asks_for_another_plan_with_the_note(self):
        row = await self.propose()
        outcome = await self.decide(row, self.owner, "adjust", note="Do not overwrite report.md; write report-v2.md")
        self.assertEqual(outcome["status"], "adjusted")
        posted = FakeClient.posted[-1]
        self.assertTrue(posted["preflight"])
        self.assertIn("report-v2.md", posted["message"])

    async def test_decline_closes_the_proposal_and_says_so_in_the_topic(self):
        row = await self.propose()
        outcome = await self.decide(row, self.owner, "decline")
        self.assertEqual(outcome["status"], "declined")
        from nucleus.models import ChatMessage
        line = await sync_to_async(lambda: ChatMessage.objects.filter(topic=self.t1, message_type=ChatMessage.MessageType.SYSTEM).order_by("-sequence").first())()
        self.assertIn("declined", line.content)
        self.assertEqual(len(FakeClient.posted), 1)  # nothing re-triggered

    async def test_a_decided_plan_cannot_be_decided_again_and_the_right_is_checked(self):
        from chat.services import PreflightError
        row = await self.propose()
        with self.assertRaises(PreflightError) as ctx:
            await self.decide(row, self.vera, "approve")  # a viewer cannot approve
        self.assertEqual(ctx.exception.status, 403)
        await self.decide(row, self.owner, "decline")
        with self.assertRaises(PreflightError) as ctx:
            await self.decide(row, self.owner, "approve")
        self.assertEqual(ctx.exception.status, 409)
        with self.assertRaises(PreflightError) as ctx:
            await self.decide(type("Row", (), {"id": "00000000-0000-0000-0000-000000000000"})(), self.owner, "approve")
        self.assertEqual(ctx.exception.status, 404)


# ── W16 Tool approvals ────────────────────────────────────────────────────────
APPROVAL = {"call_id": "c1", "tool": "run_command", "capability_id": "shell", "args_preview": 'command: "git push"'}


class ToolApprovalRelayTests(RelayFixture):
    """A tool call the worker holds lands on the row at once, is told to the topic, and expires with the reply."""

    def setUp(self):
        super().setUp()
        FakeClient.posted = []

    async def test_a_chat_turn_is_interactive_and_a_scheduled_one_is_not(self):
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"})))
        self.assertTrue(FakeClient.posted[-1]["interactive"])
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"}))
        await trigger_ai_response_async(
            company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
            user_message="chart please", user_message_id="u1", topic_id=str(self.t1.id), interactive=False,
        )
        self.assertFalse(FakeClient.posted[-1]["interactive"])

    async def test_a_request_is_stored_pending_and_published_then_expires_when_the_reply_ends(self):
        await self.run_single(FakeResponse(sse(
            {"type": "approval_requested", "id": "m", "approval": APPROVAL},
            {"type": "message_done", "content": "I could not push.", "output_type": "text", "render_as": "text"},
        )))
        published = self.events("tool_approval")
        self.assertEqual(len(published), 1)
        self.assertEqual((published[0]["approval"]["call_id"], published[0]["approval"]["tool"], published[0]["approval"]["status"]), ("c1", "run_command", "pending"))
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["approvals"][0]["status"], "expired")  # nobody decided before the reply ended
        self.assertEqual(row.metadata["approvals"][0]["args_preview"], 'command: "git push"')

    async def test_a_keepalive_is_ignored_and_a_request_without_a_call_id_is_dropped(self):
        await self.run_single(FakeResponse(sse(
            {"type": "keepalive", "id": "m"},
            {"type": "approval_requested", "id": "m", "approval": {"tool": "x"}},
            {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"},
        )))
        self.assertEqual(self.events("tool_approval"), [])
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertNotIn("approvals", row.metadata)
        self.assertEqual(row.metadata["render_as"], "text")


class ToolApprovalDecisionTests(RelayFixture):
    """Allow, deny, or allow always -- under persona.approve_run; always also needs persona.update."""

    def setUp(self):
        super().setUp()
        FakeClient.posted = []

    async def pending_row(self):
        from chat.services import record_approval_request
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"}))
        await self.run_single(FakeClient.response)
        row = (await sync_to_async(self.reply_rows)())[0]
        await sync_to_async(record_approval_request)(str(row.id), APPROVAL)
        return row

    async def decide(self, row, user, decision, always=False, call_id="c1"):
        from chat.services import decide_tool_approval
        return await decide_tool_approval(topic=self.t1, message_id=str(row.id), call_id=call_id, user=user, decision=decision, always=always)

    async def state(self, row, call_id="c1"):
        from chat.services import approval_state
        return await approval_state(str(row.id), call_id)

    async def test_pending_then_allowed_by_a_member_and_the_worker_sees_it(self):
        row = await self.pending_row()
        self.assertEqual(await self.state(row), {"status": "pending", "always": False})
        outcome = await self.decide(row, self.sara, "allow")
        self.assertEqual((outcome["status"], outcome["approval"]["decided_by_name"]), ("allowed", "sara"))
        self.assertEqual(await self.state(row), {"status": "allowed", "always": False})
        self.assertEqual(len(self.events("tool_approval_decided")), 1)
        await sync_to_async(row.refresh_from_db)()
        self.assertEqual(row.metadata["approvals"][0]["status"], "allowed")

    async def test_denied_and_the_worker_sees_it(self):
        row = await self.pending_row()
        await self.decide(row, self.owner, "deny")
        self.assertEqual((await self.state(row))["status"], "denied")

    async def test_always_writes_the_level_onto_the_persona_and_needs_persona_update(self):
        from chat.services import ApprovalError
        row = await self.pending_row()
        with self.assertRaises(ApprovalError) as ctx:
            await self.decide(row, self.sara, "allow", always=True)  # a member may allow, not change the persona
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual((await self.state(row))["status"], "pending")
        outcome = await self.decide(row, self.owner, "allow", always=True)
        self.assertTrue(outcome["approval"]["always"])
        self.assertEqual(await self.state(row), {"status": "allowed", "always": True})
        await sync_to_async(self.persona_sara.refresh_from_db)()
        self.assertEqual(self.persona_sara.tool_levels, {"shell/run_command": "auto"})

    async def test_a_viewer_cannot_decide_and_a_decision_is_final(self):
        from chat.services import ApprovalError
        row = await self.pending_row()
        with self.assertRaises(ApprovalError) as ctx:
            await self.decide(row, self.vera, "allow")
        self.assertEqual(ctx.exception.status, 403)
        await self.decide(row, self.owner, "deny")
        with self.assertRaises(ApprovalError) as ctx:
            await self.decide(row, self.owner, "allow")
        self.assertEqual(ctx.exception.status, 409)
        with self.assertRaises(ApprovalError) as ctx:
            await self.decide(row, self.owner, "allow", call_id="nope")
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(ApprovalError) as ctx:
            await self.decide(row, self.owner, "maybe")
        self.assertEqual(ctx.exception.status, 400)

    async def test_a_stopped_reply_answers_the_worker_with_stopped(self):
        row = await self.pending_row()
        await self.signals.request_stop(str(row.id))
        self.assertEqual((await self.state(row))["status"], "stopped")
        self.assertEqual((await self.state(row, "unknown"))["status"], "stopped")

    async def test_an_unknown_call_is_pending_until_the_relay_has_stored_it(self):
        row = await self.pending_row()
        self.assertEqual((await self.state(row, "not-yet"))["status"], "pending")


# ── W4 Routines ───────────────────────────────────────────────────────────────
class RoutineDirectiveTests(SimpleTestCase):
    """The first standalone /token names a routine; paths, /swarm and mid-word slashes do not."""

    def setUp(self):
        global MessageDirectives
        from chat.services import MessageDirectives

    def test_the_first_standalone_slash_token_is_the_routine_and_is_stripped(self):
        d = MessageDirectives("@Sara /weekly-digest last week")
        self.assertEqual((d.routine_name, d.clean_message, d.mention_names), ("weekly-digest", "@Sara last week", ["Sara"]))
        d = MessageDirectives("/weekly-digest @Sara")
        self.assertEqual((d.routine_name, d.clean_message), ("weekly-digest", "@Sara"))

    def test_paths_swarm_and_mid_word_slashes_are_not_routines(self):
        d = MessageDirectives("@Sara look at /etc/hosts and 50/50 odds")
        self.assertIsNone(d.routine_name)
        self.assertEqual(d.clean_message, "@Sara look at /etc/hosts and 50/50 odds")
        d = MessageDirectives("@A @B plan the launch /swarm")
        self.assertTrue(d.swarm)
        self.assertIsNone(d.routine_name)
        self.assertIsNone(MessageDirectives("@Sara /Weekly_Digest go").routine_name)  # not the slug alphabet

    def test_only_the_first_token_counts_and_the_other_directives_still_parse(self):
        d = MessageDirectives("@Sara /weekly-digest /other sales @chart")
        self.assertEqual((d.routine_name, d.output_type, d.clean_message), ("weekly-digest", "chart", "@Sara /other sales"))
        d = MessageDirectives("@Sara @session /meeting-notes today")
        self.assertTrue(d.has_session_open)
        self.assertEqual(d.routine_name, "meeting-notes")


class RoutineSendTests(MentionRightFixture):
    """`@Sara /weekly-digest …` runs Sara with the routine; an unknown routine refuses her."""

    def setUp(self):
        super().setUp()
        from intelligence.services import seed_builtin_routines
        seed_builtin_routines(self.p1)

    def test_a_known_routine_rides_the_trigger_and_leaves_the_message(self):
        r, trigger, _swarm, publish = self.send(self.sara, "@Sara /weekly-digest last week")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["refusals"], [])
        kwargs = trigger.call_args.kwargs
        self.assertEqual(kwargs["routine"].name, "weekly-digest")
        self.assertEqual(kwargs["user_message"], "@Sara last week")
        self.assertEqual(self.refused_events(publish), [])

    def test_an_unknown_routine_refuses_the_mentioned_personas_and_posts_the_message(self):
        r, trigger, _swarm, publish = self.send(self.sara, "@Sara /no-such-thing hello")
        self.assertEqual(r.status_code, 200, r.content)
        refusals = r.json()["refusals"]
        self.assertEqual([(x["name"], x["code"]) for x in refusals], [("Sara", "unknown_routine")])
        self.assertIn("/no-such-thing", refusals[0]["message"])
        trigger.assert_not_called()
        self.assertEqual(len(self.refused_events(publish)), 1)

    def test_a_routine_from_another_project_is_unknown_here(self):
        from intelligence.services import create_routine
        create_routine(self.company, self.p2, self.owner, {"name": "elsewhere", "title": "Elsewhere", "purpose": "", "instructions": "x"})
        r, trigger, _swarm, _publish = self.send(self.sara, "@Sara /elsewhere go")
        self.assertEqual(r.json()["refusals"][0]["code"], "unknown_routine")
        trigger.assert_not_called()

    def test_a_slash_token_without_a_mention_is_just_a_message(self):
        r, trigger, _swarm, publish = self.send(self.sara, "/weekly-digest is what we call it")
        self.assertEqual((r.status_code, r.json()["refusals"]), (200, []))
        trigger.assert_not_called()
        self.assertEqual(self.refused_events(publish), [])


class RoutineRelayTests(RelayFixture):
    """The routine's id rides the job the worker gets; none when no routine was named."""

    def setUp(self):
        super().setUp()
        FakeClient.posted = []

    async def test_the_job_carries_the_routine_id_or_none(self):
        from intelligence.services import seed_builtin_routines
        routines = await sync_to_async(seed_builtin_routines)(self.p1)
        digest = next(x for x in routines if x.name == "weekly-digest")
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"}))
        await trigger_ai_response_async(
            company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
            user_message="last week", user_message_id="u1", topic_id=str(self.t1.id), routine=digest,
        )
        self.assertEqual(FakeClient.posted[-1]["routine_id"], str(digest.id))
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"})))
        self.assertIsNone(FakeClient.posted[-1]["routine_id"])


# ── W22 Run ownership ─────────────────────────────────────────────────────────
class RunOwnershipTests(RelayFixture):
    """A reply belongs to the person who called it: recorded on the row and the wire, and the only one who may stop it."""

    DONE = {"type": "message_done", "content": "hi", "output_type": "text", "render_as": "text"}

    def setUp(self):
        super().setUp()
        FakeClient.posted = []

    async def test_a_reply_records_its_caller_on_the_row_and_on_message_start(self):
        FakeClient.response = FakeResponse(sse(self.DONE))
        await trigger_ai_response_async(
            company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
            user_message="hi", user_message_id="u1", topic_id=str(self.t1.id), triggered_by=self.sara,
        )
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual((row.metadata["triggered_by_id"], row.metadata["triggered_by_name"]), (str(self.sara.id), "sara"))
        start = self.events("message_start")[0]
        self.assertEqual((start["triggered_by_id"], start["triggered_by_name"]), (str(self.sara.id), "sara"))
        from chat.services import _serialise
        out = await sync_to_async(lambda: _serialise(ChatMessage.objects.select_related("sender").get(id=row.id)))()
        self.assertEqual((out["triggered_by_id"], out["triggered_by_name"]), (str(self.sara.id), "sara"))

    def test_only_the_caller_can_stop_and_a_reply_without_a_caller_keeps_the_old_rule(self):
        from chat.services import create_ai_message, request_stop_for_message
        mine = create_ai_message(self.company, self.p1, self.t1, self.persona_sara, triggered_by=self.sara)
        legacy = create_ai_message(self.company, self.p1, self.t1, self.persona_sara)
        self.assertEqual(request_stop_for_message(self.t1, mine["id"], user=self.owner), "not_owner")
        self.assertEqual(request_stop_for_message(self.t1, mine["id"], user=self.sara), "stopping")
        self.assertEqual(request_stop_for_message(self.t1, legacy["id"], user=self.owner), "stopping")
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/messages/{mine['id']}/stop/"
        r = self.call("post", path, self.owner)
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("called the persona", r.json()["detail"])

    def test_a_send_names_the_sender_as_the_caller(self):
        _r, trigger, _swarm, _publish = self.send(self.sara, "@Sara hi")
        self.assertEqual(trigger.call_args.kwargs["triggered_by"].id, self.sara.id)

    async def test_an_approved_plan_runs_for_the_person_who_asked(self):
        from chat.services import decide_preflight
        self.persona_sara.acts_after_approval = True
        await sync_to_async(self.persona_sara.save)(update_fields=["acts_after_approval"])
        # The asking message is a real row here, so the re-trigger belongs to its sender, not the approver.
        asked = await sync_to_async(ChatMessage.objects.create)(company=self.company, project=self.p1, topic=self.t1, sender=self.sara, content="@Sara go", sequence=1)
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": json.dumps(PLAN), "output_type": "preflight", "render_as": "preflight"}))
        await trigger_ai_response_async(
            company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
            user_message="go", user_message_id=str(asked.id), topic_id=str(self.t1.id), triggered_by=self.sara,
        )
        proposal = (await sync_to_async(self.reply_rows)())[0]
        FakeClient.response = FakeResponse(sse(self.DONE))
        await decide_preflight(topic=self.t1, message_id=str(proposal.id), user=self.owner, decision="approve")
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending)
        run = (await sync_to_async(self.reply_rows)())[-1]
        self.assertEqual(run.metadata["triggered_by_id"], str(self.sara.id))


# ── W8 Nudge ─────────────────────────────────────────────────────────────────
class NudgeSignalTests(SimpleTestCase):
    """The signal store keeps a reply's nudges in order and hands them out once."""

    async def test_nudges_queue_expire_and_are_taken_once(self):
        clock = {"t": 0.0}
        store = MemoryStore(now=lambda: clock["t"])
        signals = StopSignals(store)
        await signals.add_nudge("m1", {"text": "first", "user_id": "u1"})
        await signals.add_nudge("m1", {"text": "second", "user_id": "u1"})
        self.assertEqual([n["text"] for n in await signals.take_nudges("m1")], ["first", "second"])
        self.assertEqual(await signals.take_nudges("m1"), [])
        await signals.add_nudge("m2", {"text": "late", "user_id": "u1"})
        clock["t"] = 601
        self.assertEqual(await signals.take_nudges("m2"), [])  # gone after the TTL


class NudgeRouteTests(RelayFixture):
    """Only the caller nudges a running reply; a finished one answers 409; the worker pops what waits."""

    def setUp(self):
        super().setUp()
        # The route and the internal poll read the process-wide store at call time.
        patcher = patch("chat.stop_signals.stop_signals", return_value=self.signals)
        patcher.start()
        self.addCleanup(patcher.stop)

    def pending_reply(self, owner):
        from chat.services import create_ai_message
        return create_ai_message(self.company, self.p1, self.t1, self.persona_sara, triggered_by=owner)

    def nudge(self, user, message_id, text="also check the 2023 figure"):
        return self.call("post", f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/messages/{message_id}/nudge/", user, {"text": text})

    def test_the_caller_nudges_a_running_reply_and_the_worker_takes_it_once(self):
        import asyncio
        msg = self.pending_reply(self.owner)
        r = self.nudge(self.sara, msg["id"])
        self.assertEqual(r.status_code, 403, r.content)  # Sara did not call the persona
        r = self.nudge(self.owner, msg["id"], "   ")
        self.assertEqual(r.status_code, 422, r.content)
        r = self.nudge(self.owner, msg["id"])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), {"queued": True})
        waiting = asyncio.run(self.signals.take_nudges(msg["id"]))
        self.assertEqual([(n["text"], n["user_id"]) for n in waiting], [("also check the 2023 figure", str(self.owner.id))])
        # The internal poll pops them for the worker.
        asyncio.run(self.signals.add_nudge(msg["id"], {"text": "and cite it", "user_id": str(self.owner.id)}))
        import os
        from django.test import Client
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            r = Client().get(f"/api/v1/internal/messages/{msg['id']}/nudges/", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.json(), {"nudges": ["and cite it"]})
        self.assertEqual(asyncio.run(self.signals.take_nudges(msg["id"])), [])

    def test_a_finished_reply_cannot_be_nudged(self):
        from nucleus.models import ChatMessage
        msg = self.pending_reply(self.owner)
        ChatMessage.objects.filter(id=msg["id"]).update(status=ChatMessage.Status.COMPLETED)
        self.assertEqual(self.nudge(self.owner, msg["id"]).status_code, 409)
        self.assertEqual(self.nudge(self.owner, "00000000-0000-0000-0000-000000000000").status_code, 404)


class NudgeRelayTests(RelayFixture):
    """A taken nudge is announced and kept; an untaken one becomes a message when the reply ends or is stopped."""

    async def test_a_taken_nudge_is_published_and_kept_on_the_row(self):
        await self.run_single(FakeResponse(sse(
            {"type": "message_delta", "delta": "Looking"},
            {"type": "nudge_taken", "nudge": "also the 2023 figure"},
            {"type": "message_done", "content": "Done.", "output_type": "text", "render_as": "text"},
        )))
        self.assertEqual(self.events("nudge_taken"), [{"type": "nudge_taken", "id": self.events("message_done")[0]["id"], "text": "also the 2023 figure"}])
        row = (await sync_to_async(self.reply_rows)())[0]
        self.assertEqual(row.metadata["nudges"], ["also the 2023 figure"])

    async def test_an_untaken_nudge_is_posted_as_a_message_when_the_reply_ends(self):
        FakeClient.response = FakeResponse(sse({"type": "message_done", "content": "Done.", "output_type": "text", "render_as": "text"}))

        async def nudge_meanwhile():
            pending = None
            for _ in range(50):
                await asyncio.sleep(0.01)
                pending = await sync_to_async(lambda: ChatMessage.objects.filter(topic=self.t1, status="pending").first())()
                if pending:
                    break
            if pending:
                await self.signals.add_nudge(str(pending.id), {"text": "and cite it", "user_id": str(self.owner.id), "name": "Owner"})
        task = asyncio.create_task(nudge_meanwhile())
        await asyncio.sleep(0.02)
        await self.run_single(FakeResponse(sse({"type": "message_done", "content": "Done.", "output_type": "text", "render_as": "text"})))
        await task
        rows = await sync_to_async(lambda: list(ChatMessage.objects.filter(topic=self.t1).order_by("sequence")))()
        human = [r for r in rows if (r.metadata or {}).get("role") == "user"]
        self.assertEqual([r.content for r in human], ["and cite it"])
        self.assertEqual(human[0].sender_id, self.owner.id)
        self.assertEqual([e for e in self.published if e.get("type") == "message" and e.get("content") == "and cite it"][0]["sender_type"], "human")
