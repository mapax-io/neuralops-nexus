import { createFileRoute } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth.store";

export const Route = createFileRoute("/app/settings")({
  component: SettingsPage,
});

function SettingsPage() {
  const email = useAuthStore((s) => s.email);
  const serverUrl = useAuthStore((s) => s.serverUrl);

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="text-lg font-semibold text-foreground">Settings</h1>
      <div className="mt-6 rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold">Account</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <dt className="text-foreground-muted">Email</dt>
            <dd>{email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-foreground-muted">Connected server</dt>
            <dd className="truncate">{serverUrl}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
