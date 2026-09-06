"""
Agentic Manager
---------------
Owns the full agent execution loop:
  TriggerJob → Context Manager → Prompt Builder → AgentRunner → SSE events

M7 additions:
  - Resolve output type (explicit → cosine classifier → "text" default)
  - Inject output type system instruction into prompt
  - Parse <<<OUTPUT:type>>> markers from full response
  - Include output_type + render_as in message_done event

This is the entry point called by the /trigger/ router.
The AgentRunner is injected — swap Pydantic AI for LangGraph here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from apps.interfaces.agent import AgentRunner
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.factories.context_source import ContextSourceFactory
from apps.managers.prompt_builder import PromptBuilder, NewImprovedPromptBuilder
from apps.schemas.trigger import (
    TriggerJob,
    AgentEvent,
    HistoryMessage,
    TriggerSwarmJob,
    AgentEventType,
)
from apps.managers import nucleus_client
from apps.output_types import OutputTypeRegistry
from apps.output_types.markers import parse_output_markers

logger = logging.getLogger(__name__)


class NewImprovedAgenticManager:
    def __init__(
        self,
        runner: AgentRunner,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self.runner = runner
        self.embedder = embedder
        self.store = store
        self.prompt_builder = NewImprovedPromptBuilder()

    async def run(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        persona = await nucleus_client.resolve_persona(job.persona_id)

        history = await nucleus_client.fetch_history(
            topic_id=job.topic_id, exclude_message_id=job.user_message_id
        )

        messages = await self.prompt_builder.build(
            job=job, persona=persona, history=history
        )

        # Signal the start to the frontend
        yield AgentEvent(
            type=AgentEventType.START,
            id=job.msg_id,
        )

        accrued_text: list[str] = []
        async for event in self.runner.run_stream(job, messages, persona):
            match event.type:

                # Accrue streamed text
                case AgentEventType.DELTA.value:
                    accrued_text.append(event.delta)  # type: ignore

                # Persist the model's intneral state when all is said and done
                case AgentEventType.PERSIST.value:
                    internal_model_state = event.metadata.get('internal_model_state') #type: ignore
                    continue

            yield event

        full_response_content = "".join(accrued_text)
        clean_content = full_response_content
        render_as = "text"
        embed_description = None
        if full_response_content:
            # TODO fix this code!!!
            clean_content, marker_type, embed_description = parse_output_markers(
                full_response_content
            )
            final_spec = OutputTypeRegistry.get(marker_type)
            render_as = getattr(final_spec, "render_as", None) or "text"
            embed_description = None if render_as == "text" else embed_description

        # Signal the end to the frontend
        yield AgentEvent(
            type=AgentEventType.END,
            id=job.msg_id,
            content=clean_content,
            render_as=render_as,
            embed_description=embed_description,
        )

    async def swarm(self, job: TriggerSwarmJob) -> AsyncIterator[AgentEvent]: ...


class AgenticManager:
    def __init__(
        self,
        runner: AgentRunner,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self.runner = runner
        self.embedder = embedder
        self.store = store
        self.prompt_builder = PromptBuilder()

    async def run(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        """
        Full pipeline: resolve persona + history → resolve output type →
                       retrieve context → build prompt → run agent → yield events.
        """
        # 0. Resolve persona config + conversation history ourselves (#131) --
        #    job only carries persona_id/topic_id/user_message_id. This is
        #    where prompt-quality decisions (how much history, which past
        #    replies are worth showing the model) live now, not nexus-nucleus.
        persona = await nucleus_client.resolve_persona(job.persona_id)
        history = await nucleus_client.fetch_history(
            job.topic_id,
            exclude_message_id=job.user_message_id,
        )

        # 1. Resolve output type
        resolved_type = await self._resolve_output_type(job)

        # 2. Get output type spec (system instruction + render_as)
        spec = OutputTypeRegistry.get(resolved_type)
        output_instruction = spec.system_instruction if spec else None
        render_as = spec.render_as if spec else "text"

        # 3. Retrieve relevant context chunks
        chunks: list[Chunk] = []
        for source in job.context_sources:
            try:
                plugin = ContextSourceFactory.get(source.type)
                filter_dict = (
                    {"topic_id": source.source_id}
                    if source.type == "chat"
                    else {"source_id": source.source_id}
                )
                source_chunks = await plugin.retrieve(
                    query=job.message,
                    collection_id=source.collection_id,
                    top_k=5,
                    filter=filter_dict,
                )
                chunks.extend(source_chunks)
            except Exception as exc:
                logger.warning(
                    "[agentic] context retrieval failed for source %s (%s): %s",
                    source.source_id,
                    source.type,
                    exc,
                )

        # 4. Build the messages array
        messages = self.prompt_builder.build(
            job=job,
            persona=persona,
            history=history,
            context_chunks=chunks,
            output_type_instruction=output_instruction,
        )

        # 5. Yield message_start immediately
        yield AgentEvent(
            type=AgentEventType.START,
            id=job.msg_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 6. Stream from agent runner (raw — may contain markers)
        full_content: list[str] = []
        async for event in self.runner.run_stream(job, messages, persona):
            if event.type == "message_delta" and event.delta:
                full_content.append(event.delta)
            yield event

        # 7. Parse output markers from the full assembled response
        raw_full = "".join(full_content)
        clean_content, marker_type, embed_description = parse_output_markers(raw_full)

        # Marker type overrides the resolved type if present
        if marker_type and OutputTypeRegistry.get(marker_type):
            # Markers found — use the matched spec's renderer
            final_type = marker_type
            final_spec = OutputTypeRegistry.get(marker_type)
            final_render_as = final_spec.render_as if final_spec else render_as
        else:
            # No markers — the model chose to respond in plain text.
            # Always render as text regardless of the resolved output type,
            # so a conversational reply doesn't end up in a chart/html box.
            final_type = resolved_type
            final_render_as = "text"
            clean_content = raw_full
            embed_description = None  # plain text embeds as-is, no description needed

        # 8. Yield message_done with clean content + type metadata + embed description
        yield AgentEvent(
            type=AgentEventType.END,
            id=job.msg_id,
            content=clean_content,
            output_type=final_type,
            render_as=final_render_as,
            embed_description=embed_description,  # M8: None for text/code, set for html/form/terminal
        )

    async def _resolve_output_type(self, job: TriggerJob) -> str:
        """
        Resolve the output type for this job.

        Priority:
        1. Explicit type from job (set by nexus-nucleus via @mention)
        2. Cosine similarity classification (when output_type == "auto")
        3. "text" default
        """
        from apps.output_types import OutputTypeRegistry

        explicit = job.output_type

        if explicit and explicit != "auto":
            if OutputTypeRegistry.get(explicit):
                logger.debug("[agentic] output type explicit: %s", explicit)
                return explicit
            logger.warning(
                "[agentic] unknown explicit output type %r — falling back to auto",
                explicit,
            )

        # Auto-classify
        try:
            from apps.output_types.classifier import classify_output_type

            detected = await classify_output_type(job.message)
            logger.debug("[agentic] output type classified: %s", detected)
            return detected
        except Exception as exc:
            logger.warning("[agentic] classifier failed: %s", exc)
            return "text"


class AgenticSwarmManager:
    def __init__(
        self,
        runner: AgentRunner,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self.runner = runner
        self.embedder = embedder
        self.store = store
        self.prompt_builder = PromptBuilder()

    async def _resolve_output_type(self, job: TriggerSwarmJob) -> str:
        """
        Resolve the output type for this job.
        """
        from apps.output_types import OutputTypeRegistry

        explicit = job.output_type

        if explicit and explicit != "auto":
            if OutputTypeRegistry.get(explicit):
                logger.debug("[agentic] swarm output type explicit: %s", explicit)
                return explicit
            logger.warning(
                "[agentic] unknown explicit output type %r — falling back to auto",
                explicit,
            )

        # Auto-classify
        try:
            from apps.output_types.classifier import classify_output_type

            detected = await classify_output_type(job.message)
            logger.debug("[agentic] swarm output type classified: %s", detected)
            return detected
        except Exception as exc:
            logger.warning("[agentic] classifier failed: %s", exc)
            return "text"

    async def run(self, job: TriggerSwarmJob) -> AsyncIterator[AgentEvent]:
        history = await nucleus_client.fetch_history(
            job.topic_id,
            exclude_message_id=job.user_message_id,
        )

        history.append(HistoryMessage(role="user", content=job.message))

        # The first mentioned persona takes precedent
        active_persona_id = job.personas[0][0]
        resolved_type = await self._resolve_output_type(job)
        spec = OutputTypeRegistry.get(resolved_type)
        output_instruction = spec.system_instruction if spec else None
        render_as = spec.render_as if spec else "text"

        chunks = []

        for source in job.context_sources:
            try:
                plugin = ContextSourceFactory.get(source.type)
                filter_dict = (
                    {"topic_id": source.source_id}
                    if source.type == "chat"
                    else {"source_id": source.source_id}
                )
                source_chunks = await plugin.retrieve(
                    query=job.message,
                    collection_id=source.collection_id,
                    top_k=5,
                    filter=filter_dict,
                )
                chunks.extend(source_chunks)
            except Exception as exc:
                logger.warning(
                    "[agentic] context retrieval failed for source %s (%s): %s",
                    source.source_id,
                    source.type,
                    exc,
                )

        import uuid

        stack = [active_persona_id]
        hops = 0
        MAX_HOPS = 7
        is_first_hop = True

        while hops < MAX_HOPS:
            handoff_triggered = False
            delegation_triggered = False
            continue_triggered = False

            if is_first_hop:
                current_sub_msg_id = job.msg_id
                is_first_hop = False
            else:
                current_sub_msg_id = str(uuid.uuid4())

            persona = await nucleus_client.resolve_persona(active_persona_id)

            yield AgentEvent(
                type=AgentEventType.START,
                id=current_sub_msg_id,
                persona_id=active_persona_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            is_delegated = len(stack) > 1
            injected_tools = (
                []
                if is_delegated
                else self.build_tools(job.personas, active_persona_id)
            )

            # Phase 3: Targeted Prompting
            # Pass the instruction to all agents, but if they have routing tools,
            # explicitly warn them to only apply formatting if they are answering the user directly.
            current_output_instruction = output_instruction
            if output_instruction and injected_tools:
                current_output_instruction = (
                    f"{output_instruction}\n\n"
                    "CRITICAL: ONLY apply the formatting above if you are providing the FINAL direct answer to the user. "
                    "If your next action is to call a tool (like handoff_task or delegate_task), IGNORE the formatting above and do not output any markers."
                )

            # Create a shallow copy of job with empty message so it doesn't get
            # repeatedly appended to the bottom of the prompt on every hop.
            job_for_prompt = (
                job.model_copy(update={"message": ""})
                if hasattr(job, "model_copy")
                else job.copy(update={"message": ""})
            )

            messages = self.prompt_builder.build(
                job=job_for_prompt,
                persona=persona,
                history=history,
                context_chunks=chunks,
                output_type_instruction=current_output_instruction,
                swarm_mode=True,
            )

            agent_response_content = []

            async for event in self.runner.run_stream(
                job=job,
                messages=messages,
                persona=persona,
                tools=injected_tools,
            ):
                event.id = current_sub_msg_id

                if event.type == "message_delta" and event.delta:
                    agent_response_content.append(event.delta)

                yield event

                if (
                    event.type == "tool_call_start"
                    and event.tool_call.name == "handoff_task"
                ):
                    target_name = event.tool_call.args.get("target_persona")
                    instructions = event.tool_call.args.get("instructions")
                    reasoning = event.tool_call.args.get("reasoning")
                    target_id = next(
                        (p[0] for p in job.personas if p[1] == target_name), None
                    )

                    if not target_id:
                        break

                    handoff_text = f"Handing off to @{target_name}..."
                    if reasoning:
                        handoff_text += f"\n\n*Reasoning:* {reasoning}"

                    yield AgentEvent(
                        type=AgentEventType.SWARM_TRANSITION,
                        id=current_sub_msg_id,
                        content=handoff_text,
                        metadata={
                            "transition_type": "handoff",
                            "from_persona": persona.name,
                            "to_persona": target_name,
                        },
                    )

                    stack[-1] = target_id
                    active_persona_id = target_id
                    handoff_triggered = True
                    break

                if (
                    event.type == "tool_call_start"
                    and event.tool_call.name == "delegate_task"
                ):
                    target_name = event.tool_call.args.get("target_persona")
                    instructions = event.tool_call.args.get("instructions")
                    reasoning = event.tool_call.args.get("reasoning")
                    target_id = next(
                        (p[0] for p in job.personas if p[1] == target_name), None
                    )

                    if not target_id:
                        break

                    delegate_text = f"Delegating task to @{target_name}..."
                    if reasoning:
                        delegate_text += f"\n\n*Reasoning:* {reasoning}"

                    yield AgentEvent(
                        type=AgentEventType.SWARM_TRANSITION,
                        id=current_sub_msg_id,
                        content=delegate_text,
                        metadata={
                            "transition_type": "delegation",
                            "from_persona": persona.name,
                            "to_persona": target_name,
                        },
                    )

                    stack.append(target_id)
                    active_persona_id = target_id
                    delegation_triggered = True
                    break

                if (
                    event.type == "tool_call_start"
                    and event.tool_call.name == "continue_work"
                ):
                    reasoning = event.tool_call.args.get("reasoning")
                    continue_text = "Continuing work on next steps..."
                    if reasoning:
                        continue_text += f"\n\n*Reasoning:* {reasoning}"

                    yield AgentEvent(
                        type=AgentEventType.SWARM_TRANSITION,
                        id=current_sub_msg_id,
                        content=continue_text,
                        metadata={
                            "transition_type": "continue",
                            "from_persona": persona.name,
                            "to_persona": persona.name,
                        },
                    )

                    continue_triggered = True
                    break

            raw_hop = "".join(agent_response_content)
            clean_hop, marker_type, embed_description = parse_output_markers(raw_hop)

            if marker_type and OutputTypeRegistry.get(marker_type):
                final_type = marker_type
                final_spec = OutputTypeRegistry.get(marker_type)
                final_render_as = final_spec.render_as if final_spec else render_as
            else:
                final_type = resolved_type
                final_render_as = "text"
                clean_hop = raw_hop
                embed_description = None

            yield AgentEvent(
                type=AgentEventType.END,
                id=current_sub_msg_id,
                content=clean_hop,
                output_type=final_type,
                render_as=final_render_as,
                embed_description=embed_description,
            )

            if agent_response_content:
                history.append(
                    HistoryMessage(
                        role="assistant",
                        content="".join(agent_response_content),
                        sender_name=persona.name,
                    )
                )

            if handoff_triggered:
                hist_content = f"[Handed off task to @{target_name} with instructions: {instructions}]"
                if reasoning:
                    hist_content += f"\nReasoning: {reasoning}"
                history.append(
                    HistoryMessage(
                        role="assistant", content=hist_content, sender_name=persona.name
                    )
                )
                history.append(
                    HistoryMessage(
                        role="user",
                        content=f"You have been handed this task from @{persona.name}. Here are your instructions: {instructions}",
                    )
                )
                hops += 1
                continue

            if delegation_triggered:
                hist_content = f"[Delegated task to @{target_name} with instructions: {instructions}]"
                if reasoning:
                    hist_content += f"\nReasoning: {reasoning}"
                history.append(
                    HistoryMessage(
                        role="assistant", content=hist_content, sender_name=persona.name
                    )
                )
                history.append(
                    HistoryMessage(
                        role="user",
                        content=f"You have been temporarily delegated this task from @{persona.name}. Here are your instructions: {instructions}",
                    )
                )
                hops += 1
                continue

            if continue_triggered:
                hist_content = "[Called continue_work to proceed with next steps]"
                if reasoning:
                    hist_content += f"\nReasoning: {reasoning}"
                history.append(
                    HistoryMessage(
                        role="assistant", content=hist_content, sender_name=persona.name
                    )
                )
                history.append(
                    HistoryMessage(
                        role="user",
                        content="You have been granted another turn. Please output the actual code/work for the next step now. CRITICAL: Do NOT call continue_work again until you have completed a substantial portion of the work in this turn.",
                    )
                )
                hops += 1
                continue

            if (
                not handoff_triggered
                and not delegation_triggered
                and not continue_triggered
            ):
                if len(stack) > 1:
                    stack.pop()
                    active_persona_id = stack[-1]

                    target_name = next(
                        (p[1] for p in job.personas if p[0] == active_persona_id),
                        "parent",
                    )
                    return_text = f"Returning control to @{target_name}..."
                    yield AgentEvent(
                        type=AgentEventType.SWARM_TRANSITION,
                        id=current_sub_msg_id,
                        content=return_text,
                        metadata={
                            "transition_type": "return_control",
                            "from_persona": persona.name,
                            "to_persona": target_name,
                        },
                    )

                    history.append(
                        HistoryMessage(
                            role="user",
                            content=f"The delegated task to @{persona.name} has been completed. You are back in control. Please continue fulfilling the user's original request if there are remaining steps.",
                        )
                    )
                    hops += 1
                    continue
                else:
                    break

        if hops >= MAX_HOPS:
            limit_msg = (
                f"\n\n*Swarm stopped: Maximum number of handoffs ({MAX_HOPS}) reached.*"
            )
            error_msg_id = str(uuid.uuid4())
            yield AgentEvent(
                type=AgentEventType.START,
                id=error_msg_id,
                persona_id=active_persona_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            yield AgentEvent(
                type=AgentEventType.DELTA, id=error_msg_id, delta=limit_msg
            )
            yield AgentEvent(
                type=AgentEventType.END,
                id=error_msg_id,
                content=limit_msg,
                output_type="text",
                render_as="text",
                embed_description=None,
            )

    def build_handoff_tool(self, names: list, descriptions: str) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "handoff_task",
                "description": f"Transfer control to a specialized persona.\n {descriptions}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": "Explain why you are handing off, what you have accomplished so far, and why the target persona is best suited for the remaining work.",
                        },
                        "target_persona": {
                            "type": "string",
                            "enum": names,
                        },
                        "instructions": {
                            "type": "string",
                            "description": "What the next persona/agent needs to do",
                        },
                    },
                    "required": ["reasoning", "target_persona", "instructions"],
                },
            },
        }

    def build_continue_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "continue_work",
                "description": "Use this tool to grant yourself another consecutive conversational turn without waiting for the user. Essential for breaking down large tasks (like writing multiple files) into manageable steps.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": "Explain what you have accomplished in this turn and what you will do in the next turn.",
                        }
                    },
                    "required": ["reasoning"],
                },
            },
        }

    def build_delegate_tool(self, names: list, descriptions: str) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "delegate_task",
                "description": f"Delegate task to a specialized persona, and take back control once done\n {descriptions}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": "Explain why you are delegating this subtask, and what you will do once control is returned to you.",
                        },
                        "target_persona": {
                            "type": "string",
                            "enum": names,
                        },
                        "instructions": {
                            "type": "string",
                            "description": "What the next persona/agent needs to do, before returning control",
                        },
                    },
                    "required": ["reasoning", "target_persona", "instructions"],
                },
            },
        }

    def build_tools(
        self, personas: list[list[str]], active_persona_id: str
    ) -> list[dict]:
        names = [persona[1] for persona in personas if persona[0] != active_persona_id]
        descriptions = "\n".join(
            [
                f"- {persona[1]}:{persona[2]}"
                for persona in personas
                if persona[0] != active_persona_id
            ]
        )
        handoff_tool = self.build_handoff_tool(names, descriptions)
        delegate_tool = self.build_delegate_tool(names, descriptions)
        continue_tool = self.build_continue_tool()

        return [handoff_tool, delegate_tool, continue_tool]
