"use client";

import { TriangleAlert } from "lucide-react";
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
  const { serverTooOld } = usePermissions();
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
