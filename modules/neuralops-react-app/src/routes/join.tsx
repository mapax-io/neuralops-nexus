/**
 * /join?token=<invite_token>
 *
 * Landing page for invite links. Flow:
 *  1. Fetch invite info (public endpoint — shows who invited you)
 *  2. If not signed in → show sign-in/sign-up form
 *  3. After auth → verify server access (creates Django user + accepts company invite)
 *  4. Redeem the invitation token → adds user to the specific project/topic
 *  5. Add server to the saved server list → navigate to /app
 */
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles, UserPlus, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/auth.store";
import { signInWithEmail, signUpWithEmail, verifyServerAccess } from "@/services/auth.service";
import { loadServers, saveServers } from "@/components/auth/use-servers";
import { getSupabase } from "@/lib/supabase";

// ── Route definition ──────────────────────────────────────────────────────────

export const Route = createFileRoute("/join")({
  validateSearch: (search) => ({
    token: (search.token as string) ?? "",
  }),
  head: () => ({
    meta: [{ title: "Join NeuralOps — Accept Invitation" }],
  }),
  component: JoinPage,
});

// ── Types ─────────────────────────────────────────────────────────────────────

interface InviteInfo {
  email: string;
  invited_by: string;
  server_url: string;
  expires_at: string;
}

type Stage =
  | "loading"      // fetching invite info
  | "invalid"      // token not found / expired
  | "auth"         // waiting for sign-in / sign-up
  | "joining"      // redeeming the invite
  | "done"         // success
  | "error";       // redeem failed

const authSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(6, "At least 6 characters"),
});
type AuthValues = z.infer<typeof authSchema>;

// ── Component ─────────────────────────────────────────────────────────────────

function JoinPage() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const setIdentity = useAuthStore((s) => s.setIdentity);
  const setServerInfo = useAuthStore((s) => s.setServerInfo);

  const [stage, setStage] = useState<Stage>("loading");
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signup");
  const [authError, setAuthError] = useState<string | null>(null);
  const [joinMessage, setJoinMessage] = useState("");

  const serverOrigin = window.location.origin;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AuthValues>({ resolver: zodResolver(authSchema) });

  // ── Step 1: fetch invite info ───────────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setStage("invalid");
      setJoinMessage("No invitation token found in the link.");
      return;
    }

    fetch(`${serverOrigin}/api/v1/auth/invite/info/?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? "Invitation not found or already used.");
        }
        return res.json() as Promise<InviteInfo>;
      })
      .then((data) => {
        setInfo(data);
        // If already signed in, skip straight to joining
        if (supabaseToken) {
          setStage("joining");
          redeemInvite(supabaseToken);
        } else {
          setStage("auth");
        }
      })
      .catch((err) => {
        setStage("invalid");
        setJoinMessage(err.message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Step 2: handle sign-in / sign-up ────────────────────────────────────────
  async function onAuthSubmit(values: AuthValues) {
    setAuthError(null);
    try {
      const fn = authMode === "signin" ? signInWithEmail : signUpWithEmail;
      const data = await fn(values.email, values.password);
      const session = data.session;
      if (!session?.access_token || !session.user) {
        setAuthError("Check your email to confirm your account, then try signing in.");
        return;
      }
      setIdentity(session.access_token, session.user.id, session.user.email ?? values.email);
      setStage("joining");
      await redeemInvite(session.access_token);
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Authentication failed");
    }
  }

  // ── Step 3: verify server + redeem token ─────────────────────────────────────
  async function redeemInvite(accessToken: string) {
    setStage("joining");
    try {
      // 3a. Verify server access → creates Django user + auto-accepts company invite
      const verify = await verifyServerAccess(serverOrigin, accessToken);
      if (!verify.ok) {
        const msg =
          verify.status === 403
            ? "This server did not recognise your invitation. It may have expired."
            : "Could not connect to the server.";
        setStage("error");
        setJoinMessage(msg);
        return;
      }

      // 3b. Explicitly redeem the invite token → adds user to specific project/topic
      const redeemRes = await fetch(`${serverOrigin}/api/v1/auth/invite/redeem/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ token }),
      });
      // Redeem errors are non-fatal — company access was already granted
      if (!redeemRes.ok) {
        console.warn("[join] redeem endpoint returned", redeemRes.status);
      }

      // 3c. Add server to saved list (if not already there)
      const servers = loadServers();
      const alreadySaved = servers.some(
        (s) => s.url.replace(/\/$/, "") === serverOrigin.replace(/\/$/, ""),
      );
      if (!alreadySaved) {
        const name = verify.companyName ?? "NeuralOps Server";
        saveServers([...servers, { id: crypto.randomUUID(), name, url: serverOrigin }]);
      }

      // 3d. Set server context in auth store
      setServerInfo({
        serverUrl: serverOrigin,
        userId: verify.userId,
        role: verify.role,
        companyName: verify.companyName,
        isOwner: verify.isOwner,
      });

      setStage("done");
      setJoinMessage("You've joined the workspace! Redirecting…");
      setTimeout(() => navigate({ to: "/app", replace: true }), 1500);
    } catch (e) {
      setStage("error");
      setJoinMessage(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-subtle px-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">NeuralOps</h1>
          <p className="mt-1 text-sm text-foreground-muted">You've been invited to join a workspace</p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-border bg-card p-6">
          {stage === "loading" && (
            <div className="flex flex-col items-center gap-3 py-4 text-foreground-muted">
              <Loader2 className="h-6 w-6 animate-spin" />
              <p className="text-sm">Loading invitation…</p>
            </div>
          )}

          {stage === "invalid" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <XCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium text-foreground">Invitation not valid</p>
              <p className="text-xs text-foreground-muted">{joinMessage}</p>
              <Button variant="outline" size="sm" onClick={() => navigate({ to: "/" })}>
                Go to sign-in
              </Button>
            </div>
          )}

          {(stage === "auth") && (
            <>
              {/* Invite banner */}
              {info && (
                <div className="mb-5 rounded-lg border border-border-strong bg-background-subtle px-4 py-3">
                  <div className="flex items-start gap-3">
                    <UserPlus className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div className="text-xs leading-relaxed text-foreground-muted">
                      <span className="font-medium text-foreground">{info.invited_by}</span> invited{" "}
                      <span className="font-medium text-foreground">{info.email}</span> to join this
                      NeuralOps workspace.
                    </div>
                  </div>
                </div>
              )}

              {/* Auth form */}
              <form onSubmit={handleSubmit(onAuthSubmit)} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" autoComplete="email" {...register("email")} />
                  {errors.email && (
                    <p className="text-xs text-destructive">{errors.email.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete={authMode === "signin" ? "current-password" : "new-password"}
                    {...register("password")}
                  />
                  {errors.password && (
                    <p className="text-xs text-destructive">{errors.password.message}</p>
                  )}
                </div>

                {authError && (
                  <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                    {authError}
                  </p>
                )}

                <Button type="submit" disabled={isSubmitting} className="w-full">
                  {isSubmitting
                    ? "Please wait…"
                    : authMode === "signup"
                    ? "Create account & join"
                    : "Sign in & join"}
                </Button>

                <button
                  type="button"
                  onClick={() => {
                    setAuthMode(authMode === "signin" ? "signup" : "signin");
                    setAuthError(null);
                  }}
                  className="text-xs text-foreground-muted hover:text-foreground"
                >
                  {authMode === "signup"
                    ? "Already have an account? Sign in"
                    : "New to NeuralOps? Create an account"}
                </button>
              </form>
            </>
          )}

          {stage === "joining" && (
            <div className="flex flex-col items-center gap-3 py-4 text-foreground-muted">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <p className="text-sm">Joining workspace…</p>
            </div>
          )}

          {stage === "done" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <CheckCircle2 className="h-8 w-8 text-green-500" />
              <p className="text-sm font-medium text-foreground">Welcome to NeuralOps!</p>
              <p className="text-xs text-foreground-muted">{joinMessage}</p>
            </div>
          )}

          {stage === "error" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <XCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium text-foreground">Could not join</p>
              <p className="text-xs text-foreground-muted">{joinMessage}</p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setStage("auth")}>
                  Try again
                </Button>
                <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/" })}>
                  Go home
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
