"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { listRoles, setRoleRights, type RolesPayload } from "@/lib/api/roles";
import { permissionsQueryKey } from "@/hooks/use-permissions";
import { useConnectionStore } from "@/stores/connection.store";

export function useRoles() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return useQuery<RolesPayload>({
    queryKey: ["roles", serverUrl],
    queryFn: listRoles,
    enabled: !!serverUrl && !!token,
  });
}

export function useSetRoleRights() {
  const qc = useQueryClient();
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  return useMutation({
    mutationFn: ({ roleId, rights }: { roleId: string; rights: string[] }) =>
      setRoleRights(roleId, rights),
    onSuccess: async (r) => {
      const changed = r.added.length + r.removed.length;
      toast.success(
        changed === 0
          ? `${r.name} unchanged`
          : `${r.name}: ${r.added.length} added, ${r.removed.length} removed`,
      );
      await qc.invalidateQueries({ queryKey: ["roles"] });
      // The editor may hold the role they just changed, so their OWN rights can
      // move with it. Awaited so the app is never gating on the old answer.
      await qc.invalidateQueries({ queryKey: permissionsQueryKey(serverUrl) });
    },
    onError: (e) => toast.error(e.message),
  });
}
