import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { ServerList } from "@/components/auth/ServerList";
import { useAuthStore } from "@/store/auth.store";
import { Button } from "@/components/ui/button";
import { signOut } from "@/services/auth.service";

export const Route = createFileRoute("/servers")({
  head: () => ({
    meta: [{ title: "Select a server — NeuralOps" }],
  }),
  component: ServersPage,
});

function ServersPage() {
  const navigate = useNavigate();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const email = useAuthStore((s) => s.email);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  useEffect(() => {
    if (!supabaseToken) navigate({ to: "/", replace: true });
  }, [supabaseToken, navigate]);

  async function handleSignOut() {
    try {
      await signOut();
    } catch {
      /* ignore */
    }
    clearAuth();
    navigate({ to: "/" });
  }

  return (
    <div className="min-h-screen bg-background-subtle px-4 py-12">
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              Select a server
            </h1>
            <p className="mt-1 text-sm text-foreground-muted">
              Connect to a NeuralOps server to start working.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-foreground-muted">{email}</span>
            <Button variant="ghost" size="sm" onClick={handleSignOut}>
              Sign out
            </Button>
          </div>
        </div>
        <ServerList />
      </div>
    </div>
  );
}
