"""
AISystem (the interface), AISystemFactory, PydanticAISystem.

One interface for now (O4): respond(job) → stream of AgentEvent. A later
system (e.g. Claude Agent SDK, item 18) implements the same interface and the
factory chooses.

PydanticAISystem runs the steps of one reply (§1.5 Layer 0 sequence) and
records usage on EVERY ending — done, pause, stop, failure:
  - done   → record usage, then message_done with the full text and usage
  - paused → (item 2) record usage, POST the pause state to nucleus, then
             message_paused — NEVER message_done; the state must land before
             the event so a decision can't race an unsaved pause
  - cancel → the run is cancelled by the disconnect; usage is recorded
             (estimated) under a shield; no event can be sent
  - error  → usage recorded, the exception propagates and EventStream turns
             it into exactly one message_error
message_done is yielded on the normal path, never from a finally block —
yielding while a generator is being closed raises RuntimeError.
record_usage failure is logged and never turns a good reply into an error.

Resume (item 2): a TriggerJob with a `resume` block rebuilds the same agent
(same persona → same tools, by construction) and continues from the stored
messages with the decisions; the rest of the reply streams as normal and ends
in message_done (or pauses again on the next ask-tool).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol

from ai_engine.context.budget import BudgetFitter, budget_for
from ai_engine.context.context_builder import ContextBuilder
from ai_engine.context.history_policy import HistoryPolicy
from ai_engine.core.config import EngineSettings
from ai_engine.core.nucleus_client import NucleusClient
from ai_engine.core.turn_rules import (
    acts_with_tools,
    approved_plan_section,
    step_context_section,
)
from ai_engine.output_types import finalise_reply, resolve_output_spec
from ai_engine.output_types.prompting import output_instruction_block
from ai_engine.output_types.registry import OutputTypeRegistry
from ai_engine.core.specs import (
    LoadedSet,
    ModelRole,
    PersonaSpec,
    PromptSection,
    ReplyRequest,
    SearchHit,
    SearchQuery,
)
from ai_engine.prompts.layout import PromptLayout
from ai_engine.prompts.templates import PromptTemplates
from ai_engine.pydantic_ai_system.agent_builder import AgentBuilder
from ai_engine.pydantic_ai_system.escalation import pick_deep_model
from ai_engine.pydantic_ai_system.message_converter import MessageConverter
from ai_engine.pydantic_ai_system.model_factory import ModelFactory
from ai_engine.pydantic_ai_system.reply_generator import ReplyGenerator
from ai_engine.pydantic_ai_system.tools.call_persona import call_persona_toolset
from ai_engine.pydantic_ai_system.tools.nudge_gate import NudgeGate
from ai_engine.pydantic_ai_system.tools.registry import ToolRegistry
from ai_engine.pydantic_ai_system.tools.toolset_builder import ToolsetBuilder
from ai_engine.pydantic_ai_system.usage_reader import UsageReader, estimate_tokens
from ai_engine.vector_db.store import VectorStore
from fastapi_app.contracts.trigger import (
    AgentEvent,
    AgentEventType,
    RetrievedRef,
    TriggerJob,
)

log = logging.getLogger(__name__)


class AISystem(Protocol):
    def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]: ...


class AISystemFactory:
    @staticmethod
    def create(kind: str) -> AISystem:
        """Return the AI system to use — "pydantic_ai" only in Layer 0.
        Builds a fresh object graph per call: a run holds per-run state."""
        if kind != "pydantic_ai":
            raise ValueError(f"unknown AI system kind: {kind!r}")
        settings = EngineSettings()
        nucleus = NucleusClient(
            settings.nucleus_url, settings.internal_key,
            timeout_seconds=settings.nucleus_timeout_seconds,
        )
        # Layer 3: retrieval is ON only when the vector DB is configured —
        # the same lazy store the embed endpoints use (one store per process).
        from ai_engine.vector_db import get_store
        store = get_store()
        return PydanticAISystem(
            nucleus=nucleus,
            context=ContextBuilder(nucleus, HistoryPolicy(settings.history_depth)),
            layout=PromptLayout(PromptTemplates()),
            generator=ReplyGenerator(
                AgentBuilder(ModelFactory()), MessageConverter(), UsageReader(),
                fitter=BudgetFitter(estimate_tokens),  # item 16: selection
                settings=settings,
            ),
            registry=ToolRegistry(max_loaded_tools=settings.max_loaded_tools),
            toolsets=ToolsetBuilder(),
            settings=settings,
            store=store,
        )


class PydanticAISystem:
    def __init__(self, nucleus: NucleusClient, context: ContextBuilder,
                 layout: PromptLayout, generator: ReplyGenerator,
                 registry: ToolRegistry | None = None,
                 toolsets: ToolsetBuilder | None = None,
                 settings: EngineSettings | None = None,
                 store: VectorStore | None = None) -> None:
        self._nucleus = nucleus
        self._context = context
        self._layout = layout
        self._generator = generator
        self._registry = registry or ToolRegistry()
        self._toolsets = toolsets or ToolsetBuilder()
        self._settings = settings or EngineSettings()
        self._store = store  # Layer 3: None = retrieval off

    async def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(
            type=AgentEventType.START,
            id=job.msg_id,
            persona_id=job.persona_id,
            created_at=_now(),
        )
        persona: PersonaSpec | None = None
        answered_by: str | None = None
        reply_role = ModelRole.STANDARD
        loaded_for_done: tuple[str, ...] | None = None
        retrieved_refs: list[RetrievedRef] = []
        try:
            persona = await self._nucleus.get_persona(job.persona_id, job.company_id, job.project_id)
            bundle = await self._context.gather(job, persona)
            # Layer 1 (items 3+1): catalog → loaded set → capability objects.
            catalog = self._registry.catalog_for(persona)
            loaded = self._registry.tools_for(persona, job)
            clearances = frozenset(job.topic_tool_clearances or ())

            # ── Layer 6 (preflight, legacy plan_turn ported): a gated
            # persona's turn that WOULD act proposes first — one turn with no
            # capability tools, answered as the preflight output type. The
            # engine owns the acts-at-all judgement; nucleus only flags.
            preflight_turn = (bool(job.preflight) and not job.approved_plan
                              and acts_with_tools(catalog))
            if preflight_turn:
                catalog = []
                loaded = LoadedSet(tool_ids=(), catalog_hash=loaded.catalog_hash)

            # Item 46 (Layer 6): delegation — only at depth 0, never on a
            # plan-only preflight turn (a proposal must not act or delegate).
            delegate = (call_persona_toolset(job, self._settings)
                        if persona.delegation_enabled and job.delegation_depth == 0
                        and not preflight_turn else None)

            # W8: only a run someone can steer polls for nudges; the gate only
            # fires after tool calls, so it rides with the capabilities.
            nudge_gate = (NudgeGate(job.msg_id,
                                    poll=lambda: self._nucleus.get_nudges(job.msg_id))
                          if job.interactive else None)

            def build_caps(loaded_set, role: ModelRole, run_spec=None):
                if not catalog:
                    return []
                # item 16: mid-run growth is COMPACTION's job — tiers 1→2→3
                # with the run model's budget target (§4.1's one-line far-end fix)
                # run_spec: the smart router's bench pick on a DEEP run — the
                # budget follows the model that actually runs, not the seat's first.
                spec = run_spec or persona.model_for(role)
                # 7b (2026-10-20): the run model's OWN output cap, per spec.
                target = budget_for(
                    spec, self._settings.budget_loop_headroom,
                    self._settings.budget_target_pct, self._settings.budget_trigger_pct,
                    spec.max_output_tokens,
                ).target
                caps = self._toolsets.build(loaded_set, catalog, persona,
                                            interactive=job.interactive, clearances=clearances,
                                            compaction_target=target)
                if caps and nudge_gate is not None:
                    caps = list(caps) + [nudge_gate]
                return caps

            plan = self._layout.build(persona, bundle, job.message, catalog=catalog)

            # ── Layer 6 (W6 + preflight): the approved plan rides PROTECTED;
            # a runbook step's previous output rides clipped (turn_rules).
            extra_sections = tuple(section for section in (
                approved_plan_section(job.approved_plan),
                step_context_section(job.step_context,
                                     self._settings.runbook_step_context_max),
            ) if section is not None)
            if extra_sections:
                plan = dc_replace(plan, instructions=plan.instructions + extra_sections)

            # ── item 23 (Layer 4): what the reply should LOOK like ──────────
            # explicit non-auto from the trigger wins; else the classifier;
            # else text. The chosen type's contract rides as its own section.
            # A preflight turn is ALWAYS the preflight type (Layer 6).
            if preflight_turn:
                resolved_type, resolved_spec = "preflight", OutputTypeRegistry.get("preflight")
            else:
                resolved_type, resolved_spec = await resolve_output_spec(
                    job.output_type, job.message, bundle.history)
            block = output_instruction_block(
                resolved_spec.system_instruction if resolved_spec else None)
            if block:
                plan = dc_replace(plan, instructions=plan.instructions + (
                    PromptSection(kind="output_format", priority=85, stable=False,
                                  text=block),
                ))

            # ── Layer 3 (items 24/44/33, decisions 9+10): project memory ────
            # Always-search v1: the threshold throws away weak hits ("it will
            # find and if found something its ok, otherwise db is empty for
            # it"). A resume skips it — the stored state already carries the
            # context the paused run saw. Retrieval failure never breaks a
            # reply. The refs ride to message_done as retrieved_sources.
            if self._store is not None and job.resume is None:
                hits: list[SearchHit] = []
                try:
                    hits = await asyncio.to_thread(self._retrieve, job)
                except Exception:  # noqa: BLE001 — memory is a bonus, never a blocker
                    log.exception("retrieval failed for job %s — replying without memory", job.job_id)
                if hits:
                    retrieved_refs = [
                        RetrievedRef(id=h.id, kind=h.kind, label=h.label,
                                     score=round(h.score, 4), topic_id=h.topic_id)
                        for h in hits
                    ]
                    plan = dc_replace(plan, instructions=plan.instructions + (
                        PromptSection(kind="retrieved", priority=50, stable=False,
                                      text=_retrieved_section(hits)),
                    ))
                    yield AgentEvent(
                        type=AgentEventType.CONTEXT_RETRIEVED,
                        id=job.msg_id, persona_id=persona.id, persona_name=persona.name,
                        created_at=_now(),
                        retrieved=retrieved_refs, count=len(retrieved_refs),
                    )

            # ── items 13/46: the routing stage ──────────────────────────────
            router_spec = persona.model_for_or_none(ModelRole.ROUTER)
            if resolved_type != "text":
                # Layer 4 design point 1: a TYPED turn (chart, html, …) needs
                # the type's contract and a capable model — the cheap router
                # screen applies to plain-text turns only.
                router_spec = None
            deep_spec = persona.model_for_or_none(ModelRole.DEEP)
            escalation_on = job.resume is None and (router_spec or deep_spec) is not None
            escalate = None
            reply_done = False  # a run that IS the reply already streamed

            if job.resume is not None:
                # resume on the SAME seat the run paused on (item 13)
                try:
                    reply_role = ModelRole(job.resume.role)
                    persona.model_for(reply_role)
                except (ValueError, LookupError):
                    reply_role = ModelRole.STANDARD

            if escalation_on and router_spec is not None:
                # Case A — a cheap router screens first: NO tools (it hints,
                # it doesn't act — deliberate narrowing, see doc), hard timeout,
                # and any failure falls through, never blocks the reply.
                request = ReplyRequest(job=job, persona=persona, role=ModelRole.ROUTER, plan=plan)
                try:
                    async with asyncio.timeout(self._settings.router_timeout_seconds):
                        async for event in self._generator.generate(
                            request, capabilities=[], allow_escalation=True,
                            allow_ask=False,  # item 5: the screen hints, it never asks
                        ):
                            yield event
                    escalate = self._generator.escalation()
                except asyncio.CancelledError:
                    raise  # the person disconnected — not a router failure
                except (TimeoutError, Exception):  # noqa: BLE001 — item 13 fall-through
                    log.warning("router failed for job %s — falling through to STANDARD", job.job_id)
                    self._generator.set_source_on_last_run("router_failed")
                    escalate = None
                    router_spec = None  # fall through below as if no router answered
                    escalation_on = False
                else:
                    if escalate is None:
                        # the router's text IS the reply — done below
                        reply_role = ModelRole.ROUTER
                        reply_done = True
            elif escalation_on:
                # Case B — no router seat, but a DEEP seat exists: STANDARD
                # runs normally (full tools) and may hand over while trying.
                reply_role = ModelRole.STANDARD
                request = ReplyRequest(job=job, persona=persona, role=reply_role, plan=plan)
                loaded_for_done = loaded.tool_ids
                async for event in self._generator.generate(
                    request, capabilities=build_caps(loaded, reply_role),
                    catalog_hash=loaded.catalog_hash, allow_escalation=True,
                    nudges=nudge_gate, delegate=delegate,
                ):
                    yield event
                escalate = self._generator.escalation()
                reply_done = escalate is None  # it answered (or paused) itself

            deep_pick = None
            if escalate is not None:
                # ── the hand-over (trial G): a second ordinary run ──────────
                # Smart router: the DEEP seat is a BENCH — the run goes to the
                # model the router NAMED (Escalate.target_model); an invalid or
                # missing pick is the bench's first. No bench → STANDARD.
                # Three-way routing (ruled 2026-10-21): lane 'standard' sends
                # the work to the persona's everyday model instead. Only the
                # ROUTER may choose that lane — a STANDARD run that escalated
                # (case B) IS that model, so its lane is forced deep rather
                # than handing the work back to itself.
                lane = (getattr(escalate, "lane", "deep") or "deep").strip().lower() \
                    if router_spec is not None else "deep"
                deep_pick = (None if lane == "standard"
                             else pick_deep_model(escalate, persona.models_for(ModelRole.DEEP)))
                reply_role = ModelRole.DEEP if deep_pick is not None else ModelRole.STANDARD
                answered_by = (deep_pick or persona.model_for(ModelRole.STANDARD)).name
                yield AgentEvent(
                    type=AgentEventType.ESCALATION,
                    id=job.msg_id, persona_id=persona.id, persona_name=persona.name,
                    created_at=_now(), escalated_to=answered_by,
                )
                # first reply in the topic: the router's tool_hints become the set
                if job.topic_tools is None and escalate.tool_hints:
                    eligible = {entry.tool_id for entry in catalog}
                    hinted = tuple(t for t in escalate.tool_hints if t in eligible)
                    if hinted:
                        loaded = LoadedSet(tool_ids=hinted, catalog_hash=loaded.catalog_hash)
                loaded_for_done = loaded.tool_ids
                request = ReplyRequest(job=job, persona=persona, role=reply_role, plan=plan)
                async for event in self._generator.generate(
                    request, capabilities=build_caps(loaded, reply_role, deep_pick),
                    catalog_hash=loaded.catalog_hash, handover=escalate,
                    nudges=nudge_gate, delegate=delegate, primary=deep_pick,
                ):
                    yield event
            elif not reply_done:
                # the plain path: no routing stage produced the reply (no
                # seats, a resume, or the router failed) — Layer 0/1, one run.
                request = ReplyRequest(job=job, persona=persona, role=reply_role, plan=plan)
                loaded_for_done = loaded.tool_ids
                async for event in self._generator.generate(
                    request, capabilities=build_caps(loaded, reply_role),
                    resume=job.resume, catalog_hash=loaded.catalog_hash,
                    nudges=nudge_gate, delegate=delegate,
                ):
                    yield event
        except asyncio.CancelledError:
            # The person (or nucleus) stopped the run: no event can be sent any
            # more, but the partial usage must still land. Shield the write so
            # the cancellation doesn't take it down with the run.
            await self._record_usage(shielded=True)
            raise
        except Exception:
            await self._record_usage()
            raise  # EventStream turns this into exactly one message_error
        else:
            await self._record_usage()
            pause = self._generator.pause_info()
            used = self._generator.used_tools()
            if pause is not None:
                # Item 2: the paused run. State FIRST (a decision must never
                # race an unsaved pause), then the final event. A failed save
                # is a real error — resuming would be impossible.
                await self._nucleus.save_pause(
                    job.msg_id, job.job_id, job.topic_id, job.persona_id, pause,
                    role=reply_role.value,
                )
                yield AgentEvent(
                    type=AgentEventType.PAUSED,
                    id=job.msg_id,
                    persona_id=persona.id,
                    persona_name=persona.name,
                    created_at=_now(),
                    loaded_tools=list(loaded_for_done) if loaded_for_done is not None else None,
                    used_tools=used or None,
                )
                return
            fallback = self._generator.fallback_used()
            if fallback is not None:
                # item 12: the reply came from a backup model — say so plainly
                answered_by = f"{fallback.name} (fallback)"
            records = self._generator.usage_records()
            last = records[-1] if records else None
            # item 23: markers → clean content + validated type; an unmarked
            # chart the run asked for is recovered; a broken claim falls back
            # to text (decision 2). The embed description is for item 44.
            raw = self._generator.full_text()
            clean, final_type, final_render, embed_description = finalise_reply(
                raw, resolved_type)
            if final_type == "text" and clean == raw.strip():
                # no markers, nothing recovered: the saved content stays BYTE-
                # IDENTICAL to the streamed deltas (T1's contract) — parsing
                # must never trim a plain reply.
                clean = raw
            yield AgentEvent(
                type=AgentEventType.END,
                id=job.msg_id,
                persona_id=persona.id,
                persona_name=persona.name,
                created_at=_now(),
                content=clean,
                output_type=final_type,
                render_as=final_render,
                embed_description=embed_description,
                answered_by_model=answered_by,
                prompt_tokens=last.input_tokens if last else None,
                output_tokens=last.output_tokens if last else None,
                # Smart router: on a bench hand-over the window is the PICKED
                # model's, which need not be the seat's first.
                context_window=(
                    deep_pick.context_window if deep_pick is not None and reply_role is ModelRole.DEEP
                    else persona.model_for(
                        reply_role if persona.model_for_or_none(reply_role) else ModelRole.STANDARD
                    ).context_window
                ),
                # items 13 + Layer 3 bridge: the topic's cache courier + what ran
                loaded_tools=list(loaded_for_done) if loaded_for_done is not None else None,
                used_tools=used or None,
                retrieved_sources=retrieved_refs or None,  # decision 10, second half
            )
            # ── item 27 (decision 8): the memory pass — AFTER the final event,
            # fire-and-forget: memory housekeeping never delays or breaks a
            # finished reply. Needs tool outputs and a configured store.
            outputs = self._generator.tool_outputs()
            if outputs and self._store is not None:
                asyncio.create_task(self._memory_task(job, persona, outputs))

    async def _memory_task(self, job: TriggerJob, persona: PersonaSpec,
                           outputs: list[dict]) -> None:
        try:
            from ai_engine.pydantic_ai_system.memory_pass import run_memory_pass
            record, saved = await run_memory_pass(job, persona, outputs, self._store)
            if record is not None:
                await self._nucleus.record_usage([record])
            log.info("[memory] pass saved %d rows for %s", saved, job.msg_id)
        except Exception:  # noqa: BLE001 — memory is a bonus, never an error
            log.exception("memory pass failed for %s — the reply is unaffected", job.msg_id)

    def _retrieve(self, job: TriggerJob) -> list[SearchHit]:
        """Two scoped searches (design §3): documents project-wide; chat memory
        SAME TOPIC ONLY (item 44's rule). Merged by score, capped. (The
        "recall" kind left with the Recall feature, 2026-10-22.)"""
        if not self._store.has_index(job.project_id):
            return []
        top_k = self._settings.retrieval_top_k
        min_score = self._settings.retrieval_min_score
        documents = self._store.search(SearchQuery(
            company_id=job.company_id, project_id=job.project_id, text=job.message,
            kinds=("context_source",), top_k=top_k, min_score=min_score,
        ))
        memory = self._store.search(SearchQuery(
            company_id=job.company_id, project_id=job.project_id, text=job.message,
            topic_id=job.topic_id, kinds=("message",),
            top_k=top_k, min_score=min_score,
        ))
        merged = sorted(documents + memory, key=lambda h: h.score, reverse=True)
        # the reply being written is itself indexed by nucleus later — but the
        # TRIGGERING message may already be in the index; never quote it back
        merged = [h for h in merged if h.id != job.msg_id]
        return merged[:top_k]

    async def _record_usage(self, shielded: bool = False) -> None:
        """Logged on failure, never raised — a good reply stays good (T15)."""
        records = self._generator.usage_records()
        if not records:
            return
        try:
            call = self._nucleus.record_usage(records)
            if shielded:
                await asyncio.shield(asyncio.ensure_future(call))
            else:
                await call
        except asyncio.CancelledError:
            # cancelled again while recording — the shielded task finishes on its own
            if not shielded:
                raise
        except Exception:
            log.exception("record_usage failed for job %s", records[0].job_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_KIND_LABEL = {"message": "earlier in this topic",
               "context_source": "project document"}


def _retrieved_section(hits) -> str:
    """The RETRIEVED prompt section (design §3): what memory found, for the
    model. The chunk text goes HERE and only here — events carry references."""
    lines = []
    for h in hits:
        origin = _KIND_LABEL.get(h.kind, h.kind)
        suffix = f" [used tools: {', '.join(h.used_tools)}]" if h.used_tools else ""
        lines.append(f"- ({origin}) {h.label}:{suffix}\n  {h.text}")
    return ("Relevant project memory, retrieved for this message (may be "
            "incomplete — weigh it, don't assume it is everything):\n"
            + "\n".join(lines))
