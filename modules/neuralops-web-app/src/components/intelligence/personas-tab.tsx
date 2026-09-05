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
import { validateNumber } from "@/lib/validation";
import { fillPersonaName, hasPersonaNameToken } from "@/lib/persona-template";
import {
  useCreatePersona,
  useDeletePersona,
  useMcpServers,
  useModelConfigs,
  useOutputTypes,
  usePatchPersona,
  usePersonas,
  usePromptTemplates,
  useSetModelConfigProject,
} from "@/hooks/use-intelligence";
import { useProjects } from "@/hooks/use-workspace";
import {
  fetchPromptTemplate,
  MAX_MCP_SERVERS_PER_PERSONA,
  type ModelConfig,
  type ModelConfigRef,
  type Persona,
  type PersonaPatch,
} from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, ModelPicker, ProjectSelect, TabShell, Toolbar } from "./shared";
import { CreateMcpDialog } from "./mcp-tab";
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
            `${personas.filter((p) => p.mcp_servers.length > 0).length} with tools`,
            `${personas.filter((p) => p.advisor_model).length} with an advisor`,
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
          {personas.map((p) => {
            const tools = p.mcp_servers.length;
            // A mounted OAuth server whose sign-in lapsed silently breaks the
            // persona's tools — say so on the card, next to the tool count.
            const needsReconnect = p.mcp_servers.some((s) => s.auth_type === "oauth2" && !s.oauth_connected);
            return (
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
                chips={
                  <>
                    <Chip>{p.model.name}</Chip>
                    {p.advisor_model && <Chip>advisor · {p.advisor_model.name}</Chip>}
                    {tools > 0 && <Chip tone="accent">{`${tools} ${tools === 1 ? "tool" : "tools"}`}</Chip>}
                    {needsReconnect && <Chip tone="warn">reconnect needed</Chip>}
                  </>
                }
                body={p.description ?? (p.prompt ? fillPersonaName(p.prompt.system_prompt, p.name) : undefined)}
                meta={
                  <>
                    <span>answers as {p.prompt?.output_type ?? "text"}</span>
                    <span>{p.max_steps} steps</span>
                    <span>temp {p.temperature}</span>
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
            );
          })}
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
          onCreated={(p) => setProjectId(p.project_id)}
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

// ── The backing: one model, an optional advisor, 0..N tool servers ────────────
// The server's wiring rules are applied as the user picks, so the dialog shows
// exactly what will be saved: the advisor is never the primary (hidden from the
// advisor list, cleared if the primary takes its id), and a model that can't
// call tools unticks and disables the servers rather than failing on submit.
function useBacking(
  models: ModelConfig[] | undefined,
  initial: { modelId: string; advisorId: string; serverIds: string[] },
  // The persona's own refs, so capability is known even before the list loads.
  knownRefs: (ModelConfigRef | null | undefined)[] = [],
) {
  const [modelId, setModelId] = useState(initial.modelId);
  const [advisorId, setAdvisorId] = useState(initial.advisorId);
  const [serverIds, setServerIds] = useState<string[]>(initial.serverIds);
  const [clearedTools, setClearedTools] = useState(false);
  const resolve = (id: string) => models?.find((m) => m.id === id) ?? knownRefs.find((r) => r?.id === id) ?? undefined;
  const model = modelId ? resolve(modelId) : undefined;
  const lacksTools = !!model && !model.supports_tools;

  // `known` carries a model handed back by the inline register dialog — it is
  // picked before the list refetches, so its capability must not be guessed.
  const pickModel = (id: string, known?: ModelConfig) => {
    setModelId(id);
    if (id && id === advisorId) setAdvisorId("");
    const next = known ?? (id ? resolve(id) : undefined);
    if (next && !next.supports_tools && serverIds.length > 0) {
      setServerIds([]);
      setClearedTools(true);
    }
  };
  const toggleServer = (id: string) => {
    setClearedTools(false);
    setServerIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  };
  const clearAll = () => {
    setModelId("");
    setAdvisorId("");
    setServerIds([]);
    setClearedTools(false);
  };
  return { modelId, advisorId, serverIds, model, lacksTools, clearedTools, pickModel, setAdvisorId, toggleServer, clearAll };
}

function ToolServerPicker({ servers, selected, onToggle, disabledReason, clearedNote, onAdd }: {
  servers: { id: string; name: string }[];
  selected: string[];
  onToggle: (id: string) => void;
  disabledReason: string | null; // set when the chosen model can't call tools
  clearedNote: boolean;          // ticks were just cleared by a model switch
  onAdd: () => void;
}) {
  const full = selected.length >= MAX_MCP_SERVERS_PER_PERSONA;
  return (
    <fieldset>
      <legend className="mb-1.5 block text-[13px] font-medium text-ink2">Tool servers <span className="text-ink2">(optional)</span></legend>
      {servers.length === 0 ? (
        <p className="rounded-[10px] border border-dashed border-line px-3 py-2.5 text-[12.5px] text-ink2">
          No tool servers in this project yet — without one the persona answers, but can&apos;t act.
        </p>
      ) : (
        <ul className="grid gap-1.5 sm:grid-cols-2">
          {servers.map((s) => {
            const on = selected.includes(s.id);
            const off = !!disabledReason || (!on && full);
            return (
              <li key={s.id}>
                <label className={`flex items-center gap-2.5 rounded-[10px] border px-3 py-2 text-[13px] transition-colors ${on ? "border-accent bg-accent/10" : "border-line bg-surface"} ${off ? "opacity-60" : "cursor-pointer hover:border-accent/50"}`}>
                  <input type="checkbox" checked={on} disabled={off} onChange={() => onToggle(s.id)} className="accent-[var(--accent)]" />
                  <span className="truncate">{s.name}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {disabledReason ? (
          <p className="text-[12px] text-warn">{disabledReason}{clearedNote ? " Your ticks were cleared." : ""}</p>
        ) : (
          <p className="text-[12px] text-ink2">Up to {MAX_MCP_SERVERS_PER_PERSONA} tool servers per persona — this project&apos;s only, since a server belongs to one project.</p>
        )}
        <button type="button" onClick={onAdd} className="inline-flex cursor-pointer items-center gap-1 text-[12px] font-semibold text-accent hover:underline">
          <Plus size={12} strokeWidth={2.4} /> Add a tool server
        </button>
      </div>
    </fieldset>
  );
}

const toolsReason = (model: { name: string; supports_tools: boolean } | undefined) =>
  model && !model.supports_tools ? `${model.name} isn't marked tool-capable — pick another model to attach tool servers.` : null;

// Per-persona generation settings (moved off the model row server-side —
// two personas sharing a key routinely want different ones).
function GenerationSettings({ idPrefix, temp, tokens, steps, onTemp, onTokens, onSteps }: {
  idPrefix: string;
  temp: string;
  tokens: string;
  steps: string;
  onTemp: (v: string) => void;
  onTokens: (v: string) => void;
  onSteps: (v: string) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[13px] font-medium text-ink2">Generation settings</p>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label htmlFor={`${idPrefix}-temp`}>Temperature</Label>
          <Input id={`${idPrefix}-temp`} type="number" min={0} max={2} step={0.1} inputMode="decimal" value={temp} onChange={(e) => onTemp(e.target.value)} />
        </div>
        <div>
          <Label htmlFor={`${idPrefix}-max-tokens`}>Max tokens</Label>
          <Input id={`${idPrefix}-max-tokens`} type="number" min={1} step={1} inputMode="numeric" value={tokens} onChange={(e) => onTokens(e.target.value)} />
        </div>
        <div>
          <Label htmlFor={`${idPrefix}-max-steps`}>Max steps</Label>
          <Input id={`${idPrefix}-max-steps`} type="number" min={1} max={50} step={1} inputMode="numeric" value={steps} onChange={(e) => onSteps(e.target.value)} />
        </div>
      </div>
      <p className="mt-1.5 text-[12px] text-ink2">Lower temperature means steadier answers. Steps cap the tool-call rounds per reply.</p>
    </div>
  );
}

// Server-side these are unbounded; the ranges here catch typos, not taste.
const validateGeneration = (temp: string, tokens: string, steps: string) =>
  validateNumber(temp, { label: "a temperature", min: 0, max: 2 }) ??
  validateNumber(tokens, { label: "max tokens", min: 1, max: 1_000_000, integer: true }) ??
  validateNumber(steps, { label: "max steps", min: 1, max: 50, integer: true });

const sameIds = (a: string[], b: string[]) => {
  if (a.length !== b.length) return false;
  const sb = [...b].sort();
  return [...a].sort().every((x, i) => x === sb[i]);
};

function CreatePersonaDialog({ open, onClose, defaultProjectId, onCreated }: {
  open: boolean;
  onClose: () => void;
  defaultProjectId: string;
  onCreated?: (p: Persona) => void;
}) {
  const { data: projects } = useProjects();
  const { data: models } = useModelConfigs();
  const { data: servers } = useMcpServers();
  const { data: outputTypes } = useOutputTypes();
  const setProject = useSetModelConfigProject();
  // The dialog owns its target project — pre-set from the tab, switchable
  // here, and named in the title so there is never any doubt.
  const [projectId, setProjectId] = useState(defaultProjectId);
  // Inline prerequisite creation — stacked dialogs, mounted fresh per open so
  // they scope to the currently selected project.
  const [addingModel, setAddingModel] = useState(false);
  const [addingMcp, setAddingMcp] = useState(false);
  // Persona names are unique server-wide (the shadow user's handle), but the
  // API only lists per project — check what we can see live; the server
  // rejects cross-project collisions on submit (surfaced via toast).
  const { data: projectPersonas } = usePersonas(projectId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const backing = useBacking(models, { modelId: "", advisorId: "", serverIds: [] });
  const [systemPrompt, setSystemPrompt] = useState("");
  const [outputType, setOutputType] = useState("text");
  const [temp, setTemp] = useState("0.7");
  const [tokens, setTokens] = useState("4096");
  const [steps, setSteps] = useState("10");
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
    backing.clearAll();
    setSystemPrompt("");
    setOutputType("text");
    setTemp("0.7");
    setTokens("4096");
    setSteps("10");
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
  // MCP servers are project-owned — only this project's can be mounted.
  const projectServers = servers?.filter((s) => s.project_id === projectId) ?? [];
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
    if (!backing.modelId) return setErr("Pick the model that powers them.");
    // Mirrors the server's wiring rules — unreachable through the controls,
    // kept so a stale list can never produce a confusing round-trip 400.
    if (backing.lacksTools && backing.serverIds.length > 0) return setErr(toolsReason(backing.model));
    if (backing.serverIds.length > MAX_MCP_SERVERS_PER_PERSONA) return setErr(`A persona can mount at most ${MAX_MCP_SERVERS_PER_PERSONA} tool servers.`);
    if (!systemPrompt.trim()) return setErr("Write the role — it's the persona's job description.");
    const ge = validateGeneration(temp, tokens, steps);
    if (ge) return setErr(ge);
    // Attach & use: a model picked from another project is attached here
    // first (the server requires it), then the persona is created — one
    // submit, no tab-hopping. Both slots.
    for (const id of [backing.modelId, backing.advisorId].filter(Boolean)) {
      const picked = models?.find((m) => m.id === id);
      if (picked?.project_ids && !picked.project_ids.includes(projectId)) {
        try {
          await setProject.mutateAsync({ projectId, modelId: id, attach: true });
        } catch {
          return; // the hook already toasted; stay in the dialog to retry
        }
      }
    }
    create.mutate({
      name: n,
      description: description.trim() || undefined,
      project_id: projectId,
      model_config_id: backing.modelId,
      advisor_model_config_id: backing.advisorId || undefined,
      mcp_server_ids: backing.serverIds,
      temperature: Number(temp),
      max_tokens: Number(tokens),
      max_steps: Number(steps),
      prompt: { system_prompt: fillPersonaName(systemPrompt, n).trim(), output_type: outputType },
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
          {/* The name is the @mention handle — nothing to create without it. */}
          <Button type="submit" form="pe-form" size="sm" variant="primary" disabled={!name.trim()} loading={create.isPending || setProject.isPending}>Create persona</Button>
        </div>
      }
    >
      <form id="pe-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <ProjectSelect
          id="pe-project"
          value={projectId}
          onChange={(v) => {
            setProjectId(v);
            // The backing is project-scoped — selections don't carry over.
            backing.clearAll();
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
        <ModelPicker
          id="pe-model"
          projectId={projectId}
          models={models}
          value={backing.modelId}
          onChange={backing.pickModel}
          onRegisterNew={() => setAddingModel(true)}
          hint={<p className="text-[12px] text-ink2">Every answer comes from this model.</p>}
        />
        <ModelPicker
          id="pe-advisor"
          label="Advisor model"
          optional
          noneLabel="No advisor"
          exclude={backing.modelId ? [backing.modelId] : []}
          projectId={projectId}
          models={models}
          value={backing.advisorId}
          onChange={backing.setAdvisorId}
          hint={<p className="text-[12px] text-ink2">A second model the primary can consult when it gets stuck — must differ from the model.</p>}
        />
        <ToolServerPicker
          servers={projectServers}
          selected={backing.serverIds}
          onToggle={backing.toggleServer}
          disabledReason={toolsReason(backing.model)}
          clearedNote={backing.clearedTools}
          onAdd={() => setAddingMcp(true)}
        />
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
          {/* The field shows {PERSONA_NAME} filled with the name typed above,
              live; the raw text (token included) stays in state until the
              user edits the role by hand, so a later rename still follows. */}
          <textarea
            id="pe-role"
            rows={4}
            value={fillPersonaName(systemPrompt, name)}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="You are the project's data analyst. Answer with concrete numbers, cite the source table, and prefer charts for trends."
            className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[14px] leading-relaxed outline-none focus:border-accent"
          />
          {hasPersonaNameToken(systemPrompt) && !name.trim() && (
            <p className="mt-1.5 text-[12px] text-ink2">{"{PERSONA_NAME} fills in with the name above."}</p>
          )}
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
        <GenerationSettings idPrefix="pe" temp={temp} tokens={tokens} steps={steps} onTemp={setTemp} onTokens={setTokens} onSteps={setSteps} />
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
        onCreated={(m) => backing.pickModel(m.id, m)}
      />
    )}
    {addingMcp && (
      <CreateMcpDialog
        open
        onClose={() => setAddingMcp(false)}
        defaultProjectId={projectId}
        onCreated={(s) => {
          // A server created for another project can't be mounted here.
          if (s.project_id === projectId && !backing.serverIds.includes(s.id)) backing.toggleServer(s.id);
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

// The backing is mutable: model, advisor and tool servers can all be changed
// here. Only what changed is sent — the server applies non-null fields, with
// clear_advisor as the one way to remove the advisor and [] to detach all.
function EditPersonaDialog({ persona, onClose, siblings }: { persona: Persona; onClose: () => void; siblings: Persona[] }) {
  const { data: projects } = useProjects();
  const { data: models } = useModelConfigs();
  const { data: servers } = useMcpServers();
  const { data: outputTypes } = useOutputTypes();
  const setProject = useSetModelConfigProject();
  const [addingModel, setAddingModel] = useState(false);
  const [addingMcp, setAddingMcp] = useState(false);
  const [name, setName] = useState(persona.name);
  const [description, setDescription] = useState(persona.description ?? "");
  const mountedIds = persona.mcp_servers.map((s) => s.id);
  const backing = useBacking(
    models,
    { modelId: persona.model.id, advisorId: persona.advisor_model?.id ?? "", serverIds: mountedIds },
    [persona.model, persona.advisor_model],
  );
  const [systemPrompt, setSystemPrompt] = useState(persona.prompt?.system_prompt ?? "");
  const [outputType, setOutputType] = useState(persona.prompt?.output_type ?? "text");
  const [temp, setTemp] = useState(String(persona.temperature));
  const [tokens, setTokens] = useState(String(persona.max_tokens));
  const [steps, setSteps] = useState(String(persona.max_steps));
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const patch = usePatchPersona(onClose);
  // This project's servers, plus any mounted one the list doesn't carry (so
  // it can still be unticked) — never another project's.
  const projectServers = [
    ...(servers?.filter((s) => s.project_id === persona.project_id) ?? []),
    ...persona.mcp_servers.filter((m) => !servers?.some((s) => s.id === m.id)),
  ].map((s) => ({ id: s.id, name: s.name }));

  const validateName = (v: string) => {
    const n = v.trim();
    if (!n) return "Give the persona a name.";
    if (!isMentionableName(n)) return "Names must be @mentionable — letters, numbers and underscores only, and not a reserved word.";
    if (siblings.some((p) => p.name.toLowerCase() === n.toLowerCase())) return "A persona with this name already exists in this project.";
    return null;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (patch.isPending || setProject.isPending) return;
    setErr(null);
    setTouched(true);
    const n = name.trim();
    const ne = validateName(n);
    setNameErr(ne);
    if (ne) return;
    if (!backing.modelId) return setErr("Pick the model that powers them.");
    if (backing.lacksTools && backing.serverIds.length > 0) return setErr(toolsReason(backing.model));
    if (backing.serverIds.length > MAX_MCP_SERVERS_PER_PERSONA) return setErr(`A persona can mount at most ${MAX_MCP_SERVERS_PER_PERSONA} tool servers.`);
    if (!systemPrompt.trim()) return setErr("The role can't be empty — it's the persona's job description.");
    const ge = validateGeneration(temp, tokens, steps);
    if (ge) return setErr(ge);
    const advisorBefore = persona.advisor_model?.id ?? "";
    const promptChanged =
      systemPrompt.trim() !== (persona.prompt?.system_prompt ?? "") || outputType !== (persona.prompt?.output_type ?? "text");
    // Only send what changed; an unchanged name skips the server's rename path.
    const payload: PersonaPatch = {
      ...(n !== persona.name ? { name: n } : {}),
      ...(description.trim() !== (persona.description ?? "") ? { description: description.trim() } : {}),
      ...(backing.modelId !== persona.model.id ? { model_config_id: backing.modelId } : {}),
      ...(backing.advisorId !== advisorBefore
        ? backing.advisorId ? { advisor_model_config_id: backing.advisorId } : { clear_advisor: true }
        : {}),
      ...(!sameIds(backing.serverIds, mountedIds) ? { mcp_server_ids: backing.serverIds } : {}),
      ...(Number(temp) !== persona.temperature ? { temperature: Number(temp) } : {}),
      ...(Number(tokens) !== persona.max_tokens ? { max_tokens: Number(tokens) } : {}),
      ...(Number(steps) !== persona.max_steps ? { max_steps: Number(steps) } : {}),
      ...(promptChanged ? { prompt: { system_prompt: fillPersonaName(systemPrompt, n).trim(), output_type: outputType } } : {}),
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    // Attach & use for a swapped-in model from another project — same rule as
    // create: the server requires the model to be attached first.
    for (const id of [payload.model_config_id, payload.advisor_model_config_id].filter((x): x is string => !!x)) {
      const picked = models?.find((m) => m.id === id);
      if (picked?.project_ids && !picked.project_ids.includes(persona.project_id)) {
        try {
          await setProject.mutateAsync({ projectId: persona.project_id, modelId: id, attach: true });
        } catch {
          return;
        }
      }
    }
    patch.mutate({ id: persona.id, payload });
  };

  return (
    <>
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Edit @${persona.name}`}
      description="Changes apply to every future answer — a swapped model or tool set takes effect on the next @mention. Past messages stay as they were."
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="pd-form" size="sm" variant="primary" disabled={!name.trim()} loading={patch.isPending || setProject.isPending}>Save changes</Button>
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
        <ModelPicker
          id="pd-model"
          projectId={persona.project_id}
          models={models}
          value={backing.modelId}
          onChange={backing.pickModel}
          onRegisterNew={() => setAddingModel(true)}
          hint={<p className="text-[12px] text-ink2">Every answer comes from this model.</p>}
        />
        <ModelPicker
          id="pd-advisor"
          label="Advisor model"
          optional
          noneLabel="No advisor"
          exclude={backing.modelId ? [backing.modelId] : []}
          projectId={persona.project_id}
          models={models}
          value={backing.advisorId}
          onChange={backing.setAdvisorId}
          hint={<p className="text-[12px] text-ink2">A second model the primary can consult when it gets stuck — must differ from the model.</p>}
        />
        <ToolServerPicker
          servers={projectServers}
          selected={backing.serverIds}
          onToggle={backing.toggleServer}
          disabledReason={toolsReason(backing.model)}
          clearedNote={backing.clearedTools}
          onAdd={() => setAddingMcp(true)}
        />
        <div>
          <Label htmlFor="pd-role">Role</Label>
          {/* A role saved with {PERSONA_NAME} still in it shows filled; it is
              only rewritten on the server once the text is edited here. */}
          <textarea
            id="pd-role"
            rows={5}
            value={fillPersonaName(systemPrompt, name)}
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
        <GenerationSettings idPrefix="pd" temp={temp} tokens={tokens} steps={steps} onTemp={setTemp} onTokens={setTokens} onSteps={setSteps} />
        <div>
          <Label htmlFor="pd-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="pd-desc" placeholder="Shown to teammates in pickers" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} />
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
    {addingModel && (
      <CreateModelDialog
        open
        onClose={() => setAddingModel(false)}
        attachProjectId={persona.project_id}
        attachProjectName={projects?.find((p) => p.id === persona.project_id)?.name}
        onCreated={(m) => backing.pickModel(m.id, m)}
      />
    )}
    {addingMcp && (
      <CreateMcpDialog
        open
        onClose={() => setAddingMcp(false)}
        defaultProjectId={persona.project_id}
        onCreated={(s) => {
          if (s.project_id === persona.project_id && !backing.serverIds.includes(s.id)) backing.toggleServer(s.id);
        }}
      />
    )}
    </>
  );
}
