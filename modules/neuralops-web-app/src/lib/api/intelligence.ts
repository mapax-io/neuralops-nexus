import { apiJson } from "./client";

// ── Model configs ─────────────────────────────────────────────────────────────
// One model endpoint: provider + BARE model id + credentials. The server
// composes the wire id itself (`qualified_id`, "provider:model"), so a prefixed
// id ("openai/gpt-4o") is rejected with a 400. Generation settings live on the
// persona, not here — two personas sharing a key routinely want different ones.

export interface ModelConfig {
  id: string;
  name: string;
  provider: string; // openai | anthropic | google | ollama | openai_compatible
  model_id: string; // bare, e.g. "gpt-4o-mini"
  qualified_id: string; // "openai:gpt-4o-mini" — composed server-side
  api_base: string | null;
  description: string | null;
  licence_accepted: boolean;
  context_window: number;
  supports_tools: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  supports_audio: boolean;
  config: Record<string, unknown>;
  is_active: boolean;
  has_api_key: boolean;
  project_ids?: string[]; // projects the config is attached to (visibility gate)
}

// Compact form embedded in a persona.
export interface ModelConfigRef {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  qualified_id: string;
  supports_tools: boolean; // lets the UI grey out tool-server attachment
}

export const listModelConfigs = () => apiJson<ModelConfig[]>(`/api/v1/model-configs/`);

export interface ModelConfigCreate {
  name: string;
  provider: string;
  model_id: string;
  api_key?: string;
  api_base?: string;
  description?: string;
  licence_accepted: boolean; // server rejects false with a 400
  context_window?: number;
  supports_tools?: boolean;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  supports_audio?: boolean;
}

export const createModelConfig = (payload: ModelConfigCreate) =>
  apiJson<ModelConfig>(`/api/v1/model-configs/`, { method: "POST", body: JSON.stringify(payload) });

// provider and model_id are patchable: every persona built on the config
// follows to the new model on save (the dialog warns first). Same guards as
// create server-side: a known provider, a bare model id.
export interface ModelConfigPatch {
  name?: string;
  provider?: string;
  model_id?: string;
  api_key?: string; // write-only — re-encrypted on set, never returned
  api_base?: string;
  description?: string;
  context_window?: number;
  supports_tools?: boolean;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  supports_audio?: boolean;
}

export const patchModelConfig = (configId: string, payload: ModelConfigPatch) =>
  apiJson<ModelConfig>(`/api/v1/model-configs/${configId}/`, { method: "PATCH", body: JSON.stringify(payload) });

// 409 while any persona still uses the config (as model or advisor) — the
// message names them.
export const deleteModelConfig = (configId: string) =>
  apiJson<undefined>(`/api/v1/model-configs/${configId}/`, { method: "DELETE" });

// Attaching a config to a project makes it visible (and usable) there —
// distinct `model_config.attach` right, reachable by that project's own admin.
// Detaching is refused (409) while a persona in that project still uses it.
export const attachModelConfigToProject = (projectId: string, configId: string) =>
  apiJson<{ ok: boolean }>(`/api/v1/projects/${projectId}/model-configs/${configId}/attach/`, { method: "POST" });

export const detachModelConfigFromProject = (projectId: string, configId: string) =>
  apiJson<{ ok: boolean }>(`/api/v1/projects/${projectId}/model-configs/${configId}/attach/`, { method: "DELETE" });

// ── MCP servers ───────────────────────────────────────────────────────────────

export type McpAuthType = "none" | "static_secrets" | "oauth2";

// oauth_config holds only NON-secret metadata (client_secret is write-only,
// stored server-side encrypted and never returned).
export interface McpOAuthConfig {
  client_id?: string;
  authorize_endpoint?: string;
  token_endpoint?: string;
  scopes?: string[];
  token_env_var?: string; // default "OAUTH_ACCESS_TOKEN"
  expires_at?: string;    // ISO — written by the backend after a token exchange
  authorize_params?: Record<string, string>; // extra sign-in params (e.g. Atlassian audience, Google access_type)
}

export interface MCPServer {
  id: string;
  name: string;
  description: string | null;
  project_id: string; // the ONE owning project — an FK server-side, never transferable
  server_type: string; // remote (URL transports) | local (stdio)
  transport: string;   // http | sse | websocket | stdio
  url: string | null;      // URL transports
  command: string | null;  // stdio: the command NeuralOps runs
  timeout_seconds: number;
  max_retries: number;
  // Non-secret runtime configuration handed to the worker with the server
  // (e.g. {"root_path": "/data"} for a filesystem server).
  config: Record<string, unknown>;
  // Published by us (marketplace) — the only kind whose tool output may be
  // embedded. Fixed after creation: the server's PATCH has no such field.
  is_first_party: boolean;
  embed_output: boolean;
  auth_type: McpAuthType;
  oauth_config: McpOAuthConfig | null;
  // True iff a refresh token is stored (i.e. the OAuth connect has completed
  // at least once). Reflects stored-credential presence, not live validity.
  oauth_connected: boolean;
}

// Compact form embedded in a persona.
export interface MCPServerRef {
  id: string;
  name: string;
  transport: string;
  auth_type: McpAuthType;
  oauth_connected: boolean; // so the UI can flag one needing reconnect
}

export const listMcpServers = () => apiJson<MCPServer[]>(`/api/v1/mcp-servers/`);

export interface MCPServerCreate {
  name: string;
  description?: string;
  project_id: string; // MCP servers are project-owned
  url?: string;       // http / sse / websocket
  command?: string;   // stdio
  server_type?: string;
  transport?: string; // fixed after creation — the server's PATCH has no transport field
  timeout_seconds?: number;
  max_retries?: number;
  config?: Record<string, unknown>;
  is_first_party?: boolean;
  embed_output?: boolean;
  auth_type?: McpAuthType;
  oauth_config?: McpOAuthConfig;
  client_secret?: string; // write-only — folded into encrypted secrets server-side
}

export const createMcpServer = (payload: MCPServerCreate) =>
  apiJson<MCPServer>(`/api/v1/mcp-servers/`, { method: "POST", body: JSON.stringify(payload) });

export interface MCPServerPatch {
  name?: string;
  description?: string;
  url?: string;
  command?: string;
  timeout_seconds?: number;
  max_retries?: number;
  config?: Record<string, unknown>;
  embed_output?: boolean;
  auth_type?: McpAuthType;
  oauth_config?: McpOAuthConfig;
  client_secret?: string;
}

export const patchMcpServer = (serverId: string, payload: MCPServerPatch) =>
  apiJson<MCPServer>(`/api/v1/mcp-servers/${serverId}/`, { method: "PATCH", body: JSON.stringify(payload) });

// 409 while any persona still mounts the server — the message names them.
export const deleteMcpServer = (serverId: string) =>
  apiJson<undefined>(`/api/v1/mcp-servers/${serverId}/`, { method: "DELETE" });

// Begin the OAuth2 authorization-code flow for an oauth2 MCP server. Returns
// the provider consent URL; the caller opens it in a popup. The backend's
// public /oauth/callback/ exchanges the code and postMessages the result back.
export const mcpOAuthAuthorize = (serverId: string, frontendOrigin: string) =>
  apiJson<{ authorize_url: string }>(
    `/api/v1/mcp-servers/${serverId}/oauth/authorize/?frontend_origin=${encodeURIComponent(frontendOrigin)}`,
  );

// ── Personas ──────────────────────────────────────────────────────────────────
// A persona is a composition: exactly one model, an optional advisor model (a
// second opinion the primary can ask for), and zero or more MCP tool servers.
// "Agent-ness" is emergent — a persona with tool servers acts, one without
// just answers. There is no separate agent record any more.

export interface PersonaPrompt {
  id?: string;
  system_prompt: string;
  output_type: string;
  context_scope?: string[] | null;
  template_id?: string | null;
}

export interface Persona {
  id: string;
  name: string;
  description: string | null;
  project_id: string;
  model: ModelConfigRef;
  advisor_model: ModelConfigRef | null;
  mcp_servers: MCPServerRef[];
  temperature: number;
  max_tokens: number;
  max_steps: number; // tool-call rounds per reply
  prompt?: PersonaPrompt | null;
  is_active: boolean;
  avatar?: string | null;
}

// Mirrors intelligence/services.py — a guard rail, not a database constraint.
export const MAX_MCP_SERVERS_PER_PERSONA = 5;

// project_id is a required query param server-side.
export const listPersonas = (projectId: string) => apiJson<Persona[]>(`/api/v1/personas/?project_id=${encodeURIComponent(projectId)}`);

// Server-side wiring rules (400 on violation): the model and advisor must be
// attached to the project; the advisor must differ from the model; tool servers
// must belong to the project, number at most MAX_MCP_SERVERS_PER_PERSONA, and
// require a model with supports_tools.
export interface PersonaCreate {
  name: string;
  description?: string;
  project_id: string;
  model_config_id: string;
  advisor_model_config_id?: string;
  mcp_server_ids?: string[];
  temperature?: number;
  max_tokens?: number;
  max_steps?: number;
  prompt: { system_prompt: string; output_type?: string; template_id?: string };
}

export const createPersona = (payload: PersonaCreate) =>
  apiJson<Persona>(`/api/v1/personas/`, { method: "POST", body: JSON.stringify(payload) });

// PATCH semantics server-side: only non-null fields are applied. The backing is
// mutable. `clear_advisor` is the one way to remove the advisor (null means
// "not sent"); `mcp_server_ids: []` is a real value and detaches every server.
export interface PersonaPatch {
  name?: string;
  description?: string;
  model_config_id?: string;
  advisor_model_config_id?: string;
  clear_advisor?: boolean;
  mcp_server_ids?: string[];
  temperature?: number;
  max_tokens?: number;
  max_steps?: number;
  prompt?: { system_prompt: string; output_type?: string; template_id?: string };
}

export const patchPersona = (personaId: string, payload: PersonaPatch) =>
  apiJson<Persona>(`/api/v1/personas/${personaId}/`, { method: "PATCH", body: JSON.stringify(payload) });

export const deletePersona = (personaId: string) =>
  apiJson<undefined>(`/api/v1/personas/${personaId}/`, { method: "DELETE" });

// ── Prompt templates (NOTE: no trailing slash — server quirk) ─────────────────

export const listPromptTemplates = () =>
  apiJson<{ prompts: Record<string, string> }>(`/api/v1/prompt-templates`);

export const fetchPromptTemplate = (id: string) =>
  apiJson<{ content: string }>(`/api/v1/prompt-templates/${encodeURIComponent(id)}`);

// ── Output types ──────────────────────────────────────────────────────────────

export interface OutputType {
  name: string;
  label: string;
  icon: string;
  render_as: string;
}

export const listOutputTypes = () => apiJson<OutputType[]>(`/api/v1/output-types/`);
