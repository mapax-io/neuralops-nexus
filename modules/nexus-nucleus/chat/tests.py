"""
Unit tests for the realtime event contract (chat/events.py).

Pure payload construction -- no DB, no HTTP. The relay in services.py decides
when to publish; these pin what it publishes.
"""
from django.test import SimpleTestCase

from chat.events import TOOL_ACTIVITY_LABELS, tool_activity_event


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
from chat.services import trigger_ai_response_async, trigger_ai_swarm_response_async  # noqa: E402


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

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def build_request(self, method, url, **kwargs):
        return (method, url)

    async def send(self, request, stream=True):
        return FakeClient.response


@override_settings(NEXUS_AI_URL="http://worker.test", INTERNAL_API_KEY="k")
class RelayTests(MentionRightFixture):
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
