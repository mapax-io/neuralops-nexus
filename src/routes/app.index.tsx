import { createFileRoute } from "@tanstack/react-router";
import { MessageSquare } from "lucide-react";

export const Route = createFileRoute("/app/")({
  component: WorkspaceHome,
});

function WorkspaceHome() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-tint text-primary">
        <MessageSquare className="h-6 w-6" />
      </div>
      <h1 className="text-lg font-semibold text-foreground">
        Pick a topic to get started
      </h1>
      <p className="mt-1 max-w-md text-sm text-foreground-muted">
        Select a project, channel, and topic from the sidebar, or create a new
        one to begin a conversation.
      </p>
    </div>
  );
}
