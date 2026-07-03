import { Hash } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useTopics } from "@/hooks/useWorkspace";
import { useUIStore } from "@/store/ui.store";
import { useProjects } from "@/hooks/useWorkspace";

export function TopicList({
  projectId,
  channelId,
}: {
  projectId: string;
  channelId: string;
}) {
  const { data: topics, isLoading } = useTopics(projectId, channelId);
  const { data: projects } = useProjects();
  const activeTopicId = useUIStore((s) => s.activeTopicId);
  const setActiveTopicId = useUIStore((s) => s.setActiveTopicId);

  const project = projects?.find((p) => p.id === projectId);
  const channel = project?.channels.find((c) => c.id === channelId);

  return (
    <div className="flex h-full w-[220px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex items-center gap-2 border-b border-sidebar-border px-3 py-3">
        <Hash className="h-4 w-4 text-foreground-muted" />
        <span className="truncate text-sm font-semibold text-foreground">
          {channel?.name ?? "channel"}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-3/4" />
            <Skeleton className="h-7 w-2/3" />
          </div>
        )}
        {!isLoading && (!topics || topics.length === 0) && (
          <p className="px-2 py-3 text-xs text-foreground-muted">
            No conversations yet. Send a message to start one.
          </p>
        )}
        {!isLoading &&
          topics?.map((t) => {
            const active = t.id === activeTopicId;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTopicId(t.id)}
                className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm ${
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-foreground-muted hover:bg-sidebar-accent hover:text-foreground"
                }`}
              >
                {t.title}
              </button>
            );
          })}
      </div>
    </div>
  );
}
