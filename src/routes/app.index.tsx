import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/app/")({
  component: WorkspaceIndex,
});

function WorkspaceIndex() {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <div className="max-w-md space-y-2">
        <h1 className="text-xl font-semibold">Welcome to NeuralOps</h1>
        <p className="text-sm text-[color:var(--foreground-muted)]">
          Select a topic from the sidebar to get started, or create a new project.
        </p>
      </div>
    </div>
  );
}
