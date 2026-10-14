"""
Layer 1, item 2 — the approval gate: pause on ask, resume on decision
(docs/NEXUS-AI-REVAMP.md §1.3 "Item 2" entry; decisions 1, 4–7; trials D, E).

Unit tests of ApprovalPolicy (pure) plus acceptance tests through the running
service: a write tool pauses the run, a resume continues it in what is
effectively a fresh run, denial text reaches the model, reads stay silent,
off hides, unattended runs refuse instead of pausing.
"""
from __future__ import annotations

import json

import pytest

from ai_engine.core.specs import ToolCatalogEntry
from ai_engine.pydantic_ai_system.tools.approval_policy import ApprovalPolicy, ToolSource
from conftest import openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio

FS = ToolSource(kind="native", cap_key="filesystem", source_id="filesystem")


def _mcp_source(sid: str = "s1", slug: str = "gh") -> ToolSource:
    return ToolSource(kind="mcp", cap_key=f"mcp:{sid}", source_id=sid, slug=slug)


def _mcp_entry(sid: str = "s1", tool: str = "search", read_only: bool | None = None) -> ToolCatalogEntry:
    return ToolCatalogEntry(tool_id=f"mcp:{sid}/{tool}", model_name=f"gh__{tool}",
                            source_id=sid, source_kind="mcp", one_line="", read_only=read_only)


# ── ApprovalPolicy (pure) ───────────────────────────────────────────────────────

def test_a_policy_native_defaults():
    """Item 2 — native defaults: reading is automatic, acting asks.
    write_file/edit_file/create_directory and the shell commands ask; read_file
    and friends run silently — decision 6's read/write split, with no levels set."""
    policy = ApprovalPolicy({})
    assert policy.runtime_level(tool_name="read_file", source=FS, entry=None, metadata=None) == "auto"
    assert policy.runtime_level(tool_name="write_file", source=FS, entry=None, metadata=None) == "ask"
    shell = ToolSource(kind="native", cap_key="shell", source_id="shell")
    assert policy.runtime_level(tool_name="run_command", source=shell, entry=None, metadata=None) == "ask"
    assert policy.runtime_level(tool_name="check_command", source=shell, entry=None, metadata=None) == "auto"


def test_a_policy_explicit_levels_win():
    """Item 2 — persona tool_levels override every default (0.8.0 behaviour kept).
    An admin's deliberate per-tool setting ("filesystem/write_file": "auto",
    "filesystem": "off") beats the acting/read defaults, in that key order."""
    policy = ApprovalPolicy({"filesystem/write_file": "auto"})
    assert policy.runtime_level(tool_name="write_file", source=FS, entry=None, metadata=None) == "auto"
    policy = ApprovalPolicy({"filesystem": "off"})
    assert policy.runtime_level(tool_name="read_file", source=FS, entry=None, metadata=None) == "off"


def test_a_policy_mcp_unknown_asks_clearance_clears():
    """Item 2 decision 6 — an unlabeled MCP tool asks; a topic clearance makes it
    a read; a KNOWN write stays ask even when (wrongly) cleared; a stored
    read_only=True runs silently."""
    src = _mcp_source()
    unlabeled = _mcp_entry(read_only=None)
    policy = ApprovalPolicy({})
    assert policy.runtime_level(tool_name="gh__search", source=src, entry=unlabeled, metadata=None) == "ask"
    cleared = ApprovalPolicy({}, clearances={"mcp:s1/search"})
    assert cleared.runtime_level(tool_name="gh__search", source=src, entry=unlabeled, metadata=None) == "auto"
    # a known write never rides a clearance
    write = _mcp_entry(tool="create_issue", read_only=False)
    cleared_w = ApprovalPolicy({}, clearances={"mcp:s1/create_issue"})
    assert cleared_w.runtime_level(tool_name="gh__create_issue", source=src, entry=write, metadata=None) == "ask"
    # a stored read runs silently
    read = _mcp_entry(read_only=True)
    assert policy.runtime_level(tool_name="gh__search", source=src, entry=read, metadata=None) == "auto"


# ── acceptance: through the running service ─────────────────────────────────────

def _fs_persona(harness, tmp_path, tool_levels: dict | None = None) -> dict:
    return make_persona(
        openai_model(harness),
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)}}}],
        tool_levels=tool_levels,
    )


def _write_step(call_id: str = "call_w1") -> dict:
    return {"kind": "tool_call", "call_id": call_id, "name": "write_file",
            "args": {"path": "out.txt", "content": "hello-approved"}}


async def test_a1_write_tool_pauses_the_run(harness, tmp_path):
    """Item 2 — a write tool PAUSES the run for approval instead of running.
    The model calls write_file → the stream carries approval_requested (call id,
    tool, 300-char args preview, capability id) and ends with message_paused —
    no message_done, no error; the pause state lands on nucleus BEFORE the final
    event; the file is NOT written; the paused call's usage is still recorded."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [_write_step()]
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert "approval_requested" in types and types[-1] == "message_paused"
    assert "message_done" not in types and "message_error" not in types
    [req] = [e for e in events if e["type"] == "approval_requested"]
    assert req["approval"]["call_id"] == "call_w1"
    assert req["approval"]["tool"] == "write_file"
    assert req["approval"]["capability_id"] == "filesystem"
    assert "out.txt" in req["approval"]["args_preview"]
    assert len(req["approval"]["args_preview"]) <= 300

    [pause] = harness.nucleus.pause_posts
    assert pause["msg_id"] == "msg-1" and pause["state"]
    assert pause["pending"][0]["tool"] == "write_file"
    assert not (tmp_path / "out.txt").exists()
    records = await harness.wait_for_usage(1)
    assert records[0]["message_id"] == "msg-1"


async def test_a2_resume_approved_runs_the_tool(harness, tmp_path):
    """Item 2 — an approved resume EXECUTES the tool and finishes the reply.
    A second trigger carries the stored state + ToolApproved for the call: the
    tool runs now (the file exists with the original args' content), the reply
    ends in message_done, and BOTH halves billed their own model call."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [_write_step(), {"kind": "text", "text": "Done, file written."}]
    await harness.trigger()
    [pause] = harness.nucleus.pause_posts

    job = harness.job(resume={"state": pause["state"],
                              "approvals": {"call_w1": {"decision": "allow"}}})
    events = await harness.trigger(job)
    types = [e["type"] for e in events]
    assert types[-1] == "message_done" and "approval_requested" not in types
    [done] = [e for e in events if e["type"] == "message_done"]
    assert "file written" in done["content"].lower()
    assert (tmp_path / "out.txt").read_text() == "hello-approved"
    records = await harness.wait_for_usage(2)
    assert len(records) == 2  # the paused half and the resumed half


async def test_a3_resume_denied_never_runs_the_tool(harness, tmp_path):
    """Item 2 — a denied resume NEVER runs the tool; the model is told plainly.
    The tool result the model sees is the standard denial text ("It did not run
    and nothing changed"), the file does not exist, and the reply still ends in
    message_done — a denial is an answer, not an error."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [_write_step(), {"kind": "text", "text": "Understood, not writing."}]
    await harness.trigger()
    [pause] = harness.nucleus.pause_posts

    job = harness.job(resume={"state": pause["state"],
                              "approvals": {"call_w1": {"decision": "deny"}}})
    events = await harness.trigger(job)
    assert [e for e in events if e["type"] == "message_done"]
    assert not (tmp_path / "out.txt").exists()
    body = harness.provider.requests[-1]
    tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "did not run and nothing changed" in tool_msgs[0]["content"]


async def test_a4_read_tool_runs_without_asking(harness, tmp_path):
    """Item 2 decision 6 — a read tool runs silently, no approval, no pause.
    The model calls read_file; the run never pauses, the tool result (the real
    file content) reaches the model, and the reply ends in message_done."""
    (tmp_path / "data.txt").write_text("SECRET-42")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [
        {"kind": "tool_call", "call_id": "call_r1", "name": "read_file", "args": {"path": "data.txt"}},
        {"kind": "text", "text": "The file says SECRET-42."},
    ]
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert "approval_requested" not in types and "message_paused" not in types
    assert types[-1] == "message_done"
    body = harness.provider.requests[-1]
    tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "SECRET-42" in tool_msgs[0]["content"]


async def test_a5_off_tool_is_invisible(harness, tmp_path):
    """Item 2 — an explicit 'off' removes the capability entirely.
    tool_levels {"filesystem": "off"} → no catalog entry, no capability tools in
    the provider request (only item 5's built-in ask_user), no catalog section."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path, tool_levels={"filesystem": "off"})
    events = await harness.trigger()
    assert [e for e in events if e["type"] == "message_done"]
    body = harness.provider.requests[-1]
    # item 5: the built-in ask_user is always there on an interactive run —
    # "off" must remove every CAPABILITY tool, nothing else survives
    names = [t["function"]["name"] for t in body.get("tools", [])]
    assert names == ["ask_user"]
    assert "Tools available" not in json.dumps(body["messages"])


async def test_a6_unattended_run_refuses_instead_of_pausing(harness, tmp_path):
    """Item 2 — an unattended run (interactive=false) refuses ask-tools, no pause.
    Nobody can approve in a schedule: the tool is NOT run, the model hears
    0.8.0's "needs a person's approval" text as the tool result and answers on;
    the reply ends in message_done and no pause state is stored."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [_write_step(), {"kind": "text", "text": "Could not write, explained."}]
    events = await harness.trigger(harness.job(interactive=False))
    types = [e["type"] for e in events]
    assert "message_paused" not in types and types[-1] == "message_done"
    assert not harness.nucleus.pause_posts
    assert not (tmp_path / "out.txt").exists()
    body = harness.provider.requests[-1]
    tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "needs a person's approval" in tool_msgs[0]["content"]
