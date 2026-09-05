import { apiJson } from "./client";

// ── Personas ──────────────────────────────────────────────────────────────────

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
  project_id?: string | null;
  source_type: "model" | "agent";
  model_id?: string | null;
  agent_id?: string | null;
  prompt?: PersonaPrompt | null;
  avatar?: string | null;
}

// project_id is a required query param server-side.
export const listPersonas = (projectId: string) => apiJson<Persona[]>(`/api/v1/personas/?project_id=${encodeURIComponent(projectId)}`);

export interface PersonaCreate {
  name: string;
  description?: string;
  project_id: string;
  source_type: "model" | "agent";
  model_id?: string;
  agent_id?: string;
  prompt: { system_prompt: string; output_type?: string; template_id?: string };
}

export const createPersona = (payload: PersonaCreate) =>
  apiJson<Persona>(`/api/v1/personas/`, { method: "POST", body: JSON.stringify(payload) });

// PATCH semantics server-side: only non-null fields are applied — a field
// can be changed but never cleared to null through this endpoint.
export interface PersonaPatch {
  name?: string;
  description?: string;
  prompt?: { system_prompt: string; output_type?: string; template_id?: string };
}

export const patchPersona = (personaId: string, payload: PersonaPatch) =>
  apiJson<Persona>(`/api/v1/personas/${personaId}/`, { method: "PATCH", body: JSON.stringify(payload) });

export const deletePersona = (personaId: string) =>
  apiJson<undefined>(`/api/v1/personas/${personaId}/`, { method: "DELETE" });

// ── AI models ─────────────────────────────────────────────────────────────────

export interface AIModel {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  api_base: string | null;
  description: string | null;
  temperature: number;
  max_tokens: number;
  context_window: number;
  supports_tools: boolean;
  has_api_key: boolean;
  project_ids?: string[]; // projects the model is attached to (visibility gate)
}

export const listModels = () => apiJson<AIModel[]>(`/api/v1/ai-models/`);

export interface AIModelCreate {
  name: string;
  provider: string;
  model_id: string;
  api_key?: string;
  api_base?: string;
  description?: string;
  licence_accepted: boolean; // server rejects false with a 400
  supports_tools?: boolean;
}

export const createModel = (payload: AIModelCreate) =>
  apiJson<AIModel>(`/api/v1/ai-models/`, { method: "POST", body: JSON.stringify(payload) });

export const deleteModel = (modelId: string) =>
  apiJson<undefined>(`/api/v1/ai-models/${modelId}/`, { method: "DELETE" });

// Attaching a model to a project makes it visible (and usable) there —
// distinct `ai_model.attach` right, reachable by that project's own admin.
export const attachModelToProject = (projectId: string, modelId: string) =>
  apiJson<{ ok: boolean }>(`/api/v1/projects/${projectId}/ai-models/${modelId}/attach/`, { method: "POST" });

export const detachModelFromProject = (projectId: string, modelId: string) =>
  apiJson<{ ok: boolean }>(`/api/v1/projects/${projectId}/ai-models/${modelId}/attach/`, { method: "DELETE" });

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
  server_type: string;
  transport: string;
  url: string | null;
  timeout_seconds: number;
  embed_output: boolean;
  auth_type: McpAuthType;
  oauth_config: McpOAuthConfig | null;
  // True iff a refresh token is stored (i.e. the OAuth connect has completed
  // at least once). Reflects stored-credential presence, not live validity.
  oauth_connected: boolean;
}

export const listMcpServers = () => apiJson<MCPServer[]>(`/api/v1/mcp-servers/`);

export interface MCPServerCreate {
  name: string;
  description?: string;
  project_id: string; // MCP servers are project-owned
  url: string;
  server_type?: string;
  transport?: string;
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
  auth_type?: McpAuthType;
  oauth_config?: McpOAuthConfig;
  client_secret?: string;
}

export const patchMcpServer = (serverId: string, payload: MCPServerPatch) =>
  apiJson<MCPServer>(`/api/v1/mcp-servers/${serverId}/`, { method: "PATCH", body: JSON.stringify(payload) });

export const deleteMcpServer = (serverId: string) =>
  apiJson<undefined>(`/api/v1/mcp-servers/${serverId}/`, { method: "DELETE" });

// Begin the OAuth2 authorization-code flow for an oauth2 MCP server. Returns
// the provider consent URL; the caller opens it in a popup. The backend's
// public /oauth/callback/ exchanges the code and postMessages the result back.
export const mcpOAuthAuthorize = (serverId: string, frontendOrigin: string) =>
  apiJson<{ authorize_url: string }>(
    `/api/v1/mcp-servers/${serverId}/oauth/authorize/?frontend_origin=${encodeURIComponent(frontendOrigin)}`,
  );

// ── Agents ────────────────────────────────────────────────────────────────────

export interface AIAgent {
  id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  agent_type: string;
  model_id: string | null;
  model_name: string | null;
  mcp_server_id: string | null;
  mcp_server_name: string | null;
  safety_mode: boolean;
  max_steps: number;
}

export const listAgents = () => apiJson<AIAgent[]>(`/api/v1/agents/`);

export interface AIAgentCreate {
  name: string;
  description?: string;
  project_id: string; // agents are project-owned
  model_id: string;
  mcp_server_id?: string;
  safety_mode?: boolean;
  max_steps?: number;
}

export const createAgent = (payload: AIAgentCreate) =>
  apiJson<AIAgent>(`/api/v1/agents/`, { method: "POST", body: JSON.stringify(payload) });

// mcp_server_id can be changed but not cleared (server applies only
// non-null fields) — the edit UI reflects that.
export interface AIAgentPatch {
  name?: string;
  description?: string;
  model_id?: string;
  mcp_server_id?: string;
  safety_mode?: boolean;
  max_steps?: number;
}

export const patchAgent = (agentId: string, payload: AIAgentPatch) =>
  apiJson<AIAgent>(`/api/v1/agents/${agentId}/`, { method: "PATCH", body: JSON.stringify(payload) });

export const deleteAgent = (agentId: string) =>
  apiJson<undefined>(`/api/v1/agents/${agentId}/`, { method: "DELETE" });

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
