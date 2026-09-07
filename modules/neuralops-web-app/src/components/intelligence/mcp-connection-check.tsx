"use client";

import { useRef, useState } from "react";
import { CircleAlert, CircleX, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  createMcpServer, listMcpServers, patchMcpServer, verifyMcpConnection,
  type MCPServer, type MCPServerCreate, type MCPServerPatch, type McpVerifyRequest, type McpVerifyResult,
} from "@/lib/api/intelligence";
import { connectMcpOAuth, OAuthPopupError } from "@/lib/mcp-oauth";

// Saving an MCP server is a sequence, not a POST: check the connection the
// way a persona run would open it, then save, then (OAuth) sign in and
// confirm with the token. The dialog stays open until every step has
// passed, and every failure lands here as a status the footer can show —
// the fields stay editable throughout, so the fix happens in place.
export type CheckStatus =
  | { kind: "idle" }
  | { kind: "busy"; phase: "checking" | "saving" | "signing-in" | "confirming" }
  // The probe said no — the fields are wrong somewhere.
  | { kind: "failed"; result: McpVerifyResult }
  // The check itself could not run: the worker is down, or the server is
  // too old to have the route. The row can still be saved unchecked.
  | { kind: "unavailable"; reason: "worker" | "unsupported"; message: string }
  // The row is saved; the provider sign-in did not complete.
  | { kind: "sign-in-failed"; message: string }
  // Saving itself failed (a 4xx/5xx, or the server went away).
  | { kind: "error"; message: string };

export interface SavePlan {
  serverId?: string;               // an existing row (edit), or one created earlier in this dialog
  probe: McpVerifyRequest;         // the connection as typed (+ project_id or server_id)
  payload: MCPServerCreate | MCPServerPatch;
  oauth: boolean;                  // auth_type === "oauth2" — a sign-in follows the save
  skipCheck?: boolean;             // "Save without checking" after an unavailable check
  onCreated?: (server: MCPServer) => void;   // the row now exists — retries must patch it
  onSaved: (server: MCPServer, outcome: SaveOutcome) => void;
}

export interface SaveOutcome {
  checked: boolean;                // a probe passed (before the save, or after the sign-in)
  tools: number;
  connected: boolean;              // OAuth sign-in completed in this run
}

export function useMcpConnectionFlow(serverUrl: string | null) {
  const [status, setStatus] = useState<CheckStatus>({ kind: "idle" });
  // The plan of the run in progress, kept for a sign-in retry after the row exists.
  const planRef = useRef<{ plan: SavePlan; server: MCPServer; outcome: SaveOutcome } | null>(null);

  const signIn = async (plan: SavePlan, server: MCPServer, outcome: SaveOutcome) => {
    planRef.current = { plan, server, outcome };
    setStatus({ kind: "busy", phase: "signing-in" });
    try {
      await connectMcpOAuth(server.id, serverUrl, async () => {
        // Popup closed without a message — the exchange may still have
        // completed server-side; a token that was not there before is a yes.
        const after = (await listMcpServers()).find((s) => s.id === server.id);
        if (!after?.oauth_connected) return false;
        return !server.oauth_connected || (after.oauth_config?.expires_at ?? null) !== (server.oauth_config?.expires_at ?? null);
      });
    } catch (e) {
      const message = e instanceof OAuthPopupError
        ? (e.code === "cancelled" ? "Sign-in was cancelled." : e.message)
        : (e instanceof Error ? e.message : "Couldn't complete the sign-in.");
      setStatus({ kind: "sign-in-failed", message });
      return;
    }
    setStatus({ kind: "busy", phase: "confirming" });
    let result: McpVerifyResult | null = null;
    try {
      result = await verifyMcpConnection({ server_id: server.id });
    } catch (e) {
      // The token is stored either way; an older server just can't confirm it.
      if (!(e instanceof ApiError && e.status === 404)) {
        setStatus({ kind: "error", message: e instanceof Error ? e.message : "Couldn't confirm the connection." });
        return;
      }
    }
    if (result && !result.ok && result.code !== "worker_unavailable") {
      setStatus({ kind: "failed", result });
      return;
    }
    setStatus({ kind: "idle" });
    plan.onSaved(server, { ...outcome, connected: true, checked: !!result?.ok, tools: result?.ok ? result.tools.length : outcome.tools });
  };

  const run = async (plan: SavePlan) => {
    let outcome: SaveOutcome = { checked: false, tools: 0, connected: false };
    if (!plan.skipCheck) {
      setStatus({ kind: "busy", phase: "checking" });
      let result: McpVerifyResult;
      try {
        result = await verifyMcpConnection(plan.probe);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setStatus({ kind: "unavailable", reason: "unsupported", message: "This server can't check connections yet — it's an older version. You can save the server without a check." });
        } else {
          setStatus({ kind: "error", message: e instanceof Error ? e.message : "The connection check failed." });
        }
        return;
      }
      if (result.code === "worker_unavailable") {
        setStatus({ kind: "unavailable", reason: "worker", message: result.error ?? "The AI worker isn't reachable, so the connection can't be checked right now." });
        return;
      }
      // An OAuth server answers 401 until someone has signed in — that is
      // the sign-in step's job, not a wrong address.
      const needsSignIn = plan.oauth && result.code === "auth_required";
      if (!result.ok && !needsSignIn) {
        setStatus({ kind: "failed", result });
        return;
      }
      outcome = { checked: result.ok, tools: result.ok ? result.tools.length : 0, connected: false };
    }
    setStatus({ kind: "busy", phase: "saving" });
    let server: MCPServer;
    try {
      server = plan.serverId
        ? await patchMcpServer(plan.serverId, plan.payload as MCPServerPatch)
        : await createMcpServer(plan.payload as MCPServerCreate);
    } catch (e) {
      setStatus({ kind: "error", message: e instanceof Error ? e.message : "Couldn't save the server." });
      return;
    }
    if (!plan.serverId) plan.onCreated?.(server);
    if (plan.oauth && !server.oauth_connected) {
      await signIn(plan, server, outcome);
      return;
    }
    setStatus({ kind: "idle" });
    plan.onSaved(server, outcome);
  };

  const retrySignIn = () => {
    const held = planRef.current;
    if (held) void signIn(held.plan, held.server, held.outcome);
  };

  const reset = () => {
    planRef.current = null;
    setStatus({ kind: "idle" });
  };

  return { status, run, retrySignIn, reset, busy: status.kind === "busy" };
}

// Reads the step (or the failure) in the pinned footer, next to the buttons,
// so it is visible however far the form is scrolled.
export function ConnectionCheckPanel({ status, target, onSaveAnyway, onSignIn }: {
  status: CheckStatus;
  target: string;                  // what is being checked — the URL or command
  onSaveAnyway: () => void;
  onSignIn: () => void;
}) {
  if (status.kind === "idle") return null;
  if (status.kind === "busy") {
    const text = {
      checking: `Checking the connection to ${target || "the server"}…`,
      saving: "Saving…",
      "signing-in": "Finish signing in in the window that opened…",
      confirming: "Signed in — confirming the connection…",
    }[status.phase];
    return (
      <p role="status" className="flex min-w-0 items-center gap-2 text-[12.5px] text-ink2">
        <LoaderCircle size={14} strokeWidth={2} className="flex-none animate-spin" /> <span className="truncate">{text}</span>
      </p>
    );
  }
  if (status.kind === "failed") {
    return (
      <p role="alert" className="flex min-w-0 items-start gap-2 text-[12.5px] leading-snug text-crit">
        <CircleX size={14} strokeWidth={2} className="mt-0.5 flex-none" />
        <span><b>Couldn&apos;t connect.</b> {status.result.error} Fix it above and try again.</span>
      </p>
    );
  }
  if (status.kind === "error") {
    return (
      <p role="alert" className="flex min-w-0 items-start gap-2 text-[12.5px] leading-snug text-crit">
        <CircleX size={14} strokeWidth={2} className="mt-0.5 flex-none" /><span>{status.message}</span>
      </p>
    );
  }
  if (status.kind === "unavailable") {
    return (
      <div role="alert" className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] leading-snug text-warn">
        <span className="flex items-start gap-2"><CircleAlert size={14} strokeWidth={2} className="mt-0.5 flex-none" /><span>{status.message}</span></span>
        <Button type="button" size="sm" variant="ghost" onClick={onSaveAnyway}>Save without checking</Button>
      </div>
    );
  }
  return (
    <div role="alert" className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] leading-snug text-warn">
      <span className="flex items-start gap-2"><CircleAlert size={14} strokeWidth={2} className="mt-0.5 flex-none" /><span>{status.message} The server is saved — sign in now, or later from its card.</span></span>
      <Button type="button" size="sm" variant="ghost" onClick={onSignIn}>Sign in</Button>
    </div>
  );
}
