/**
 * /join?server=<django_url>&token=<invite_token>
 *
 * Landing page for invite links.
 *
 * Works in two modes:
 *  A) Email confirmation OFF (recommended for private teams):
 *     signUp → live session → redeem → /app  (single click, no email needed)
 *
 *  B) Email confirmation ON:
 *     signUp → "check your email" state → user clicks confirm link →
 *     Supabase redirects back to THIS page with #access_token in URL →
 *     page reads hash, resumes redeem → /app
 */
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Sparkles, UserPlus, Loader2, CheckCircle2, XCircle,
  Server, Mail,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/auth.store";
import { signInWithEmail, signUpWithEmail, verifyServerAccess } from "@/services/auth.service";
import { loadServers, saveServers } from "@/components/auth/use-servers";
import { getSupabase } from "@/lib/supabase";

// ── Route ─────────────────────────────────────────────────────────────────────

export const Route = createFileRoute("/join")({
  validateSearch: (search) => ({
    token:  (search.token  as string) ?? "",
    server: (search.server as string) ?? "",
  }),
  head: () => ({ meta: [{ title: "Join NeuralOps — Accept Invitation" }] }),
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
  | "loading"        // fetching invite info
  | "invalid"        // bad/missing token or server
  | "auth"           // sign-in / sign-up form
  | "confirm_email"  // waiting for user to click the confirmation email
  | "joining"        // calling verify + redeem
  | "done"           // all good → redirecting
  | "error";

const authSchema = z.object({
  email:    z.string().email("Enter a valid email"),
  password: z.string().min(6, "At least 6 characters"),
});
type AuthValues = z.infer<typeof authSchema>;

// ── Component ─────────────────────────────────────────────────────────────────

function JoinPage() {
  const { token, server: serverParam } = Route.useSearch();
  const navigate   = useNavigate();
  const setIdentity   = useAuthStore((s) => s.setIdentity);
  const setServerInfo = useAuthStore((s) => s.setServerInfo);
  const existingToken = useAuthStore((s) => s.supabaseToken);

  const [stage,    setStage]    = useState<Stage>("loading");
  const [info,     setInfo]     = useState<InviteInfo | null>(null);
  const [djangoUrl, setDjangoUrl] = useState<string>("");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signup");
  const [authError, setAuthError] = useState<string | null>(null);
  const [message,  setMessage]  = useState("");

  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<AuthValues>({ resolver: zodResolver(authSchema) });

  // ── On mount: handle both normal load AND Supabase email-confirm redirect ──
  useEffect(() => {
    // Mode B: Supabase redirected back after email confirmation.
    // Tokens arrive in the URL hash: #access_token=...&type=signup
    const hash = window.location.hash;
    if (hash.includes("access_token")) {
      const hp = new URLSearchParams(hash.replace(/^#/, ""));
      const at = hp.get("access_token");
      const rt = hp.get("refresh_token") ?? "";
      if (at) {
        // Remove hash from URL so a refresh doesn't re-trigger this
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        // Tell Supabase client about the session
        getSupabase().auth.setSession({ access_token: at, refresh_token: rt }).then(({ data }) => {
          const s = data.session;
          if (s) {
            setIdentity(s.access_token, s.user.id, s.user.email ?? "");
            const srv = serverParam.replace(/\/$/, "");
            setDjangoUrl(srv);
            if (srv && token) {
              setStage("joining");
              redeemInvite(s.access_token, srv);
            } else {
              setStage("error");
              setMessage("Missing server or token after email confirmation.");
            }
          } else {
            setStage("error");
            setMessage("Could not restore session after email confirmation.");
          }
        });
        return; // skip normal init
      }
    }

    // Mode A: normal page load
    if (!token) {
      setStage("invalid");
      setMessage("No invitation token found in the link.");
      return;
    }
    if (!serverParam) {
      setStage("invalid");
      setMessage("This invite link is missing the server address. Ask the sender to resend it.");
      return;
    }

    const cleanServer = serverParam.replace(/\/$/, "");
    setDjangoUrl(cleanServer);

    fetch(`${cleanServer}/api/v1/auth/invite/info/?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? "Invitation not found or already used.");
        }
        return res.json() as Promise<InviteInfo>;
      })
      .then((data) => {
        setInfo(data);
        // Already signed in → jump straight to redeem
        if (existingToken) {
          setStage("joining");
          redeemInvite(existingToken, cleanServer);
        } else {
          setStage("auth");
        }
      })
      .catch((err) => {
        setStage("invalid");
        setMessage(err.message);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Sign-in / sign-up ──────────────────────────────────────────────────────
  async function onAuthSubmit(values: AuthValues) {
    setAuthError(null);
    try {
      if (authMode === "signin") {
        const data = await signInWithEmail(values.email, values.password);
        const session = data.session;
        if (!session?.access_token || !session.user) {
          setAuthError("Sign-in failed. Check your email and password.");
          return;
        }
        setIdentity(session.access_token, session.user.id, session.user.email ?? values.email);
        setStage("joining");
        await redeemInvite(session.access_token, djangoUrl);

      } else {
        // Sign-up: redirect back to THIS join page after email confirmation
        // so the hash handler above can complete the flow automatically.
        const confirmRedirect =
          `${window.location.origin}/join?server=${encodeURIComponent(serverParam)}&token=${encodeURIComponent(token)}`;

        const { data, error } = await getSupabase().auth.signUp({
          email:    values.email,
          password: values.password,
          options:  { emailRedirectTo: confirmRedirect },
        });
        if (error) throw error;

        const session = data.session;
        if (session?.access_token && session.user) {
          // Email confirmation is OFF → live session, proceed immediately
          setIdentity(session.access_token, session.user.id, session.user.email ?? values.email);
          setStage("joining");
          await redeemInvite(session.access_token, djangoUrl);
        } else {
          // Email confirmation is ON → waiting for the user to click the link
          setStage("confirm_email");
        }
      }
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Authentication failed");
    }
  }

  // ── Verify server + redeem invite token ────────────────────────────────────
  async function redeemInvite(accessToken: string, serverUrl: string) {
    const cleanServer = serverUrl.replace(/\/$/, "");
    try {
      // Creates Django user & accepts company-level invite
      const verify = await verifyServerAccess(cleanServer, accessToken);
      if (!verify.ok) {
        setStage("error");
        setMessage(
          verify.status === 403
            ? "This server did not recognise your invitation. It may have expired."
            : "Could not reach the NeuralOps server. Check your network."
        );
        return;
      }

      // Add user to specific project/topic
      await fetch(`${cleanServer}/api/v1/auth/invite/redeem/`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body:    JSON.stringify({ token }),
      }).catch(() => {/* non-fatal */});

      // Auto-add server to saved list
      const servers = loadServers();
      if (!servers.some((s) => s.url.replace(/\/$/, "") === cleanServer)) {
        saveServers([
          ...servers,
          { id: crypto.randomUUID(), name: verify.companyName ?? "NeuralOps Server", url: cleanServer },
        ]);
      }

      // Activate this server
      setServerInfo({
        serverUrl:   cleanServer,
        userId:      verify.userId,
        role:        verify.role,
        companyName: verify.companyName,
        isOwner:     verify.isOwner,
      });

      setStage("done");
      setMessage("You've joined the workspace! Taking you in…");
      setTimeout(() => navigate({ to: "/app", replace: true }), 1200);
    } catch (e) {
      setStage("error");
      setMessage(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  // ── UI ─────────────────────────────────────────────────────────────────────

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-subtle px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">NeuralOps</h1>
          <p className="mt-1 text-sm text-foreground-muted">You've been invited to join a workspace</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">

          {/* Loading */}
          {stage === "loading" && (
            <div className="flex flex-col items-center gap-3 py-4 text-foreground-muted">
              <Loader2 className="h-6 w-6 animate-spin" />
              <p className="text-sm">Loading invitation…</p>
            </div>
          )}

          {/* Invalid */}
          {stage === "invalid" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <XCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium text-foreground">Invitation not valid</p>
              <p className="text-xs text-foreground-muted">{message}</p>
              <Button variant="outline" size="sm" onClick={() => navigate({ to: "/" })}>Go to sign-in</Button>
            </div>
          )}

          {/* Auth form */}
          {stage === "auth" && (
            <>
              {info && (
                <div className="mb-5 space-y-2">
                  <div className="rounded-lg border border-border-strong bg-background-subtle px-4 py-3">
                    <div className="flex items-start gap-3">
                      <UserPlus className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <p className="text-xs leading-relaxed text-foreground-muted">
                        <span className="font-medium text-foreground">{info.invited_by}</span>{" "}
                        invited <span className="font-medium text-foreground">{info.email}</span> to join this workspace.
                      </p>
                    </div>
                  </div>
                  {djangoUrl && (
                    <div className="flex items-center gap-2 rounded-lg border border-border bg-background-subtle px-3 py-2">
                      <Server className="h-3 w-3 shrink-0 text-foreground-muted" />
                      <span className="truncate font-mono text-[11px] text-foreground-muted">{djangoUrl}</span>
                    </div>
                  )}
                </div>
              )}

              <form onSubmit={handleSubmit(onAuthSubmit)} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" autoComplete="email" {...register("email")} />
                  {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password" type="password"
                    autoComplete={authMode === "signin" ? "current-password" : "new-password"}
                    {...register("password")}
                  />
                  {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
                </div>

                {authError && (
                  <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                    {authError}
                  </p>
                )}

                <Button type="submit" disabled={isSubmitting} className="w-full">
                  {isSubmitting ? "Please wait…" : authMode === "signup" ? "Create account & join" : "Sign in & join"}
                </Button>

                <button
                  type="button"
                  onClick={() => { setAuthMode(authMode === "signin" ? "signup" : "signin"); setAuthError(null); }}
                  className="text-xs text-foreground-muted hover:text-foreground"
                >
                  {authMode === "signup" ? "Already have an account? Sign in" : "New to NeuralOps? Create an account"}
                </button>
              </form>
            </>
          )}

          {/* Waiting for email confirmation */}
          {stage === "confirm_email" && (
            <div className="flex flex-col items-center gap-4 py-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <Mail className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Check your email</p>
                <p className="mt-1 text-xs text-foreground-muted">
                  We sent a confirmation link. Click it and you'll be taken straight into the workspace — no extra steps.
                </p>
              </div>
              <button
                type="button"
                onClick={() => { setStage("auth"); setAuthMode("signin"); }}
                className="text-xs text-foreground-muted hover:text-foreground"
              >
                Already confirmed? Sign in instead
              </button>
            </div>
          )}

          {/* Joining */}
          {stage === "joining" && (
            <div className="flex flex-col items-center gap-3 py-4 text-foreground-muted">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <p className="text-sm">Joining workspace…</p>
            </div>
          )}

          {/* Done */}
          {stage === "done" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <CheckCircle2 className="h-8 w-8 text-green-500" />
              <p className="text-sm font-medium text-foreground">Welcome to NeuralOps!</p>
              <p className="text-xs text-foreground-muted">{message}</p>
            </div>
          )}

          {/* Error */}
          {stage === "error" && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <XCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium text-foreground">Could not join</p>
              <p className="text-xs text-foreground-muted">{message}</p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setStage("auth")}>Try again</Button>
                <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/" })}>Go home</Button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
