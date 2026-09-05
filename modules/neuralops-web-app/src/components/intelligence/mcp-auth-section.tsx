"use client";

import { useState } from "react";
import { ChevronDown, Copy, ExternalLink, Eye, EyeOff, Square, SquareCheck, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { copyText } from "@/lib/browser";
import { Input, Label } from "@/components/ui/field";
import type { McpAuthType, McpOAuthConfig } from "@/lib/api/intelligence";
import { validateUrl } from "@/lib/validation";
import { useConnectionStore } from "@/stores/connection.store";

// ── OAuth draft (form state) ──────────────────────────────────────────────────
export interface OAuthDraft {
  client_id: string;
  client_secret: string;        // write-only; blank on edit = keep stored secret
  authorize_endpoint: string;
  token_endpoint: string;
  scopes: string;               // space/comma separated in the field
  token_env_var: string;
  authorize_params: string;     // extra sign-in params some providers require ("key=value", comma/newline separated)
}

export const emptyOAuthDraft = (): OAuthDraft => ({
  client_id: "", client_secret: "", authorize_endpoint: "", token_endpoint: "",
  scopes: "", token_env_var: "OAUTH_ACCESS_TOKEN", authorize_params: "",
});

// "key=value" text <-> record, so presets and the manual field share one shape.
const paramsToText = (p?: Record<string, string> | null) =>
  Object.entries(p ?? {}).map(([k, v]) => `${k}=${v}`).join(", ");
const paramsFromText = (t: string): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const part of t.split(/[\n,]+/)) {
    const i = part.indexOf("=");
    if (i > 0) { const k = part.slice(0, i).trim(); if (k) out[k] = part.slice(i + 1).trim(); }
  }
  return out;
};

export function draftFromConfig(cfg: McpOAuthConfig | null | undefined): OAuthDraft {
  return {
    client_id: cfg?.client_id ?? "",
    client_secret: "", // never returned by the server
    authorize_endpoint: cfg?.authorize_endpoint ?? "",
    token_endpoint: cfg?.token_endpoint ?? "",
    scopes: (cfg?.scopes ?? []).join(" "),
    token_env_var: cfg?.token_env_var ?? "OAUTH_ACCESS_TOKEN",
    authorize_params: paramsToText(cfg?.authorize_params),
  };
}

// Split the draft into the API shape: oauth_config (non-secret) + write-only
// client_secret (omitted when blank so an edit keeps the stored one).
export function draftToPayload(d: OAuthDraft): { oauth_config: McpOAuthConfig; client_secret?: string } {
  const scopes = d.scopes.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
  const authorize_params = paramsFromText(d.authorize_params);
  return {
    oauth_config: {
      client_id: d.client_id.trim(),
      authorize_endpoint: d.authorize_endpoint.trim(),
      token_endpoint: d.token_endpoint.trim(),
      scopes,
      token_env_var: d.token_env_var.trim() || "OAUTH_ACCESS_TOKEN",
      ...(Object.keys(authorize_params).length ? { authorize_params } : {}),
    },
    ...(d.client_secret.trim() ? { client_secret: d.client_secret.trim() } : {}),
  };
}

// Returns an error string, or null. `hasStoredSecret` lets edit keep a blank
// secret; create always needs one.
export function validateOAuth(d: OAuthDraft, opts: { isEdit: boolean; hasStoredSecret: boolean }): string | null {
  if (!d.client_id.trim()) return "Enter the OAuth app's Client ID.";
  const ae = validateUrl(d.authorize_endpoint, { label: "the authorize endpoint" });
  if (ae) return ae;
  const te = validateUrl(d.token_endpoint, { label: "the token endpoint" });
  if (te) return te;
  if (!d.client_secret.trim() && !(opts.isEdit && opts.hasStoredSecret)) {
    return "Enter the OAuth app's Client Secret.";
  }
  return null;
}

// ── Provider presets ──────────────────────────────────────────────────────────
// OAuth is provider-agnostic: any authorization-code provider works by filling
// the fields. These presets are one-click convenience for common ones; the
// backend passes `authorize_params` through so providers that need extra sign-in
// params (Atlassian's audience, Google's access_type/prompt) get a refresh token.
interface Provider {
  id: string;
  label: string;
  authorize_endpoint: string;
  token_endpoint: string;
  scopes: string;
  authorize_params?: Record<string, string>;
  appsUrl: string;              // where to create an OAuth app
  appsLabel: string;            // human path to that page
  refreshNote: React.ReactNode; // how this provider issues a refresh token
  suggestUrl?: string;          // suggested MCP server URL (only when a hosted one exists)
}

// The official hosted GitHub MCP server (suggested for the server URL).
export const GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/";

const PROVIDERS: Provider[] = [
  {
    id: "github", label: "GitHub",
    authorize_endpoint: "https://github.com/login/oauth/authorize",
    token_endpoint: "https://github.com/login/oauth/access_token",
    scopes: "repo read:org read:user",
    appsUrl: "https://github.com/settings/applications/new",
    appsLabel: "GitHub → Settings → Developer settings → OAuth Apps → New",
    refreshNote: <>tick <GhToggle label="Expire user access tokens" on /> in the OAuth app so GitHub issues a refresh token.</>,
    suggestUrl: GITHUB_MCP_URL,
  },
  {
    id: "gitlab", label: "GitLab",
    authorize_endpoint: "https://gitlab.com/oauth/authorize",
    token_endpoint: "https://gitlab.com/oauth/token",
    scopes: "read_api read_user",
    appsUrl: "https://gitlab.com/-/profile/applications",
    appsLabel: "GitLab → Preferences → Applications",
    refreshNote: <>GitLab returns a refresh token automatically for the authorization-code flow — nothing extra needed.</>,
  },
  {
    id: "atlassian", label: "Jira (Atlassian)",
    authorize_endpoint: "https://auth.atlassian.com/authorize",
    token_endpoint: "https://auth.atlassian.com/oauth/token",
    scopes: "read:jira-work read:jira-user offline_access",
    authorize_params: { audience: "api.atlassian.com", prompt: "consent" },
    appsUrl: "https://developer.atlassian.com/console/myapps/",
    appsLabel: "Atlassian Developer Console → Create → OAuth 2.0 (3LO)",
    refreshNote: <>the <code>offline_access</code> scope plus <code>prompt=consent</code> (this preset adds them) make Atlassian issue a refresh token.</>,
  },
  {
    id: "google", label: "Google",
    authorize_endpoint: "https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint: "https://oauth2.googleapis.com/token",
    scopes: "openid email profile",
    authorize_params: { access_type: "offline", prompt: "consent" },
    appsUrl: "https://console.cloud.google.com/apis/credentials",
    appsLabel: "Google Cloud Console → APIs & Services → Credentials → OAuth client ID",
    refreshNote: <><code>access_type=offline</code> plus <code>prompt=consent</code> (this preset adds them) make Google issue a refresh token.</>,
  },
];

// ── The section ───────────────────────────────────────────────────────────────
export function McpAuthSection({
  authType, onAuthType, oauth, onOauth, isEdit, hasStoredSecret, onSuggestUrl,
}: {
  authType: McpAuthType;
  onAuthType: (t: McpAuthType) => void;
  oauth: OAuthDraft;
  onOauth: (d: OAuthDraft) => void;
  isEdit: boolean;
  hasStoredSecret: boolean;
  onSuggestUrl?: (url: string) => void; // parent fills the server URL if empty
}) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  // The redirect URI the provider must be registered with (backend-fixed).
  const callbackUrl = serverUrl ? `${serverUrl.replace(/\/$/, "")}/api/v1/mcp-servers/oauth/callback/` : "";
  const set = (patch: Partial<OAuthDraft>) => onOauth({ ...oauth, ...patch });
  // Track which preset is active (inferred from the endpoints on edit) so the
  // guide can show provider-specific hints. null = a custom/other provider.
  const [providerId, setProviderId] = useState<string | null>(
    () => PROVIDERS.find((p) => p.authorize_endpoint === oauth.authorize_endpoint)?.id ?? null,
  );
  const provider = PROVIDERS.find((p) => p.id === providerId) ?? null;
  // First-timers get the guide open by default (no client id yet); a preset opens it too.
  const [guideOpen, setGuideOpen] = useState(!oauth.client_id);
  const [showSecret, setShowSecret] = useState(false);
  const applyPreset = (p: Provider) => {
    set({
      authorize_endpoint: p.authorize_endpoint,
      token_endpoint: p.token_endpoint,
      scopes: p.scopes,
      token_env_var: "OAUTH_ACCESS_TOKEN",
      authorize_params: paramsToText(p.authorize_params),
      client_secret: "", // never carry a secret across providers
    });
    setProviderId(p.id);
    if (p.suggestUrl) onSuggestUrl?.(p.suggestUrl);
    setGuideOpen(true);
  };
  const copy = (text: string, label: string) =>
    copyText(text).then((ok) => (ok ? toast.success(`${label} copied.`) : toast.error("Couldn't copy.")));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Label htmlFor="mcp-auth">Authentication</Label>
        <select
          id="mcp-auth"
          value={authType}
          // Clear the secret on switch: the static Secret and the OAuth Client
          // Secret share oauth.client_secret, so a value typed in one mode must
          // never carry into the other (it would be stored as the wrong credential).
          onChange={(e) => { onAuthType(e.target.value as McpAuthType); set({ client_secret: "" }); }}
          className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-sm outline-none transition-[border-color] focus:border-accent"
        >
          <option value="none">None — the server needs no credentials</option>
          <option value="static_secrets">Static secret — a fixed token you paste</option>
          <option value="oauth2">OAuth 2.0 — sign in to a provider (GitHub, GitLab, Jira, Google, …)</option>
        </select>
      </div>

      {authType === "static_secrets" && (
        <div>
          <Label htmlFor="mcp-secret">Secret{isEdit && <span className="text-ink2"> (leave blank to keep the current one)</span>}</Label>
          <SecretInput id="mcp-secret" placeholder="Paste the server's token" value={oauth.client_secret}
            onChange={(v) => set({ client_secret: v })} shown={showSecret} onToggle={() => setShowSecret((x) => !x)} />
        </div>
      )}

      {authType === "oauth2" && (
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface2/40 p-3.5">
          <p className="text-[12px] text-ink2">Sign in to <b className="text-ink">any OAuth 2.0 provider</b> after you save. Pick one below for one-click setup, or fill the fields for any other provider.</p>

          {/* Provider preset picker — one click fills the endpoints, scopes and
              any extra sign-in params a provider needs. */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 text-[12px] font-medium text-ink2"><Wand2 size={13} strokeWidth={2} /> Quick setup:</span>
            {PROVIDERS.map((p) => (
              <button key={p.id} type="button" onClick={() => applyPreset(p)}
                className={`cursor-pointer rounded-lg border px-2.5 py-1 text-[12px] font-medium transition-colors ${providerId === p.id ? "border-accent/60 bg-accent/10 text-ink" : "border-line bg-surface text-ink2 hover:border-accent/50 hover:text-ink"}`}>
                {p.label}
              </button>
            ))}
          </div>

          {/* Step-by-step setup guide — provider-aware, works for any provider. */}
          <div className="overflow-hidden rounded-lg border border-line bg-surface">
            <button type="button" onClick={() => setGuideOpen((x) => !x)}
              className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-[12.5px] font-semibold text-ink hover:bg-surface2/50">
              <ChevronDown size={14} strokeWidth={2.2} className={`flex-none text-ink2 transition-transform ${guideOpen ? "" : "-rotate-90"}`} />
              First time? Set up an OAuth app step by step{provider ? ` (${provider.label})` : ""}
            </button>
            {guideOpen && (
              <ol className="flex flex-col gap-2.5 border-t border-line px-4 py-3 text-[12.5px] leading-relaxed text-ink2">
                <GuideStep n={1}>
                  Create an OAuth app on your provider
                  {provider
                    ? <> — <ExtLink href={provider.appsUrl}>{provider.appsLabel}</ExtLink></>
                    : <> (in its developer / OAuth-app settings)</>}. Name it anything, e.g. <code className="rounded bg-surface2 px-1">NeuralOps MCP</code>.
                </GuideStep>
                <GuideStep n={2}>
                  Register this as the app&apos;s <b className="text-ink">Redirect URI</b> (some providers call it the &ldquo;Authorization callback URL&rdquo;) exactly:
                  {callbackUrl ? (
                    <span className="mt-1 flex items-center gap-2">
                      <code className="min-w-0 flex-1 truncate rounded bg-surface2 px-1.5 py-0.5 font-mono text-[11.5px] text-ink">{callbackUrl}</code>
                      <button type="button" aria-label="Copy redirect URI" onClick={() => copy(callbackUrl, "Redirect URI")}
                        className="flex size-6 flex-none cursor-pointer items-center justify-center rounded text-ink2 hover:bg-surface2 hover:text-ink"><Copy size={13} strokeWidth={2} /></button>
                    </span>
                  ) : <span className="text-warn"> (connect to a server first so we can show your redirect URI)</span>}
                </GuideStep>
                <GuideStep n={3}>
                  <b className="text-crit">Important:</b> make sure it issues a <b className="text-ink">refresh token</b> — NeuralOps needs it to keep the connection alive, and without it the server stays &ldquo;not connected&rdquo; after you sign in.{" "}
                  {provider ? provider.refreshNote : <>Request offline access: an <code className="rounded bg-surface2 px-1">offline_access</code> scope, or params like <code className="rounded bg-surface2 px-1">access_type=offline</code> / <code className="rounded bg-surface2 px-1">prompt=consent</code> in the field below — check your provider&apos;s docs.</>}
                </GuideStep>
                <GuideStep n={4}>Copy the <b className="text-ink">Client ID</b> and generate a <b className="text-ink">Client Secret</b> (providers usually show the secret only once), then paste both below.</GuideStep>
                <GuideStep n={5}>
                  Set the server&apos;s <b className="text-ink">URL</b> (top of this form) to your MCP server&apos;s endpoint
                  {provider?.suggestUrl ? <> — e.g. <code className="rounded bg-surface2 px-1">{provider.suggestUrl}</code></> : <> (the MCP server that talks to {provider ? provider.label : "your provider"})</>}.
                </GuideStep>
                <GuideStep n={6}>Save, then click <b className="text-ink">Connect</b> on the server and sign in.</GuideStep>
              </ol>
            )}
          </div>

          {callbackUrl && (
            <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[11.5px]">
              <p className="text-ink2">Register this <b className="text-ink">redirect URI / callback URL</b> in your OAuth app:</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate font-mono text-ink">{callbackUrl}</code>
                <button type="button" aria-label="Copy callback URL"
                  onClick={() => copy(callbackUrl, "Callback URL")}
                  className="flex size-6 flex-none cursor-pointer items-center justify-center rounded text-ink2 hover:bg-surface2 hover:text-ink">
                  <Copy size={13} strokeWidth={2} />
                </button>
              </div>
            </div>
          )}

          <div>
            <Label htmlFor="oa-client" required>Client ID</Label>
            <Input id="oa-client" required name="mcp-oauth-client-id" placeholder="e.g. Ov23li… / your-app-id" value={oauth.client_id} onChange={(e) => set({ client_id: e.target.value })}
              autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} data-1p-ignore data-lpignore="true" data-form-type="other" className="font-mono" />
          </div>
          <div>
            <Label htmlFor="oa-secret" required={!(isEdit && hasStoredSecret)}>Client Secret{isEdit && hasStoredSecret && <span className="text-ink2"> (leave blank to keep current)</span>}</Label>
            <SecretInput id="oa-secret" required={!(isEdit && hasStoredSecret)} placeholder={isEdit && hasStoredSecret ? "•••••••• (stored — leave blank to keep)" : "The OAuth app's client secret"}
              value={oauth.client_secret} onChange={(v) => set({ client_secret: v })} shown={showSecret} onToggle={() => setShowSecret((x) => !x)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="oa-auth" required>Authorize endpoint</Label>
              <Input id="oa-auth" required inputMode="url" placeholder="https://provider.com/oauth/authorize" value={oauth.authorize_endpoint} onChange={(e) => set({ authorize_endpoint: e.target.value })} className="font-mono text-[12px]" />
              <FieldHint>Required. Where you&apos;re sent to sign in and approve access — from your provider&apos;s OAuth docs. GitHub <code className="rounded bg-surface2 px-1 py-px">…/login/oauth/authorize</code>, GitLab <code className="rounded bg-surface2 px-1 py-px">…/oauth/authorize</code>, Atlassian <code className="rounded bg-surface2 px-1 py-px">auth.atlassian.com/authorize</code>. A preset fills it.</FieldHint>
            </div>
            <div>
              <Label htmlFor="oa-token" required>Token endpoint</Label>
              <Input id="oa-token" required inputMode="url" placeholder="https://provider.com/oauth/token" value={oauth.token_endpoint} onChange={(e) => set({ token_endpoint: e.target.value })} className="font-mono text-[12px]" />
              <FieldHint>Required. Where your approval is exchanged for a token (server-side). Note the exact path differs per provider — GitHub uses <code className="rounded bg-surface2 px-1 py-px">/access_token</code>, most others <code className="rounded bg-surface2 px-1 py-px">/token</code>. A preset fills it.</FieldHint>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="oa-scopes">Scopes <span className="text-ink2">(optional · space-separated)</span></Label>
              <Input id="oa-scopes" placeholder="read_api read_user" value={oauth.scopes} onChange={(e) => set({ scopes: e.target.value })} />
              <FieldHint>Permissions to request — keep it minimal, and include the provider&apos;s offline/refresh scope if it has one (e.g. Atlassian&apos;s <code className="rounded bg-surface2 px-1 py-px">offline_access</code>). Leave blank to accept the provider&apos;s defaults.</FieldHint>
            </div>
            <div>
              <Label htmlFor="oa-env">Token env var <span className="text-ink2">(optional)</span></Label>
              <Input id="oa-env" placeholder="OAUTH_ACCESS_TOKEN" value={oauth.token_env_var} onChange={(e) => set({ token_env_var: e.target.value })} className="font-mono text-[12px]" />
              <FieldHint>The key the token is stored under. A remote (URL) server receives it as an <code className="rounded bg-surface2 px-1 py-px">Authorization: Bearer</code> header, so the name doesn&apos;t matter — keep the default. A local (command) server reads this exact env var, so match its docs.</FieldHint>
            </div>
          </div>
          <div>
            <Label htmlFor="oa-params">Extra authorize parameters <span className="text-ink2">(optional)</span></Label>
            <Input id="oa-params" placeholder="audience=api.atlassian.com, prompt=consent" value={oauth.authorize_params} onChange={(e) => set({ authorize_params: e.target.value })} className="font-mono text-[12px]" />
            <FieldHint>Extra query params some providers require on the sign-in URL to return a refresh token, as <code className="rounded bg-surface2 px-1 py-px">key=value</code> (comma-separated). <b>Jira</b> needs <code className="rounded bg-surface2 px-1 py-px">audience=api.atlassian.com, prompt=consent</code>; <b>Google</b> needs <code className="rounded bg-surface2 px-1 py-px">access_type=offline, prompt=consent</code>. The presets fill these; GitHub/GitLab need none.</FieldHint>
          </div>
        </div>
      )}
    </div>
  );
}

// A password input with a show/hide eye toggle. Never pre-filled — the server
// never returns a secret, and the field starts blank.
function SecretInput({ id, value, placeholder, onChange, shown, onToggle, required }: {
  id: string; value: string; placeholder?: string; onChange: (v: string) => void; shown: boolean; onToggle: () => void; required?: boolean;
}) {
  return (
    <div className="relative">
      <Input id={id} name={id} type={shown ? "text" : "password"} placeholder={placeholder} value={value} required={required}
        onChange={(e) => onChange(e.target.value)} autoComplete="new-password" autoCorrect="off" autoCapitalize="off"
        spellCheck={false} data-1p-ignore data-lpignore="true" data-form-type="other" className="pr-10 font-mono" />
      <button type="button" aria-label={shown ? "Hide secret" : "Show secret"} onClick={onToggle}
        className="absolute right-1 top-1/2 flex size-8 -translate-y-1/2 cursor-pointer items-center justify-center rounded text-ink2 hover:text-ink">
        {shown ? <EyeOff size={15} strokeWidth={2} /> : <Eye size={15} strokeWidth={2} />}
      </button>
    </div>
  );
}

// Muted one-liner under a field: says what it's for and shows an example.
function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-[11px] leading-snug text-ink2">{children}</p>;
}

// A provider-form checkbox reference rendered as a badge that mirrors the state
// to set it to — checked/accent means turn on, empty/muted means leave off.
function GhToggle({ label, on = false }: { label: string; on?: boolean }) {
  return (
    <span className={`mx-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-px align-baseline text-[11px] font-medium ${on ? "border-accent/40 bg-accent/10 text-ink" : "border-line bg-surface2 text-ink2"}`}>
      {on ? <SquareCheck size={12} strokeWidth={2.2} className="flex-none text-accent" /> : <Square size={12} strokeWidth={2.2} className="flex-none" />}
      {label}
    </span>
  );
}

function GuideStep({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span className="flex size-5 flex-none items-center justify-center rounded-full bg-accent/15 text-[10.5px] font-bold text-accent">{n}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </li>
  );
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-medium text-accent underline hover:opacity-80">
      {children}<ExternalLink size={11} strokeWidth={2.2} />
    </a>
  );
}
