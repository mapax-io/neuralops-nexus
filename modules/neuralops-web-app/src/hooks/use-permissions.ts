"use client";

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/client";
import { getMyPermissions } from "@/lib/api/permissions";
import {
  can as canRight,
  canAnyProject as canAnyProjectRight,
  type Right,
  type Scope,
} from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";

export interface PermissionGate {
  /** The server answered. Until then nothing is offered. */
  ready: boolean;
  /**
   * The server has no /me/permissions/ route — it predates scoped permissions.
   * Distinct from "you hold nothing": the app cannot gate anything against
   * such a server, so it says so instead of silently hiding every control.
   */
  serverTooOld: boolean;
  /** May the caller do `right` against the object named by `scope`? */
  can: (right: Right, scope: Scope) => boolean;
  /**
   * Whether the right is held on AT LEAST ONE reachable project — for controls
   * that span projects rather than targeting one (e.g. "Attach to projects",
   * which opens a picker). A lookup across the payload's own keys; the client
   * never walks the scope hierarchy itself.
   */
  canAnyProject: (right: Right) => boolean;
}

/**
 * The signed-in user's effective rights, from the server — the only source of
 * gating in the app. There is no role-name rule anywhere in the client.
 *
 * Reach (company -> project -> topic) is resolved server-side and arrives
 * pre-flattened, so every answer here is a set lookup.
 */
export function usePermissions(): PermissionGate {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);

  const { data, error } = useQuery({
    queryKey: ["permissions", serverUrl],
    queryFn: getMyPermissions,
    // Prerequisites must exist or the call 401s on a reload.
    enabled: !!serverUrl && !!token,
    staleTime: 300_000,
    // A server without the route answers 404 every time; retrying is noise.
    // Anything else is transient and stays retryable.
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  const can = useCallback((right: Right, scope: Scope) => canRight(data, right, scope), [data]);
  const canAnyProject = useCallback((right: Right) => canAnyProjectRight(data, right), [data]);
  const serverTooOld = error instanceof ApiError && error.status === 404;

  return useMemo(
    () => ({ ready: !!data, serverTooOld, can, canAnyProject }),
    [data, serverTooOld, can, canAnyProject],
  );
}
