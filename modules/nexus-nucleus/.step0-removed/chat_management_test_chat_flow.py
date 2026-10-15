"""
python manage.py test_chat_flow [--plain-only | --ai-only | --list-only]

Exercises send_message() end-to-end -- both the plain-message path and the
@mention -> AI trigger path -- plus list_messages() paging, against real DB
fixtures. Reuses whatever company/project/channel/topic/persona already
exists (e.g. from earlier manual testing), only creating what's missing --
safe to re-run any time.

Calls chat_api.send_message() directly (not over real HTTP) with a fake
request object carrying `.auth = owner`, since that's all a Django Ninja
async view needs once you're past the routing layer.
"""
import asyncio
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from chat import api as chat_api
from chat import services as chat_svc
from chat.schema import SendMessageIn
from intelligence import services as isvc
from nucleus.models import AIModel, ChatMessage, Company, Persona
from workspace import services as wsvc

User = get_user_model()


class Command(BaseCommand):
    help = "Exercise send_message (plain + AI trigger) and list_messages end-to-end."

    def add_arguments(self, parser):
        parser.add_argument("--plain-only", action="store_true", help="Only run the plain-message test.")
        parser.add_argument("--ai-only", action="store_true", help="Only run the AI-trigger test.")
        parser.add_argument("--list-only", action="store_true", help="Only run the list_messages test.")

    def handle(self, *args, **options):
        run_all = not any([options["plain_only"], options["ai_only"], options["list_only"]])

        if run_all or options["plain_only"]:
            self._section("send_message (plain)")
            self.test_send_message_plain()

        if run_all or options["ai_only"]:
            self._section("send_message (AI trigger)")
            self.test_send_message_ai_trigger()

        if run_all or options["list_only"]:
            self._section("list_messages")
            self.test_list_messages()

    def _section(self, title):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.NOTICE(title))
        self.stdout.write("=" * 60)

    # ── Fixtures -- fetched, not recreated, so this is safe to re-run ─────────

    def get_fixtures(self):
        """Pulls the company/owner/project that already exist in your DB."""
        company = Company.objects.first()
        if not company:
            raise RuntimeError("No Company exists yet -- nothing to test against.")
        owner = company.owner
        project = wsvc.list_projects(company, owner).first()
        if not project:
            raise RuntimeError("No Project exists yet -- create one first.")
        return company, owner, project

    def get_topic_fixtures(self):
        """One level deeper -- pulls (or creates) a channel + topic."""
        company, owner, project = self.get_fixtures()

        channel = wsvc.list_channels(owner, project).first()
        if not channel:
            channel = wsvc.create_channel(company, project, "general")

        topic = wsvc.list_topics(owner, channel).first()
        if not topic:
            topic = wsvc.create_topic(company, project, channel, "Test Topic", creator=owner)

        return company, owner, project, channel, topic

    def get_test_persona(self, company, project, owner):
        """
        Reuses an existing model-backed persona in this project if one
        exists, otherwise creates a throwaway one off the first AIModel
        found on the company. Needed for the @mention -> AI trigger path,
        since that only fires for personas with a model actually attached
        (see chat/api.py:_trigger_personas).
        """
        persona = Persona.objects.filter(
            project=project, source_type="model", model__isnull=False, is_active=True,
        ).select_related("model").first()
        if persona:
            return persona

        model = AIModel.objects.filter(company=company, is_active=True).first()
        if not model:
            raise RuntimeError(
                "No AIModel exists on this company -- create one first "
                "(AI Intelligence admin page, or isvc.create_ai_model())."
            )

        return isvc.create_persona(company, owner, {
            "name": "TestBot",
            "source_type": "model",
            "model_id": str(model.id),
            "project_id": str(project.id),
            "prompt": {"system_prompt": "You are a helpful test assistant. Keep replies short."},
        })

    async def _run_send_message(self, request, project_id, channel_id, topic_id, payload):
        """
        send_message() schedules its side effects (embed, Centrifugo
        publish, AI trigger) as fire-and-forget asyncio.create_task()
        calls -- fine under the real ASGI server, which keeps running
        after the response is sent, but asyncio.run() tears the loop
        down the instant this coroutine returns and would cancel every
        one of them mid-flight. So: wait for whatever got scheduled
        before handing control back, since we actually want to see the
        AI's reply land in the DB, not just the initial save.
        """
        result = await chat_api.send_message(request, project_id, channel_id, topic_id, payload)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return result

    # ── Tests -- one method per thing being tested ─────────────────────────

    def test_send_message_plain(self):
        """A plain message -- no @mention, no @session -- should just save,
        publish, and embed. No AI message should ever appear for this one."""
        company, owner, project, channel, topic = self.get_topic_fixtures()
        payload = SendMessageIn(content="Hello from test_chat_flow -- plain message, no AI.")
        request = SimpleNamespace(auth=owner)

        result = asyncio.run(self._run_send_message(
            request, str(project.id), str(channel.id), str(topic.id), payload,
        ))
        self.stdout.write(f"send_message (plain): {result['message']['id']} - {result['message']['content']}")
        return result

    def test_send_message_ai_trigger(self):
        """@mentions a persona -- should save the human message, then trigger
        nexus-ai and write a real AI reply back into the same topic."""
        company, owner, project, channel, topic = self.get_topic_fixtures()
        persona = self.get_test_persona(company, project, owner)

        payload = SendMessageIn(content=f"@{persona.name} say hello in one short sentence.")
        request = SimpleNamespace(auth=owner)

        result = asyncio.run(self._run_send_message(
            request, str(project.id), str(channel.id), str(topic.id), payload,
        ))
        self.stdout.write(f"send_message (AI trigger): {result['message']['id']} - {result['message']['content']}")

        ai_msg = (
            ChatMessage.objects.filter(topic=topic, sender=persona.identity_user)
            .order_by("-sequence").first()
        )
        if ai_msg:
            self.stdout.write(self.style.SUCCESS(
                f"  -> AI reply [{ai_msg.status}]: {ai_msg.content[:200]!r}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "  -> no AI message found -- check NEXUS_AI_URL / persona.model config."
            ))
        return result

    def test_list_messages(self):
        """Exercises chat_svc.list_messages() including before_sequence paging."""
        company, owner, project, channel, topic = self.get_topic_fixtures()

        page1 = chat_svc.list_messages(str(topic.id), limit=5)
        self.stdout.write(f"list_messages (limit=5): {len(page1)} messages")
        for m in page1:
            self.stdout.write(f"  seq={m['sequence']} [{m['sender_type']}] {m['content'][:60]!r}")

        if page1:
            oldest_seq = page1[0]["sequence"]
            page2 = chat_svc.list_messages(str(topic.id), limit=5, before_sequence=oldest_seq)
            self.stdout.write(f"list_messages (before_sequence={oldest_seq}): {len(page2)} older messages")

        return page1
