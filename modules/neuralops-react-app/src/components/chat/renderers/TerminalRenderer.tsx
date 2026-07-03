export function TerminalRenderer({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <pre
      className="overflow-x-auto rounded-md border p-4 font-mono text-xs leading-relaxed"
      style={{
        backgroundColor: "var(--code-bg)",
        borderColor: "var(--code-border)",
        color: "var(--code-text)",
      }}
    >
      {lines.map((line, i) => {
        const isCmd = line.trimStart().startsWith("$");
        return (
          <div
            key={i}
            style={{ color: isCmd ? "var(--code-cmd)" : "var(--code-text)" }}
          >
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
