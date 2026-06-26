import { Loader2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  loginUrl: string;
  activated?: boolean;
}

function displayDomain(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function ActivationScreen({ loginUrl, activated }: Props) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[color:var(--background-subtle)] px-4">
      <div className="w-full max-w-md rounded-xl border border-[color:var(--border)] bg-[color:var(--card)] p-8 shadow-sm">
        <div className="flex flex-col items-center gap-6 text-center">
          <div className="flex items-center gap-2">
            <div className="size-8 rounded-md bg-[color:var(--primary)]" />
            <span className="text-lg font-semibold">NeuralOps</span>
          </div>

          <div className="space-y-1">
            <h1 className="text-2xl font-semibold">Activate this device</h1>
            <p className="text-sm text-[color:var(--foreground-muted)]">
              Sign in to connect this device to your NeuralOps account.
            </p>
          </div>

          <div className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--background-subtle)] px-4 py-3">
            <div className="text-xs uppercase tracking-wide text-[color:var(--muted-foreground)]">
              Portal
            </div>
            <div className="font-mono text-sm text-[color:var(--foreground)]">
              {displayDomain(loginUrl)}
            </div>
          </div>

          <Button
            asChild
            className="w-full"
            style={{ backgroundColor: "var(--primary)", color: "var(--primary-foreground)" }}
          >
            <a href={loginUrl} target="_blank" rel="noreferrer">
              Open sign in page <ExternalLink className="ml-2 size-4" />
            </a>
          </Button>

          <div className="h-px w-full bg-[color:var(--border)]" />

          {activated ? (
            <div className="text-sm font-medium text-[color:var(--primary)]">
              ✓ Activated — launching…
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-[color:var(--foreground-muted)]">
              <Loader2 className="size-4 animate-spin text-[color:var(--primary)]" />
              Waiting for activation… This page will update automatically.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
