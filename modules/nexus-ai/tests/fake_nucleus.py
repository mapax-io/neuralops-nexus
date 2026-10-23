"""
A fake nucleus: serves the persona and history endpoints nexus-ai calls, and
records what lands on the new usage endpoint. Shapes follow
modules/nexus-nucleus/internal/api.py (PersonaInternal, HistoryMessageInternal).
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def make_model(provider: str, base_url: str, *, config_id: str = "m1",
               model_id: str = "fake-model", context_window: int = 200_000) -> dict:
    """A ModelInternal-shaped dict pointing at the fake provider."""
    return {
        "id": config_id,
        "name": f"Fake {provider}",
        "provider": provider,
        "model_id": model_id,
        "qualified_id": f"{provider}:{model_id}",
        "api_base": base_url,
        "api_key": "test-key-not-real",
        "context_window": context_window,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": False,
    }


def make_persona(model: dict, *, system_prompt: str = "You are NeuralBot. PERSONA-PROMPT-MARKER.",
                 project_brief: str | None = None, temperature: float = 0.3,
                 max_tokens: int = 777, capabilities: list | None = None,
                 tool_levels: dict | None = None, mcp_servers: list | None = None,
                 router_model: dict | None = None, deep_model: dict | None = None,
                 deep_models: list | None = None,
                 fallback_models: list | None = None, max_steps: int = 8,
                 utility_model: dict | None = None, persona_id: str = "p1",
                 delegation_enabled: bool = False) -> dict:
    """A PersonaInternal-shaped dict. Smart router: `deep_models` is the BENCH
    (today's nucleus always sends it); a lone `deep_model` mirrors into a
    one-item bench the way nucleus does, and the single field is kept as the
    bench's first for an older engine image."""
    bench = deep_models if deep_models is not None else ([deep_model] if deep_model else [])
    return {
        "id": persona_id,
        "name": "NeuralBot",
        "prompt": {"system_prompt": system_prompt, "output_type": "text", "context_scope": None},
        "model": model,
        "advisor_model": None,
        "mcp_servers": mcp_servers or [],
        "capabilities": capabilities or [],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "max_steps": max_steps,
        "project_brief": project_brief,
        "utility_model": utility_model,
        "tool_levels": tool_levels or {},
        "fallback_models": fallback_models or [],
        # item 13 (nucleus change 3): the optional seats
        "router_model": router_model,
        # smart router: the bench, first entry mirrored into the legacy field
        "deep_models": bench,
        "deep_model": deep_model or (bench[0] if bench else None),
        # item 46 (Layer 6, handoff change 14): the supervisor checkbox
        "delegation_enabled": delegation_enabled,
    }


class FakeNucleus:
    def __init__(self) -> None:
        self.persona: dict = {}
        self.history: list[dict] = []
        self.usage_posts: list[dict] = []     # every POST body to the usage endpoint
        self.usage_status: int = 201          # set 500 for T15
        self.history_params: list[dict] = []
        self.pause_posts: list[dict] = []     # item 2: every pause POST (msg_id added)
        self.nudges: dict[str, list[str]] = {}  # W8: msg_id → waiting texts (taken once)
        self.personas: dict[str, dict] = {}   # item 46: extra personas by id (callees)

    def reset(self) -> None:
        self.persona = {}
        self.history = []
        self.usage_posts.clear()
        self.usage_status = 201
        self.history_params.clear()
        self.pause_posts.clear()
        self.nudges = {}
        self.personas = {}

    async def get_persona(self, request: Request) -> JSONResponse:
        # item 46: a callee persona is served by its id; the default persona
        # answers everything else (most tests configure exactly one).
        persona_id = request.path_params.get("persona_id", "")
        if persona_id in self.personas:
            return JSONResponse(self.personas[persona_id])
        if not self.persona:
            return JSONResponse({"detail": "Persona not found."}, status_code=404)
        return JSONResponse(self.persona)

    async def get_history(self, request: Request) -> JSONResponse:
        self.history_params.append(dict(request.query_params))
        return JSONResponse(self.history)

    async def post_usage(self, request: Request) -> JSONResponse:
        body = await request.json()
        if self.usage_status != 201:
            return JSONResponse({"detail": "scripted failure"}, status_code=self.usage_status)
        self.usage_posts.append(body)
        return JSONResponse({"ok": True}, status_code=201)

    async def get_nudges(self, request: Request) -> JSONResponse:
        # W8: taken ONCE — nucleus consumes on GET (legacy contract)
        msg_id = request.path_params["msg_id"]
        return JSONResponse({"nudges": self.nudges.pop(msg_id, [])})

    async def post_pause(self, request: Request) -> JSONResponse:
        body = await request.json()
        body["msg_id"] = request.path_params["msg_id"]
        self.pause_posts.append(body)
        return JSONResponse({"ok": True}, status_code=201)


def make_app(nucleus: FakeNucleus) -> Starlette:
    return Starlette(routes=[
        Route("/api/v1/internal/personas/{persona_id}/", nucleus.get_persona, methods=["GET"]),
        Route("/api/v1/internal/topics/{topic_id}/history/", nucleus.get_history, methods=["GET"]),
        Route("/api/v1/internal/usage/", nucleus.post_usage, methods=["POST"]),
        Route("/api/v1/internal/messages/{msg_id}/pause/", nucleus.post_pause, methods=["POST"]),
        Route("/api/v1/internal/messages/{msg_id}/nudges/", nucleus.get_nudges, methods=["GET"]),
    ])
