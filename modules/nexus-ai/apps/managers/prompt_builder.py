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
from apps.output_types.classifier import classify_output_type
from apps.schemas.trigger import (
    HistoryMessage,
    PersonaConfig,
    TriggerJob,
    TriggerSwarmJob,
)


class NewImprovedPromptBuilder:
    async def build(
        self,
        job: TriggerJob | TriggerSwarmJob,
        persona: PersonaConfig,
        history: list[HistoryMessage],
    ) -> Sequence[ModelMessage]:
        """
        Assemble messages array.
        Order: system (+ output instruction) → context → history → current message

        persona/history are passed explicitly rather than read off `job`
        (#131) -- job only carries persona_id/topic_id; AgenticManager.run()
        resolves both via nucleus_client before calling this.
        """
        messages: list[ModelMessage] = []
        context_chunks: list[Chunk] = []
        system_content = persona.system_prompt

        try:
            output_type_instruction = await classify_output_type(job.message)
        except Exception:
            output_type_instruction = "text"

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
                top_k=5,
                filter=filter,
            )
            context_chunks.extend(source_chunks)

        if output_type_instruction:
            system_content = (
                f"{system_content}\n\n"
                f"--- OUTPUT FORMAT INSTRUCTION ---\n"
                f"{output_type_instruction}"
            )

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
        if output_type_instruction:
            system_content = (
                f"{system_content}\n\n"
                f"--- OUTPUT FORMAT INSTRUCTION ---\n"
                f"{output_type_instruction}"
            )

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
