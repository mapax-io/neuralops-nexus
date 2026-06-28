import { useEffect, useState } from "react";
import type { ServerEntry } from "@/types";

const KEY = "neuralops-servers";

function generateId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

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
    const next = [...servers, { ...entry, id: generateId() }];
    setServers(next);
    saveServers(next);
  }

  function remove(id: string) {
    const next = servers.filter((s) => s.id !== id);
    setServers(next);
    saveServers(next);
  }

  function touch(id: string) {
    const next = servers.map((s) =>
      s.id === id ? { ...s, lastConnected: Date.now() } : s,
    );
    setServers(next);
    saveServers(next);
  }

  return { servers, add, remove, touch };
}
