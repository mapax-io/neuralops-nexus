import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { ActivationScreen } from "@/components/auth/ActivationScreen";
import { useAuthInit, useAuthStatus } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/auth.store";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Activate device — NeuralOps" },
      {
        name: "description",
        content: "Activate this device to start using NeuralOps.",
      },
    ],
  }),
  component: ActivatePage,
});

function ActivatePage() {
  const navigate = useNavigate();
  const { userId, setIdentity } = useAuthStore();
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [activated, setActivated] = useState(false);

  const init = useAuthInit();

  // Handle init response
  useEffect(() => {
    const data = init.data;
    if (!data) return;
    if (
      data.status === "authenticated" &&
      data.user_id &&
      data.email &&
      data.session_expires_at
    ) {
      setIdentity(data.user_id, data.email, data.session_expires_at);
      navigate({ to: "/app" });
    } else if (data.status === "unauthenticated" && data.login_url) {
      setLoginUrl(data.login_url);
    }
  }, [init.data, setIdentity, navigate]);

  // Already authenticated from persisted store
  useEffect(() => {
    if (userId) navigate({ to: "/app" });
  }, [userId, navigate]);

  const status = useAuthStatus(!!loginUrl && !activated);

  useEffect(() => {
    const data = status.data;
    if (!data) return;
    if (
      data.status === "active" &&
      data.user_id &&
      data.email &&
      data.session_expires_at
    ) {
      setIdentity(data.user_id, data.email, data.session_expires_at);
      setActivated(true);
      setTimeout(() => navigate({ to: "/app" }), 600);
    } else if (data.status === "session_expired") {
      setLoginUrl(null);
      init.refetch();
    }
  }, [status.data, setIdentity, navigate, init]);

  if (init.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[color:var(--background-subtle)]">
        <Loader2 className="size-6 animate-spin text-[color:var(--primary)]" />
      </div>
    );
  }

  if (init.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[color:var(--background-subtle)] px-4">
        <div className="w-full max-w-md space-y-4 rounded-xl border border-[color:var(--border)] bg-[color:var(--card)] p-8 text-center shadow-sm">
          <h1 className="text-xl font-semibold">Backend unreachable</h1>
          <p className="text-sm text-[color:var(--foreground-muted)]">
            Could not reach the NeuralOps backend. Make sure the app is running.
          </p>
          <Button onClick={() => init.refetch()}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!loginUrl) return null;

  return <ActivationScreen loginUrl={loginUrl} activated={activated} />;
}
