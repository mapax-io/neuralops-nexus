"use client";

import { useEffect, useState } from "react";
import { useUiStore } from "@/stores/ui.store";
import { CircleCheck, CircleX, Link2, Pencil, Plug2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateNumber, validateRequired, validateUrl as vUrl } from "@/lib/validation";
import { useCreateMcpServer, useDeleteMcpServer, useMcpOAuthConnect, useMcpServers, usePatchMcpServer } from "@/hooks/use-intelligence";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useProjects } from "@/hooks/use-workspace";
import type { MCPServer } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, ProjectSelect, TabShell, Toolbar } from "./shared";
import { McpAuthSection, draftFromConfig, draftToPayload, emptyOAuthDraft, validateOAuth, type OAuthDraft } from "./mcp-auth-section";

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
const selectClass = "h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]";
// What identifies a server's connection: its URL, or for STDIO its command.
const endpointOf = (s: { transport: string; url: string | null; command: string | null }) => (isStdio(s.transport) ? s.command : s.url);
// Server defaults for a call: 60s per tool call, 3 retries.
const validateTimeout = (v: string) => validateNumber(v, { label: "the timeout", min: 1, max: 3600, integer: true });
const validateRetries = (v: string) => validateNumber(v, { label: "the retry count", min: 0, max: 10, integer: true });

function CallSettings({ idPrefix, timeout, retries, onTimeout, onRetries }: {
  idPrefix: string; timeout: string; retries: string; onTimeout: (v: string) => void; onRetries: (v: string) => void;
}) {
  return (
    <div className="grid max-w-sm grid-cols-2 gap-3">
      <div>
        <Label htmlFor={`${idPrefix}-timeout`} required>Timeout (seconds)</Label>
        <Input id={`${idPrefix}-timeout`} type="number" required min={1} max={3600} step={1} inputMode="numeric" value={timeout} onChange={(e) => onTimeout(e.target.value)} />
      </div>
      <div>
        <Label htmlFor={`${idPrefix}-retries`} required>Max retries</Label>
        <Input id={`${idPrefix}-retries`} type="number" required min={0} max={10} step={1} inputMode="numeric" value={retries} onChange={(e) => onRetries(e.target.value)} />
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
      blurb="Tools personas can call over the Model Context Protocol — register any MCP server by URL."
      action={!!servers?.length && canManage && (
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <Plus size={14} strokeWidth={2} /> Add server
        </Button>
      )}
    >
      {!!servers?.length && (
        <Toolbar
          facts={[
            `${servers.length} ${servers.length === 1 ? "server" : "servers"}`,
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
              icon={<Plug2 size={17} strokeWidth={2} className={s.auth_type === "oauth2" ? (s.oauth_connected ? "text-ok" : "text-crit") : undefined} />}
              title={s.name}
              chips={
                <>
                  <Chip>{s.transport}</Chip>
                  {projectName(s.project_id) && <Chip tone="accent">{projectName(s.project_id)}</Chip>}
                  {s.auth_type === "oauth2" && (
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
              meta={
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
              }
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
                  <button
                    aria-label={`Remove MCP server ${s.name}`}
                    title="Remove server"
                    onClick={() => setRemoving(s)}
                    className="flex size-7 cursor-pointer items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                  >
                    <Trash2 size={14} strokeWidth={2} />
                  </button>
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
        title="Remove this MCP tool server?"
        body={
          <p>
            <b className="text-ink">{removing?.name}</b> will be removed. If a persona still mounts it, the
            server refuses and names the persona — untick the server there first.
          </p>
        }
        confirmLabel="Remove server"
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
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<string>("http");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [timeout, setTimeout_] = useState("60");
  const [retries, setRetries] = useState("3");
  const [authType, setAuthType] = useState<MCPServer["auth_type"]>("none");
  const [oauth, setOauth] = useState<OAuthDraft>(emptyOAuthDraft);
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [urlErr, setUrlErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
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

  const reset = () => {
    setProjectId(defaultProjectId ?? "");
    setName("");
    setTransport("http");
    setUrl("");
    setCommand("");
    setDescription("");
    setTimeout_("60");
    setRetries("3");
    setAuthType("none");
    setOauth(emptyOAuthDraft());
    setErr(null);
    setNameErr(null);
    setUrlErr(null);
    setTouched(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateMcpServer((s) => {
    onCreated?.(s);
    close();
  });
  const projName = allProjects?.find((p) => p.id === projectId)?.name;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setTouched(true);
    const ne = validateName(name);
    const ue = validateUrl(url);
    setNameErr(ne);
    setUrlErr(ue);
    if (!projectId) return setErr("Pick the project this server belongs to.");
    if (ne || ue) return;
    const ce = validateTimeout(timeout) ?? validateRetries(retries);
    if (ce) return setErr(ce);
    if (authType === "oauth2") {
      const oe = validateOAuth(oauth, { isEdit: false, hasStoredSecret: false });
      if (oe) return setErr(oe);
    }
    // Duplicate CONNECTION guard: the same endpoint + auth config already
    // registered in this project is a duplicate even under a different name.
    const draftCfg = authType === "oauth2" ? draftToPayload(oauth).oauth_config : null;
    const mySig = connSignature(stdio ? command : url, authType, draftCfg);
    const dupConn = servers?.find((s) => s.project_id === projectId && connSignature(endpointOf(s), s.auth_type, s.oauth_config ?? null) === mySig);
    if (dupConn) return setErr(`This project already has a server with these exact connection details ("${dupConn.name}").`);
    create.mutate({
      project_id: projectId, name: name.trim(),
      transport, server_type: stdio ? "local" : "remote",
      ...(stdio ? { command: command.trim() } : { url: url.trim() }),
      description: description.trim() || undefined,
      timeout_seconds: Number(timeout), max_retries: Number(retries),
      auth_type: authType,
      ...(authType === "oauth2" ? draftToPayload(oauth)
        : authType === "static_secrets" && oauth.client_secret.trim() ? { client_secret: oauth.client_secret.trim() }
        : {}),
    });
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      size="2xl"
      title={`Add an MCP tool server${projName ? ` — ${projName}` : ""}`}
      description="Any server that speaks the Model Context Protocol — reached by URL over HTTP, SSE or WebSocket, or run as a local command over STDIO. Personas in the owning project can mount its tools."
      icon={<Plug2 size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="mcp-form" size="sm" variant="primary" loading={create.isPending}>Add server</Button>
        </div>
      }
    >
      <form id="mcp-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <ProjectSelect id="mcp-project" value={projectId} onChange={setProjectId} only={allProjects ?? []} />
        <div>
          <Label htmlFor="mcp-name" required>Name</Label>
          <Input
            id="mcp-name"
            required
            autoFocus
            placeholder="e.g. Warehouse tools"
            value={name}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validateName(e.target.value));
            }}
            onBlur={() => {
              if (name) {
                setTouched(true); // blur = first judgement; typing then re-validates live
                setNameErr(validateName(name));
              }
            }}
            maxLength={100}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
        <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
          <div>
            <Label htmlFor="mcp-transport">Transport</Label>
            <select
              id="mcp-transport"
              value={transport}
              onChange={(e) => {
                setTransport(e.target.value);
                setUrlErr(null); // the other field's error no longer applies
              }}
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
                aria-invalid={!!urlErr}
                onChange={(e) => {
                  setCommand(e.target.value);
                  if (touched) setUrlErr(validateRequired(e.target.value, "the command"));
                }}
                className="font-mono"
              />
              {urlErr ? <FieldError>{urlErr}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Runs on the NeuralOps server; its tools are read over stdin/stdout.</p>}
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
                aria-invalid={!!urlErr}
                onChange={(e) => {
                  setUrl(e.target.value);
                  if (touched) setUrlErr(validateUrl(e.target.value));
                }}
                onBlur={() => {
                  if (url) {
                    setTouched(true);
                    setUrlErr(validateUrl(url));
                  }
                }}
                className="font-mono"
              />
              <FieldError>{urlErr}</FieldError>
            </div>
          )}
        </div>
        <div>
          <Label htmlFor="mcp-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="mcp-desc" placeholder="What tools does it expose?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <CallSettings idPrefix="mcp" timeout={timeout} retries={retries} onTimeout={setTimeout_} onRetries={setRetries} />
        <McpAuthSection authType={authType} onAuthType={setAuthType} oauth={oauth} onOauth={setOauth} isEdit={false} hasStoredSecret={false} onSuggestUrl={(u) => { if (!stdio && !url.trim()) setUrl(u); }} />
        {authType === "oauth2" && <p className="text-[11.5px] text-ink2">After adding, click <b>Connect</b> on the server to sign in.</p>}
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}

function EditMcpDialog({ server, onClose, siblings }: { server: MCPServer; onClose: () => void; siblings: MCPServer[] }) {
  const [name, setName] = useState(server.name);
  const [url, setUrl] = useState(server.url ?? "");
  const [command, setCommand] = useState(server.command ?? "");
  const [description, setDescription] = useState(server.description ?? "");
  const [timeout, setTimeout_] = useState(String(server.timeout_seconds));
  const [retries, setRetries] = useState(String(server.max_retries));
  const [authType, setAuthType] = useState<MCPServer["auth_type"]>(server.auth_type);
  const stdio = isStdio(server.transport);
  const [oauth, setOauth] = useState<OAuthDraft>(() => draftFromConfig(server.oauth_config));
  const [authErr, setAuthErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [urlErr, setUrlErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const patch = usePatchMcpServer(onClose);

  const validateName = (v: string) => {
    const shared = vName(v, { label: "server name" });
    if (shared) return shared;
    // Per-project uniqueness, matching the server rule.
    if (siblings.some((x) => x.project_id === server.project_id && x.name.toLowerCase() === v.trim().toLowerCase()))
      return "This project already has an MCP server with this name.";
    return null;
  };
  const validateUrl = (v: string) => (stdio ? validateRequired(command, "the command") : vUrl(v, { label: "the server URL" }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    const ne = validateName(name);
    const ue = validateUrl(url);
    setNameErr(ne);
    setUrlErr(ue);
    if (ne || ue) return;
    const ce = validateTimeout(timeout) ?? validateRetries(retries);
    if (ce) { setAuthErr(ce); return; }
    if (authType === "oauth2") {
      // A client_secret is already stored whenever the server was ALREADY
      // oauth2 (create/edit both require one) — regardless of whether the
      // OAuth sign-in completed (oauth_connected = refresh_token present).
      // Switching static→oauth2 here has no stored secret yet, so it's required.
      const hasStoredSecret = server.auth_type === "oauth2";
      const oe = validateOAuth(oauth, { isEdit: true, hasStoredSecret });
      if (oe) { setAuthErr(oe); return; }
    }
    setAuthErr(null);
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
      ...(description.trim() !== (server.description ?? "") ? { description: description.trim() } : {}),
      ...(Number(timeout) !== server.timeout_seconds ? { timeout_seconds: Number(timeout) } : {}),
      ...(Number(retries) !== server.max_retries ? { max_retries: Number(retries) } : {}),
      ...authPayload,
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    patch.mutate({ id: server.id, payload });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="2xl"
      title={`Edit ${server.name}`}
      description="Changes apply to the next tool call — personas pick up the new address automatically."
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="mce-form" size="sm" variant="primary" loading={patch.isPending}>Save changes</Button>
        </div>
      }
    >
      <form id="mce-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="mce-name" required>Name</Label>
          <Input
            id="mce-name"
            required
            autoFocus
            value={name}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validateName(e.target.value));
            }}
            onBlur={() => {
              if (name) {
                setTouched(true);
                setNameErr(validateName(name));
              }
            }}
            maxLength={100}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
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
                aria-invalid={!!urlErr}
                onChange={(e) => {
                  setCommand(e.target.value);
                  if (touched) setUrlErr(validateRequired(e.target.value, "the command"));
                }}
                className="font-mono"
              />
              <FieldError>{urlErr}</FieldError>
            </div>
          ) : (
            <div>
              <Label htmlFor="mce-url" required>URL</Label>
              <Input
                id="mce-url"
                required
                inputMode="url"
                value={url}
                aria-invalid={!!urlErr}
                onChange={(e) => {
                  setUrl(e.target.value);
                  if (touched) setUrlErr(validateUrl(e.target.value));
                }}
                onBlur={() => {
                  if (url) {
                    setTouched(true);
                    setUrlErr(validateUrl(url));
                  }
                }}
                className="font-mono"
              />
              <FieldError>{urlErr}</FieldError>
            </div>
          )}
        </div>
        <div>
          <Label htmlFor="mce-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="mce-desc" placeholder="What tools does it expose?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <CallSettings idPrefix="mce" timeout={timeout} retries={retries} onTimeout={setTimeout_} onRetries={setRetries} />
        <McpAuthSection authType={authType} onAuthType={setAuthType} oauth={oauth} onOauth={setOauth} isEdit hasStoredSecret={server.auth_type === "oauth2"} onSuggestUrl={(u) => { if (!stdio && !url.trim()) setUrl(u); }} />
        <FieldError>{authErr}</FieldError>
      </form>
    </Dialog>
  );
}
