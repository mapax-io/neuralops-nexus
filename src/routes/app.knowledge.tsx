import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/app/knowledge")({
  component: () => (
    <div className="p-8">
      <h1 className="text-xl font-semibold">Knowledge</h1>
      <p className="mt-2 text-sm text-[color:var(--foreground-muted)]">
        Knowledge base coming soon.
      </p>
    </div>
  ),
});
