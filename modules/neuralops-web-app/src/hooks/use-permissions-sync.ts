"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { permissionsQueryKey, usePermissions } from "@/hooks/use-permissions";
import { useProjects, useTopics } from "@/hooks/use-workspace";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelection } from "@/stores/selection.store";

/**
 * Keeps the rights payload honest about objects the app already knows exist.
 *
 * The payload is keyed by object id, and the server keys exactly what
 * row_rules makes visible -- the same source the project and topic lists come
 * from. So the two agreeing is an invariant, and a project or topic the UI can
 * see but the payload does not key is PROVABLY stale, not a denial. Left alone
 * it reads as "you may do nothing here", which is how a freshly created
 * project showed no controls until a refresh.
 *
 * Rather than enumerating every way that can happen -- you created it, a
 * teammate created it, someone added you to it, a role you hold was edited --
 * this reconciles the two and refetches once when they disagree. Mutations
 * that mint ids still invalidate directly (see useInvalidate) so the common
 * path is immediate; this is the safety net for everything else.
 *
 * Refetches at most once per unseen id, so a legitimately absent key (an
 * object visible with no rights on it) cannot loop.
 */
export function usePermissionsSync() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const qc = useQueryClient();
  const { ready, keyedProjects, keyedTopics } = usePermissions();
  const { sel } = useSelection();
  const { data: projects } = useProjects();
  const { data: topics } = useTopics(sel?.pid, sel?.cid);

  // Ids already reconciled, so a genuinely unkeyed object asks only once.
  const asked = useRef<Set<string>>(new Set());
  useEffect(() => {
    asked.current = new Set();
  }, [serverUrl]);

  useEffect(() => {
    if (!ready) return; // nothing to compare against yet
    const unseen: string[] = [];
    for (const p of projects ?? []) {
      if (!keyedProjects.has(p.id) && !asked.current.has(p.id)) unseen.push(p.id);
    }
    for (const t of topics ?? []) {
      if (!keyedTopics.has(t.id) && !asked.current.has(t.id)) unseen.push(t.id);
    }
    if (!unseen.length) return;
    unseen.forEach((id) => asked.current.add(id));
    void qc.invalidateQueries({ queryKey: permissionsQueryKey(serverUrl) });
  }, [ready, keyedProjects, keyedTopics, projects, topics, qc, serverUrl]);
}
