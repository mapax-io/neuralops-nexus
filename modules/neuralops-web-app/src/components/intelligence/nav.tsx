"use client";

import { Brain, Cpu, Plug2, UserRound } from "lucide-react";
import { useMcpServers, useModelConfigs } from "@/hooks/use-intelligence";

export const INTEL_SECTIONS = [
  { key: "personas", label: "Personas", hint: "AI teammates", icon: UserRound },
  { key: "models", label: "AI models", hint: "Keys & endpoints", icon: Cpu },
  { key: "mcp", label: "MCP servers", hint: "Tools for personas", icon: Plug2 },
] as const;

export type IntelSection = (typeof INTEL_SECTIONS)[number]["key"];

// Settings-style vertical navigation (horizontal scroll strip below lg).
export function IntelNav({ section, onSection }: { section: IntelSection; onSection: (s: IntelSection) => void }) {
  const { data: models } = useModelConfigs();
  const { data: mcp } = useMcpServers();
  const counts: Partial<Record<IntelSection, number>> = {
    models: models?.length,
    mcp: mcp?.length,
  };

  return (
    <aside className="flex flex-none flex-col border-b border-line bg-bg2/60 lg:w-60 lg:border-b-0 lg:border-r">
      <div className="hidden items-center gap-2.5 border-b border-line px-4 py-3.5 lg:flex">
        <span className="flex size-8 items-center justify-center rounded-[10px] bg-accent text-accent-ink">
          <Brain size={16} strokeWidth={2} />
        </span>
        <div className="min-w-0">
          <p className="font-display text-[14px] font-bold leading-tight">Intelligence</p>
          <p className="truncate text-[11.5px] text-ink2">What powers your AI teammates</p>
        </div>
      </div>
      <nav aria-label="Intelligence sections" className="flex gap-1 overflow-x-auto p-2 lg:flex-col lg:overflow-visible lg:p-2.5">
        {INTEL_SECTIONS.map((s) => {
          const active = section === s.key;
          return (
            <button
              key={s.key}
              aria-current={active ? "page" : undefined}
              onClick={() => onSection(s.key)}
              className={`relative flex flex-none items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors lg:w-full ${
                active ? "bg-accent/10 text-ink" : "text-ink2 hover:bg-surface hover:text-ink"
              }`}
            >
              {active && <span aria-hidden className="absolute inset-y-1.5 left-0 hidden w-0.5 rounded-full bg-accent lg:block" />}
              <s.icon size={16} strokeWidth={2} className={`flex-none ${active ? "text-accent" : ""}`} />
              <span className="min-w-0 lg:flex-1">
                <span className={`block text-[13.5px] leading-tight ${active ? "font-semibold" : "font-medium"}`}>{s.label}</span>
                <span className="hidden text-[11.5px] text-ink2 lg:block">{s.hint}</span>
              </span>
              {!!counts[s.key] && (
                <span className={`hidden flex-none rounded-full px-1.5 py-px font-mono text-[10.5px] font-semibold lg:block ${active ? "bg-accent/15 text-accent" : "bg-surface2 text-ink2"}`}>
                  {counts[s.key]}
                </span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="hidden flex-1 lg:block" />
      <p className="hidden border-t border-line px-4 py-3 text-[11.5px] leading-relaxed text-ink2 lg:block">
        Register a model, wire tools through MCP — then give the mix a name and a role as a persona. A persona
        with tools acts; one without just answers.
      </p>
    </aside>
  );
}
