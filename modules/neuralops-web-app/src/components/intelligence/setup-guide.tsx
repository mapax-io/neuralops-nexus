"use client";

import { ArrowRight, Circle, CircleCheck } from "lucide-react";
import { useMcpServers, useModelConfigs, usePersonas } from "@/hooks/use-intelligence";
import { useProjects } from "@/hooks/use-workspace";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { companyScope, projectScope } from "@/lib/permissions";
import { usePermissions } from "@/hooks/use-permissions";
import { useUiStore } from "@/stores/ui.store";
import type { IntelSection } from "./nav";

// The nav's footer: where this workspace stands on the three things a persona
// needs, with the next action one click away — instead of a paragraph
// explaining the model. Reads the same project the personas tab shows.
export function SetupGuide({ onSection }: { onSection: (s: IntelSection) => void }) {
  const { can } = usePermissions();
  const { data: projects } = useProjects();
  const intelProject = useUiStore((u) => u.intelProject);
  const setIntelCreate = useUiStore((u) => u.setIntelCreate);
  const activeProject = intelProject ?? projects?.[0]?.id;
  const projectName = projects?.find((p) => p.id === activeProject)?.name;
  const { data: models } = useModelConfigs();
  const { data: mcp } = useMcpServers();
  const { data: personas } = usePersonas(activeProject);
  const loading = !projects || !models || !mcp || (!!activeProject && !personas);
  const showLoading = useDelayedLoading(loading);

  if (loading) {
    return showLoading ? (
      <div aria-busy className="hidden border-t border-line px-4 py-3 lg:block">
        {[0, 1, 2].map((i) => <div key={i} className="mb-2 h-3 w-4/5 animate-pulse rounded bg-surface2 last:mb-0" />)}
      </div>
    ) : null;
  }

  if (projects.length === 0) {
    return (
      <p className="hidden border-t border-line px-4 py-3 text-[11.5px] leading-relaxed text-ink2 lg:block">
        Create a project first — personas and their tools live inside one.
      </p>
    );
  }

  const hasModel = models.length > 0;
  const projectTools = mcp.filter((s) => s.project_id === activeProject).length;
  const personaCount = personas?.length ?? 0;
  const steps: { key: IntelSection; label: string; done: boolean; action: string; allowed: boolean; blocked?: string }[] = [
    { key: "models", label: "A model with a key", done: hasModel, action: "Register a model",
      allowed: can("model_config.create", companyScope()) },
    { key: "mcp", label: "Tools for the project", done: projectTools > 0, action: "Add tools",
      allowed: can("mcp_server.create", projectScope(activeProject)) },
    { key: "personas", label: "A persona with a role", done: personaCount > 0, action: "New persona",
      allowed: can("persona.create", projectScope(activeProject)),
      blocked: hasModel ? undefined : "needs a model first" },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  // Switch to the section and open its create dialog in one click.
  const go = (section: IntelSection) => {
    onSection(section);
    setIntelCreate(true);
  };

  return (
    <div className="hidden border-t border-line px-4 py-3 lg:block">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[11.5px] font-semibold uppercase tracking-wide text-ink2">Setup{projectName ? ` — ${projectName}` : ""}</p>
        <p className="font-mono text-[10.5px] text-ink2">{doneCount}/{steps.length}</p>
      </div>
      <ol aria-label="Setup steps" className="flex flex-col gap-1.5">
        {steps.map((s) => (
          <li key={s.key} className="flex items-center gap-2 text-[12px]">
            {s.done
              ? <CircleCheck size={14} strokeWidth={2.2} className="flex-none text-ok" aria-label="done" />
              : <Circle size={14} strokeWidth={2} className="flex-none text-ink2/50" aria-label="to do" />}
            <span className={`min-w-0 flex-1 truncate ${s.done ? "text-ink2" : "text-ink"}`}>{s.label}</span>
            {!s.done && s.allowed && (s.blocked
              ? <span className="flex-none text-[11px] text-ink2">{s.blocked}</span>
              : (
                <button type="button" onClick={() => go(s.key)} className="inline-flex flex-none items-center gap-0.5 text-[11.5px] font-semibold text-accent hover:underline">
                  {s.action} <ArrowRight size={11} strokeWidth={2.4} />
                </button>
              ))}
          </li>
        ))}
      </ol>
      {doneCount === steps.length && personas && personas.length > 0 && (
        <p className="mt-2.5 text-[11.5px] leading-relaxed text-ink2">
          Ready — mention <b className="text-ink">@{personas[0].name}</b> in any of {projectName}&apos;s chats to bring them in.
        </p>
      )}
    </div>
  );
}
