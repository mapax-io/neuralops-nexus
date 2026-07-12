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

let centrifugeInstance: Centrifuge | null = null;

export function useCentrifugo() {
  const serverUrl = useAuthStore((s) => s.serverUrl);
  const subsRef = useRef<Map<string, Subscription>>(new Map());

  useEffect(() => {
    if (!serverUrl) return;

    const wsUrl = getCentrifugoWsUrl(serverUrl);

    // Reuse existing connection if already created
    if (!centrifugeInstance) {
      centrifugeInstance = new Centrifuge(wsUrl);
      centrifugeInstance.connect();
    }

    return () => {
      // Don't disconnect on unmount — keep connection alive across components
    };
  }, [serverUrl]);

  const subscribe = useCallback(
    (channel: string, onMessage: (data: unknown) => void) => {
      if (!centrifugeInstance) return () => {};

      // Reuse existing subscription if already subscribed
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
