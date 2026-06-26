import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/app/agents")({
  component: () => (
    <div className="p-8">
      <h1 className="text-xl font-semibold">Agents</h1>
      <p className="mt-2 text-sm text-[color:var(--foreground-muted)]">
        Agent orchestration coming soon.
      </p>
    </div>
  ),
});
