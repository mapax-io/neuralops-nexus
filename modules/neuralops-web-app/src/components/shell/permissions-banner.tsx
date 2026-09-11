"use client";

import { RefreshCw, TriangleAlert } from "lucide-react";
import { usePermissions } from "@/hooks/use-permissions";

// Says so when the connected server predates scoped permissions
// (GET /api/v1/me/permissions/ answers 404). Without it the app has nothing
// to gate on and every management control is simply absent — which reads as
// a broken app rather than an out-of-date server. Sits under the top bar,
// beside ConnectivityBanner, and is the only thing that explains the gap.
//
// The client deliberately does NOT guess from the company role instead: role
// bundles are editable server-side, and a company role can never express the
// project- or topic-scoped assignment that most of these controls turn on.
export function PermissionsBanner() {
  const { serverTooOld, failed, retry } = usePermissions();

  // Same consequence as an out-of-date server -- nothing can be offered -- but
  // a different cause and a different remedy, so it says which and offers the
  // remedy. Silently hiding every control is what this banner exists to avoid.
  if (failed) {
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-warn/30 bg-warn/10 px-4 py-1.5 text-[12.5px] text-warn"
      >
        <span className="flex items-center gap-2">
          <TriangleAlert size={14} strokeWidth={2} className="flex-none" />
          Couldn&apos;t load what you&apos;re allowed to do, so management controls are hidden.
        </span>
        <button
          type="button"
          onClick={retry}
          className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-warn/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-warn/10"
        >
          <RefreshCw size={12} strokeWidth={2} /> Try again
        </button>
      </div>
    );
  }

  if (!serverTooOld) return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-warn/30 bg-warn/10 px-4 py-1.5 text-[12.5px] text-warn"
    >
      <TriangleAlert size={14} strokeWidth={2} className="flex-none" />
      <span>
        This server is out of date — it can&apos;t tell the app what you&apos;re allowed to do, so
        management controls are hidden. Update the server to create and edit projects, personas,
        models and MCP servers.
      </span>
    </div>
  );
}
