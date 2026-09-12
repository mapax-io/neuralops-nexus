"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as intel from "@/lib/api/intelligence";
import { useConnectionStore } from "@/stores/connection.store";

function useGate() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return { serverUrl, enabled: !!serverUrl && !!token };
}

export function useModelConfigs() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["model-configs", serverUrl], queryFn: intel.listModelConfigs, enabled });
}

export function useMcpServers() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["mcp-servers", serverUrl], queryFn: intel.listMcpServers, enabled });
}

export function usePersonas(projectId?: string) {
  const { serverUrl, enabled } = useGate();
  return useQuery({
    queryKey: ["personas", serverUrl, projectId],
    queryFn: () => intel.listPersonas(projectId!),
    enabled: enabled && !!projectId,
  });
}

export function usePromptTemplates() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["prompt-templates", serverUrl], queryFn: intel.listPromptTemplates, enabled, staleTime: 300_000 });
}

export function useOutputTypes() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["output-types", serverUrl], queryFn: intel.listOutputTypes, enabled, staleTime: 300_000 });
}

function useInvalidate(...keys: string[]) {
  const qc = useQueryClient();
  // Returns a promise resolving after the refetches — callers that must not
  // show stale state (ModelProjectsDialog) await it.
  return () => Promise.all(keys.map((key) => qc.invalidateQueries({ queryKey: [key] })));
}

export function useCreateModelConfig(onDone?: (m: intel.ModelConfig) => void) {
  const inv = useInvalidate("model-configs");
  return useMutation({
    mutationFn: intel.createModelConfig,
    onSuccess: (m) => {
      toast.success(`Model "${m.name}" registered.`);
      inv();
      onDone?.(m);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function usePatchModelConfig(onDone?: () => void) {
  // Persona cards embed the model's name and tool capability.
  const inv = useInvalidate("model-configs", "personas");
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: intel.ModelConfigPatch }) => intel.patchModelConfig(id, payload),
    onSuccess: (m) => {
      toast.success(`Model "${m.name}" updated.`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useSetModelConfigProject() {
  const inv = useInvalidate("model-configs");
  return useMutation({
    mutationFn: ({ projectId, modelId, attach }: { projectId: string; modelId: string; attach: boolean }) =>
      attach ? intel.attachModelConfigToProject(projectId, modelId) : intel.detachModelConfigFromProject(projectId, modelId),
    // AWAIT the refetch: the dialog's checkboxes derive from the query cache,
    // and re-enabling them against stale data would invert the next click.
    onSuccess: async (_r, v) => {
      toast.success(v.attach ? "Model attached to the project." : "Model detached from the project.");
      await inv();
    },
    // A detach refused while a persona still uses the model arrives as a 409
    // naming the persona — surfaced as-is.
    onError: (e) => toast.error(e.message),
  });
}

export function useDeleteModelConfig() {
  const inv = useInvalidate("model-configs", "personas");
  return useMutation({
    mutationFn: intel.deleteModelConfig,
    onSuccess: () => {
      toast.success("Model removed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useCreateMcpServer(onDone?: (s: intel.MCPServer) => void) {
  const inv = useInvalidate("mcp-servers");
  return useMutation({
    mutationFn: intel.createMcpServer,
    onSuccess: (s) => {
      toast.success(`MCP server "${s.name}" added.`);
      inv();
      onDone?.(s);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function usePatchMcpServer(onDone?: () => void) {
  // Persona cards embed the server's name and auth state.
  const inv = useInvalidate("mcp-servers", "personas");
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: intel.MCPServerPatch }) => intel.patchMcpServer(id, payload),
    onSuccess: (s) => {
      toast.success(`MCP server "${s.name}" updated.`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useDeleteMcpServer() {
  const inv = useInvalidate("mcp-servers", "personas");
  return useMutation({
    mutationFn: intel.deleteMcpServer,
    onSuccess: () => {
      toast.success("MCP server removed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useCreatePersona(onDone?: (p: intel.Persona) => void) {
  const inv = useInvalidate("personas");
  return useMutation({
    mutationFn: intel.createPersona,
    onSuccess: (p) => {
      toast.success(`@${p.name} is ready — mention them in any chat of their project.`);
      inv();
      onDone?.(p);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function usePatchPersona(onDone?: () => void) {
  // Schedules embed persona_name — a rename must reach the schedules panel.
  const inv = useInvalidate("personas", "schedules");
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: intel.PersonaPatch }) => intel.patchPersona(id, payload),
    onSuccess: (p) => {
      toast.success(`@${p.name} updated.`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useDeletePersona() {
  const inv = useInvalidate("personas", "schedules");
  return useMutation({
    mutationFn: intel.deletePersona,
    onSuccess: () => {
      toast.success("Persona removed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

// ── MCP OAuth connect (popup flow) ──────────────────────────────────────────
import { connectMcpOAuth, OAuthPopupError } from "@/lib/mcp-oauth";

export function useMcpOAuthConnect() {
  const qc = useQueryClient();
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  return useMutation({
    mutationFn: ({ serverId, wasConnected, beforeExpiry }: { serverId: string; name: string; wasConnected: boolean; beforeExpiry: string | null }) =>
      connectMcpOAuth(serverId, serverUrl, async () => {
        // Popup closed without a message — ask the backend whether THIS attempt
        // actually connected. A brand-new connection (wasn't connected before)
        // or a refreshed token (expiry advanced) is a real success; an unchanged
        // already-connected server means the user just cancelled the re-auth, so
        // don't report a false "connected".
        const after = (await intel.listMcpServers()).find((s) => s.id === serverId);
        if (!after?.oauth_connected) return false;
        return !wasConnected || (after.oauth_config?.expires_at ?? null) !== beforeExpiry;
      }),
    onSuccess: async (_r, v) => {
      toast.success(`${v.name} connected.`);
      // Persona cards flag a mounted server that needs reconnecting.
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["mcp-servers", serverUrl] }),
        qc.invalidateQueries({ queryKey: ["personas", serverUrl] }),
      ]);
    },
    onError: (e) => {
      // Cancellation is not an error worth a red toast — the user chose to stop.
      if (e instanceof OAuthPopupError && e.code === "cancelled") return;
      toast.error(e instanceof Error ? e.message : "Couldn't connect the server.");
    },
  });
}

// Model ids to suggest for a provider. OpenRouter's public catalog is the one
// key-less source that lists every major provider's current models under a
// single prefix scheme ("anthropic/claude-sonnet-5"), so it doubles as a
// directory for the providers served natively. Advisory only: the field stays
// free text, a failed or slow fetch just means no suggestions, and nothing is
// asked of the catalog before a model dialog is actually open.
const CATALOG_URL = "https://openrouter.ai/api/v1/models";
const CATALOG_PROVIDERS = new Set(["anthropic", "openai", "google"]);
const CATALOG_TTL_MS = 24 * 60 * 60_000;

export interface CatalogModel {
  id: string;
  name: string;
}

async function fetchCatalog({ signal }: { signal: AbortSignal }): Promise<CatalogModel[]> {
  const res = await fetch(CATALOG_URL, { signal });
  if (!res.ok) throw new Error(`The model catalog answered ${res.status}.`);
  const body = (await res.json()) as { data?: unknown } | null;
  if (!Array.isArray(body?.data)) throw new Error("The model catalog answered in an unexpected shape.");
  // A third party's payload: keep only rows shaped the way the field needs.
  return (body.data as unknown[]).flatMap((row) => {
    const m = row as { id?: unknown; name?: unknown } | null;
    return typeof m?.id === "string" && typeof m?.name === "string" ? [{ id: m.id, name: m.name }] : [];
  });
}

export function useProviderModels(provider: string, enabled = true): CatalogModel[] {
  const covered = CATALOG_PROVIDERS.has(provider);
  // Not keyed by server on purpose: the catalog is the same whichever nucleus
  // the app is connected to.
  const { data } = useQuery({
    queryKey: ["model-catalog"],
    queryFn: fetchCatalog,
    enabled: enabled && covered,
    retry: 1,
    staleTime: CATALOG_TTL_MS,
    gcTime: CATALOG_TTL_MS,
  });
  return useMemo(() => {
    if (!covered || !data) return [];
    const prefix = `${provider}/`;
    // Catalog names read "Anthropic: Claude Sonnet 5" -- the provider is already picked.
    return data
      .filter((m) => m.id.startsWith(prefix))
      .map((m) => ({ id: m.id.slice(prefix.length), name: m.name.replace(/^[^:]+:\s*/, "") }));
  }, [covered, data, provider]);
}
