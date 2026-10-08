"""
Prompt Builder
--------------
Assembles the final messages array for LiteLLM from:
  - persona system prompt
  - output type system instruction (M7 — appended to system prompt)
  - retrieved context chunks (with source labels)
  - conversation history
  - current user message

Returns a clean list[dict] ready for the LLM call.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from apps.interfaces.vectorstore import Chunk
from typing import Sequence
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
    TextPart,
)
from apps.factories.context_source import ContextSourceFactory
from apps.output_types.registry import TYPES_WITHOUT_CHOICE
from apps.schemas.trigger import (
    HistoryMessage,
    PersonaConfig,
    TriggerJob,
    TriggerSwarmJob,
)
from apps.core.config import settings
from apps.implementations.context_sources.recall.recall_context_source import RECALL_LABEL


BRIEF_HEADING = "Project brief — applies to every reply in this project:"


def compose_system_prompt(project_brief: str | None, persona_prompt: str) -> str:
    """
    The system prompt a persona runs with: the project's brief in its own
    block FIRST, then the persona's own prompt. Order is deliberate -- the
    brief is the team's standing instruction, the persona prompt its role
    within it. No brief means the persona prompt alone, byte for byte.
    """
    brief = (project_brief or "").strip()
    if not brief:
        return persona_prompt
    return f"{BRIEF_HEADING}\n{brief}\n\n{persona_prompt}"

CHOICE_EXCEPTION = (
    "One exception to the format above: when you genuinely cannot continue without the person choosing "
    "between a few concrete options (not a rhetorical question, not something you could decide or look up "
    "yourself), answer with ONLY a choice prompt, in exactly this form and nothing else:\n"
    "<<<OUTPUT:choice>>>\n"
    '{ "question": "one clear question", "options": [ { "id": "short-id", "label": "the option", "hint": "one line of consequence, optional" } ], "multiple": false }\n'
    "<<<END_OUTPUT>>>\n"
    "Two to six options; multiple is true only when more than one may be picked together. "
    "The person's pick comes back as their next message, and you carry on from there."
)


def with_output_instruction(system_content: str, output_type_instruction: str | None) -> str:
    """
    The system prompt with the resolved type's format instruction, plus the one
    standing exception -- a choice prompt when the persona must ask -- for
    every type but a plan or a choice itself. Both prompt paths use this.
    """
    if not output_type_instruction:
        return system_content
    block = output_type_instruction
    if not any(f"<<<OUTPUT:{name}>>>" in output_type_instruction for name in TYPES_WITHOUT_CHOICE):
        block = f"{output_type_instruction}\n\n{CHOICE_EXCEPTION}"
    return f"{system_content}\n\n--- OUTPUT FORMAT INSTRUCTION ---\n{block}"

class NewImprovedPromptBuilder:
    async def build(
        self,
        job: TriggerJob | TriggerSwarmJob,
        persona: PersonaConfig,
        history: list[HistoryMessage],
        output_type_instruction: str | None = None,
    ) -> Sequence[ModelMessage]:
        """
        Assemble messages array.
        Order: system (+ output instruction) → context → history → current message

        persona/history are passed explicitly rather than read off `job`
        (#131) -- job only carries persona_id/topic_id; AgenticManager.run()
        resolves both via nucleus_client before calling this.

        `output_type_instruction` is the resolved spec's system_instruction,
        resolved by the manager (which needs the same spec for render_as) and
        passed in -- never the type's name.
        """
        messages: list[ModelMessage] = []
        context_chunks: list[Chunk] = []
        system_content = persona.system_prompt

        recall_chunks: list[Chunk] = []
        for source in job.context_sources:
            plugin = ContextSourceFactory.get(source.type)
            filter = (
                {"topic_id": source.source_id}
                if source.type == "chat"
                else {"source_id": source.source_id}
            )
            source_chunks = await plugin.retrieve(
                query=job.message,
                collection_id=source.collection_id,
                top_k=settings.RECALL_TOP_K if source.type == "recall" else 5,
                filter=filter,
            )
            # What the team recorded (W5) is its own block, not one more source.
            (recall_chunks if source.type == "recall" else context_chunks).extend(source_chunks)

        system_content = with_output_instruction(system_content, output_type_instruction)

        messages.append(ModelRequest(parts=[SystemPromptPart(content=system_content)]))

        # 2. Context chunks — grouped and labelled by source
        if context_chunks:
            context_text = self._format_chunks(context_chunks)

            messages.append(
                ModelRequest(
                    parts=[
                        UserPromptPart(
                            content=f"[Relevant context from attached sources]\n\n{context_text}"
                        )
                    ]
                )
            )
            # When an output format is active, use a terse ack that doesn't
            # set a conversational tone — otherwise the model echoes it.
            context_ack = (
                "Context noted."
                if output_type_instruction
                else "I've reviewed the provided context. How can I help?"
            )

            messages.append(ModelResponse(parts=[TextPart(content=context_ack)]))

        # 2b. What the team has recorded about the project (W5) -- after the
        #     attached sources, before the conversation, so it reads as
        #     standing knowledge rather than part of this exchange.
        if recall_chunks:
            messages.append(ModelRequest(parts=[UserPromptPart(content=f"[{RECALL_LABEL}]\n\n{self._format_recall(recall_chunks)}")]))
            messages.append(ModelResponse(parts=[TextPart(content="Noted.")]))

        # 3. Conversation history (role: user/assistant only — strip sender_name)
        #    For assistant messages that contain rendered HTML (charts, tables, diagrams),
        #    replace the raw HTML with a short placeholder. Sending full HTML blocks wastes
        #    tokens and confuses the model when asked to make follow-up modifications.
        for msg in history:
            content = self._summarise_rendered(msg.content, msg.role)

            # Tag assistant turns that came from a *different* persona/agent
            # so the model doesn't mistake another agent's reply for its own
            # prior turn (ported from upstream/dev's older design during the
            # #131 merge -- sender_name/persona are resolved params here,
            # not read off `job`, since job no longer carries persona/history).

            if msg.role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif msg.role == "assistant":
                content = (
                    f"[Another Agent: {msg.sender_name}]\n{content}"
                    if getattr(msg, "sender_name", None)
                    and msg.sender_name != persona.name
                    else content
                )
                messages.append(ModelResponse(parts=[TextPart(content=content)]))

        # 4. Current user message
        if job.message:
            messages.append(ModelRequest(parts=[UserPromptPart(content=job.message)]))

        return messages

    def _summarise_rendered(self, content: str, role: str) -> str:
        """
        For assistant history messages that are rendered HTML (charts, tables, diagrams),
        re-wrap up to 2000 chars of the HTML in output markers.

        Two goals:
        1. Show the model its own marker convention so it knows to use markers again.
        2. Give enough HTML context for follow-up modifications ("make bars blue").
        3. Cap at 2000 chars to avoid flooding the context with boilerplate.
        """
        if role != "assistant":
            return content
        stripped = content.strip()
        if not (stripped.startswith("<!DOCTYPE") or stripped.startswith("<html")):
            return content

        MAX_CHARS = 2000
        if len(stripped) <= MAX_CHARS:
            return stripped
        return stripped[:MAX_CHARS] + "\n<!-- ... truncated ... -->"

    def _format_recall(self, chunks: list[Chunk]) -> str:
        """One line per entry: its kind and who recorded it, then the text."""
        lines = []
        for chunk in chunks:
            who = chunk.metadata.get("author_name") or "the team"
            lines.append(f"- ({chunk.metadata.get('kind', 'fact')}, {who}) {chunk.text}")
        return "\n".join(lines)

    def _format_chunks(self, chunks: list[Chunk]) -> str:
        """Format chunks with source labels for clear attribution."""
        parts: list[str] = []
        for chunk in chunks:
            label = chunk.metadata.get("label", "source")
            chunk_type = chunk.metadata.get("type", "")
            language = chunk.metadata.get("language", "")

            if chunk_type == "code" and language:
                parts.append(f"[From {label}]\n```{language}\n{chunk.text}\n```")
            else:
                parts.append(f"[From {label}]\n{chunk.text}")

        return "\n\n---\n\n".join(parts)


class PromptBuilder:
    def build(
        self,
        job: TriggerJob | TriggerSwarmJob,
        persona: PersonaConfig,
        history: list[HistoryMessage],
        context_chunks: list[Chunk],
        output_type_instruction: str | None = None,
        swarm_mode: bool = False,
    ) -> list[dict]:
        """
        Assemble messages array.
        Order: system (+ output instruction) → context → history → current message

        persona/history are passed explicitly rather than read off `job`
        (#131) -- job only carries persona_id/topic_id; AgenticManager.run()
        resolves both via nucleus_client before calling this.
        """
        messages: list[dict] = []

        # 1. System prompt — persona prompt + optional output type instruction
        system_content = persona.system_prompt
        system_content = with_output_instruction(system_content, output_type_instruction)

        if swarm_mode:
            system_content = (
                f"{system_content}\n\n"
                f"--- SWARM ROUTING ---\n"
                f"You are part of a multi-agent swarm. You may transfer this conversation to other specialized agents if their expertise is needed.\n"
                f"- Use 'delegate_task' if you need a prerequisite subtask completed by someone else before you can finish your own work. Control will automatically return to you afterwards.\n"
                f"- Use 'handoff_task' ONLY if you have fully completed your responsibilities and want to permanently pass the baton to the next agent.\n"
                f"- Use 'continue_work' if you are implementing a large system with multiple files. Do NOT use placeholders. Implement the full logic for one file, and then call 'continue_work' to grant yourself another turn to write the next file. CRITICAL: You must write actual code BEFORE calling this tool. Never call it in an empty turn.\n"
                f"CRITICAL: You MUST write a text response explaining your actions and fulfilling your part of the task BEFORE you call a routing tool. Never call a routing tool without providing a text response first.\n"
                f"CRITICAL: If you can fully answer the user's query yourself, or if the task has already been completed, DO NOT use these tools. Simply answer the user directly to end the chain."
            )
        messages.append(
            {
                "role": "system",
                "content": system_content,
            }
        )

        # 2. Context chunks — grouped and labelled by source
        if context_chunks:
            context_text = self._format_chunks(context_chunks)
            messages.append(
                {
                    "role": "user",
                    "content": f"[Relevant context from attached sources]\n\n{context_text}",
                }
            )
            # When an output format is active, use a terse ack that doesn't
            # set a conversational tone — otherwise the model echoes it.
            context_ack = (
                "Context noted."
                if output_type_instruction
                else "I've reviewed the provided context. How can I help?"
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": context_ack,
                }
            )

        # 3. Conversation history (role: user/assistant only — strip sender_name)
        #    For assistant messages that contain rendered HTML (charts, tables, diagrams),
        #    replace the raw HTML with a short placeholder. Sending full HTML blocks wastes
        #    tokens and confuses the model when asked to make follow-up modifications.
        for msg in history:
            content = self._summarise_rendered(msg.content, msg.role)

            # Tag assistant turns that came from a *different* persona/agent
            # so the model doesn't mistake another agent's reply for its own
            # prior turn (ported from upstream/dev's older design during the
            # #131 merge -- sender_name/persona are resolved params here,
            # not read off `job`, since job no longer carries persona/history).
            if (
                msg.role == "assistant"
                and getattr(msg, "sender_name", None)
                and msg.sender_name != persona.name
            ):
                content = f"[Another Agent: {msg.sender_name}]\n{content}"

            messages.append(
                {
                    "role": msg.role,
                    "content": content,
                }
            )

        # 4. Current user message
        if job.message:
            messages.append(
                {
                    "role": "user",
                    "content": job.message,
                }
            )

        return messages

    def _summarise_rendered(self, content: str, role: str) -> str:
        """
        For assistant history messages that are rendered HTML (charts, tables, diagrams),
        re-wrap up to 2000 chars of the HTML in output markers.

        Two goals:
        1. Show the model its own marker convention so it knows to use markers again.
        2. Give enough HTML context for follow-up modifications ("make bars blue").
        3. Cap at 2000 chars to avoid flooding the context with boilerplate.
        """
        if role != "assistant":
            return content
        stripped = content.strip()
        if not (stripped.startswith("<!DOCTYPE") or stripped.startswith("<html")):
            return content

        MAX_CHARS = 2000
        if len(stripped) <= MAX_CHARS:
            return stripped
        return stripped[:MAX_CHARS] + "\n<!-- ... truncated ... -->"

    def _format_chunks(self, chunks: list[Chunk]) -> str:
        """Format chunks with source labels for clear attribution."""
        parts: list[str] = []
        for chunk in chunks:
            label = chunk.metadata.get("label", "source")
            chunk_type = chunk.metadata.get("type", "")
            language = chunk.metadata.get("language", "")

            if chunk_type == "code" and language:
                parts.append(f"[From {label}]\n```{language}\n{chunk.text}\n```")
            else:
                parts.append(f"[From {label}]\n{chunk.text}")

        return "\n\n---\n\n".join(parts)
