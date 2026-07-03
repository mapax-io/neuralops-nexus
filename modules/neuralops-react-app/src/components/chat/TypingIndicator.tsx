import type { TypingActor } from "./types";

export function TypingIndicator({ actors }: { actors: TypingActor[] }) {
  if (actors.length === 0) return null;

  const names = actors.map((a) => a.name);
  const anyThinking = actors.some(
    (a) => a.type === "persona" || a.type === "agent",
  );
  const verb = anyThinking ? "thinking" : "typing";

  const label =
    names.length === 1
      ? `${names[0]} is ${verb}...`
      : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]} are ${verb}...`;

  return (
    <div className="flex items-center gap-2 px-4 py-2 text-xs text-foreground-muted">
      <div className="flex -space-x-1">
        {actors.slice(0, 3).map((a) => (
          <div
            key={a.id}
            className="flex h-6 w-6 items-center justify-center rounded-full border border-background bg-accent text-[10px] font-semibold text-accent-foreground"
          >
            {a.avatar ? (
              <img
                src={a.avatar}
                alt={a.name}
                className="h-full w-full rounded-full object-cover"
              />
            ) : (
              a.name.slice(0, 1).toUpperCase()
            )}
          </div>
        ))}
      </div>
      <span>{label}</span>
      <span className="flex gap-0.5">
        <span className="h-1 w-1 animate-bounce rounded-full bg-foreground-muted [animation-delay:-0.3s]" />
        <span className="h-1 w-1 animate-bounce rounded-full bg-foreground-muted [animation-delay:-0.15s]" />
        <span className="h-1 w-1 animate-bounce rounded-full bg-foreground-muted" />
      </span>
    </div>
  );
}
