"use client";

import { useEffect, useRef, useState } from "react";
import { useUiStore } from "@/stores/ui.store";
import { FolderKanban, Pencil, Plus, Sparkles, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { absolutizeMedia } from "@/lib/api/client";
import { isMentionableName } from "@/lib/composer/directives";
import {
  useAgents,
  useCreatePersona,
  useDeletePersona,
  useModels,
  useOutputTypes,
  usePatchPersona,
  usePersonas,
  usePromptTemplates,
  useSetModelProject,
} from "@/hooks/use-intelligence";
import { useProjects } from "@/hooks/use-workspace";
import { fetchPromptTemplate, type Persona } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, ModelPicker, ProjectSelect, TabShell, Toolbar } from "./shared";
import { CreateAgentDialog } from "./agents-tab";
import { CreateModelDialog } from "./models-tab";

export function PersonasTab({ canManage, embedded, defaultProjectId }: { canManage: boolean; embedded?: boolean; defaultProjectId?: string }) {
  const { data: projects } = useProjects();
  const [projectId, setProjectId] = useState<string | undefined>(undefined);
  // When opened from a chat's slash command, default to THAT chat's project.
  const activeProject = projectId ?? defaultProjectId ?? projects?.[0]?.id;
  const { data: personas, isLoading, error, refetch } = usePersonas(activeProject);
  const [creating, setCreating] = useState(false);
  // One-shot intent from /add-* slash commands (ui.store.intelCreate).
  const intelCreate = useUiStore((u) => u.intelCreate);
  const setIntelCreate = useUiStore((u) => u.setIntelCreate);
  useEffect(() => {
    if (!intelCreate) return;
    setIntelCreate(false);
    // Deferred: setState directly inside an effect cascades renders (house rule).
    const raf = requestAnimationFrame(() => {
      if (canManage) setCreating(true);
    });
    return () => cancelAnimationFrame(raf);
  }, [intelCreate, setIntelCreate, canManage]);
  const [editing, setEditing] = useState<Persona | null>(null);
  const [removing, setRemoving] = useState<Persona | null>(null);
  const del = useDeletePersona();
  // Projects still loading counts as LOADING, not "no personas" — the empty
  // state must never flash while the project picker is still resolving.
  const showLoading = useDelayedLoading(!projects || (!!activeProject && isLoading));

  return (
    <TabShell
      embedded={embedded}
      title="Personas"
      blurb="AI teammates with a role in plain language — @mention them in their project's chats."
      action={
        <div className="flex items-center gap-2">
          {/* The list is SCOPED by this — styled as a loud filter pill, not a
              quiet form field, so switching projects is impossible to miss. */}
          <div className="flex h-9 items-stretch">
            <label htmlFor="ps-project" className="flex items-center gap-1.5 rounded-l-[10px] border border-r-0 border-accent/40 bg-accent/10 px-2.5 text-[12px] font-semibold text-accent">
              <FolderKanban size={14} strokeWidth={2.2} /> Project
            </label>
            <select
              id="ps-project"
              value={activeProject ?? ""}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-48 rounded-r-[10px] border border-accent/40 bg-surface px-3 text-[13.5px] font-semibold outline-none transition-[border-color,box-shadow] hover:border-accent focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            >
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          {!!personas?.length && canManage && activeProject && (
            <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
              <Plus size={14} strokeWidth={2} /> New persona
            </Button>
          )}
        </div>
      }
    >
      {!!personas?.length && (
        <Toolbar
          facts={[
            `${personas.length} ${personas.length === 1 ? "persona" : "personas"}`,
            `${personas.filter((p) => p.source_type === "agent").length} agent-backed`,
            `${personas.filter((p) => p.source_type === "model").length} model-backed`,
          ]}
        />
      )}
      <ListState
        loading={showLoading}
        error={error}
        onRetry={refetch}
        empty={!showLoading && !!projects && (personas?.length === 0 || !activeProject)}
        emptyTitle="No personas in this project"
        emptyIcon={<UserRound size={24} strokeWidth={1.8} />}
        emptyHint={canManage ? "Create one, give it a role, and @mention it in any of this project's chats." : "An admin can add AI teammates to this project."}
        emptyAction={canManage && activeProject ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} strokeWidth={2} /> New persona</Button> : undefined}
      />
      {!showLoading && !!personas?.length && (
        <CardGrid>
          {personas.map((p) => (
            <EntityCard
              key={p.id}
              icon={
                p.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
                  <img src={absolutizeMedia(p.avatar) ?? undefined} alt="" className="size-full object-cover" />
                ) : (
                  <UserRound size={17} strokeWidth={2} />
                )
              }
              title={`@${p.name}`}
              chips={<Chip tone={p.source_type === "agent" ? "accent" : "neutral"}>{p.source_type === "agent" ? "agent · tools" : "model"}</Chip>}
              body={p.description ?? p.prompt?.system_prompt}
              meta={
                <>
                  <span>answers as {p.prompt?.output_type ?? "text"}</span>
                  <span>@mention to bring in</span>
                </>
              }
              actions={canManage && (
                <>
                  <button
                    aria-label={`Edit persona ${p.name}`}
                    title="Edit persona"
                    onClick={() => setEditing(p)}
                    className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                  >
                    <Pencil size={14} strokeWidth={2} />
                  </button>
                  <button
                    aria-label={`Remove persona ${p.name}`}
                    title="Remove persona"
                    onClick={() => setRemoving(p)}
                    className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                  >
                    <Trash2 size={14} strokeWidth={2} />
                  </button>
                </>
              )}
            />
          ))}
        </CardGrid>
      )}
      {activeProject && (
        <CreatePersonaDialog
          key={activeProject}
          open={creating}
          onClose={() => setCreating(false)}
          defaultProjectId={activeProject}
          // The dialog owns its project — if the persona landed elsewhere,
          // follow it so the new card is visible, not mysteriously absent.
          onCreated={(p) => {
            if (p.project_id) setProjectId(p.project_id);
          }}
        />
      )}
      {editing && (
        <EditPersonaDialog
          key={editing.id}
          persona={editing}
          onClose={() => setEditing(null)}
          siblings={(personas ?? []).filter((p) => p.id !== editing.id)}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) del.mutate(removing.id);
          setRemoving(null);
        }}
        title="Remove this persona?"
        body={
          <p>
            <b className="text-ink">@{removing?.name}</b> leaves the team. Their past messages stay in the
            chats; the name becomes available again for a new persona.
          </p>
        }
        confirmLabel="Remove persona"
        loading={del.isPending}
      />
    </TabShell>
  );
}

function CreatePersonaDialog({ open, onClose, defaultProjectId, onCreated }: {
  open: boolean;
  onClose: () => void;
  defaultProjectId: string;
  onCreated?: (p: Persona) => void;
}) {
  const { data: projects } = useProjects();
  const { data: models } = useModels();
  const { data: agents } = useAgents();
  const { data: outputTypes } = useOutputTypes();
  const setProject = useSetModelProject();
  // The dialog owns its target project — pre-set from the tab, switchable
  // here, and named in the title so there is never any doubt.
  const [projectId, setProjectId] = useState(defaultProjectId);
  // Inline prerequisite creation — stacked dialogs, mounted fresh per open so
  // they scope to the currently selected project.
  const [addingModel, setAddingModel] = useState(false);
  const [addingAgent, setAddingAgent] = useState(false);
  // Persona names are unique server-wide (the shadow user's handle), but the
  // API only lists per project — check what we can see live; the server
  // rejects cross-project collisions on submit (surfaced via toast).
  const { data: projectPersonas } = usePersonas(projectId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceType, setSourceType] = useState<"model" | "agent">("model");
  const [modelId, setModelId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [outputType, setOutputType] = useState("text");
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  // Server-shipped role templates: picking one fills the Role field with its
  // content. These are files, not DB templates — their ids never go in the
  // payload's template_id (that expects a DB PromptTemplate id).
  const { data: templates } = usePromptTemplates();
  const [templateId, setTemplateId] = useState("");
  const [tplLoading, setTplLoading] = useState(false);
  // Monotonic sequence guards the fetch: a slow response must not overwrite
  // the Role field after a cancel/reset or after a NEWER pick already landed.
  const tplSeqRef = useRef(0);
  const pickTemplate = (id: string) => {
    setTemplateId(id);
    if (!id) return; // back to blank keeps whatever was typed
    const seq = ++tplSeqRef.current;
    setTplLoading(true);
    fetchPromptTemplate(id)
      .then((r) => {
        if (tplSeqRef.current === seq) setSystemPrompt(r.content);
      })
      .catch(() => tplSeqRef.current === seq && toast.error("Couldn't load that template — write the role by hand or retry."))
      .finally(() => tplSeqRef.current === seq && setTplLoading(false));
  };

  const validateName = (v: string) => {
    const n = v.trim();
    if (!n) return "Give the persona a name.";
    if (!isMentionableName(n)) return "Names must be @mentionable — letters, numbers and underscores only, and not a reserved word.";
    if (projectPersonas?.some((p) => p.name.toLowerCase() === n.toLowerCase())) return "A persona with this name already exists in this project.";
    return null;
  };

  const reset = () => {
    setProjectId(defaultProjectId);
    setName("");
    setDescription("");
    setSourceType("model");
    setModelId("");
    setAgentId("");
    setSystemPrompt("");
    setOutputType("text");
    setErr(null);
    setNameErr(null);
    setTouched(false);
    setTemplateId("");
    tplSeqRef.current++; // orphan any in-flight template fetch
    setTplLoading(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreatePersona((p) => {
    onCreated?.(p);
    close();
  });
  const projectAgents = agents?.filter((a) => a.project_id === projectId) ?? [];
  const projName = projects?.find((p) => p.id === projectId)?.name;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // The attach await opens a window where create.isPending is still false —
    // the footer button's loading covers it, this guard covers the race.
    if (create.isPending || setProject.isPending) return;
    setErr(null);
    setTouched(true);
    const n = name.trim();
    const ne = validateName(n);
    setNameErr(ne);
    if (ne) return;
    if (sourceType === "model" && !modelId) return setErr("Pick the model that powers them.");
    if (sourceType === "agent" && !agentId) return setErr("Pick the agent that powers them.");
    if (!systemPrompt.trim()) return setErr("Write the role — it's the persona's job description.");
    // Attach & use: a model picked from another project is attached here
    // first, then the persona is created — one submit, no tab-hopping.
    if (sourceType === "model") {
      const picked = models?.find((m) => m.id === modelId);
      if (picked?.project_ids && !picked.project_ids.includes(projectId)) {
        try {
          await setProject.mutateAsync({ projectId, modelId, attach: true });
        } catch {
          return; // the hook already toasted; stay in the dialog to retry
        }
      }
    }
    create.mutate({
      name: n,
      description: description.trim() || undefined,
      project_id: projectId,
      source_type: sourceType,
      model_id: sourceType === "model" ? modelId : undefined,
      agent_id: sourceType === "agent" ? agentId : undefined,
      prompt: { system_prompt: systemPrompt.trim(), output_type: outputType },
    });
  };

  return (
    <>
    <Dialog
      open={open}
      onClose={close}
      size="lg"
      title={`New persona${projName ? ` — ${projName}` : ""}`}
      description="An AI teammate for this project. The role you write here is their standing instructions for every answer."
      icon={<Sparkles size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="pe-form" size="sm" variant="primary" loading={create.isPending || setProject.isPending}>Create persona</Button>
        </div>
      }
    >
      <form id="pe-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <ProjectSelect
          id="pe-project"
          value={projectId}
          onChange={(v) => {
            setProjectId(v);
            // The backing pickers are project-scoped — selections don't carry over.
            setModelId("");
            setAgentId("");
          }}
          only={projects ?? []}
        />
        <div>
          <Label htmlFor="pe-name">Name</Label>
          <Input
            id="pe-name"
            autoFocus
            placeholder="e.g. Layla"
            value={name}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validateName(e.target.value));
            }}
            onBlur={() => {
              if (name) {
                setTouched(true);
                setNameErr(validateName(name));
              }
            }}
            maxLength={30}
          />
          {nameErr ? (
            <FieldError>{nameErr}</FieldError>
          ) : (
            <p className="mt-1.5 text-[12px] text-ink2">Teammates will type @{name.trim() || "name"} to bring them in.</p>
          )}
        </div>
        <div>
          <Label>Powered by</Label>
          <div
            className="flex gap-2"
            role="radiogroup"
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              e.preventDefault();
              const btns = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button[role=radio]"));
              const idx = btns.findIndex((b) => b.getAttribute("aria-checked") === "true");
              const next = btns[(idx + (e.key === "ArrowRight" ? 1 : -1) + btns.length) % btns.length];
              next?.focus();
              next?.click();
            }} aria-label="Powered by">
            {(["model", "agent"] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={sourceType === t}
                onClick={() => setSourceType(t)}
                className={`flex-1 rounded-[10px] border px-3 py-2 text-[13px] font-semibold transition-colors ${sourceType === t ? "border-accent bg-accent/10 text-accent" : "border-line bg-surface text-ink2 hover:border-accent/50"}`}
              >
                {t === "model" ? "Model — answers" : "Agent — acts with tools"}
              </button>
            ))}
          </div>
        </div>
        {sourceType === "model" ? (
          <ModelPicker
            id="pe-model"
            projectId={projectId}
            models={models}
            value={modelId}
            onChange={setModelId}
            onRegisterNew={() => setAddingModel(true)}
          />
        ) : (
          <div>
            <Label htmlFor="pe-agent">Agent</Label>
            <select id="pe-agent" value={agentId} onChange={(e) => setAgentId(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
              <option value="" disabled>Choose an agent…</option>
              {projectAgents.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
              {projectAgents.length === 0 && <p className="text-[12px] text-warn">This project has no agents yet.</p>}
              <button type="button" onClick={() => setAddingAgent(true)} className="inline-flex cursor-pointer items-center gap-1 text-[12px] font-semibold text-accent hover:underline">
                <Plus size={12} strokeWidth={2.4} /> Create an agent
              </button>
            </div>
          </div>
        )}
        {Object.keys(templates?.prompts ?? {}).length > 0 && (
          <div>
            <Label htmlFor="pe-template">Start from a template <span className="text-ink2">(optional)</span></Label>
            <select
              id="pe-template"
              value={templateId}
              onChange={(e) => pickTemplate(e.target.value)}
              className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            >
              <option value="">Blank — write your own role</option>
              {Object.entries(templates?.prompts ?? {}).map(([id, path]) => (
                <option key={id} value={id}>{templateLabel(path)}</option>
              ))}
            </select>
            <p className="mt-1.5 text-[12px] text-ink2">{tplLoading ? "Loading template…" : "Picking one fills the role below — edit it freely after."}</p>
          </div>
        )}
        <div>
          <Label htmlFor="pe-role">Role</Label>
          <textarea
            id="pe-role"
            rows={4}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="You are the project's data analyst. Answer with concrete numbers, cite the source table, and prefer charts for trends."
            className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[14px] leading-relaxed outline-none focus:border-accent"
          />
        </div>
        <div>
          <Label htmlFor="pe-output">Default answer format</Label>
          <select id="pe-output" value={outputType} onChange={(e) => setOutputType(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
            {(outputTypes ?? [{ name: "text", label: "Text" }]).map((t) => (
              <option key={t.name} value={t.name}>{t.label}</option>
            ))}
          </select>
          <p className="mt-1.5 text-[12px] text-ink2">Anyone can still override per message with @chart, @table, and friends.</p>
        </div>
        <div>
          <Label htmlFor="pe-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="pe-desc" placeholder="Shown to teammates in pickers" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} />
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
    {/* Stacked prerequisite dialogs — the flow never leaves this screen. */}
    {addingModel && (
      <CreateModelDialog
        open
        onClose={() => setAddingModel(false)}
        attachProjectId={projectId}
        attachProjectName={projName}
        onCreated={(m) => setModelId(m.id)}
      />
    )}
    {addingAgent && (
      <CreateAgentDialog
        open
        onClose={() => setAddingAgent(false)}
        defaultProjectId={projectId}
        onCreated={(a) => {
          if (a.project_id === projectId) setAgentId(a.id);
        }}
      />
    )}
    </>
  );
}

// "personas/data-analyst.md" → "personas / data analyst"
function templateLabel(path: string): string {
  return path.replace(/\.[a-z]+$/i, "").replace(/[-_]/g, " ").split("/").join(" / ");
}

function EditPersonaDialog({ persona, onClose, siblings }: { persona: Persona; onClose: () => void; siblings: Persona[] }) {
  const { data: outputTypes } = useOutputTypes();
  const [name, setName] = useState(persona.name);
  const [description, setDescription] = useState(persona.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(persona.prompt?.system_prompt ?? "");
  const [outputType, setOutputType] = useState(persona.prompt?.output_type ?? "text");
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const patch = usePatchPersona(onClose);

  const validateName = (v: string) => {
    const n = v.trim();
    if (!n) return "Give the persona a name.";
    if (!isMentionableName(n)) return "Names must be @mentionable — letters, numbers and underscores only, and not a reserved word.";
    if (siblings.some((p) => p.name.toLowerCase() === n.toLowerCase())) return "A persona with this name already exists in this project.";
    return null;
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setTouched(true);
    const n = name.trim();
    const ne = validateName(n);
    setNameErr(ne);
    if (ne) return;
    if (!systemPrompt.trim()) return setErr("The role can't be empty — it's the persona's job description.");
    // Only send what changed; an unchanged name skips the server's rename path.
    const promptChanged =
      systemPrompt.trim() !== (persona.prompt?.system_prompt ?? "") || outputType !== (persona.prompt?.output_type ?? "text");
    const payload = {
      ...(n !== persona.name ? { name: n } : {}),
      ...(description.trim() !== (persona.description ?? "") ? { description: description.trim() } : {}),
      ...(promptChanged ? { prompt: { system_prompt: systemPrompt.trim(), output_type: outputType } } : {}),
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    patch.mutate({ id: persona.id, payload });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Edit @${persona.name}`}
      description="Changes apply to every future answer. Past messages stay as they were."
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="pd-form" size="sm" variant="primary" loading={patch.isPending}>Save changes</Button>
        </div>
      }
    >
      <form id="pd-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="pd-name">Name</Label>
          <Input
            id="pd-name"
            autoFocus
            value={name}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validateName(e.target.value));
            }}
            onBlur={() => {
              if (name) {
                setTouched(true);
                setNameErr(validateName(name));
              }
            }}
            maxLength={30}
          />
          {nameErr ? (
            <FieldError>{nameErr}</FieldError>
          ) : (
            <p className="mt-1.5 text-[12px] text-ink2">Renaming updates the @mention everywhere from now on.</p>
          )}
        </div>
        <div>
          <Label htmlFor="pd-role">Role</Label>
          <textarea
            id="pd-role"
            rows={5}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[14px] leading-relaxed outline-none focus:border-accent"
          />
        </div>
        <div>
          <Label htmlFor="pd-output">Default answer format</Label>
          <select
            id="pd-output"
            value={outputType}
            onChange={(e) => setOutputType(e.target.value)}
            className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          >
            {(outputTypes ?? [{ name: "text", label: "Text" }]).map((t) => (
              <option key={t.name} value={t.name}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="pd-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="pd-desc" placeholder="Shown to teammates in pickers" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} />
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}
