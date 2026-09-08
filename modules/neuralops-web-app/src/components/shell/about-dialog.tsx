"use client";

import { Info } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { NexusMark } from "@/components/brand/wordmark";
import { APP_NAME, APP_STAGE, APP_VERSION } from "@/lib/version";
import { useConnectionStore } from "@/stores/connection.store";

export function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { serverUrl, connection } = useConnectionStore();
  return (
    <Dialog open={open} onClose={onClose} title={`About ${APP_NAME}`} icon={<Info size={17} strokeWidth={2} />} tone="info">
      <div className="flex items-center gap-3">
        <NexusMark className="size-10" />
        <div>
          <p className="font-display text-[16px] font-bold">{APP_NAME}</p>
          <p className="text-[13px] text-ink2">{APP_STAGE} · v{APP_VERSION}</p>
        </div>
      </div>
      <p className="mt-4 text-[13.5px] text-ink2">The operating system for AI-driven teams — humans, personas, and agents in one shared workspace.</p>
      {serverUrl && (
        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl border border-line bg-surface2 p-4 text-[12.5px]">
          <dt className="text-ink2">Server</dt><dd title={serverUrl ?? undefined} className="truncate font-mono">{serverUrl}</dd>
          <dt className="text-ink2">Server version</dt><dd className="font-mono">{connection?.serverVersion ?? "unknown"}</dd>
          <dt className="text-ink2">Core</dt><dd className="font-mono">{connection?.moduleVersions.nucleus ?? "—"}</dd>
          <dt className="text-ink2">AI worker</dt><dd className="font-mono">{connection?.moduleVersions.nexusAi ?? "—"}</dd>
          <dt className="text-ink2">Transport</dt><dd className="font-mono">{connection?.moduleVersions.transport ?? "—"}</dd>
        </dl>
      )}
    </Dialog>
  );
}
