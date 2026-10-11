"""
HistoryPolicy — which history messages go into the prompt.

The rules are the Layer 0 behaviour rules (docs/NEXUS-AI-REVAMP.md §1.5),
applied to rows that already exclude the triggering message. 0.8.0 lineage:
the html/visual filters and the [Another Agent: …] prefix are ported behaviour
(legacy nucleus_client.shape_history, prompt_builder). Never reorders.
"""
from __future__ import annotations

from ai_engine.core.specs import HistoryMessage, HistoryRow, PersonaSpec

_VISUAL_TYPES = {"chart", "table", "diagram", "html", "form"}
_DROPPED_STATUSES = {"FAILED", "CANCELLED", "PENDING", "STREAMING"}


class HistoryPolicy:
    def __init__(self, depth: int) -> None:  # O3: HISTORY_DEPTH, default 10
        self.depth = depth

    def select(self, rows: list[HistoryRow], persona: PersonaSpec) -> list[HistoryMessage]:
        selected: list[HistoryMessage] = []
        for row in rows:
            # status filter — only when nucleus sends one (nucleus change 2)
            if row.status and row.status.upper() in _DROPPED_STATUSES:
                continue
            if row.stopped:
                continue
            content = (row.content or "").strip()
            if not content:
                continue

            if row.sender_type == "human":
                role = "user"
            elif row.sender_type == "persona":
                role = "assistant"
            else:
                continue  # "system" notifications aren't a persona's own words

            text = row.content
            if role == "assistant":
                if row.render_as == "html" and not (
                    content.startswith("<!DOCTYPE") or content.startswith("<html")
                ):
                    continue  # claims HTML, doesn't look like it — a broken render
                if row.output_type in _VISUAL_TYPES and row.render_as == "text":
                    continue  # a visual that fell back to text — a failed render
                if row.sender_name and row.sender_name != persona.name:
                    text = f"[Another Agent: {row.sender_name}]\n{text}"

            selected.append(HistoryMessage(role=role, author=row.sender_name, text=text))

        # keep the newest `depth`, oldest first; never reorder (O3)
        return selected[-self.depth:]
