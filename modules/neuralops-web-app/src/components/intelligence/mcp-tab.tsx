"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useUiStore } from "@/stores/ui.store";
import { Check, CircleCheck, CircleX, Link2, Lock, Pencil, Plug2, Plus, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogSection } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateNumber, validateRequired, validateUrl as vUrl } from "@/lib/validation";
import { useFormErrors } from "@/hooks/use-form-errors";
import { useDeleteMcpServer, useMcpOAuthConnect, useMcpServers } from "@/hooks/use-intelligence";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useProjects } from "@/hooks/use-workspace";
import type { MCPServer, MCPServerCreate, MCPServerPatch } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, ProjectSelect, TabShell, Toolbar } from "./shared";
import { McpAuthSection, draftFromConfig, draftToPayload, emptyOAuthDraft, validateOAuth, type OAuthDraft } from "./mcp-auth-section";
import { CapabilityEditor } from "./capability-editor";
import { ConnectionCheckPanel, useMcpConnectionFlow, type SaveOutcome } from "./mcp-connection-check";
import { capabilityLabels, defaultCapabilityConfig, formatCapabilityConfig, type CapabilityConfig } from "@/lib/mcp-capabilities";

// A server's connection identity: same URL + same auth config = the same
// connection. The client secret is write-only (never returned), so a duplicate
// is identified by the non-secret fields — enough to catch a re-registration.
function connSignature(
  url: string | null | undefined,
  authType: string,
  cfg: { client_id?: string; authorize_endpoint?: string; token_endpoint?: string; scopes?: string[]; token_env_var?: string } | null,
): string {
  // Normalize scheme+host (case-insensitive) but keep the path/query case —
  // paths ARE case-sensitive, so "/MCP" and "/mcp" are different endpoints.
  const raw = (url ?? "").trim().replace(/\/+$/, "");
  let u = raw.toLowerCase();
  try { const p = new URL(raw); u = `${p.protocol}//${p.host.toLowerCase()}${p.pathname.replace(/\/+$/, "")}${p.search}`; } catch { /* partial input — best-effort lowercase */ }
  if (authType !== "oauth2") return `${authType}|${u}`;
  const c = cfg ?? {};
  const scopes = [...(c.scopes ?? [])].map((s) => s.trim()).filter(Boolean).sort().join(" ");
  return ["oauth2", u, c.client_id ?? "", c.authorize_endpoint ?? "", c.token_endpoint ?? "", scopes, c.token_env_var ?? ""].join("|");
}

// The four transports the server accepts. URL transports are "remote"
// servers; STDIO is a "local" one NeuralOps launches from a command. The
// transport is fixed after creation (the server's PATCH has no such field).
const TRANSPORTS = [
  { value: "http", label: "HTTP" },
  { value: "sse", label: "SSE" },
  { value: "websocket", label: "WebSocket" },
  { value: "stdio", label: "STDIO — a local command" },
] as const;
const isStdio = (transport: string) => transport === "stdio";
// server_type: where the server runs. remote/local follow the transport by
// default; docker, kubernetes and hosted are explicit choices with their own
// fields. Fixed after creation (the server's PATCH has no server_type).
const RUNTIMES = [
  { value: "remote", label: "Remote — reached by URL" },
  { value: "local", label: "Local — a command on this server" },
  { value: "docker", label: "Docker container" },
  { value: "kubernetes", label: "Kubernetes service" },
  { value: "hosted", label: "Hosted / online provider" },
] as const;
const runtimeFor = (transport: string) => (isStdio(transport) ? "local" : "remote");
const runtimeLabel = (v: string) => RUNTIMES.find((r) => r.value === v)?.label ?? v;
const selectClass = "h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]";
// What identifies a server's connection: its URL, or for STDIO its command.
const endpointOf = (s: { transport: string; url: string | null; command: string | null }) => (isStdio(s.transport) ? s.command : s.url);
// Server defaults for a call: 60s per tool call, 3 retries.
const validateTimeout = (v: string) => validateNumber(v, { label: "the timeout", min: 1, max: 3600, integer: true });
const validateRetries = (v: string) => validateNumber(v, { label: "the retry count", min: 0, max: 10, integer: true });

// The worker receives `config` verbatim with the server, so it must be a JSON
// object — anything else is caught here, before a 400 or a confusing runtime.
function parseConfig(text: string): { value?: Record<string, unknown>; error?: string } {
  const t = text.trim();
  if (!t) return { value: {} };
  try {
    const v: unknown = JSON.parse(t);
    if (!v || typeof v !== "object" || Array.isArray(v)) return { error: "Extra configuration must be a JSON object, like {\"root_path\": \"/data\"}." };
    return { value: v as Record<string, unknown> };
  } catch {
    return { error: "Extra configuration must be a JSON object, like {\"root_path\": \"/data\"}." };
  }
}
const formatConfig = (c: Record<string, unknown> | null | undefined) => (c && Object.keys(c).length ? JSON.stringify(c, null, 2) : "");

function RuntimeFields({ idPrefix, config, onConfig, firstParty, onFirstParty, embed, onEmbed, firstPartyFixed, configError, onConfigBlur }: {
  idPrefix: string;
  config: string; onConfig: (v: string) => void;
  // Runtime validation from the host form: shown in place of the hint.
  configError?: string | null; onConfigBlur?: () => void;
  firstParty: boolean; onFirstParty?: (v: boolean) => void; // absent on edit — fixed server-side
  embed: boolean; onEmbed: (v: boolean) => void;
  firstPartyFixed?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <Label htmlFor={`${idPrefix}-config`}>Extra configuration <span className="text-ink2">(JSON, optional)</span></Label>
        <textarea
          id={`${idPrefix}-config`}
          rows={3}
          value={config}
          aria-invalid={!!configError}
          onChange={(e) => onConfig(e.target.value)}
          onBlur={onConfigBlur}
          placeholder={'{"root_path": "/data"}'}
          spellCheck={false}
          className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2 font-mono text-[12.5px] leading-relaxed outline-none focus:border-accent"
        />
        {configError ? <FieldError>{configError}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Non-secret settings handed to the server as-is. Secrets go under Authentication.</p>}
      </div>
      {firstPartyFixed ? (
        <p className="text-[12px] text-ink2">{firstParty ? "First-party server (published by us)." : "Third-party server."} Fixed after creation.</p>
      ) : (
        <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={firstParty} onChange={(e) => { onFirstParty?.(e.target.checked); if (!e.target.checked) onEmbed(false); }} className="mt-0.5 accent-[var(--accent)]" />
          First-party server (published by us) — the only kind whose tool output may be embedded
        </label>
      )}
      <label className={`flex items-start gap-2.5 text-[12.5px] ${firstParty ? "text-ink2" : "text-ink2/60"}`}>
        <input type="checkbox" checked={embed} disabled={!firstParty} onChange={(e) => onEmbed(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
        Embed tool output into the project&apos;s knowledge base
      </label>
    </div>
  );
}

// Two kinds of tool source share one table server-side (#104). EXTERNAL is a
// real MCP server reached over a transport; INTERNAL is a set of built-in
// capabilities the AI worker provides in-process, configured by JSON — no
// transport, endpoint, credentials or call settings apply. Fixed after
// creation (a flip would wipe the endpoint and credentials server-side).
type Kind = "external" | "internal";
const KINDS: { value: Kind; label: string; blurb: string }[] = [
  { value: "external", label: "External MCP server", blurb: "Reached over HTTP, SSE or WebSocket, or run as a local STDIO command." },
  { value: "internal", label: "Built-in capabilities", blurb: "Filesystem, shell, web search and more — provided in-process, no server to run." },
];

function KindSwitch({ value, onChange }: { value: Kind; onChange: (k: Kind) => void }) {
  return (
    <fieldset>
      <legend className="mb-1.5 block text-[13px] font-medium text-ink2">Kind</legend>
      <div role="radiogroup" aria-label="Kind" className="grid gap-2 sm:grid-cols-2">
        {KINDS.map((k) => {
          const on = k.value === value;
          return (
            <label key={k.value} className={`flex cursor-pointer items-start gap-2.5 rounded-[10px] border px-3 py-2.5 text-[13px] transition-colors ${on ? "border-accent bg-accent/10" : "border-line bg-surface hover:border-accent/50"}`}>
              <input type="radio" name="mcp-kind" value={k.value} checked={on} onChange={() => onChange(k.value)} className="mt-0.5 accent-[var(--accent)]" />
              <span className="min-w-0">
                <span className="font-medium">{k.label}</span>
                <span className="block text-[12px] text-ink2">{k.blurb}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function CapabilityMeta({ config }: { config: CapabilityConfig }) {
  const labels = capabilityLabels(config);
  return labels.length ? <span className="truncate" title={labels.join(", ")}>{labels.join(" · ")}</span> : <span>no capabilities on</span>;
}

function RuntimeDetails({ idPrefix, runtime, image, dockerCommand, service, onImage, onDockerCommand, onService }: {
  idPrefix: string; runtime: string;
  image: string; dockerCommand: string; service: string;
  onImage: (v: string) => void; onDockerCommand: (v: string) => void; onService: (v: string) => void;
}) {
  if (runtime === "docker") {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor={`${idPrefix}-image`}>Docker image</Label>
          <Input id={`${idPrefix}-image`} placeholder="ghcr.io/org/mcp-server:1.2" value={image} onChange={(e) => onImage(e.target.value)} className="font-mono" />
        </div>
        <div>
          <Label htmlFor={`${idPrefix}-dcmd`}>Container command <span className="text-ink2">(optional)</span></Label>
          <Input id={`${idPrefix}-dcmd`} placeholder="mcp-server --port 8080" value={dockerCommand} onChange={(e) => onDockerCommand(e.target.value)} className="font-mono" />
        </div>
        <p className="col-span-full -mt-1 text-[12px] text-ink2">Stored with the server for the runtime that starts the container; the AI worker reaches it over the transport above.</p>
      </div>
    );
  }
  if (runtime === "kubernetes") {
    return (
      <div>
        <Label htmlFor={`${idPrefix}-svc`}>Kubernetes service</Label>
        <Input id={`${idPrefix}-svc`} placeholder="mcp-tools.default.svc.cluster.local" value={service} onChange={(e) => onService(e.target.value)} className="font-mono" />
        <p className="mt-1.5 text-[12px] text-ink2">Stored with the server for the cluster runtime; the AI worker reaches it over the transport above.</p>
      </div>
    );
  }
  return null;
}

function CallSettings({ idPrefix, timeout, retries, onTimeout, onRetries, errors, onBlur }: {
  idPrefix: string; timeout: string; retries: string; onTimeout: (v: string) => void; onRetries: (v: string) => void;
  // Runtime validation from the host form, per field.
  errors?: { timeout?: string | null; retries?: string | null };
  onBlur?: (field: "timeout" | "retries") => void;
}) {
  return (
    <div className="grid max-w-sm grid-cols-2 gap-3">
      <div>
        <Label htmlFor={`${idPrefix}-timeout`} required>Timeout (seconds)</Label>
        <Input id={`${idPrefix}-timeout`} type="number" required min={1} max={3600} step={1} inputMode="numeric" value={timeout} aria-invalid={!!errors?.timeout} onChange={(e) => onTimeout(e.target.value)} onBlur={() => onBlur?.("timeout")} />
        <FieldError>{errors?.timeout}</FieldError>
      </div>
      <div>
        <Label htmlFor={`${idPrefix}-retries`} required>Max retries</Label>
        <Input id={`${idPrefix}-retries`} type="number" required min={0} max={10} step={1} inputMode="numeric" value={retries} aria-invalid={!!errors?.retries} onChange={(e) => onRetries(e.target.value)} onBlur={() => onBlur?.("retries")} />
        <FieldError>{errors?.retries}</FieldError>
      </div>
      <p className="col-span-2 -mt-1 text-[12px] text-ink2">Per tool call: how long to wait for the server, and how many times to retry a failed call.</p>
    </div>
  );
}

export function McpTab({ embedded, defaultProjectId }: { embedded?: boolean; defaultProjectId?: string } = {}) {
  // mcp_server.* create/update/delete are PROJECT-scope rights.
  const role = useConnectionStore((s) => s.connection?.role);
  const { data: projects } = useProjects();
  const { data: servers, isLoading, error, refetch } = useMcpServers();
  const canManage = isCompanyAdmin(role);
  const canTouch = isCompanyAdmin(role);
  const connect = useMcpOAuthConnect();
  const [creating, setCreating] = useState(false);
  // One-shot intent from /add-* slash commands (ui.store.intelCreate).
  const intelCreate = useUiStore((u) => u.intelCreate);
  const setIntelCreate = useUiStore((u) => u.setIntelCreate);
  useEffect(() => {
    if (!intelCreate) return;
    setIntelCreate(false);
    // Deferred: setState directly inside an effect cascades renders (house rule).
    const raf = requestAnimationFrame(() => {
      if (canManage) setCreating(true);
    });
    return () => cancelAnimationFrame(raf);
  }, [intelCreate, setIntelCreate, canManage]);
  const [editing, setEditing] = useState<MCPServer | null>(null);
  const [removing, setRemoving] = useState<MCPServer | null>(null);
  const showLoading = useDelayedLoading(isLoading);
  const del = useDeleteMcpServer();
  const projectName = (id: string) => projects?.find((p) => p.id === id)?.name;

  return (
    <TabShell
      embedded={embedded}
      title="MCP tool servers"
      blurb="External MCP servers by URL or command, plus built-in capabilities the AI worker provides — personas mount both the same way."
      action={!!servers?.length && canManage && (
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <Plus size={14} strokeWidth={2} /> Add server
        </Button>
      )}
    >
      {!!servers?.length && (
        <Toolbar
          facts={[
            `${servers.filter((sv) => !sv.is_internal).length} external`,
            `${servers.filter((sv) => sv.is_internal).length} built-in`,
            `${new Set(servers.map((sv) => sv.project_id)).size} ${new Set(servers.map((sv) => sv.project_id)).size === 1 ? "project" : "projects"}`,
          ]}
        />
      )}
      <ListState
        loading={showLoading}
        error={error}
        onRetry={refetch}
        empty={servers?.length === 0}
        emptyTitle="No MCP tool servers yet"
        emptyIcon={<Plug2 size={24} strokeWidth={1.8} />}
        emptyHint={canManage ? "Point at any MCP server and your personas can start acting, not just answering." : "An admin can register MCP servers to give personas tools."}
        emptyAction={canManage ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} strokeWidth={2} /> Add server</Button> : undefined}
      />
      {!showLoading && !!servers?.length && (
        <CardGrid>
          {servers.map((s) => (
            <EntityCard
              key={s.id}
              icon={s.is_internal
                ? <Sparkles size={17} strokeWidth={2} className="text-accent" />
                : <Plug2 size={17} strokeWidth={2} className={s.auth_type === "oauth2" ? (s.oauth_connected ? "text-ok" : "text-crit") : undefined} />}
              title={s.name}
              chips={
                <>
                  {s.is_internal ? <Chip tone="accent">built-in</Chip> : <Chip>{s.transport}</Chip>}
                  {s.is_default && <Chip tone="ok">default</Chip>}
                  {projectName(s.project_id) && <Chip tone="accent">{projectName(s.project_id)}</Chip>}
                  {!s.is_internal && s.auth_type === "oauth2" && (
                    <>
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${s.oauth_connected ? "border-ok/40 bg-ok/10 text-ok" : "border-crit/40 bg-crit/10 text-crit"}`}>
                        {s.oauth_connected ? <CircleCheck size={11} strokeWidth={2.6} /> : <CircleX size={11} strokeWidth={2.6} />}
                        {s.oauth_connected ? "connected" : "not connected"}
                      </span>
                      {canTouch && (
                        <button
                          type="button"
                          title={s.oauth_connected ? "Reconnect — sign in to the provider again" : "Sign in to the provider"}
                          onClick={() => connect.mutate({ serverId: s.id, name: s.name, wasConnected: s.oauth_connected, beforeExpiry: s.oauth_config?.expires_at ?? null })}
                          disabled={connect.isPending}
                          className={`inline-flex cursor-pointer items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold transition-colors disabled:cursor-default disabled:opacity-60 ${s.oauth_connected ? "border border-line text-ink2 hover:bg-surface2 hover:text-ink" : "bg-accent text-accent-ink hover:brightness-105"}`}
                        >
                          <Link2 size={11} strokeWidth={2.4} />
                          {connect.isPending && connect.variables?.serverId === s.id ? "Connecting…" : s.oauth_connected ? "Reconnect" : "Connect"}
                        </button>
                      )}
                    </>
                  )}
                </>
              }
              body={s.description ?? undefined}
              meta={s.is_internal ? <CapabilityMeta config={s.capability_config} /> : (
                <>
                  {endpointOf(s) && <span title={endpointOf(s) ?? undefined} className="truncate font-mono">{endpointOf(s)}</span>}
                  <span>timeout {s.timeout_seconds}s</span>
                  {s.auth_type === "oauth2" && s.oauth_connected && s.oauth_config?.expires_at && (
                    <span
                      title="Access tokens refresh automatically on next use — you only need to Reconnect if you revoke access on the provider."
                      className="inline-flex items-center gap-1"
                    >
                      <RefreshCw size={11} strokeWidth={2} />
                      token renews after {new Date(s.oauth_config.expires_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
                    </span>
                  )}
                </>
              )}
              actions={canTouch && (
                <>
                  <button
                    aria-label={`Edit MCP server ${s.name}`}
                    title="Edit server"
                    onClick={() => setEditing(s)}
                    className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                  >
                    <Pencil size={14} strokeWidth={2} />
                  </button>
                  {s.is_protected ? (
                    // The project's provisioned default: the server refuses to
                    // delete it, so the action is not offered — the lock says why.
                    <span
                      role="img"
                      aria-label={`${s.name} is this project's default and cannot be removed`}
                      title="This project's default capabilities — not removable"
                      className="flex size-7 items-center justify-center rounded-md text-ink2/60"
                    >
                      <Lock size={13} strokeWidth={2} />
                    </span>
                  ) : (
                    <button
                      aria-label={`Remove MCP server ${s.name}`}
                      title={s.is_internal ? "Remove capabilities" : "Remove server"}
                      onClick={() => setRemoving(s)}
                      className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </button>
                  )}
                </>
              )}
            />
          ))}
        </CardGrid>
      )}
      <CreateMcpDialog open={creating} onClose={() => setCreating(false)} defaultProjectId={defaultProjectId} />
      {editing && (
        <EditMcpDialog
          key={editing.id}
          server={editing}
          onClose={() => setEditing(null)}
          siblings={(servers ?? []).filter((x) => x.id !== editing.id)}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) del.mutate(removing.id);
          setRemoving(null);
        }}
        title={removing?.is_internal ? "Remove these built-in capabilities?" : "Remove this MCP tool server?"}
        body={
          <p>
            <b className="text-ink">{removing?.name}</b> will be removed. If a persona still mounts it, the
            server refuses and names the persona — untick it there first.
          </p>
        }
        confirmLabel={removing?.is_internal ? "Remove capabilities" : "Remove server"}
        loading={del.isPending}
      />
    </TabShell>
  );
}

export function CreateMcpDialog({ open, onClose, defaultProjectId, onCreated }: {
  open: boolean;
  onClose: () => void;
  defaultProjectId?: string;
  // Launched inline from the persona builder: hands the new server back so the
  // host can tick it — no tab-hopping.
  onCreated?: (s: MCPServer) => void;
}) {
  const { data: allProjects } = useProjects();
  const { data: servers } = useMcpServers();
  const [projectId, setProjectId] = useState(defaultProjectId ?? "");
  const [kind, setKind] = useState<Kind>("external");
  const [caps, setCaps] = useState<CapabilityConfig>(() => defaultCapabilityConfig());
  const [capErr, setCapErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<string>("http");
  // null = follows the transport (remote/local); set once the user picks.
  const [runtime, setRuntime] = useState<string | null>(null);
  const [dockerImage, setDockerImage] = useState("");
  const [dockerCommand, setDockerCommand] = useState("");
  const [k8sService, setK8sService] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [timeout, setTimeout_] = useState("60");
  const [retries, setRetries] = useState("3");
  const [config, setConfig] = useState("");
  const [firstParty, setFirstParty] = useState(false);
  const [embed, setEmbed] = useState(false);
  const [authType, setAuthType] = useState<MCPServer["auth_type"]>("none");
  const [oauth, setOauth] = useState<OAuthDraft>(emptyOAuthDraft);
  const stdio = isStdio(transport);

  const validateName = (v: string) => {
    const shared = vName(v, { label: "server name" });
    if (shared) return shared;
    // Names are unique PER PROJECT (matches the server rule) — the same name
    // in another project is legal.
    if (servers?.some((s) => s.project_id === projectId && s.name.toLowerCase() === v.trim().toLowerCase()))
      return "This project already has an MCP server with this name.";
    return null;
  };
  // URL transports need a URL; STDIO needs the command instead — the same
  // either/or the server enforces with its check constraints.
  const validateUrl = (v: string) => (stdio ? validateRequired(command, "the command") : vUrl(v, { label: "the server URL" }));

  const internal = kind === "internal";
  const serverType = runtime ?? runtimeFor(transport);
  // Duplicate CONNECTION guard: the same endpoint + auth config already
  // registered in this project is a duplicate even under a different name.
  const mySig = connSignature(stdio ? command : url, authType, authType === "oauth2" ? draftToPayload(oauth).oauth_config : null);
  const dupConn = internal ? undefined : servers?.find((s) => s.project_id === projectId && connSignature(endpointOf(s), s.auth_type, s.oauth_config ?? null) === mySig);
  // Every rule the submit needs, derived live: the button gates on all of
  // them, each field shows its own once visited. capJson is the editor's own
  // parse error — it displays it itself, so it only gates here.
  const form = useFormErrors({
    project: [projectId, projectId ? null : internal ? "Pick the project these capabilities belong to." : "Pick the project this server belongs to."],
    name: [name, validateName(name)],
    caps: internal && Object.keys(caps).length === 0 ? "Turn on at least one capability." : null,
    capJson: internal ? capErr : null,
    url: [stdio ? command : url, internal ? null : validateUrl(url) ?? (dupConn ? `This project already has a server with these exact connection details ("${dupConn.name}").` : null)],
    timeout: [timeout, internal ? null : validateTimeout(timeout)],
    retries: [retries, internal ? null : validateRetries(retries)],
    config: [config, internal ? null : parseConfig(config).error ?? null],
    oauth: [oauth.client_id || oauth.authorize_endpoint || oauth.token_endpoint || oauth.client_secret, !internal && authType === "oauth2" ? validateOAuth(oauth, { isEdit: false, hasStoredSecret: false }) : null],
  });

  const qc = useQueryClient();
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const flow = useMcpConnectionFlow(serverUrl);
  // Set once the row exists with an OAuth sign-in still pending: later
  // submits patch it instead of creating a second one, and closing leaves
  // it saved.
  const [createdId, setCreatedId] = useState<string | null>(null);
  const invalidate = () => Promise.all([
    qc.invalidateQueries({ queryKey: ["mcp-servers", serverUrl] }),
    qc.invalidateQueries({ queryKey: ["personas", serverUrl] }),
  ]);

  const reset = () => {
    setCreatedId(null);
    flow.reset();
    setProjectId(defaultProjectId ?? "");
    setKind("external");
    setCaps(defaultCapabilityConfig());
    setCapErr(null);
    setName("");
    setTransport("http");
    setRuntime(null);
    setDockerImage("");
    setDockerCommand("");
    setK8sService("");
    setUrl("");
    setCommand("");
    setDescription("");
    setTimeout_("60");
    setRetries("3");
    setConfig("");
    setFirstParty(false);
    setEmbed(false);
    setAuthType("none");
    setOauth(emptyOAuthDraft());
    form.reset();
  };
  const close = () => {
    reset();
    onClose();
  };
  const projName = allProjects?.find((p) => p.id === projectId)?.name;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    // The button is gated on form.invalid; a submit that slips through
    // reveals every message instead of posting.
    if (form.invalid) return form.touchAll();
    if (flow.busy) return;
    void save(false);
  };

  // Everything the row needs, as the create API takes it.
  const buildPayload = (): MCPServerCreate => {
    if (internal) {
      // Only the fields an internal row has — the server clears the rest and
      // forces auth_type to "none" anyway.
      return { project_id: projectId, name: name.trim(), description: description.trim() || undefined, is_internal: true, capability_config: caps };
    }
    const cfg = parseConfig(config);
    return {
      project_id: projectId, name: name.trim(),
      transport, server_type: serverType,
      ...(stdio ? { command: command.trim() } : { url: url.trim() }),
      ...(serverType === "docker" ? { docker_image: dockerImage.trim() || undefined, docker_command: dockerCommand.trim() || undefined } : {}),
      ...(serverType === "kubernetes" ? { kubernetes_service: k8sService.trim() || undefined } : {}),
      description: description.trim() || undefined,
      timeout_seconds: Number(timeout), max_retries: Number(retries),
      config: cfg.value, is_first_party: firstParty, embed_output: firstParty && embed,
      auth_type: authType,
      ...(authType === "oauth2" ? draftToPayload(oauth)
        : authType === "static_secrets" && oauth.client_secret.trim() ? { client_secret: oauth.client_secret.trim() }
        : {}),
    };
  };
  // A row created earlier in this dialog is patched with the same fields
  // minus the ones fixed at creation.
  const toPatch = (p: MCPServerCreate): MCPServerPatch => ({
    name: p.name, description: p.description, url: p.url, command: p.command,
    docker_image: p.docker_image, docker_command: p.docker_command, kubernetes_service: p.kubernetes_service,
    timeout_seconds: p.timeout_seconds, max_retries: p.max_retries, config: p.config, embed_output: p.embed_output,
    auth_type: p.auth_type, oauth_config: p.oauth_config, client_secret: p.client_secret, capability_config: p.capability_config,
  });
  const secretForCheck = authType === "static_secrets" && oauth.client_secret.trim() ? { client_secret: oauth.client_secret.trim() } : {};
  const done = (server: MCPServer, outcome: SaveOutcome) => {
    const tools = outcome.tools === 1 ? "1 tool" : `${outcome.tools} tools`;
    toast.success(
      internal ? `"${server.name}" added.`
        : outcome.connected ? `"${server.name}" added and connected — ${tools} available.`
        : outcome.checked ? `"${server.name}" added — ${tools} available.`
        : `"${server.name}" added without a connection check.`,
    );
    void invalidate();
    onCreated?.(server);
    close();
  };
  // Check the connection the way a run would, then save; an OAuth server
  // then opens its sign-in. The dialog stays open until every step passed.
  const save = (skipCheck: boolean) => {
    const payload = buildPayload();
    return flow.run({
      serverId: createdId ?? undefined,
      probe: {
        project_id: projectId, transport,
        url: stdio ? undefined : url.trim(), command: stdio ? command.trim() : undefined,
        config: parseConfig(config).value, timeout_seconds: Number(timeout), auth_type: authType,
        ...secretForCheck,
        ...(authType === "oauth2" ? { oauth_config: draftToPayload(oauth).oauth_config } : {}),
      },
      payload: createdId ? toPatch(payload) : payload,
      oauth: !internal && authType === "oauth2",
      skipCheck: internal || skipCheck,
      onCreated: (s) => { setCreatedId(s.id); void invalidate(); },
      onSaved: done,
    });
  };
  const signsIn = !internal && authType === "oauth2";
  const submitLabel = internal ? "Add capabilities"
    : createdId ? (signsIn ? "Save & sign in" : "Save & check again")
    : signsIn ? "Add & sign in" : "Add server";

  return (
    <Dialog
      open={open}
      onClose={close}
      size="2xl"
      title={`${internal ? "Add built-in capabilities" : "Add an MCP tool server"}${projName ? ` — ${projName}` : ""}`}
      description={internal
        ? "Capabilities the AI worker provides in-process — filesystem, shell, web search and more. Personas in the owning project mount them like any tool source."
        : "Any server that speaks the Model Context Protocol — reached by URL over HTTP, SSE or WebSocket, or run as a local command over STDIO. Personas in the owning project can mount its tools."}
      icon={internal ? <Sparkles size={17} strokeWidth={2} /> : <Plug2 size={17} strokeWidth={2} />}
      tone="accent"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="min-w-0 flex-1 basis-full sm:basis-0">
            <ConnectionCheckPanel status={flow.status} target={stdio ? command.trim() : url.trim()} onSaveAnyway={() => void save(true)} onSignIn={flow.retrySignIn} />
          </div>
          <Button type="button" size="sm" onClick={close}><X size={14} strokeWidth={2} /> {createdId ? "Done for now" : "Cancel"}</Button>
          <Button type="submit" form="mcp-form" size="sm" variant="primary" disabled={form.invalid} loading={flow.busy}><Plus size={14} strokeWidth={2} /> {submitLabel}</Button>
        </div>
      }
    >
      <form id="mcp-form" onSubmit={submit} noValidate className="flex flex-col">
        <DialogSection title="Basics" hint="What kind of tool source this is, and the project that owns it.">
        <KindSwitch value={kind} onChange={setKind} />
        <ProjectSelect id="mcp-project" value={projectId} onChange={setProjectId} only={allProjects ?? []} onBlur={() => form.touch("project")} error={form.error("project")} />
        <div>
          <Label htmlFor="mcp-name" required>Name</Label>
          <Input
            id="mcp-name"
            required
            autoFocus
            placeholder={internal ? "e.g. Research capabilities" : "e.g. Warehouse tools"}
            value={name}
            aria-invalid={!!form.error("name")}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => form.touch("name")}
            maxLength={100}
          />
          <FieldError>{form.error("name")}</FieldError>
        </div>
        <div>
          <Label htmlFor="mcp-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="mcp-desc" placeholder={internal ? "What are these for?" : "What tools does it expose?"} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        </DialogSection>
        {internal && (
          <DialogSection title="Capabilities" hint="What a persona mounting this row can do, and how each capability is configured.">
            <CapabilityEditor idPrefix="mcp" value={caps} onChange={(v) => { setCaps(v); form.touch("caps"); }} onError={setCapErr} />
            <FieldError>{form.error("caps")}</FieldError>
          </DialogSection>
        )}
        {!internal && (
          <>
        <DialogSection title="Connection" hint="How the AI worker reaches the server.">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
          <div>
            <Label htmlFor="mcp-transport">Transport</Label>
            <select
              id="mcp-transport"
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
              className={selectClass}
            >
              {TRANSPORTS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          {stdio ? (
            <div>
              <Label htmlFor="mcp-command" required>Command</Label>
              <Input
                id="mcp-command"
                required
                placeholder="npx -y @modelcontextprotocol/server-filesystem /data"
                value={command}
                aria-invalid={!!form.error("url")}
                onChange={(e) => setCommand(e.target.value)}
                onBlur={() => form.touch("url")}
                className="font-mono"
              />
              {form.error("url") ? <FieldError>{form.error("url")}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Runs on the NeuralOps server; its tools are read over stdin/stdout.</p>}
            </div>
          ) : (
            <div>
              <Label htmlFor="mcp-url" required>URL</Label>
              <Input
                id="mcp-url"
                required
                inputMode="url"
                placeholder="http://tools.internal:8080/mcp"
                value={url}
                aria-invalid={!!form.error("url")}
                onChange={(e) => setUrl(e.target.value)}
                onBlur={() => form.touch("url")}
                className="font-mono"
              />
              <FieldError>{form.error("url")}</FieldError>
            </div>
          )}
        </div>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
              <div>
                <Label htmlFor="mcp-runtime">Runs as</Label>
                <select id="mcp-runtime" value={serverType} onChange={(e) => setRuntime(e.target.value)} className={selectClass}>
                  {RUNTIMES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              <RuntimeDetails idPrefix="mcp" runtime={serverType} image={dockerImage} dockerCommand={dockerCommand} service={k8sService} onImage={setDockerImage} onDockerCommand={setDockerCommand} onService={setK8sService} />
            </div>
        </DialogSection>
        <DialogSection title="Calls">
            <CallSettings idPrefix="mcp" timeout={timeout} retries={retries} onTimeout={setTimeout_} onRetries={setRetries} errors={{ timeout: form.error("timeout"), retries: form.error("retries") }} onBlur={form.touch} />
        </DialogSection>
        <DialogSection title="Runtime">
            <RuntimeFields idPrefix="mcp" config={config} onConfig={setConfig} firstParty={firstParty} onFirstParty={setFirstParty} embed={embed} onEmbed={setEmbed} configError={form.error("config")} onConfigBlur={() => form.touch("config")} />
        </DialogSection>
        <DialogSection title="Access" hint="How the worker authenticates to the server.">
            {/* Blur bubbles: leaving any OAuth field is the cue to judge the set. */}
            <div onBlur={() => form.touch("oauth")}>
              <McpAuthSection authType={authType} onAuthType={setAuthType} oauth={oauth} onOauth={setOauth} isEdit={false} hasStoredSecret={false} onSuggestUrl={(u) => { if (!stdio && !url.trim()) setUrl(u); }} />
              <FieldError>{form.error("oauth")}</FieldError>
            </div>
        </DialogSection>
          </>
        )}
      </form>
    </Dialog>
  );
}

function EditMcpDialog({ server, onClose, siblings }: { server: MCPServer; onClose: () => void; siblings: MCPServer[] }) {
  const [name, setName] = useState(server.name);
  const [caps, setCaps] = useState<CapabilityConfig>(() => structuredClone(server.capability_config ?? {}));
  const [capErr, setCapErr] = useState<string | null>(null);
  const [url, setUrl] = useState(server.url ?? "");
  const [command, setCommand] = useState(server.command ?? "");
  const [dockerImage, setDockerImage] = useState(server.docker_image ?? "");
  const [dockerCommand, setDockerCommand] = useState(server.docker_command ?? "");
  const [k8sService, setK8sService] = useState(server.kubernetes_service ?? "");
  const [description, setDescription] = useState(server.description ?? "");
  const [timeout, setTimeout_] = useState(String(server.timeout_seconds));
  const [retries, setRetries] = useState(String(server.max_retries));
  const [config, setConfig] = useState(() => formatConfig(server.config));
  const [embed, setEmbed] = useState(server.embed_output);
  const [authType, setAuthType] = useState<MCPServer["auth_type"]>(server.auth_type);
  const stdio = isStdio(server.transport);
  const [oauth, setOauth] = useState<OAuthDraft>(() => draftFromConfig(server.oauth_config));
  const qc = useQueryClient();
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const flow = useMcpConnectionFlow(serverUrl);
  // The change set of the submit in progress, kept for "Save without checking".
  const [pending, setPending] = useState<MCPServerPatch | null>(null);

  const validateName = (v: string) => {
    const shared = vName(v, { label: "server name" });
    if (shared) return shared;
    // Per-project uniqueness, matching the server rule.
    if (siblings.some((x) => x.project_id === server.project_id && x.name.toLowerCase() === v.trim().toLowerCase()))
      return "This project already has an MCP server with this name.";
    return null;
  };
  const validateUrl = (v: string) => (stdio ? validateRequired(command, "the command") : vUrl(v, { label: "the server URL" }));
  const form = useFormErrors({
    name: [name, validateName(name)],
    caps: server.is_internal && Object.keys(caps).length === 0 ? "Turn on at least one capability." : null,
    capJson: server.is_internal ? capErr : null,
    url: [stdio ? command : url, server.is_internal ? null : validateUrl(url)],
    timeout: [timeout, server.is_internal ? null : validateTimeout(timeout)],
    retries: [retries, server.is_internal ? null : validateRetries(retries)],
    config: [config, server.is_internal ? null : parseConfig(config).error ?? null],
    // A client_secret is already stored whenever the server was ALREADY
    // oauth2 (create/edit both require one) — regardless of whether the
    // OAuth sign-in completed (oauth_connected = refresh_token present).
    // Switching static→oauth2 here has no stored secret yet, so it's required.
    oauth: [oauth.client_id || oauth.authorize_endpoint || oauth.token_endpoint || oauth.client_secret, !server.is_internal && authType === "oauth2" ? validateOAuth(oauth, { isEdit: true, hasStoredSecret: server.auth_type === "oauth2" }) : null],
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (form.invalid) return form.touchAll();
    if (server.is_internal) {
      const payload = {
        ...(name.trim() !== server.name ? { name: name.trim() } : {}),
        ...(description.trim() !== (server.description ?? "") ? { description: description.trim() } : {}),
        ...(formatCapabilityConfig(caps) !== formatCapabilityConfig(server.capability_config) ? { capability_config: caps } : {}),
      };
      if (Object.keys(payload).length === 0) return onClose();
      void save(payload, true);
      return;
    }
    const cfg = parseConfig(config);
    const authChanged = authType !== server.auth_type;
    const oauthTouched = authType === "oauth2" && (authChanged
      || oauth.client_id.trim() !== (server.oauth_config?.client_id ?? "")
      || oauth.authorize_endpoint.trim() !== (server.oauth_config?.authorize_endpoint ?? "")
      || oauth.token_endpoint.trim() !== (server.oauth_config?.token_endpoint ?? "")
      || oauth.token_env_var.trim() !== (server.oauth_config?.token_env_var ?? "OAUTH_ACCESS_TOKEN")
      || oauth.scopes.trim() !== (server.oauth_config?.scopes ?? []).join(" ")
      || !!oauth.client_secret.trim());
    const authPayload =
      authType === "oauth2" && oauthTouched ? { auth_type: authType, ...draftToPayload(oauth) }
      : authType === "static_secrets" && (authChanged || oauth.client_secret.trim())
        ? { auth_type: authType, ...(oauth.client_secret.trim() ? { client_secret: oauth.client_secret.trim() } : {}) }
      : authChanged ? { auth_type: authType }
      : {};
    const payload = {
      ...(name.trim() !== server.name ? { name: name.trim() } : {}),
      ...(!stdio && url.trim() !== (server.url ?? "") ? { url: url.trim() } : {}),
      ...(stdio && command.trim() !== (server.command ?? "") ? { command: command.trim() } : {}),
      ...(server.server_type === "docker" && dockerImage.trim() !== (server.docker_image ?? "") ? { docker_image: dockerImage.trim() } : {}),
      ...(server.server_type === "docker" && dockerCommand.trim() !== (server.docker_command ?? "") ? { docker_command: dockerCommand.trim() } : {}),
      ...(server.server_type === "kubernetes" && k8sService.trim() !== (server.kubernetes_service ?? "") ? { kubernetes_service: k8sService.trim() } : {}),
      ...(description.trim() !== (server.description ?? "") ? { description: description.trim() } : {}),
      ...(Number(timeout) !== server.timeout_seconds ? { timeout_seconds: Number(timeout) } : {}),
      ...(Number(retries) !== server.max_retries ? { max_retries: Number(retries) } : {}),
      ...(JSON.stringify(cfg.value) !== JSON.stringify(server.config ?? {}) ? { config: cfg.value } : {}),
      ...(embed !== server.embed_output ? { embed_output: embed } : {}),
      ...authPayload,
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    setPending(payload);
    void save(payload, false);
  };

  // Check the connection as changed (stored secrets fill in what is not
  // re-typed), then patch; an OAuth server not yet signed in opens its
  // sign-in after the save.
  const save = (payload: MCPServerPatch, skipCheck: boolean) => {
    if (flow.busy) return;
    return flow.run({
      serverId: server.id,
      probe: {
        server_id: server.id, transport: server.transport,
        url: stdio ? undefined : url.trim(), command: stdio ? command.trim() : undefined,
        config: parseConfig(config).value, timeout_seconds: Number(timeout), auth_type: authType,
        ...(authType === "static_secrets" && oauth.client_secret.trim() ? { client_secret: oauth.client_secret.trim() } : {}),
        ...(authType === "oauth2" ? { oauth_config: draftToPayload(oauth).oauth_config } : {}),
      },
      payload,
      oauth: !server.is_internal && authType === "oauth2",
      skipCheck: server.is_internal || skipCheck,
      onSaved: (s, outcome) => {
        const tools = outcome.tools === 1 ? "1 tool" : `${outcome.tools} tools`;
        toast.success(
          server.is_internal ? `"${s.name}" updated.`
            : outcome.connected ? `"${s.name}" updated and connected — ${tools} available.`
            : outcome.checked ? `"${s.name}" updated — ${tools} available.`
            : `"${s.name}" updated without a connection check.`,
        );
        void Promise.all([
          qc.invalidateQueries({ queryKey: ["mcp-servers", serverUrl] }),
          qc.invalidateQueries({ queryKey: ["personas", serverUrl] }),
        ]);
        onClose();
      },
    });
  };
  const submitLabel = !server.is_internal && authType === "oauth2" && !server.oauth_connected ? "Save & sign in" : "Save changes";

  return (
    <Dialog
      open
      onClose={onClose}
      size="2xl"
      title={`Edit ${server.name}`}
      description={server.is_internal ? "Changes apply to the persona's next run." : "Changes apply to the next tool call — personas pick up the new address automatically."}
      icon={<Pencil size={17} strokeWidth={2} />}
      tone="info"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="min-w-0 flex-1 basis-full sm:basis-0">
            <ConnectionCheckPanel status={flow.status} target={stdio ? command.trim() : url.trim()} onSaveAnyway={() => { if (pending) void save(pending, true); }} onSignIn={flow.retrySignIn} />
          </div>
          <Button type="button" size="sm" onClick={onClose}><X size={14} strokeWidth={2} /> Cancel</Button>
          <Button type="submit" form="mce-form" size="sm" variant="primary" disabled={form.invalid} loading={flow.busy}><Check size={14} strokeWidth={2} /> {submitLabel}</Button>
        </div>
      }
    >
      <form id="mce-form" onSubmit={submit} noValidate className="flex flex-col">
        <DialogSection title="Basics">
        <div>
          <Label htmlFor="mce-name" required>Name</Label>
          <Input
            id="mce-name"
            required
            autoFocus
            value={name}
            aria-invalid={!!form.error("name")}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => form.touch("name")}
            maxLength={100}
          />
          <FieldError>{form.error("name")}</FieldError>
        </div>
        {server.is_internal && (
          <div className="rounded-[10px] border border-line bg-surface2/60 px-3 py-2.5 text-[13px]">
            <p className="text-[12px] text-ink2">Kind <span className="text-ink2/70">(fixed)</span></p>
            <p className="mt-0.5">Built-in capabilities{server.is_default ? " — this project's default" : ""}</p>
          </div>
        )}
        <div>
          <Label htmlFor="mce-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="mce-desc" placeholder={server.is_internal ? "What are these for?" : "What tools does it expose?"} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        </DialogSection>
        {server.is_internal && (
          <DialogSection title="Capabilities" hint="What a persona mounting this row can do, and how each capability is configured.">
            <CapabilityEditor idPrefix="mce" value={caps} onChange={(v) => { setCaps(v); form.touch("caps"); }} onError={setCapErr} />
            <FieldError>{form.error("caps")}</FieldError>
          </DialogSection>
        )}
        {!server.is_internal && (
          <>
        <DialogSection title="Connection" hint="How the AI worker reaches the server. Transport and runtime are fixed after creation.">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
          <div className="rounded-[10px] border border-line bg-surface2/60 px-3 py-2.5 text-[13px]">
            <p className="text-[12px] text-ink2">Transport <span className="text-ink2/70">(fixed)</span></p>
            <p className="mt-0.5"><code className="font-mono text-[12.5px]">{server.transport}</code></p>
          </div>
          {stdio ? (
            <div>
              <Label htmlFor="mce-command" required>Command</Label>
              <Input
                id="mce-command"
                required
                value={command}
                aria-invalid={!!form.error("url")}
                onChange={(e) => setCommand(e.target.value)}
                onBlur={() => form.touch("url")}
                className="font-mono"
              />
              <FieldError>{form.error("url")}</FieldError>
            </div>
          ) : (
            <div>
              <Label htmlFor="mce-url" required>URL</Label>
              <Input
                id="mce-url"
                required
                inputMode="url"
                value={url}
                aria-invalid={!!form.error("url")}
                onChange={(e) => setUrl(e.target.value)}
                onBlur={() => form.touch("url")}
                className="font-mono"
              />
              <FieldError>{form.error("url")}</FieldError>
            </div>
          )}
        </div>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
              <div className="rounded-[10px] border border-line bg-surface2/60 px-3 py-2.5 text-[13px]">
                <p className="text-[12px] text-ink2">Runs as <span className="text-ink2/70">(fixed)</span></p>
                <p className="mt-0.5">{runtimeLabel(server.server_type)}</p>
              </div>
              <RuntimeDetails idPrefix="mce" runtime={server.server_type} image={dockerImage} dockerCommand={dockerCommand} service={k8sService} onImage={setDockerImage} onDockerCommand={setDockerCommand} onService={setK8sService} />
            </div>
        </DialogSection>
        <DialogSection title="Calls">
            <CallSettings idPrefix="mce" timeout={timeout} retries={retries} onTimeout={setTimeout_} onRetries={setRetries} errors={{ timeout: form.error("timeout"), retries: form.error("retries") }} onBlur={form.touch} />
        </DialogSection>
        <DialogSection title="Runtime">
            <RuntimeFields idPrefix="mce" config={config} onConfig={setConfig} firstParty={server.is_first_party} firstPartyFixed embed={embed} onEmbed={setEmbed} configError={form.error("config")} onConfigBlur={() => form.touch("config")} />
        </DialogSection>
        <DialogSection title="Access" hint="How the worker authenticates to the server.">
            <div onBlur={() => form.touch("oauth")}>
              <McpAuthSection authType={authType} onAuthType={setAuthType} oauth={oauth} onOauth={setOauth} isEdit hasStoredSecret={server.auth_type === "oauth2"} onSuggestUrl={(u) => { if (!stdio && !url.trim()) setUrl(u); }} />
              <FieldError>{form.error("oauth")}</FieldError>
            </div>
        </DialogSection>
          </>
        )}
      </form>
    </Dialog>
  );
}
