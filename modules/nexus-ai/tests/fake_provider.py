"""
A fake model server that answers exactly like OpenAI's and Anthropic's
streaming APIs and records every request body — the same instrument the
2026-10-10 trial used (NEXUS-AI-REVAMP.md §1.5 "Trial results").

One Starlette app serves both shapes:

    POST {base}/chat/completions   — OpenAI chat-completions streaming
    POST {base}/v1/messages        — Anthropic messages streaming

Behaviour is set per-test through `FakeProvider.script`:

    script.text           the reply text, streamed word by word
    script.usage          provider-shaped usage numbers (dict, raw fields)
    script.cut_after      cut the SSE stream after N data lines (no proper end)
    script.status         non-200 → error body, no stream
    script.delay_between  seconds of silence between chunks (for keepalive tests)

Every request body lands in `provider.requests` (parsed JSON, in order).
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
from dataclasses import dataclass, field

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


@dataclass
class Script:
    text: str = "Hello from the fake model."
    usage: dict | None = None          # raw provider-shaped usage fields
    cut_after: int | None = None       # cut the stream after N SSE data lines
    status: int = 200                  # non-200: fail the call outright
    delay_between: float = 0.0         # silence between chunks
    stop_reason: str = "stop"          # OpenAI finish_reason / Anthropic stop_reason


class FakeProvider:
    """The scripted fake. One instance per test; served by `serve()` below."""

    def __init__(self) -> None:
        self.script = Script()
        self.requests: list[dict] = []
        self.headers: list[dict] = []

    def reset(self) -> None:
        self.script = Script()
        self.requests.clear()
        self.headers.clear()

    # ── OpenAI chat-completions streaming ─────────────────────────────────
    async def openai_chat(self, request: Request) -> Response:
        body = await request.json()
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        s = self.script
        if s.status != 200:
            return JSONResponse({"error": {"message": "scripted failure"}}, status_code=s.status)

        usage = s.usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

        async def lines():
            n = 0
            base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk",
                    "created": 1760000000, "model": body.get("model", "fake")}

            def chunk(delta: dict, finish: str | None = None, extra: dict | None = None) -> bytes:
                payload = dict(base)
                payload["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
                if extra:
                    payload.update(extra)
                return f"data: {json.dumps(payload)}\n\n".encode()

            out = [chunk({"role": "assistant", "content": ""})]
            for word in s.text.split(" "):
                out.append(chunk({"content": word + " "}))
            out.append(chunk({}, finish=s.stop_reason))
            # usage-only chunk (stream_options.include_usage)
            payload = dict(base)
            payload["choices"] = []
            payload["usage"] = usage
            out.append(f"data: {json.dumps(payload)}\n\n".encode())
            out.append(b"data: [DONE]\n\n")

            for line in out:
                if s.cut_after is not None and n >= s.cut_after:
                    return  # cut: the connection just ends, no [DONE], no usage
                n += 1
                if s.delay_between:
                    await asyncio.sleep(s.delay_between)
                yield line

        return StreamingResponse(lines(), media_type="text/event-stream")

    # ── Anthropic messages streaming ──────────────────────────────────────
    async def anthropic_messages(self, request: Request) -> Response:
        body = await request.json()
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        s = self.script
        if s.status != 200:
            return JSONResponse({"type": "error", "error": {"type": "api_error", "message": "scripted failure"}},
                                status_code=s.status)

        usage = s.usage or {"input_tokens": 10, "output_tokens": 5}
        start_usage = {k: v for k, v in usage.items() if k != "output_tokens"}
        start_usage["output_tokens"] = 1  # the provisional count Anthropic sends first

        def ev(name: str, payload: dict) -> bytes:
            return f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode()

        async def lines():
            n = 0
            out = [
                ev("message_start", {"type": "message_start", "message": {
                    "id": "msg_fake", "type": "message", "role": "assistant", "content": [],
                    "model": body.get("model", "fake"), "stop_reason": None, "stop_sequence": None,
                    "usage": start_usage}}),
                ev("content_block_start", {"type": "content_block_start", "index": 0,
                                           "content_block": {"type": "text", "text": ""}}),
            ]
            for word in s.text.split(" "):
                out.append(ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                      "delta": {"type": "text_delta", "text": word + " "}}))
            out += [
                ev("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ev("message_delta", {"type": "message_delta",
                                     "delta": {"stop_reason": ("end_turn" if s.stop_reason == "stop" else s.stop_reason),
                                               "stop_sequence": None},
                                     "usage": {"output_tokens": usage.get("output_tokens", 5)}}),
                ev("message_stop", {"type": "message_stop"}),
            ]
            for line in out:
                if s.cut_after is not None and n >= s.cut_after:
                    return
                n += 1
                if s.delay_between:
                    await asyncio.sleep(s.delay_between)
                yield line

        return StreamingResponse(lines(), media_type="text/event-stream")


def make_app(provider: FakeProvider) -> Starlette:
    return Starlette(routes=[
        Route("/v1/chat/completions", provider.openai_chat, methods=["POST"]),
        Route("/chat/completions", provider.openai_chat, methods=["POST"]),
        Route("/v1/messages", provider.anthropic_messages, methods=["POST"]),
    ])


class ServedApp:
    """uvicorn in a thread on a free port; .url is the base URL."""

    def __init__(self, app, host: str = "127.0.0.1") -> None:
        sock = socket.socket()
        sock.bind((host, 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self.url = f"http://{host}:{self.port}"
        config = uvicorn.Config(app, host=host, port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> "ServedApp":
        self.thread.start()
        import time
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.02)
        raise RuntimeError("fake server did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
