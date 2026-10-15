"""
Built-in context panel providers for M6.

  FilePanelProvider  — shows files attached to a topic; each file is individually removable
  WebPanelProvider   — shows web links attached to a topic, in their own "Web Links" group
  ChatPanelProvider  — shows chat messages; individual messages can be excluded from context

Each class is decorated with @ContextPanelRegistry.register so it is available
as soon as this module is imported. Import this module once (in api.py) and all
providers are registered automatically.
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

from .panel_provider import ContextPanelItem, ContextPanelProvider, ContextPanelRegistry

logger = logging.getLogger(__name__)


@ContextPanelRegistry.register
class FilePanelProvider(ContextPanelProvider):
    """
    Shows file ContextSource records attached to a topic.

    Deleting an item removes the entire ContextSource (file + vectors) —
    the same operation as calling the detach_context_source() service.
    """

    directive = "file"
    label = "Files"
    icon = "file-text"
    source_type = "file"        # the ContextSource.Type this group lists
    can_delete_source = False   # no "delete all files at once" button
    can_delete_items = True     # each file has its own delete button

    def list_items(self, topic, company) -> list[ContextPanelItem]:
        from nucleus.models import ContextSource

        sources = (
            ContextSource.objects.filter(topic=topic, type=self.source_type, is_active=True)
            .order_by("created_at")
        )
        items = []
        for src in sources:
            size_kb = round(src.file_size / 1024, 1) if src.file_size else 0
            items.append(
                ContextPanelItem(
                    id=str(src.id),
                    label=src.name,
                    deletable=True,
                    metadata={
                        "status": src.status,
                        "file_size": src.file_size,
                        "size_kb": size_kb,
                        "mime_type": src.mime_type,
                        "created_at": src.created_at.isoformat(),
                        "type": src.type,
                    },
                )
            )
        return items

    def delete_item(self, item_id: str, topic, company) -> None:
        """Detach and delete the ContextSource record + its ChromaDB collection."""
        from context.services import detach_context_source
        detach_context_source(item_id)


@ContextPanelRegistry.register
class WebPanelProvider(FilePanelProvider):
    """Same as FilePanelProvider, but lists web links as their own group."""

    directive = "web"
    label = "Web Links"
    icon = "globe"
    source_type = "web"


@ContextPanelRegistry.register
class ChatPanelProvider(ContextPanelProvider):
    """
    Shows human and AI chat messages in the topic.

    Removing an item sets is_deleted_from_context=True so the message
    is no longer included in AI context retrieval, while the message
    itself remains visible in the chat history.
    """

    directive = "chat"
    label = "Chat History"
    icon = "message-square"
    can_delete_source = False   # can't remove the whole chat group
    can_delete_items = True     # individual messages can be excluded

    def list_items(self, topic, company) -> list[ContextPanelItem]:
        from nucleus.models import ChatMessage

        messages = (
            ChatMessage.objects.filter(
                topic=topic,
                is_active=True,
                is_deleted_from_context=False,
                message_type__in=[
                    ChatMessage.MessageType.TEXT,
                    ChatMessage.MessageType.MARKDOWN,
                ],
            )
            .select_related("sender")
            .order_by("created_at")
        )
        items = []
        for msg in messages:
            sender_name = msg.sender.get_display_name() if msg.sender else "AI"
            full_content = msg.content or ""
            snippet = full_content[:80]
            if len(full_content) > 80:
                snippet += "…"
            sender_type = (
                getattr(msg.sender, "user_type", "human")
                if msg.sender
                else "ai"
            )
            items.append(
                ContextPanelItem(
                    id=str(msg.id),
                    label=f"{sender_name}: {snippet}",
                    deletable=True,
                    metadata={
                        "created_at": msg.created_at.isoformat(),
                        "sender_name": sender_name,
                        "sender_type": sender_type,
                        "content": full_content,
                        "sequence": msg.sequence,
                    },
                )
            )
        return items

    def delete_item(self, item_id: str, topic, company) -> None:
        """
        Exclude a message from AI context retrieval.
        Sets is_deleted_from_context=True — the message stays in the chat UI.
        Also requests nexus-ai to remove the vector (best effort).
        """
        from nucleus.models import ChatMessage

        try:
            msg = ChatMessage.objects.get(id=item_id, topic=topic, is_active=True)
        except ChatMessage.DoesNotExist:
            return

        msg.is_deleted_from_context = True
        msg.save(update_fields=["is_deleted_from_context"])

        # Best-effort vector deletion — ignore errors
        _delete_message_vector(str(msg.id), str(company.id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _delete_message_vector(message_id: str, company_id: str) -> None:
    """
    Drop a message's vector through NexusAIClient (Step 3, one door). The
    engine also drops the reply's tool memory under the same id (change 11.6).
    Fire-and-forget — the client never raises here.
    """
    from chat.nexus_ai import NexusAIClient

    NexusAIClient().delete_message_vector(message_id, company_id)
