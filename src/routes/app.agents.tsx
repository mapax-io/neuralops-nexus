import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/app/agents")({
  component: () => (
    <div className="p-8">
      <h1 className="text-lg font-semibold text-foreground">Agents</h1>
      <p className="mt-1 text-sm text-foreground-muted">
        Manage your autonomous agents. Coming next.
      </p>
    </div>
  ),
});
