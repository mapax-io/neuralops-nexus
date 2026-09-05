"use client";

import { useEffect, useState } from "react";
import { useUiStore } from "@/stores/ui.store";
import { Boxes, Cpu, KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateNumber, validateUrl as vUrl } from "@/lib/validation";
import { useCreateModelConfig, useDeleteModelConfig, useModelConfigs, usePatchModelConfig, useSetModelConfigProject } from "@/hooks/use-intelligence";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useProjects } from "@/hooks/use-workspace";
import type { ModelConfig, ModelConfigPatch } from "@/lib/api/intelligence";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { CardGrid, Chip, EntityCard, ListState, TabShell, Toolbar } from "./shared";

// The server's five providers (ModelConfig.Provider). The model id is the BARE
// name — the server composes "provider:model" itself and rejects a prefix.
// `base`: whether an API base URL applies (required for anything OpenAI-shaped
// behind a custom endpoint, optional for a local Ollama, unused natively).
const PROVIDERS = [
  { value: "anthropic", label: "Anthropic", placeholder: "claude-sonnet-5", needsKey: true, base: "none" },
  { value: "openai", label: "OpenAI", placeholder: "gpt-5", needsKey: true, base: "none" },
  { value: "google", label: "Google (Gemini)", placeholder: "gemini-2.0-flash", needsKey: true, base: "none" },
  { value: "ollama", label: "Ollama (local)", placeholder: "llama3", needsKey: false, base: "optional" },
  { value: "openai_compatible", label: "OpenAI-compatible endpoint", placeholder: "your-model-name", needsKey: false, base: "required" },
] as const;

const providerOf = (value: string) => PROVIDERS.find((p) => p.value === value);
const providerLabel = (value: string) => providerOf(value)?.label ?? value;

const validateModelId = (v: string) => {
  const t = v.trim();
  if (!t) return "Enter the model id.";
  if (t.includes("/") || t.includes(":")) return "Use the bare model name — the provider is picked above, so no openai/ or anthropic: prefix.";
  return null;
};
const validateContext = (v: string) => validateNumber(v, { label: "the context window", min: 1, integer: true });

const CAPABILITIES: { key: "supports_tools" | "supports_streaming" | "supports_vision" | "supports_audio"; label: string }[] = [
  { key: "supports_tools", label: "Supports tool use — needed to give personas MCP tools; most modern chat models do" },
  { key: "supports_streaming", label: "Streams responses" },
  { key: "supports_vision", label: "Understands images" },
  { key: "supports_audio", label: "Understands audio" },
];
type Capabilities = Record<(typeof CAPABILITIES)[number]["key"], boolean>;

function CapabilityChecks({ value, onChange }: { value: Capabilities; onChange: (v: Capabilities) => void }) {
  return (
    <div className="flex flex-col gap-2">
      {CAPABILITIES.map((c) => (
        <label key={c.key} className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={value[c.key]} onChange={(e) => onChange({ ...value, [c.key]: e.target.checked })} className="mt-0.5 accent-[var(--accent)]" />
          {c.label}
        </label>
      ))}
    </div>
  );
}

export function ModelsTab({ canManage, embedded }: { canManage: boolean; embedded?: boolean }) {
  // canManage (create/edit/delete + keys) is COMPANY-scope only; ATTACH is a
  // separate, lighter PROJECT-scope right a Project Admin also holds.
  const role = useConnectionStore((s) => s.connection?.role);
  const canAttach = isCompanyAdmin(role);
  const { data: models, isLoading, error, refetch } = useModelConfigs();
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
  const [editing, setEditing] = useState<ModelConfig | null>(null);
  const [removing, setRemoving] = useState<ModelConfig | null>(null);
  const showLoading = useDelayedLoading(isLoading);
  const del = useDeleteModelConfig();

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
            `${new Set(models.map((m) => m.provider)).size} ${new Set(models.map((m) => m.provider)).size === 1 ? "provider" : "providers"}`,
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
                  <span title={m.qualified_id} className="max-w-full truncate font-mono">{m.qualified_id}</span>
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
                    <>
                      <button
                        aria-label={`Edit model ${m.name}`}
                        title="Edit model"
                        onClick={() => setEditing(m)}
                        className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                      >
                        <Pencil size={14} strokeWidth={2} />
                      </button>
                      <button
                        aria-label={`Remove model ${m.name}`}
                        title="Remove model"
                        onClick={() => setRemoving(m)}
                        className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                      >
                        <Trash2 size={14} strokeWidth={2} />
                      </button>
                    </>
                  )}
                </>
              )}
            />
          ))}
        </CardGrid>
      )}
      <CreateModelDialog open={creating} onClose={() => setCreating(false)} />
      {editing && <EditModelDialog key={editing.id} model={editing} onClose={() => setEditing(null)} siblings={(models ?? []).filter((x) => x.id !== editing.id)} />}
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
            <b className="text-ink">{removing?.name}</b> and its key will be removed. If a persona still uses it —
            as its model or its advisor — the server refuses and names the persona, so nothing stops answering silently.
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
  // Launched inline from a project-scoped flow (persona builder): the new model
  // is attached to that project right after registration and handed back
  // through onCreated so the host can select it — no tab-hopping.
  attachProjectId?: string;
  attachProjectName?: string;
  onCreated?: (m: ModelConfig) => void;
}) {
  const { data: models } = useModelConfigs();
  const setProject = useSetModelConfigProject();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<string>("anthropic");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [contextWindow, setContextWindow] = useState("8192");
  const [caps, setCaps] = useState<Capabilities>({ supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false });
  const [licence, setLicence] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [idErr, setIdErr] = useState<string | null>(null);
  const [baseErr, setBaseErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const prov = providerOf(provider) ?? PROVIDERS[0];
  const showsBase = prov.base !== "none";

  const validateName = (v: string) => vName(v, { label: "model name", existing: models?.map((m) => m.name) });
  const validateBase = (v: string) => vUrl(v, { label: "the API base URL", required: prov.base === "required" });

  const reset = () => {
    setName("");
    setProvider("anthropic");
    setModelId("");
    setApiKey("");
    setApiBase("");
    setContextWindow("8192");
    setCaps({ supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false });
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
  const create = useCreateModelConfig((m) => {
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
    const ie = validateModelId(modelId);
    const be = showsBase ? validateBase(apiBase) : null;
    setNameErr(ne);
    setIdErr(ie);
    setBaseErr(be);
    if (ne || ie || be) return;
    const ce = validateContext(contextWindow);
    if (ce) return setErr(ce);
    if (prov.needsKey && !apiKey.trim()) return setErr("This provider needs an API key.");
    if (!licence) return setErr("You must accept the provider's terms to register the model.");
    create.mutate({
      name: name.trim(),
      provider,
      model_id: modelId.trim(),
      api_key: apiKey.trim() || undefined,
      // A field hidden by the provider switch must not ride along — a stale
      // api_base typed for a compatible endpoint would misroute a native model.
      api_base: showsBase ? apiBase.trim() || undefined : undefined,
      licence_accepted: true,
      context_window: Number(contextWindow),
      ...caps,
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
        <div className="grid gap-4 sm:grid-cols-2">
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
                if (touched) setIdErr(validateModelId(e.target.value));
              }}
              onBlur={() => {
                if (modelId) {
                  setTouched(true);
                  setIdErr(validateModelId(modelId));
                }
              }}
              className="font-mono"
            />
            {idErr ? <FieldError>{idErr}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Bare model name — no provider prefix. Becomes {provider}:{modelId.trim() || prov.placeholder}.</p>}
          </div>
        </div>
        <div>
          <Label htmlFor="m-key">API key{!prov.needsKey && <span className="text-ink2"> (optional)</span>}</Label>
          <Input id="m-key" type="password" autoComplete="off" placeholder="sk-…" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        {showsBase && (
          <div>
            <Label htmlFor="m-base">API base{prov.base === "optional" && <span className="text-ink2"> (optional)</span>}</Label>
            <Input id="m-base" inputMode="url" placeholder={provider === "ollama" ? "http://localhost:11434" : "https://api.example.com/v1"} value={apiBase} aria-invalid={!!baseErr}
              onChange={(e) => { setApiBase(e.target.value); if (touched) setBaseErr(validateBase(e.target.value)); }}
              className="font-mono" />
            <FieldError>{baseErr}</FieldError>
          </div>
        )}
        <div>
          <Label htmlFor="m-ctx">Context window</Label>
          <Input id="m-ctx" type="number" min={1} step={1} inputMode="numeric" value={contextWindow} onChange={(e) => setContextWindow(e.target.value)} className="sm:max-w-[12rem]" />
          <p className="mt-1.5 text-[12px] text-ink2">Tokens the model can take in one call — check the provider&apos;s model page.</p>
        </div>
        <CapabilityChecks value={caps} onChange={setCaps} />
        <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={licence} onChange={(e) => setLicence(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          I accept the model provider&apos;s terms of service for this key and usage.
        </label>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}

// Everything but the identity: rotating the key used to mean delete-and-recreate,
// which the delete guard refuses while a persona uses the model. Provider and
// model id stay read-only — changing them would repoint every persona at a
// different model.
function EditModelDialog({ model, onClose, siblings }: { model: ModelConfig; onClose: () => void; siblings: ModelConfig[] }) {
  const [name, setName] = useState(model.name);
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState(model.api_base ?? "");
  const [description, setDescription] = useState(model.description ?? "");
  const [contextWindow, setContextWindow] = useState(String(model.context_window));
  const [caps, setCaps] = useState<Capabilities>({
    supports_tools: model.supports_tools, supports_streaming: model.supports_streaming,
    supports_vision: model.supports_vision, supports_audio: model.supports_audio,
  });
  const [err, setErr] = useState<string | null>(null);
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [baseErr, setBaseErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const patch = usePatchModelConfig(onClose);
  const prov = providerOf(model.provider);
  // A native provider can still be proxied through api_base — keep it editable
  // whenever the provider allows one or a value is already set.
  const showsBase = (prov?.base ?? "optional") !== "none" || !!model.api_base;

  const validateName = (v: string) => vName(v, { label: "model name", existing: siblings.map((m) => m.name), current: model.name });
  const validateBase = (v: string) => vUrl(v, { label: "the API base URL", required: prov?.base === "required" });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setTouched(true);
    const ne = validateName(name);
    const be = showsBase ? validateBase(apiBase) : null;
    setNameErr(ne);
    setBaseErr(be);
    if (ne || be) return;
    const ce = validateContext(contextWindow);
    if (ce) return setErr(ce);
    // Only what changed; a blank key field means "keep the current key".
    const payload: ModelConfigPatch = {
      ...(name.trim() !== model.name ? { name: name.trim() } : {}),
      ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      ...(showsBase && apiBase.trim() !== (model.api_base ?? "") ? { api_base: apiBase.trim() } : {}),
      ...(description.trim() !== (model.description ?? "") ? { description: description.trim() } : {}),
      ...(Number(contextWindow) !== model.context_window ? { context_window: Number(contextWindow) } : {}),
      ...Object.fromEntries(CAPABILITIES.filter((c) => caps[c.key] !== model[c.key]).map((c) => [c.key, caps[c.key]])),
    };
    if (Object.keys(payload).length === 0) return onClose(); // nothing changed
    patch.mutate({ id: model.id, payload });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Edit ${model.name}`}
      description="Changes apply to the next call. To move to a different model, register it and repoint the personas — the model id is fixed."
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="me-form" size="sm" variant="primary" loading={patch.isPending}>Save changes</Button>
        </div>
      }
    >
      <form id="me-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="me-name">Name</Label>
          <Input
            id="me-name"
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
        <div className="rounded-[10px] border border-line bg-surface2/60 px-3 py-2.5 text-[13px]">
          <p className="text-[12px] text-ink2">Provider · model id <span className="text-ink2/70">(fixed)</span></p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2">
            <span className="font-medium">{providerLabel(model.provider)}</span>
            <code className="font-mono text-[12.5px] text-ink2">{model.qualified_id}</code>
          </p>
        </div>
        <div>
          <Label htmlFor="me-key">New API key <span className="text-ink2">(optional)</span></Label>
          <Input id="me-key" type="password" autoComplete="off" placeholder={model.has_api_key ? "Leave blank to keep the current key" : "No key stored yet"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        {showsBase && (
          <div>
            <Label htmlFor="me-base">API base{prov?.base !== "required" && <span className="text-ink2"> (optional)</span>}</Label>
            <Input id="me-base" inputMode="url" value={apiBase} aria-invalid={!!baseErr}
              onChange={(e) => { setApiBase(e.target.value); if (touched) setBaseErr(validateBase(e.target.value)); }}
              className="font-mono" />
            <FieldError>{baseErr}</FieldError>
          </div>
        )}
        <div>
          <Label htmlFor="me-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="me-desc" placeholder="What is this model for?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <div>
          <Label htmlFor="me-ctx">Context window</Label>
          <Input id="me-ctx" type="number" min={1} step={1} inputMode="numeric" value={contextWindow} onChange={(e) => setContextWindow(e.target.value)} className="sm:max-w-[12rem]" />
        </div>
        <CapabilityChecks value={caps} onChange={setCaps} />
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}

// Attach/detach happen per toggle (the API is per-project) — the list always
// shows the server's current truth, re-read after every change.
function ModelProjectsDialog({ modelId, onClose }: { modelId: string; onClose: () => void }) {
  const { data: models } = useModelConfigs();
  const { data: allProjects, isLoading } = useProjects();
  // model_config.attach is PROJECT-scope: list only projects where the user can
  // actually attach (all of them for a Company Admin).
  const projects = allProjects;
  const setProject = useSetModelConfigProject();
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
      description="Attaching makes the model visible in a project so its personas can be built on it. Detaching is refused while a persona there still uses it."
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
