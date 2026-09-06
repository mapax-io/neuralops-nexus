"""Schemas for the /trigger/ endpoint (nexus-nucleus → nexus-ai) and SSE events."""

from enum import Enum
from typing import Any
from typing import Annotated
from pydantic import BaseModel, Field, validate_call
from pydantic_ai import capabilities


# ── Inbound job payload ────────────────────────────────────────────────────────


class ModelConfig(BaseModel):
    provider: str  # "litellm" | "local"
    model_id: str  # "anthropic/claude-haiku-4-5-20251001"
    api_key: str | None = None  # decrypted key from AIModel — passed per-call
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_vision: bool = False


class MCPServerConfig(BaseModel):
    """MCP server descriptor passed from nexus-nucleus in the TriggerJob."""

    id: str
    name: str
    transport: str  # "stdio" | "http" | "sse" | "websocket"
    url: str | None = None  # for http/sse/websocket
    command: str | None = None  # for stdio
    config: dict = Field(default_factory=dict)
    # Decrypted secret env vars (e.g. GITHUB_PERSONAL_ACCESS_TOKEN). Forwarded
    # as subprocess env when spawning a stdio server -- never into `command`,
    # which is plain text end to end (DB, UI, this payload).
    secrets: dict = Field(default_factory=dict)
    timeout_seconds: int = 60
    is_first_party: bool = False
    embed_output: bool = False
    needs_reauth: bool = False  # NEW
    # auth_type + token_env_var: which key in `secrets` holds the bearer
    # access token to send as an Authorization header on http/sse/
    # streamable-http transports (see pydantic_ai_runner.py:_run_with_mcp).
    # stdio servers ignore this -- they get the whole `secrets` dict as
    # subprocess env instead.
    auth_type: str = "static_secrets"
    token_env_var: str = "OAUTH_ACCESS_TOKEN"


class NativePydanticAICapabilities(str, Enum):
    FILESYSTEM = "Filesystem"
    SHELL = "Shell"
    MCP = "MCP"
    STACK_ONE = "Stack One"
    LOCAL_STACK = "Local Stack"
    WEB_SEARCH = "Web Search"
    WEB_FETCH = "Web Fetch"
    X_SEARCH = "X Search"
    THINKING = "Thinking"
    PLANNING = "Planning"
    SUBAGENTS = "Sub Agents"
    DYNAMIC_WORKFLOW = "Dynamic Workflow"
    ADVISOR = "Advisor"
    TOOL_SEARCH = "Tool Search"
    COMPACTION = "Compaction"
    MEMORY = "Memory"
    SKILLS = "Skills"
    REPO_CONTEXT = "Repo Context"
    GAURDRAILS = "Gaurdrails"
    SPEND_LIMITS = "Spend Limits"
    TOOL_APPROVAL = "Tool Approval"
    CAPABILITY_CREATION = "Capability Creation"


FileSystemPattern = Annotated[
    str, 
    Field(
        min_length=1,
        pattern=r'^[^/\\<>:"|\x00][^<>:"|\x00]*$',
        description="A glob pattern (e.g., '*.py', 'src/**/*'). Cannot be an absolute path.",
        title="Glob Pattern"
    )
]

class FileSystem(BaseModel):
    root_dir: str = Field(
        default=".",
        pattern=r'^[^/\\<>:"|\x00][^<>:"|\x00]*$',
    )
    allowed_patterns: list[FileSystemPattern] = Field(
        default_factory=list,
        description="Allowlist globs. If non-empty, only matching paths are accessible."
    )
    denied_patterns: list[FileSystemPattern] = Field(
        default_factory=list,
        description="Denylist globs. Matching paths are always rejected."
    )
    protected_patterns: list[FileSystemPattern] = Field(
        default_factory=lambda: [".git/*", ".env", ".env.*", "*.pem", "*.key", "**/secrets*"],
        description="Read-only globs. Writes to matching paths are rejected."
    )

class WebSearchArgs(BaseModel):
    local: str = Field(
        default='duckduckgo',
        min_length=1,
        max_length=16,
        pattern=r'^[^<>:"|?*\x00]+$',
        description="Search Engine Provider",
        title="Search Engine",
    )

class WebFetchArgs(BaseModel):
    local: bool = True

class ShellCommands(str, Enum):
    ls = "ls"
    touch = "touch"
    rm = "rm"
    git = "git"
    cd = "cd"
    cat = "cat"
    echo = "echo"
    grep = "grep"
    pwd = "pwd"
    mkdir = "mkdir"
    cp = "cp"
    mv = "mv"
    head = "head"
    tail = "tail"
    curl = "curl"


class Shell(BaseModel):
    allowed_commands: list[ShellCommands]
    denied_commands: list[ShellCommands]
    allow_interactive: bool = True
    default_timeout: float = 30.0
    max_output_chars: int = 50_000

class MCPArgs(BaseModel):...
class Thinking(BaseModel):...
class Planning(BaseModel):...
class Memory(BaseModel):...

# TODO *still under construction, do not touch!*
class PersonaCapabilities(BaseModel):...

class PersonaConfig(BaseModel):
    id: str
    name: str  # "NeuralBot"
    system_prompt: str
    model: ModelConfig
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    capabilities: PersonaCapabilities = Field(default_factory=PersonaCapabilities)


class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    sender_name: str | None = None  # display only, not sent to LLM


class ContextSourceRef(BaseModel):
    source_id: str
    type: str  # "doc" | "code"
    label: str  # "auth.py"
    language: str | None = None
    collection_id: str  # Chroma collection to search


class TriggerJob(BaseModel):
    """
    Deliberately minimal (#131) -- nexus-nucleus only tells us WHO and
    WHAT, not HOW. persona_id and topic_id are resolved into a full
    PersonaConfig and history list by apps/managers/nucleus_client.py,
    right at the top of AgenticManager.run(), not here on the schema.
    context_sources is the one exception still pushed by nucleus -- see
    the comment on trigger_ai_response_async in chat/services.py for why.
    """

    job_id: str
    msg_id: str  # pre-generated UUID — used in SSE events + DB save

    persona_id: str
    topic_id: str
    user_message_id: str  # the human message this is replying to --
    # excluded when nucleus_client fetches history,
    # since it's sent separately as `message` below
    message: str  # the user's current message (mentions stripped)
    context_sources: list[ContextSourceRef] = Field(default_factory=list)

    # M7: output type — resolved in nexus-nucleus from @mention detection.
    # "auto" = nexus-ai should classify intent via cosine similarity.
    # Any other value = explicit override (e.g. "chart", "terminal", "code").
    output_type: str = "auto"


class TriggerSwarmJob(BaseModel):
    """
    Deliberately minimal (#131) -- nexus-nucleus only tells us WHO and
    WHAT, not HOW. persona_id and topic_id are resolved into a full
    PersonaConfig and history list by apps/managers/nucleus_client.py,
    right at the top of AgenticManager.run(), not here on the schema.
    context_sources is the one exception still pushed by nucleus -- see
    the comment on trigger_ai_response_async in chat/services.py for why.
    """

    job_id: str
    msg_id: str  # pre-generated UUID — used in SSE events + DB save

    personas: list[list[str]]
    topic_id: str
    user_message_id: str  # the human message this is replying to --
    # excluded when nucleus_client fetches history,
    # since it's sent separately as `message` below
    message: str  # the user's current message (mentions stripped)
    context_sources: list[ContextSourceRef] = Field(default_factory=list)

    # M7: output type — resolved in nexus-nucleus from @mention detection.
    # "auto" = nexus-ai should classify intent via cosine similarity.
    # Any other value = explicit override (e.g. "chart", "terminal", "code").
    output_type: str = "auto"


# ── Outbound SSE events (nexus-ai → nexus-nucleus) ────────────────────────────


class ToolCallData(BaseModel):
    name: str
    args: dict[str, Any]


class AgentEventType(str, Enum):
    PERSIST = "persist_internal_state"
    START = "message_start"
    DELTA = "message_delta"
    END = "message_done"
    ERROR = "message_error"
    TOOL_CALL_START = "tool_call_start"
    SWARM_TRANSITION = "swarm_transition"


class AgentEvent(BaseModel):
    type: AgentEventType
    id: str  # msg_id

    # message_start only
    created_at: str | None = None
    persona_id: str | None = None
    persona_name: str | None = None

    # message_delta only
    delta: str | None = None

    # tool_call_start only
    tool_call: ToolCallData | None = None

    # message_done only
    content: str | None = None  # full assembled response (markers stripped) for DB save

    # M7: output type metadata — populated in message_done
    output_type: str | None = None  # resolved type: "chart", "terminal", "text", etc.
    render_as: str | None = None  # renderer hint: "html" | "code" | "text" | "terminal"

    # M8: embed description — text inside <<<EMBED>>>...<<<END_EMBED>>> block
    # Only present for html/form/terminal render_as. Used instead of raw HTML for embedding.
    embed_description: str | None = None

    # message_error only -- see apps/routers/trigger.py:_event_stream. Emitted
    # when anything in AgenticManager.run() raises (persona resolve, history
    # fetch, the LLM call itself, ...), so the SSE stream ends with one clean
    # event nucleus can act on instead of the connection just dying mid-body.
    error: str | None = None
    error_code: str | None = None  # NEW -- e.g. "mcp_reauth_required"

    # swarm_transition only
    metadata: dict | None = None
