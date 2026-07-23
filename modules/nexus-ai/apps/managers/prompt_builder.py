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

from apps.interfaces.vectorstore import Chunk
from apps.schemas.trigger import TriggerJob


class PromptBuilder:

    def build(
        self,
        job: TriggerJob,
        context_chunks: list[Chunk],
        output_type_instruction: str | None = None,
    ) -> list[dict]:
        """
        Assemble messages array.
        Order: system (+ output instruction) → context → history → current message
        """
        messages: list[dict] = []

        # 1. System prompt — persona prompt + optional output type instruction
        system_content = job.persona.system_prompt
        if output_type_instruction:
            system_content = (
                f"{system_content}\n\n"
                f"--- OUTPUT FORMAT INSTRUCTION ---\n"
                f"{output_type_instruction}"
            )
        messages.append({
            "role": "system",
            "content": system_content,
        })

        # 2. Context chunks — grouped and labelled by source
        if context_chunks:
            context_text = self._format_chunks(context_chunks)
            messages.append({
                "role": "user",
                "content": f"[Relevant context from attached sources]\n\n{context_text}",
            })
            # When an output format is active, use a terse ack that doesn't
            # set a conversational tone — otherwise the model echoes it.
            context_ack = (
                "Context noted."
                if output_type_instruction
                else "I've reviewed the provided context. How can I help?"
            )
            messages.append({
                "role": "assistant",
                "content": context_ack,
            })

        # 3. Conversation history (role: user/assistant only — strip sender_name)
        #    For assistant messages that contain rendered HTML (charts, tables, diagrams),
        #    replace the raw HTML with a short placeholder. Sending full HTML blocks wastes
        #    tokens and confuses the model when asked to make follow-up modifications.
        for msg in job.history:
            messages.append({
                "role": msg.role,
                "content": self._summarise_rendered(msg.content, msg.role),
            })

        # 4. Current user message
        messages.append({
            "role": "user",
            "content": job.message,
        })

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
                parts.append(
                    f"[From {label}]\n```{language}\n{chunk.text}\n```"
                )
            else:
                parts.append(f"[From {label}]\n{chunk.text}")

        return "\n\n---\n\n".join(parts)
