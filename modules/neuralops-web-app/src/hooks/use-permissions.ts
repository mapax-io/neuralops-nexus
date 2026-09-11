"use client";

import { useCallback, useMemo } from "react";
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/client";
import { getMyPermissions } from "@/lib/api/permissions";
import {
  can as canRight,
  canAnyProject as canAnyProjectRight,
  type Right,
  type Scope,
} from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";

/** Shared so priming, reading and invalidation cannot drift apart. */
export const permissionsQueryKey = (serverUrl: string | null) => ["permissions", serverUrl];

/**
 * Fetch the caller's rights into the cache before the workspace renders.
 * Called during connect so the shell never paints a screen whose controls are
 * gated on an answer that has not arrived -- see the loading gate below.
 */
export async function primePermissions(qc: QueryClient, serverUrl: string | null) {
  if (!serverUrl) return;
  await qc.prefetchQuery({
    queryKey: permissionsQueryKey(serverUrl),
    queryFn: getMyPermissions,
    staleTime: PERMISSIONS_STALE_MS,
  });
}

const PERMISSIONS_STALE_MS = 300_000;

export interface PermissionGate {
  /** The server answered. Until then nothing is offered. */
  ready: boolean;
  /**
   * The answer is still in flight. Callers that draw gated controls must hold
   * rather than render: with no rights yet every control resolves to hidden,
   * which reads as "you cannot do this" instead of "not loaded". That window
   * is exactly how an owner saw no New topic button straight after signing in.
   */
  loading: boolean;
  /**
   * The server has no /me/permissions/ route — it predates scoped permissions.
   * Distinct from "you hold nothing": the app cannot gate anything against
   * such a server, so it says so instead of silently hiding every control.
   */
  serverTooOld: boolean;
  /**
   * The request settled without an answer for a reason that is NOT the route
   * being absent — a 500, a dropped connection. Same consequence as
   * serverTooOld (nothing can be offered) but a different cause and a
   * different remedy, so it is surfaced separately and is retryable. Without
   * this the app would render every control hidden and say nothing, which is
   * the bug this file exists to prevent, wearing a different hat.
   */
  failed: boolean;
  /** Try again after a failure. */
  retry: () => void;
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

  const enabled = !!serverUrl && !!token;
  const { data, error, isPending, refetch } = useQuery({
    queryKey: permissionsQueryKey(serverUrl),
    queryFn: getMyPermissions,
    // Prerequisites must exist or the call 401s on a reload.
    enabled,
    staleTime: PERMISSIONS_STALE_MS,
    // A server without the route answers 404 every time; retrying is noise.
    // Anything else is transient and stays retryable.
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  const can = useCallback((right: Right, scope: Scope) => canRight(data, right, scope), [data]);
  const canAnyProject = useCallback((right: Right) => canAnyProjectRight(data, right), [data]);
  const serverTooOld = error instanceof ApiError && error.status === 404;
  const failed = !!error && !serverTooOld;
  const retry = useCallback(() => void refetch(), [refetch]);
  // A disabled query sits at "pending" forever, so only count it as loading
  // once it can actually run. Settled-with-an-error is NOT loading: the app
  // must move on and say so rather than hold the screen indefinitely.
  const loading = enabled && isPending;

  return useMemo(
    () => ({ ready: !!data, loading, serverTooOld, failed, retry, can, canAnyProject }),
    [data, loading, serverTooOld, failed, retry, can, canAnyProject],
  );
}
