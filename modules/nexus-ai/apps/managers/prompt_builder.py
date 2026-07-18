"""
Prompt Builder
--------------
Assembles the final messages array for LiteLLM from:
  - persona system prompt
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
    ) -> list[dict]:
        """
        Assemble messages array.
        Order: system → context → history → current message
        """
        messages: list[dict] = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": job.persona.system_prompt,
        })

        # 2. Context chunks — grouped and labelled by source
        if context_chunks:
            context_text = self._format_chunks(context_chunks)
            messages.append({
                "role": "user",
                "content": f"[Relevant context from attached sources]\n\n{context_text}",
            })
            messages.append({
                "role": "assistant",
                "content": "I've reviewed the provided context. How can I help?",
            })

        # 3. Conversation history (role: user/assistant only — strip sender_name)
        for msg in job.history:
            messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        # 4. Current user message
        messages.append({
            "role": "user",
            "content": job.message,
        })

        return messages

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
