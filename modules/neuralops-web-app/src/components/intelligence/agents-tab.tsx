"use client";

import { useEffect, useState } from "react";
import { useUiStore } from "@/stores/ui.store";
import { Bot, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName } from "@/lib/validation";
import { useAgents, useCreateAgent, useDeleteAgent, useMcpServers, useModels, usePatchAgent, useSetModelProject } from "@/hooks/use-intelligence";
import { useProjects } from "@/hooks/use-workspace";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import type { AIAgent } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, ModelPicker, ProjectSelect, TabShell, Toolbar } from "./shared";
import { CreateModelDialog } from "./models-tab";
import { CreateMcpDialog } from "./mcp-tab";

export function AgentsTab({ embedded, defaultProjectId }: { embedded?: boolean; defaultProjectId?: string } = {}) {
  // agent.* create/update/delete are PROJECT-scope rights: a Company Admin
  // reaches every project, a Project Admin their own (role stories).
  const role = useConnectionStore((s) => s.connection?.role);
  const canManage = isCompanyAdmin(role);
  const canTouch = isCompanyAdmin(role);
  const { data: agents, isLoading, error, refetch } = useAgents();
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
  const [editing, setEditing] = useState<AIAgent | null>(null);
  const [removing, setRemoving] = useState<AIAgent | null>(null);
  const showLoading = useDelayedLoading(isLoading);
  const del = useDeleteAgent();

  return (
    <TabShell
      embedded={embedded}
      title="Agents"
      blurb="A model plus tools in a loop — plans, acts, with safety mode and a step budget."
      action={!!agents?.length && canManage && (
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <Plus size={14} strokeWidth={2} /> New agent
        </Button>
      )}
    >
      {!!agents?.length && (
        <Toolbar
          facts={[
            `${agents.length} ${agents.length === 1 ? "agent" : "agents"}`,
            `${agents.filter((a) => a.mcp_server_id).length} with tools`,
            `${agents.filter((a) => a.safety_mode).length} safety on`,
          ]}
        />
      )}
      <ListState
        loading={showLoading}
        error={error}
        onRetry={refetch}
        empty={agents?.length === 0}
        emptyTitle="No agents yet"
        emptyIcon={<Bot size={24} strokeWidth={1.8} />}
        emptyHint={canManage ? "Combine a registered model with an MCP server to make an agent that acts." : "An admin can create agents that combine models with tools."}
        emptyAction={canManage ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} strokeWidth={2} /> New agent</Button> : undefined}
      />
      {!showLoading && !!agents?.length && (
        <CardGrid>
          {agents.map((a) => (
            <EntityCard
              key={a.id}
              icon={<Bot size={17} strokeWidth={2} />}
              title={a.name}
              chips={
                <>
                  {a.mcp_server_name && <Chip tone="accent">{a.mcp_server_name}</Chip>}
                  {a.safety_mode && <Chip tone="ok">safety on</Chip>}
                </>
              }
              body={a.description ?? undefined}
              meta={
                <>
                  {a.model_name && <span>{a.model_name}</span>}
                  <span>{a.max_steps} steps max</span>
                </>
              }
              actions={canTouch && (
                <>
                  <button
                    aria-label={`Edit agent ${a.name}`}
                    title="Edit agent"
                    onClick={() => setEditing(a)}
                    className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                  >
                    <Pencil size={14} strokeWidth={2} />
                  </button>
                  <button
                    aria-label={`Remove agent ${a.name}`}
                    title="Remove agent"
                    onClick={() => setRemoving(a)}
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
      <CreateAgentDialog open={creating} onClose={() => setCreating(false)} defaultProjectId={defaultProjectId} />
      {editing && (
        <EditAgentDialog
          key={editing.id}
          agent={editing}
          onClose={() => setEditing(null)}
          siblings={(agents ?? []).filter((x) => x.id !== editing.id)}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) del.mutate(removing.id);
          setRemoving(null);
        }}
        title="Remove this agent?"
        body={
          <p>
            <b className="text-ink">{removing?.name}</b> will be removed. Personas backed by it stop answering
            until they&apos;re rewired.
          </p>
        }
        confirmLabel="Remove agent"
        loading={del.isPending}
      />
    </TabShell>
  );
}

export function CreateAgentDialog({ open, onClose, defaultProjectId, onCreated }: {
  open: boolean;
  onClose: () => void;
  defaultProjectId?: string;
  // Launched inline from the persona builder: hands the new agent back so the
  // host can select it — no tab-hopping.
  onCreated?: (a: AIAgent) => void;
}) {
  const { data: allProjects } = useProjects();
  const { data: models } = useModels();
  const { data: servers } = useMcpServers();
  const { data: agents } = useAgents();
  const setProject = useSetModelProject();
  const [projectId, setProjectId] = useState(defaultProjectId ?? "");
  // Inline prerequisite creation — stacked dialogs, mounted fresh per open so
  // they pick up the currently selected project.
  const [addingModel, setAddingModel] = useState(false);
  const [addingMcp, setAddingMcp] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [modelId, setModelId] = useState("");
  const [mcpId, setMcpId] = useState("");
  const [maxSteps, setMaxSteps] = useState(5);
  const [safety, setSafety] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const validateName = (v: string) => {
    const shared = vName(v, { label: "agent name" });
    if (shared) return shared;
    // Per-project uniqueness (the server's rule) — same name elsewhere is fine.
    if (agents?.some((a) => a.project_id === projectId && a.name.toLowerCase() === v.trim().toLowerCase()))
      return "This project already has an agent with this name.";
    return null;
  };

  // MCP servers are project-owned; the model picker honors the attach gate
  // itself (and offers attach & use for the rest).
  const projectServers = servers?.filter((s) => s.project_id === projectId) ?? [];
  const projName = allProjects?.find((p) => p.id === projectId)?.name;

  const reset = () => {
    setProjectId(defaultProjectId ?? "");
    setName("");
    setDescription("");
    setModelId("");
    setMcpId("");
    setMaxSteps(5);
    setSafety(true);
    setErr(null);
    setNameErr(null);
    setTouched(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateAgent((a) => {
    onCreated?.(a);
    close();
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // The attach await opens a window where create.isPending is still false —
    // the footer button's loading covers it, this guard covers the race.
    if (create.isPending || setProject.isPending) return;
    setErr(null);
    setTouched(true);
    const ne = validateName(name);
    setNameErr(ne);
    if (!projectId) return setErr("Pick the project this agent belongs to.");
    if (ne) return;
    if (!modelId) return setErr("Pick the model that powers it.");
    if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 20) return setErr("Step budget must be a whole number between 1 and 20.");
    // Attach & use: a model picked from another project is attached here
    // first, then the agent is created — one submit, no tab-hopping.
    const picked = models?.find((m) => m.id === modelId);
    if (picked?.project_ids && !picked.project_ids.includes(projectId)) {
      try {
        await setProject.mutateAsync({ projectId, modelId, attach: true });
      } catch {
        return; // the hook already toasted; stay in the dialog to retry
      }
    }
    create.mutate({
      project_id: projectId,
      name: name.trim(),
      description: description.trim() || undefined,
      model_id: modelId,
      mcp_server_id: mcpId || undefined,
      safety_mode: safety,
      max_steps: maxSteps,
    });
  };

  return (
    <>
    <Dialog
      open={open}
      onClose={close}
      size="lg"
      title={`New agent${projName ? ` — ${projName}` : ""}`}
      description="A model that can plan and use tools in a loop. Give it a model, optionally an MCP server, and a step budget."
      icon={<Bot size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="ag-form" size="sm" variant="primary" loading={create.isPending || setProject.isPending}>Create agent</Button>
        </div>
      }
    >
      <form id="ag-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <ProjectSelect
          id="ag-project"
          value={projectId}
          onChange={(v) => {
            setProjectId(v);
            // Model and MCP picks are project-scoped — a stale mcpId from the
            // old project would create a cross-project agent.
            setModelId("");
            setMcpId("");
          }}
          only={allProjects ?? []}
        />
        <div>
          <Label htmlFor="ag-name">Name</Label>
          <Input
            id="ag-name"
            autoFocus
            placeholder="e.g. Data analyst"
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
            maxLength={100}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
        <ModelPicker
          id="ag-model"
          projectId={projectId}
          models={models}
          value={modelId}
          onChange={setModelId}
          onRegisterNew={() => setAddingModel(true)}
        />
        <div>
          <Label htmlFor="ag-mcp">MCP server <span className="text-ink2">(optional)</span></Label>
          <select id="ag-mcp" value={mcpId} onChange={(e) => setMcpId(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
            <option value="">No tools — reasoning only</option>
            {projectServers.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="text-[12px] text-ink2">Only this project&apos;s tool servers — MCP servers belong to one project.</p>
            <button type="button" onClick={() => setAddingMcp(true)} className="inline-flex cursor-pointer items-center gap-1 text-[12px] font-semibold text-accent hover:underline">
              <Plus size={12} strokeWidth={2.4} /> Add a tool server
            </button>
          </div>
        </div>
        <div>
          <Label htmlFor="ag-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="ag-desc" placeholder="What is this agent for?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="ag-steps">Step budget</Label>
            <Input id="ag-steps" type="number" min={1} max={20} step={1} value={maxSteps} onChange={(e) => setMaxSteps(Number(e.target.value))} />
          </div>
          <label className="flex items-center gap-2.5 self-end pb-2.5 text-[13px]">
            <input type="checkbox" checked={safety} onChange={(e) => setSafety(e.target.checked)} className="accent-[var(--accent)]" />
            <span className="flex items-center gap-1.5"><ShieldCheck size={14} strokeWidth={2} className="text-ok" /> Safety mode</span>
          </label>
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
    {/* Stacked prerequisite dialogs — mounted per open so they scope to the
        currently selected project; results select themselves on return. */}
    {addingModel && (
      <CreateModelDialog
        open
        onClose={() => setAddingModel(false)}
        // No project picked yet → plain registration; the picker still offers
        // the new model and attach-on-create covers it once a project is set.
        attachProjectId={projectId || undefined}
        attachProjectName={projName}
        onCreated={(m) => setModelId(m.id)}
      />
    )}
    {addingMcp && (
      <CreateMcpDialog
        open
        onClose={() => setAddingMcp(false)}
        defaultProjectId={projectId}
        onCreated={(s) => {
          // No project picked yet → adopt the server's project so the pick
          // is valid; a mismatched project keeps the selection empty instead.
          if (!projectId) {
            setProjectId(s.project_id);
            setMcpId(s.id);
          } else if (s.project_id === projectId) {
            setMcpId(s.id);
          }
        }}
      />
    )}
    </>
  );
}

function EditAgentDialog({ agent, onClose, siblings }: { agent: AIAgent; onClose: () => void; siblings: AIAgent[] }) {
  const { data: models } = useModels();
  const { data: servers } = useMcpServers();
  const [name, setName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description ?? "");
  const [modelId, setModelId] = useState(agent.model_id ?? "");
  const [mcpId, setMcpId] = useState(agent.mcp_server_id ?? "");
  const [maxSteps, setMaxSteps] = useState(agent.max_steps);
  const [safety, setSafety] = useState(agent.safety_mode);
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const patch = usePatchAgent(onClose);
  // Agents are project-owned — a duplicate name only clashes inside the project.
  const projectSiblings = siblings.filter((x) => x.project_id === agent.project_id);
  // Same contracts as create: project-owned MCP servers, attached models only.
  const projectServers = servers?.filter((s) => s.project_id === agent.project_id) ?? [];
  const projectModels =
    models?.filter((m) => !m.project_ids || !agent.project_id || m.project_ids.includes(agent.project_id) || m.id === agent.model_id) ?? [];

  const validateName = (v: string) => {
    const shared = vName(v, { label: "agent name" });
    if (shared) return shared;
    if (projectSiblings.some((x) => x.name.toLowerCase() === v.trim().toLowerCase())) return "An agent with this name already exists in this project.";
    return null;
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setTouched(true);
    const ne = validateName(name);
    setNameErr(ne);
    if (ne) return;
    if (!modelId) return setErr("Pick the model that powers it.");
    if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 20) return setErr("Step budget must be a whole number between 1 and 20.");
    const payload = {
      ...(name.trim() !== agent.name ? { name: name.trim() } : {}),
      ...(description.trim() !== (agent.description ?? "") ? { description: description.trim() } : {}),
      ...(modelId !== (agent.model_id ?? "") ? { model_id: modelId } : {}),
      ...(mcpId && mcpId !== (agent.mcp_server_id ?? "") ? { mcp_server_id: mcpId } : {}),
      ...(safety !== agent.safety_mode ? { safety_mode: safety } : {}),
      ...(maxSteps !== agent.max_steps ? { max_steps: maxSteps } : {}),
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    patch.mutate({ id: agent.id, payload });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Edit ${agent.name}`}
      description="Changes apply the next time the agent runs — in-flight work finishes on the old settings."
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="age-form" size="sm" variant="primary" loading={patch.isPending}>Save changes</Button>
        </div>
      }
    >
      <form id="age-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="age-name">Name</Label>
          <Input
            id="age-name"
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
            maxLength={100}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
        <div>
          <Label htmlFor="age-model">Model</Label>
          <select id="age-model" value={modelId} onChange={(e) => setModelId(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
            <option value="" disabled>Choose a model…</option>
            {projectModels.map((m) => (
              <option key={m.id} value={m.id}>{m.name} ({m.model_id})</option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="age-mcp">MCP server</Label>
          <select id="age-mcp" value={mcpId} onChange={(e) => setMcpId(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
            {/* The server applies only non-null patch fields, so an attached
                MCP server can be swapped but not removed here. */}
            {!agent.mcp_server_id && <option value="">No tools — reasoning only</option>}
            {projectServers.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {!!agent.mcp_server_id && (
            <p className="mt-1.5 text-[12px] text-ink2">Tools can be swapped for another server, not removed — recreate the agent to go tool-less.</p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="age-steps">Step budget</Label>
            <Input id="age-steps" type="number" min={1} max={20} step={1} value={maxSteps} onChange={(e) => setMaxSteps(Number(e.target.value))} />
          </div>
          <label className="flex items-center gap-2.5 self-end pb-2.5 text-[13px]">
            <input type="checkbox" checked={safety} onChange={(e) => setSafety(e.target.checked)} className="accent-[var(--accent)]" />
            <span className="flex items-center gap-1.5"><ShieldCheck size={14} strokeWidth={2} className="text-ok" /> Safety mode</span>
          </label>
        </div>
        <div>
          <Label htmlFor="age-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="age-desc" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}
