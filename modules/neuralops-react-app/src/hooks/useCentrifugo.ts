import { useEffect, useRef, useCallback } from "react";
import { Centrifuge, type Subscription } from "centrifuge";
import { useAuthStore } from "@/store/auth.store";

// Derive Centrifugo WS URL from server URL.
// nginx routes /connection/websocket → Centrifugo internally.
// React only ever knows the nginx URL — no port-swapping needed.
function getCentrifugoWsUrl(serverUrl: string): string {
  return serverUrl
    .replace(/^https/, "wss")
    .replace(/^http/, "ws")
    .replace(/\/?$/, "/connection/websocket");
}

// Module-level singleton — one connection shared across all hook instances.
// Keyed by URL so a server URL change triggers a clean reconnect.
let centrifugeInstance: Centrifuge | null = null;
let centrifugeUrl: string | null = null;

export function useCentrifugo() {
  const serverUrl = useAuthStore((s) => s.serverUrl);
  const subsRef = useRef<Map<string, Subscription>>(new Map());

  useEffect(() => {
    if (!serverUrl) return;

    const wsUrl = getCentrifugoWsUrl(serverUrl);

    // If the server URL changed, disconnect the old instance and start fresh
    if (centrifugeInstance && centrifugeUrl !== wsUrl) {
      centrifugeInstance.disconnect();
      centrifugeInstance = null;
      centrifugeUrl = null;
      subsRef.current.clear();
    }

    // Create and connect only if not already connected to this URL
    if (!centrifugeInstance) {
      centrifugeInstance = new Centrifuge(wsUrl);
      centrifugeUrl = wsUrl;
      centrifugeInstance.connect();
    }

    return () => {
      // Keep connection alive across component unmounts —
      // only disconnect when the URL changes (handled above on next render)
    };
  }, [serverUrl]);

  const subscribe = useCallback(
    (channel: string, onMessage: (data: unknown) => void) => {
      if (!centrifugeInstance) return () => {};

      // Reuse existing subscription if already subscribed to this channel
      let sub = subsRef.current.get(channel);
      if (!sub) {
        sub = centrifugeInstance.newSubscription(channel);
        subsRef.current.set(channel, sub);
      }

      const handler = (ctx: { data: unknown }) => onMessage(ctx.data);
      sub.on("publication", handler);
      sub.subscribe();

      return () => {
        sub?.off("publication", handler);
      };
    },
    [],
  );

  return { subscribe };
}
