"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import { SectionHeader } from "@/components/ui/section-header";
import { useProjects } from "@/hooks/use-workspace";
import type { ModelConfig } from "@/lib/api/intelligence";

// Shared chrome for the three intelligence tabs: consistent header, list
// states, and the project selector used by project-owned resources.

export function TabShell({ title, blurb, action, children, embedded }: {
  title: string;
  blurb: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  // Hosted inside a dialog (slash commands): the dialog already provides the
  // title, so the section header would double up — show only the action row.
  embedded?: boolean;
}) {
  if (embedded) {
    return (
      <div className="@container">
        {action && <div className="mb-3 flex justify-end">{action}</div>}
        {children}
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-[1680px] @container">
      <SectionHeader title={title} blurb={blurb} actions={action} />
      <div className="mt-4">{children}</div>
    </div>
  );
}

// One toolbar row directly above the content: contextual controls first, then
// the count facts as left-aligned badges — no floating chrome bands.
export function Toolbar({ children, facts }: { children?: React.ReactNode; facts?: string[] }) {
  return (
    <div className="mb-3 flex min-h-9 flex-wrap items-center gap-x-3 gap-y-2">
      {children}
      {!!facts?.length && (
        <div className="flex flex-wrap items-center gap-1.5">
          {facts.map((f) => (
            <span key={f} className="inline-flex items-center rounded-full border border-line bg-surface2 px-2 py-0.5 text-[11px] font-medium text-ink2">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function CardGrid({ children }: { children: React.ReactNode }) {
  // Container-query columns: the grid adapts to WHERE it renders — full
  // page or a slash-command dialog — instead of the viewport (which squished
  // cards into 4 tiny columns inside a 3xl dialog on a wide screen).
  return <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3 @6xl:grid-cols-4">{children}</div>;
}

// Entity card: identity + chips up top, one meta line pinned to the footer,
// actions revealed on hover (always visible on touch). The actions are a real
// flex item, not an overlay: they take their own room in the header row, so a
// long title or a wrapped chip never runs underneath them however many there
// are (the models card has three).
export function EntityCard({ icon, title, chips, body, meta, actions }: {
  icon: React.ReactNode;
  title: React.ReactNode;
  chips?: React.ReactNode;
  body?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="group relative flex flex-col rounded-xl border border-line bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[0_16px_44px_-20px_var(--accent-soft)]">
      <div className="flex items-start gap-3">
        <span className="flex size-10 flex-none items-center justify-center overflow-hidden rounded-[10px] border border-line bg-surface2 text-ink2">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-[14px] font-semibold">{title}{chips}</p>
          {body && <p className="mt-1 line-clamp-2 text-[12.5px] leading-relaxed text-ink2">{body}</p>}
        </div>
        {actions && (
          <div className="-mr-1 -mt-1 flex flex-none gap-0.5 opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-within:opacity-100">
            {actions}
          </div>
        )}
      </div>
      {meta && <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-2.5 text-[11.5px] text-ink2">{meta}</div>}
    </div>
  );
}

export function ListState({ loading, error, onRetry, empty, emptyTitle, emptyHint, emptyAction, emptyIcon }: {
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  empty: boolean;
  emptyTitle: string;
  emptyHint: string;
  emptyAction?: React.ReactNode;
  emptyIcon?: React.ReactNode;
}) {
  if (loading) {
    return (
      <div className="flex flex-col gap-2.5" role="status" aria-label="Loading">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14 w-2/3" />
      </div>
    );
  }
  if (error) {
    return (
      <p className="text-[13.5px] text-crit">
        Couldn&apos;t load this list. <Button size="sm" variant="ghost" onClick={onRetry}>Retry</Button>
      </p>
    );
  }
  if (empty) {
    return (
      <div className="flex min-h-[45vh] items-center justify-center">
        <EmptyState icon={emptyIcon} title={emptyTitle} hint={emptyHint} action={emptyAction} />
      </div>
    );
  }
  return null;
}

export function Chip({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "accent" | "ok" | "warn" }) {
  const tones = {
    neutral: "border-line bg-surface2 text-ink2",
    accent: "border-accent/30 bg-accent/10 text-accent",
    ok: "border-ok/30 bg-ok/10 text-ok",
    warn: "border-warn/30 bg-warn/10 text-warn",
  } as const;
  return <span className={`rounded-full border px-2 py-px text-[10.5px] font-semibold ${tones[tone]}`}>{children}</span>;
}

// Model picker for the persona builder's two slots (model, advisor). Never a
// dead end: models not yet attached to the project are offered under an
// "attach & use" group (the caller attaches them on submit), and a new model
// can be registered inline without leaving the flow.
export function ModelPicker({ id, projectId, models, value, onChange, onRegisterNew, registerLabel = "Register a new model", label = "Model", optional, noneLabel = "None", exclude, hint }: {
  id: string;
  projectId: string;
  models: ModelConfig[] | undefined;
  value: string;
  onChange: (modelId: string) => void;
  // Opens the stacked CreateModelDialog; omitted when the user lacks the right.
  onRegisterNew?: () => void;
  registerLabel?: string;
  label?: string;
  // An optional slot (the advisor) starts from a real "none" choice.
  optional?: boolean;
  noneLabel?: string;
  // Ids hidden from this slot — the advisor must never be the primary model.
  exclude?: string[];
  hint?: React.ReactNode;
}) {
  const visible = models?.filter((m) => !exclude?.includes(m.id));
  // A model without project_ids predates the visibility gate — usable anywhere.
  const inProject = visible?.filter((m) => !m.project_ids || m.project_ids.includes(projectId)) ?? [];
  const attachable = visible?.filter((m) => m.project_ids && !m.project_ids.includes(projectId)) ?? [];
  // Models exist but every one is excluded (the advisor slot with a single
  // registered model): say why the list is empty instead of leaving a bare
  // "No advisor" — otherwise it reads as a dead end.
  const noneEligible = !!models?.length && (visible?.length ?? 0) === 0;
  const opt = (m: ModelConfig) => <option key={m.id} value={m.id}>{m.name} ({m.qualified_id})</option>;
  return (
    <div>
      <Label htmlFor={id} required={!optional}>{label}{optional && <span className="text-ink2"> (optional)</span>}</Label>
      <select
        id={id}
        required={!optional}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
      >
        {optional ? <option value="">{noneLabel}</option> : <option value="" disabled>Choose a model…</option>}
        {/* Without a chosen project the in/attachable split is meaningless —
            one flat list; the groups appear once the project is picked. */}
        {!projectId ? (
          (visible ?? []).map(opt)
        ) : (
          <>
            {inProject.length > 0 && <optgroup label="In this project">{inProject.map(opt)}</optgroup>}
            {attachable.length > 0 && (
              <optgroup label="Attach & use — registered, not in this project yet">{attachable.map(opt)}</optgroup>
            )}
          </>
        )}
      </select>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {models?.length === 0 && !optional ? (
          <p className="text-[12px] text-warn">No models registered on this server yet.</p>
        ) : noneEligible ? (
          <p className="text-[12px] text-warn">Your only model is already the primary — register a second one to use it here.</p>
        ) : !projectId ? hint : attachable.some((m) => m.id === value) ? (
          <p className="text-[12px] text-ink2">This model gets attached to the project when you save.</p>
        ) : attachable.length > 0 && !optional ? (
          <p className="text-[12px] text-ink2">Models from other projects are attached automatically when picked.</p>
        ) : hint}
        {onRegisterNew && (
          <button type="button" onClick={onRegisterNew} className="inline-flex cursor-pointer items-center gap-1 text-[12px] font-semibold text-accent hover:underline">
            <Plus size={12} strokeWidth={2.4} /> {registerLabel}
          </button>
        )}
      </div>
    </div>
  );
}

export function ProjectSelect({ id, value, onChange, only }: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  // Restrict the choices (e.g. to projects the user administers) — the
  // server enforces the right either way; this avoids offering a 403.
  only?: { id: string; name: string }[];
}) {
  const { data: all } = useProjects();
  const projects = only ?? all;
  return (
    <div>
      <Label htmlFor={id} required>Project</Label>
      <select
        id={id}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
      >
        <option value="" disabled>Choose a project…</option>
        {projects?.map((p) => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>
      <p className="mt-1.5 text-[12px] text-ink2">Owned by one project — its team decides who can use it.</p>
    </div>
  );
}
