"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, ServerOff, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { GATEWAY_STATUSES, useConnectivity } from "@/lib/connectivity";
import { onConnectionStatus } from "@/lib/realtime/centrifugo";
import { useConnectionStore } from "@/stores/connection.store";

// Says so when nothing can get through: the device is offline, or the
// connected server stopped answering. Sits under the top bar for the whole
// workspace. Recovery is automatic — a probe with backoff while the server
// is down, the browser's own online event for the device — and announced,
// so nobody keeps typing into a void or wonders whether it is back.
const FIRST_RETRY_MS = 4_000;
const MAX_RETRY_MS = 20_000;
// Realtime drops for many reasons; only a drop that lasts is worth a probe.
const REALTIME_GRACE_MS = 6_000;

// Is the server answering? Anything but a network failure or a gateway
// answer counts — a 401 still means nucleus is there.
async function pingServer(serverUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${serverUrl}/api/v1/auth/config/`, { cache: "no-store" });
    return !GATEWAY_STATUSES.has(res.status);
  } catch {
    return false;
  }
}

export function ConnectivityBanner() {
  const browserOnline = useConnectivity((s) => s.browserOnline);
  const serverDown = useConnectivity((s) => s.serverDown);
  const setBrowserOnline = useConnectivity((s) => s.setBrowserOnline);
  const reportServerOk = useConnectivity((s) => s.reportServerOk);
  const reportServerFailure = useConnectivity((s) => s.reportServerFailure);
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const serverName = useConnectionStore((s) => s.connection?.companyName);
  const qc = useQueryClient();
  const [retrying, setRetrying] = useState(false);

  // The device's own network, from the browser.
  useEffect(() => {
    const sync = () => setBrowserOnline(navigator.onLine);
    const raf = requestAnimationFrame(sync);
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, [setBrowserOnline]);

  // Announce the transitions, not the initial reading.
  const seenOnline = useRef<boolean | null>(null);
  useEffect(() => {
    if (seenOnline.current !== null && seenOnline.current !== browserOnline) {
      if (browserOnline) toast.success("You're back online.");
      else toast.warning("You're offline — changes can't be sent until the connection is back.");
    }
    seenOnline.current = browserOnline;
  }, [browserOnline]);

  const recovered = useCallback(() => {
    reportServerOk();
    toast.success(`Connected to ${serverName ?? "the server"} again.`);
    void qc.invalidateQueries();
  }, [reportServerOk, serverName, qc]);

  // Probe with backoff while the server is down and the device is online.
  useEffect(() => {
    if (!serverDown || !browserOnline || !serverUrl) return;
    let alive = true;
    let delay = FIRST_RETRY_MS;
    let timer = 0;
    const tick = async () => {
      const ok = await pingServer(serverUrl);
      if (!alive) return;
      if (ok) return recovered();
      delay = Math.min(delay * 1.5, MAX_RETRY_MS);
      timer = window.setTimeout(tick, delay);
    };
    timer = window.setTimeout(tick, delay);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [serverDown, browserOnline, serverUrl, recovered]);

  // A realtime drop that lasts is the earliest sign the server is gone —
  // confirm it with a probe before saying so.
  useEffect(() => {
    if (!serverUrl) return;
    let timer = 0;
    const stop = onConnectionStatus((s) => {
      clearTimeout(timer);
      if (s === "connected") return;
      timer = window.setTimeout(async () => {
        if (useConnectivity.getState().serverDown || !navigator.onLine) return;
        if (!(await pingServer(serverUrl))) reportServerFailure();
      }, REALTIME_GRACE_MS);
    });
    return () => {
      clearTimeout(timer);
      stop();
    };
  }, [serverUrl, reportServerFailure]);

  const retryNow = async () => {
    if (!serverUrl || retrying) return;
    setRetrying(true);
    const ok = await pingServer(serverUrl);
    setRetrying(false);
    if (ok) recovered();
    else toast.error(`Still can't reach ${serverName ?? "the server"}.`);
  };

  if (!browserOnline) {
    return (
      <div role="status" className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-4 py-1.5 text-[12.5px] text-warn">
        <WifiOff size={14} strokeWidth={2} className="flex-none" />
        <span>You&apos;re offline — check your internet connection. Changes can&apos;t be sent until it&apos;s back.</span>
      </div>
    );
  }
  if (serverDown) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-crit/30 bg-crit/10 px-4 py-1.5 text-[12.5px] text-crit">
        <span className="flex items-center gap-2"><ServerOff size={14} strokeWidth={2} className="flex-none" /> Can&apos;t reach {serverName ?? serverUrl ?? "the server"} — it may be down or restarting. Retrying automatically…</span>
        <button type="button" onClick={retryNow} disabled={retrying} className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-crit/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-crit/10 disabled:opacity-60">
          <RefreshCw size={12} strokeWidth={2} className={retrying ? "animate-spin" : ""} /> {retrying ? "Checking…" : "Retry now"}
        </button>
      </div>
    );
  }
  return null;
}
