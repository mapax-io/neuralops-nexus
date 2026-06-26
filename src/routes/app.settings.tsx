import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth.store";
import { useNavigate } from "@tanstack/react-router";

export const Route = createFileRoute("/app/settings")({
  component: SettingsPage,
});

function SettingsPage() {
  const { email, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-[color:var(--foreground-muted)]">
          Manage your device and account.
        </p>
      </div>
      <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--card)] p-6">
        <div className="text-xs uppercase tracking-wider text-[color:var(--foreground-muted)]">
          Signed in as
        </div>
        <div className="mt-1 text-sm font-medium">{email ?? "—"}</div>
      </div>
      <Button
        variant="outline"
        onClick={() => {
          clearAuth();
          navigate({ to: "/" });
        }}
      >
        Deactivate device
      </Button>
    </div>
  );
}
