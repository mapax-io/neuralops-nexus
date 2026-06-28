import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useAuthStore } from "@/store/auth.store";

export const Route = createFileRoute("/app")({
  component: AppLayout,
});

function AppLayout() {
  const navigate = useNavigate();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const serverUrl = useAuthStore((s) => s.serverUrl);

  useEffect(() => {
    if (!supabaseToken) navigate({ to: "/", replace: true });
    else if (!serverUrl) navigate({ to: "/servers", replace: true });
  }, [supabaseToken, serverUrl, navigate]);

  if (!supabaseToken || !serverUrl) return null;

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
