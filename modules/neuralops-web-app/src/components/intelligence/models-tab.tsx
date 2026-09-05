"use client";

import { useEffect, useState } from "react";
import { useUiStore } from "@/stores/ui.store";
import { Boxes, Cpu, KeyRound, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateUrl as vUrl } from "@/lib/validation";
import { useCreateModel, useDeleteModel, useModels, useSetModelProject } from "@/hooks/use-intelligence";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useProjects } from "@/hooks/use-workspace";
import type { AIModel } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, TabShell, Toolbar } from "./shared";

const PROVIDERS = [
  { value: "anthropic", label: "Anthropic", placeholder: "anthropic/claude-sonnet-5", needsKey: true },
  { value: "openai", label: "OpenAI", placeholder: "openai/gpt-5", needsKey: true },
  { value: "ollama", label: "Ollama (local)", placeholder: "ollama/llama3", needsKey: false },
  { value: "other", label: "Other (LiteLLM id)", placeholder: "provider/model-name", needsKey: true },
];

export function ModelsTab({ canManage, embedded }: { canManage: boolean; embedded?: boolean }) {
  // canManage (create/delete + keys) is COMPANY-scope only; ATTACH is a
  // separate, lighter PROJECT-scope right a Project Admin also holds.
  const role = useConnectionStore((s) => s.connection?.role);
  const canAttach = isCompanyAdmin(role);
  const { data: models, isLoading, error, refetch } = useModels();
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
  const [managing, setManaging] = useState<string | null>(null); // model id
  const [removing, setRemoving] = useState<AIModel | null>(null);
  const showLoading = useDelayedLoading(isLoading);
  const del = useDeleteModel();

  return (
    <TabShell
      embedded={embedded}
      title="AI models"
      blurb="Model endpoints with your own keys — encrypted at rest, never shown again."
      action={!!models?.length && canManage && (
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <Plus size={14} strokeWidth={2} /> Register model
        </Button>
      )}
    >
      {!!models?.length && (
        <Toolbar
          facts={[
            `${models.length} ${models.length === 1 ? "model" : "models"}`,
            `${models.filter((m) => m.supports_tools).length} tool-capable`,
            `${new Set(models.map((m) => m.provider)).size} providers`,
          ]}
        />
      )}
      <ListState
        loading={showLoading}
        error={error}
        onRetry={refetch}
        empty={models?.length === 0}
        emptyTitle="No models yet"
        emptyIcon={<Cpu size={24} strokeWidth={1.8} />}
        emptyHint={canManage ? "Register a model with your own API key — everything AI starts here." : "An admin needs to register a model before personas can answer."}
        emptyAction={canManage ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} strokeWidth={2} /> Register model</Button> : undefined}
      />
      {!showLoading && !!models?.length && (
        <CardGrid>
          {models.map((m) => (
            <EntityCard
              key={m.id}
              icon={<Cpu size={17} strokeWidth={2} />}
              title={m.name}
              chips={
                <>
                  {m.has_api_key ? <Chip tone="ok">key set</Chip> : m.provider === "ollama" ? <Chip>local</Chip> : <Chip tone="warn">no key</Chip>}
                  {m.supports_tools && <Chip tone="accent">tools</Chip>}
                </>
              }
              body={m.description ?? undefined}
              meta={
                <>
                  <span title={m.model_id} className="max-w-full truncate font-mono">{m.model_id}</span>
                  {m.api_base && <span title={m.api_base} className="max-w-full truncate font-mono">{m.api_base}</span>}
                  <span>ctx {Math.round(m.context_window / 1000)}k</span>
                  <span>{m.project_ids?.length ?? 0} {(m.project_ids?.length ?? 0) === 1 ? "project" : "projects"}</span>
                </>
              }
              actions={(canManage || canAttach) && (
                <>
                  {canAttach && (
                    <button
                      aria-label={`Manage projects for ${m.name}`}
                      title="Attach to projects"
                      onClick={() => setManaging(m.id)}
                      className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                    >
                      <Boxes size={14} strokeWidth={2} />
                    </button>
                  )}
                  {canManage && (
                    <button
                      aria-label={`Remove model ${m.name}`}
                      title="Remove model"
                      onClick={() => setRemoving(m)}
                      className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </button>
                  )}
                </>
              )}
            />
          ))}
        </CardGrid>
      )}
      <CreateModelDialog open={creating} onClose={() => setCreating(false)} />
      {managing && <ModelProjectsDialog modelId={managing} onClose={() => setManaging(null)} />}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) del.mutate(removing.id);
          setRemoving(null);
        }}
        title="Remove this model?"
        body={
          <p>
            <b className="text-ink">{removing?.name}</b> will be removed. Personas and agents backed by it will
            stop answering until they&apos;re pointed at another model.
          </p>
        }
        confirmLabel="Remove model"
        loading={del.isPending}
      />
    </TabShell>
  );
}

export function CreateModelDialog({ open, onClose, attachProjectId, attachProjectName, onCreated }: {
  open: boolean;
  onClose: () => void;
  // Launched inline from a project-scoped flow (persona/agent builder): the
  // new model is attached to that project right after registration and handed
  // back through onCreated so the host can select it — no tab-hopping.
  attachProjectId?: string;
  attachProjectName?: string;
  onCreated?: (m: AIModel) => void;
}) {
  const { data: models } = useModels();
  const setProject = useSetModelProject();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("anthropic");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [supportsTools, setSupportsTools] = useState(true);
  const [licence, setLicence] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [idErr, setIdErr] = useState<string | null>(null);
  const [baseErr, setBaseErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const prov = PROVIDERS.find((p) => p.value === provider) ?? PROVIDERS[0];

  const validateName = (v: string) => {
    const shared = vName(v, { label: "model name", existing: models?.map((m) => m.name) });
    if (shared) return shared;
    return null;
  };
  const validateId = (v: string) => (!v.trim().includes("/") ? "Use the LiteLLM id format: provider/model-name." : null);

  const reset = () => {
    setName("");
    setProvider("anthropic");
    setModelId("");
    setApiKey("");
    setApiBase("");
    setSupportsTools(true);
    setLicence(false);
    setErr(null);
    setNameErr(null);
    setIdErr(null);
    setBaseErr(null);
    setTouched(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateModel((m) => {
    const done = () => {
      onCreated?.(m);
      close();
    };
    // Attach failure still hands the model back — it registered fine, and the
    // host's picker offers it under attach & use, so the flow recovers in place.
    if (attachProjectId) setProject.mutate({ projectId: attachProjectId, modelId: m.id, attach: true }, { onSettled: done });
    else done();
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setTouched(true);
    const ne = validateName(name);
    const ie = validateId(modelId);
    const showsBase = provider === "ollama" || provider === "other";
    const be = showsBase ? vUrl(apiBase, { label: "the API base URL", required: false }) : null;
    setNameErr(ne);
    setIdErr(ie);
    setBaseErr(be);
    if (ne || ie || be) return;
    if (prov.needsKey && !apiKey.trim()) return setErr("This provider needs an API key.");
    if (!licence) return setErr("You must accept the provider's terms to register the model.");
    create.mutate({
      name: name.trim(),
      provider: provider === "other" ? modelId.trim().split("/")[0] : provider,
      model_id: modelId.trim(),
      // A field hidden by the provider switch must not ride along — a stale
      // api_base typed for "Other" would silently misroute an Anthropic model.
      api_key: prov.needsKey ? apiKey.trim() || undefined : undefined,
      api_base: provider === "ollama" || provider === "other" ? apiBase.trim() || undefined : undefined,
      licence_accepted: true,
      supports_tools: supportsTools,
    });
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      size="lg"
      title={`Register an AI model${attachProjectName ? ` — ${attachProjectName}` : ""}`}
      description={`Bring your own key. It's encrypted at rest, used only to run your personas, and never shown or returned again.${attachProjectName ? ` The model is attached to ${attachProjectName} and ready to pick right away.` : ""}`}
      icon={<KeyRound size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="m-form" size="sm" variant="primary" loading={create.isPending || setProject.isPending}>Register model</Button>
        </div>
      }
    >
      <form id="m-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="m-name">Name</Label>
          <Input
            id="m-name"
            autoFocus
            placeholder="e.g. Claude for Aurora"
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
          <Label htmlFor="m-provider">Provider</Label>
          <select
            id="m-provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="m-id">Model id</Label>
          <Input
            id="m-id"
            placeholder={prov.placeholder}
            value={modelId}
            aria-invalid={!!idErr}
            onChange={(e) => {
              setModelId(e.target.value);
              if (touched) setIdErr(validateId(e.target.value));
            }}
            onBlur={() => {
              if (modelId) {
                setTouched(true);
                setIdErr(validateId(modelId));
              }
            }}
            className="font-mono"
          />
          {idErr ? <FieldError>{idErr}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">LiteLLM format — provider prefix, slash, model name.</p>}
        </div>
        {prov.needsKey && (
          <div>
            <Label htmlFor="m-key">API key</Label>
            <Input id="m-key" type="password" autoComplete="off" placeholder="sk-…" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          </div>
        )}
        {(provider === "ollama" || provider === "other") && (
          <div>
            <Label htmlFor="m-base">API base <span className="text-ink2">(optional)</span></Label>
            <Input id="m-base" inputMode="url" placeholder="http://localhost:11434" value={apiBase} aria-invalid={!!baseErr}
              onChange={(e) => { setApiBase(e.target.value); if (touched) setBaseErr(vUrl(e.target.value, { label: "the API base URL", required: false })); }}
              className="font-mono" />
            <FieldError>{baseErr}</FieldError>
          </div>
        )}
        <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={supportsTools} onChange={(e) => setSupportsTools(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          Supports tool use — required for agents; most modern chat models do.
        </label>
        <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={licence} onChange={(e) => setLicence(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          I accept the model provider&apos;s terms of service for this key and usage.
        </label>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}

// Attach/detach happen per toggle (the API is per-project) — the list always
// shows the server's current truth, re-read after every change.
function ModelProjectsDialog({ modelId, onClose }: { modelId: string; onClose: () => void }) {
  const { data: models } = useModels();
  const { data: allProjects, isLoading } = useProjects();
  // ai_model.attach is PROJECT-scope: list only projects where the user can
  // actually attach (all of them for a Company Admin).
  const projects = allProjects;
  const setProject = useSetModelProject();
  const [pending, setPending] = useState<string | null>(null);
  const model = models?.find((m) => m.id === modelId);
  const attached = new Set(model?.project_ids ?? []);

  const toggle = (projectId: string) => {
    if (pending) return; // one flight at a time keeps the list truthful
    setPending(projectId);
    setProject.mutate(
      { projectId, modelId, attach: !attached.has(projectId) },
      { onSettled: () => setPending(null) },
    );
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Projects for ${model?.name ?? "this model"}`}
      description="Attaching makes the model visible in a project — its personas and agents can be built on it."
      icon={<Boxes size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end">
          <Button size="sm" onClick={onClose}>Done</Button>
        </div>
      }
    >
      {isLoading && <p className="py-4 text-center text-[13px] text-ink2">Loading projects…</p>}
      {models && !model && (
        <p className="py-4 text-center text-[13px] text-crit">This model no longer exists — it may have been removed by another admin.</p>
      )}
      {!isLoading && !!model && (projects?.length ?? 0) === 0 && (
        <p className="py-4 text-center text-[13px] text-ink2">No projects yet — create one in the workspace first.</p>
      )}
      {!!model && (
      <ul className="flex flex-col">
        {projects?.map((p) => (
          <li key={p.id} className="border-b border-line last:border-b-0">
            <label className="flex cursor-pointer items-center gap-3 py-2.5 text-[14px]">
              <input
                type="checkbox"
                checked={attached.has(p.id)}
                disabled={pending !== null}
                onChange={() => toggle(p.id)}
                className="accent-[var(--accent)]"
              />
              <span className="flex-1 truncate">{p.name}</span>
              {pending === p.id && <span className="text-[12px] text-ink2">saving…</span>}
            </label>
          </li>
        ))}
      </ul>
      )}
    </Dialog>
  );
}
