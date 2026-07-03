// Centrifugo real-time connection hook
// Full implementation will be added when backend chat API is ready
// For now: sets up the connection structure

import { useEffect, useRef } from "react";
import { useAuthStore } from "@/store/auth.store";

export function useCentrifugo() {
  const serverUrl = useAuthStore((s) => s.serverUrl);
  const connectionRef = useRef<unknown>(null);

  useEffect(() => {
    if (!serverUrl) return;
    // TODO: Initialize Centrifuge client
    // const centrifuge = new Centrifuge(`${serverUrl}/connection/websocket`);
    // centrifuge.connect();
    // connectionRef.current = centrifuge;
    // return () => centrifuge.disconnect();
  }, [serverUrl]);

  const subscribe = (channel: string, _onMessage: (data: unknown) => void) => {
    // TODO: Subscribe to channel
    console.log("Centrifugo subscribe:", channel);
  };

  return { subscribe, connectionRef };
}
