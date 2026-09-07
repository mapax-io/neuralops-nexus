"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchServerConfig } from "@/lib/api/servers";
import { useConnectionStore } from "@/stores/connection.store";

// The connected server's own view of itself — above all `server_url`, the
// public address it uses when it builds OAuth redirects. It can differ from
// the address the app dialled (a LAN address here, a public hostname there),
// and a redirect URI registered from the wrong one fails at the provider.
export function useServerConfig() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  return useQuery({
    queryKey: ["server-config", serverUrl],
    queryFn: () => fetchServerConfig(serverUrl!),
    enabled: !!serverUrl,
    staleTime: 5 * 60_000,
  });
}
