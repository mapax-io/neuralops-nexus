import { useEffect, useState } from "react";
import type { ServerEntry } from "@/types";

const KEY = "neuralops-servers";

export function loadServers(): ServerEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as ServerEntry[]) : [];
  } catch {
    return [];
  }
}

export function saveServers(servers: ServerEntry[]) {
  localStorage.setItem(KEY, JSON.stringify(servers));
}

export function useServers() {
  const [servers, setServers] = useState<ServerEntry[]>([]);

  useEffect(() => {
    setServers(loadServers());
  }, []);

  function add(entry: Omit<ServerEntry, "id">) {
    const next = [...servers, { ...entry, id: crypto.randomUUID() }];
    setServers(next);
    saveServers(next);
  }

  function remove(id: string) {
    const next = servers.filter((s) => s.id !== id);
    setServers(next);
    saveServers(next);
  }

  return { servers, add, remove };
}
