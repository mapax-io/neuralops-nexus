import { useState, useCallback } from "react";
import {
  getContextPanel,
  deleteContextPanelItems,
  type ContextPanelGroup,
} from "@/services/context.service";

export type SelectedItem = { directive: string; id: string };

export function useContextPanel(projectId: string | null, topicId: string | null) {
  const [groups, setGroups] = useState<ContextPanelGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  // Stable key for a selection entry: "directive:id"
  const itemKey = (directive: string, id: string) => `${directive}:${id}`;

  const load = useCallback(async () => {
    if (!projectId || !topicId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getContextPanel(projectId, topicId);
      setGroups(data);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load context panel");
    } finally {
      setLoading(false);
    }
  }, [projectId, topicId]);

  const toggleItem = useCallback((directive: string, id: string) => {
    const key = itemKey(directive, id);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const toggleGroup = useCallback((directive: string, ids: string[]) => {
    const keys = ids.map((id) => itemKey(directive, id));
    const allSelected = keys.every((k) => selected.has(k));
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        keys.forEach((k) => next.delete(k));
      } else {
        keys.forEach((k) => next.add(k));
      }
      return next;
    });
  }, [selected]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const deleteSelected = useCallback(async () => {
    if (!projectId || !topicId || selected.size === 0) return;
    setDeleting(true);
    try {
      const items = Array.from(selected).map((key) => {
        const colonIdx = key.indexOf(":");
        return {
          directive: key.slice(0, colonIdx),
          id: key.slice(colonIdx + 1),
        };
      });
      await deleteContextPanelItems(projectId, topicId, items);
      // Reload to reflect deletions
      const data = await getContextPanel(projectId, topicId);
      setGroups(data);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete items");
    } finally {
      setDeleting(false);
    }
  }, [projectId, topicId, selected]);

  const isItemSelected = useCallback(
    (directive: string, id: string) => selected.has(itemKey(directive, id)),
    [selected],
  );

  const isGroupFullySelected = useCallback(
    (directive: string, ids: string[]) =>
      ids.length > 0 && ids.every((id) => selected.has(itemKey(directive, id))),
    [selected],
  );

  return {
    groups,
    loading,
    error,
    selected,
    deleting,
    load,
    toggleItem,
    toggleGroup,
    clearSelection,
    deleteSelected,
    isItemSelected,
    isGroupFullySelected,
  };
}
