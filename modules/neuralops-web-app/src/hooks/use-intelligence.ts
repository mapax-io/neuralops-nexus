"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as intel from "@/lib/api/intelligence";
import { useConnectionStore } from "@/stores/connection.store";

function useGate() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return { serverUrl, enabled: !!serverUrl && !!token };
}

export function useModels() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["ai-models", serverUrl], queryFn: intel.listModels, enabled });
}

export function useMcpServers() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["mcp-servers", serverUrl], queryFn: intel.listMcpServers, enabled });
}

export function useAgents() {
  const { serverUrl, enabled } = useGate();
  return useQuery({ queryKey: ["agents", serverUrl], queryFn: intel.listAgents, enabled });
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

export function useCreateModel(onDone?: (m: intel.AIModel) => void) {
  const inv = useInvalidate("ai-models");
  return useMutation({
    mutationFn: intel.createModel,
    onSuccess: (m) => {
      toast.success(`Model "${m.name}" registered.`);
      inv();
      onDone?.(m);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useSetModelProject() {
  const inv = useInvalidate("ai-models");
  return useMutation({
    mutationFn: ({ projectId, modelId, attach }: { projectId: string; modelId: string; attach: boolean }) =>
      attach ? intel.attachModelToProject(projectId, modelId) : intel.detachModelFromProject(projectId, modelId),
    // AWAIT the refetch: the dialog's checkboxes derive from the query cache,
    // and re-enabling them against stale data would invert the next click.
    onSuccess: async (_r, v) => {
      toast.success(v.attach ? "Model attached to the project." : "Model detached from the project.");
      await inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useDeleteModel() {
  // Agents embed model_name — removing a model must refresh their cards.
  const inv = useInvalidate("ai-models", "agents");
  return useMutation({
    mutationFn: intel.deleteModel,
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
  const inv = useInvalidate("mcp-servers");
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
  const inv = useInvalidate("mcp-servers", "agents");
  return useMutation({
    mutationFn: intel.deleteMcpServer,
    onSuccess: () => {
      toast.success("MCP server removed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useCreateAgent(onDone?: (a: intel.AIAgent) => void) {
  const inv = useInvalidate("agents");
  return useMutation({
    mutationFn: intel.createAgent,
    onSuccess: (a) => {
      toast.success(`Agent "${a.name}" created.`);
      inv();
      onDone?.(a);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function usePatchAgent(onDone?: () => void) {
  const inv = useInvalidate("agents");
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: intel.AIAgentPatch }) => intel.patchAgent(id, payload),
    onSuccess: (a) => {
      toast.success(`Agent "${a.name}" updated.`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useDeleteAgent() {
  const inv = useInvalidate("agents");
  return useMutation({
    mutationFn: intel.deleteAgent,
    onSuccess: () => {
      toast.success("Agent removed.");
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
      await qc.invalidateQueries({ queryKey: ["mcp-servers", serverUrl] });
    },
    onError: (e) => {
      // Cancellation is not an error worth a red toast — the user chose to stop.
      if (e instanceof OAuthPopupError && e.code === "cancelled") return;
      toast.error(e instanceof Error ? e.message : "Couldn't connect the server.");
    },
  });
}
