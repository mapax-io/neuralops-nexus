"""
ContextPanelProvider — abstract interface every developer must implement
to expose their context source in the M6 context panel UI.

Each provider must:
  - declare `directive`         — matches the source type string (e.g. "file", "chat")
  - declare `label`             — displayed as the group header in the panel
  - declare `icon`              — Lucide icon name (e.g. "file-text", "message-square")
  - declare `can_delete_source` — whether the whole group can be deleted at once
  - declare `can_delete_items`  — whether individual items inside the group can be removed
  - implement `list_items(topic, company)` → list[ContextPanelItem]
  - implement `delete_item(item_id, topic, company)` if can_delete_items=True
  - optionally implement `delete_source(source_id, topic, company)` if can_delete_source=True
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextPanelItem:
    id: str
    label: str
    deletable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextPanelProvider(ABC):
    directive: str = ""
    label: str = ""
    icon: str = "layers"
    can_delete_source: bool = False
    can_delete_items: bool = True

    @abstractmethod
    def list_items(self, topic, company) -> list[ContextPanelItem]:
        """Return all items to display in this group of the context panel tree."""
        ...

    def delete_item(self, item_id: str, topic, company) -> None:
        """Remove a single item from context. Raise if can_delete_items=False."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support item deletion."
        )

    def delete_source(self, source_id: str, topic, company) -> None:
        """Delete the entire context source. Raise if can_delete_source=False."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support source deletion."
        )

    def to_dict(self, topic, company) -> dict:
        """Serialise this provider's group + all its items for the API response."""
        try:
            items = self.list_items(topic, company)
        except Exception as exc:
            logger.warning("[panel] list_items failed for %s: %s", self.directive, exc)
            items = []

        return {
            "directive": self.directive,
            "label": self.label,
            "icon": self.icon,
            "can_delete_source": self.can_delete_source,
            "can_delete_items": self.can_delete_items,
            "items": [
                {
                    "id": item.id,
                    "label": item.label,
                    "deletable": item.deletable,
                    "metadata": item.metadata,
                }
                for item in items
            ],
        }


class _ContextPanelRegistry:
    """Auto-registration registry for ContextPanelProviders."""

    def __init__(self):
        self._providers: dict[str, ContextPanelProvider] = {}

    def register(self, provider_cls: type[ContextPanelProvider]) -> type[ContextPanelProvider]:
        """Decorator — registers the provider class and returns it unchanged."""
        instance = provider_cls()
        if not instance.directive:
            raise ValueError(
                f"{provider_cls.__name__} must declare a non-empty `directive`."
            )
        self._providers[instance.directive] = instance
        return provider_cls

    def get(self, directive: str) -> ContextPanelProvider:
        """Return the provider for the given directive. Raises KeyError if not found."""
        return self._providers[directive]

    def get_all(self) -> list[ContextPanelProvider]:
        """Return all registered providers in registration order."""
        return list(self._providers.values())


ContextPanelRegistry = _ContextPanelRegistry()
