import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/app/knowledge")({
  component: () => (
    <div className="p-8">
      <h1 className="text-lg font-semibold text-foreground">Knowledge</h1>
      <p className="mt-1 text-sm text-foreground-muted">
        Knowledge base management. Coming next.
      </p>
    </div>
  ),
});
