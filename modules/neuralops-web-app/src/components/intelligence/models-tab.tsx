"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useUiStore } from "@/stores/ui.store";
import { Boxes, Check, Cpu, KeyRound, Pencil, Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogSection } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateNumber, validateUrl as vUrl } from "@/lib/validation";
import { useFormErrors } from "@/hooks/use-form-errors";
import { DEFAULT_CONTEXT_WINDOW, defaultContextWindow } from "@/lib/model-context";
import { useCreateModelConfig, useDeleteModelConfig, useModelConfigs, usePatchModelConfig, useSetModelConfigProject, useOpenRouterModels } from "@/hooks/use-intelligence";
import { companyScope } from "@/lib/permissions";
import { usePermissions } from "@/hooks/use-permissions";
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

export function ModelsTab({ embedded }: { embedded?: boolean }) {
  // Registering/editing/deleting a config (and its key) is COMPANY-scope;
  // ATTACH is a separate, lighter PROJECT-scope right a Project Admin holds,
  // so it is asked across every project rather than against the company.
  const { can, canAnyProject } = usePermissions();
  const canCreate = can("model_config.create", companyScope());
  const canEdit = can("model_config.update", companyScope());
  const canRemove = can("model_config.delete", companyScope());
  const canAttach = canAnyProject("model_config.attach");
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
      if (canCreate) setCreating(true);
    });
    return () => cancelAnimationFrame(raf);
  }, [intelCreate, setIntelCreate, canCreate]);
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
      action={!!models?.length && canCreate && (
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
        emptyHint={canCreate ? "Register a model with your own API key — everything AI starts here." : "An admin needs to register a model before personas can answer."}
        emptyAction={canCreate ? <Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} strokeWidth={2} /> Register model</Button> : undefined}
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
              actions={(canEdit || canRemove || canAttach) && (
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
                  {canEdit && (
                    <button
                      aria-label={`Edit model ${m.name}`}
                      title="Edit model"
                      onClick={() => setEditing(m)}
                      className="flex size-7 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                    >
                      <Pencil size={14} strokeWidth={2} />
                    </button>
                  )}
                  {canRemove && (
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
function ModelCombobox({
  id,
  value,
  onChange,
  onBlur,
  options,
  placeholder,
  error,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  onBlur: () => void;
  options: { id: string; name: string }[];
  placeholder?: string;
  error?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function click(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", click);
    return () => document.removeEventListener("mousedown", click);
  }, []);

  const filtered = useMemo(() => {
    const search = value.toLowerCase();
    return options.filter(o => o.id.toLowerCase().includes(search) || o.name.toLowerCase().includes(search));
  }, [options, value]);

  return (
    <div className="relative" ref={wrapperRef}>
      <Input id={id} value={value} onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={onBlur} aria-invalid={error} placeholder={placeholder} className="font-mono" autoComplete="off" />
      {open && filtered.length > 0 && (
        <div className="absolute top-[calc(100%+4px)] left-0 max-h-60 w-full overflow-y-auto rounded-[10px] border border-line bg-surface shadow-[0_4px_16px_rgba(0,0,0,0.1)] z-10 p-1 flex flex-col">
          {filtered.map(o => (
            <button key={o.id} type="button" onMouseDown={(e) => { e.preventDefault(); onChange(o.id); setOpen(false); }} className="w-full text-left px-2.5 py-1.5 text-sm rounded-[6px] hover:bg-surface2 flex flex-col gap-0.5">
              <span className="font-medium text-ink truncate leading-tight">{o.name}</span>
              <span className="font-mono text-[11px] text-ink2 truncate leading-tight">{o.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
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

  const { data: catalog } = useOpenRouterModels();
  const matchingModels = useMemo(() => {
    if (!catalog) return [];
    if (!["anthropic", "openai", "google"].includes(provider)) return [];
    const prefix = provider + "/";
    return catalog
      .filter((m) => m.id.startsWith(prefix))
      .map((m) => ({
        id: m.id.slice(prefix.length),
        name: m.name.replace(/^[^:]+:\s*/, ""),
      }));
  }, [catalog, provider]);
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [description, setDescription] = useState("");
  const [contextWindow, setContextWindow] = useState(String(DEFAULT_CONTEXT_WINDOW));
  // The context window follows the model id until the user types a size of
  // their own — then it is theirs and the id stops overriding it.
  const [ctxTouched, setCtxTouched] = useState(false);
  // The one capability that changes behaviour: the server refuses MCP servers
  // on a persona whose model lacks it, and defaults a new model to "no tools".
  const [supportsTools, setSupportsTools] = useState(true);
  const [licence, setLicence] = useState(false);
  const prov = providerOf(provider) ?? PROVIDERS[0];
  const showsBase = prov.base !== "none";
  const ctxKnown = defaultContextWindow(provider, modelId) !== DEFAULT_CONTEXT_WINDOW;
  const syncContext = (nextProvider: string, nextId: string) => {
    if (!ctxTouched) setContextWindow(String(defaultContextWindow(nextProvider, nextId)));
  };

  const validateName = (v: string) => vName(v, { label: "model name", existing: models?.map((m) => m.name) });
  const validateBase = (v: string) => vUrl(v, { label: "the API base URL", required: prov.base === "required" });
  // Every rule the submit needs, derived live: the button gates on all of
  // them, each field shows its own once visited.
  const form = useFormErrors({
    name: [name, validateName(name)],
    id: [modelId, validateModelId(modelId)],
    base: [apiBase, showsBase ? validateBase(apiBase) : null],
    key: [apiKey, prov.needsKey && !apiKey.trim() ? "This provider needs an API key." : null],
    ctx: [contextWindow, validateContext(contextWindow)],
    licence: [licence, licence ? null : "You must accept the provider's terms to register the model."],
  });

  const reset = () => {
    setName("");
    setProvider("anthropic");
    setModelId("");
    setApiKey("");
    setApiBase("");
    setDescription("");
    setContextWindow(String(DEFAULT_CONTEXT_WINDOW));
    setCtxTouched(false);
    setSupportsTools(true);
    setLicence(false);
    form.reset();
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
    // The button is gated on form.invalid; a submit that slips through
    // reveals every message instead of posting.
    if (form.invalid) return form.touchAll();
    create.mutate({
      name: name.trim(),
      provider,
      model_id: modelId.trim(),
      api_key: apiKey.trim() || undefined,
      // A field hidden by the provider switch must not ride along — a stale
      // api_base typed for a compatible endpoint would misroute a native model.
      api_base: showsBase ? apiBase.trim() || undefined : undefined,
      description: description.trim() || undefined,
      licence_accepted: true,
      context_window: Number(contextWindow),
      // Streaming, vision and audio are left to the server defaults — nothing
      // downstream reads them yet — and stay adjustable in the edit dialog.
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
      tone="accent"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}><X size={14} strokeWidth={2} /> Cancel</Button>
          <Button type="submit" form="m-form" size="sm" variant="primary" disabled={form.invalid} loading={create.isPending || setProject.isPending}><KeyRound size={14} strokeWidth={2} /> Register model</Button>
        </div>
      }
    >
      <form id="m-form" onSubmit={submit} noValidate className="flex flex-col">
        <DialogSection title="Identity" hint="A name for this workspace, and the provider’s bare model id.">
        <div>
          <Label htmlFor="m-name" required>Name</Label>
          <Input
            id="m-name"
            required
            autoFocus
            placeholder="e.g. Claude for Aurora"
            value={name}
            aria-invalid={!!form.error("name")}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => form.touch("name")}
            maxLength={100}
          />
          <FieldError>{form.error("name")}</FieldError>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="m-provider">Provider</Label>
            <select
              id="m-provider"
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                syncContext(e.target.value, modelId);
              }}
              className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="m-id" required>Model id</Label>
            {matchingModels.length > 0 ? (
              <ModelCombobox id="m-id" value={modelId} options={matchingModels} placeholder={prov.placeholder} error={!!form.error("id")} onChange={(v) => { setModelId(v); syncContext(provider, v); }} onBlur={() => form.touch("id")} />
            ) : (
              <Input
                id="m-id"
                required
                placeholder={prov.placeholder}
                value={modelId}
                aria-invalid={!!form.error("id")}
                onChange={(e) => {
                  setModelId(e.target.value);
                  syncContext(provider, e.target.value);
                }}
                onBlur={() => form.touch("id")}
                className="font-mono"
              />
            )}
            {form.error("id") ? <FieldError>{form.error("id")}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Bare model name — no provider prefix. Becomes {provider}:{modelId.trim() || prov.placeholder}.</p>}
          </div>
        </div>
        </DialogSection>
        <DialogSection title="Access" hint="Your own key — encrypted at rest, used only to run personas.">
        <div>
          <Label htmlFor="m-key" required={prov.needsKey}>API key{!prov.needsKey && <span className="text-ink2"> (optional)</span>}</Label>
          <Input id="m-key" type="password" required={prov.needsKey} autoComplete="off" placeholder="sk-…" value={apiKey} aria-invalid={!!form.error("key")} onChange={(e) => setApiKey(e.target.value)} onBlur={() => form.touch("key")} />
          <FieldError>{form.error("key")}</FieldError>
        </div>
        {showsBase && (
          <div>
            <Label htmlFor="m-base" required={prov.base === "required"}>API base{prov.base === "optional" && <span className="text-ink2"> (optional)</span>}</Label>
            <Input id="m-base" required={prov.base === "required"} inputMode="url" placeholder={provider === "ollama" ? "http://localhost:11434" : "https://api.example.com/v1"} value={apiBase} aria-invalid={!!form.error("base")}
              onChange={(e) => setApiBase(e.target.value)}
              onBlur={() => form.touch("base")}
              className="font-mono" />
            <FieldError>{form.error("base")}</FieldError>
          </div>
        )}
        </DialogSection>
        <DialogSection title="Details">
        <div>
          <Label htmlFor="m-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="m-desc" placeholder="What is this model for?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <div>
          <Label htmlFor="m-ctx" required>Context window</Label>
          <Input id="m-ctx" type="number" required min={1} step={1} inputMode="numeric" value={contextWindow} aria-invalid={!!form.error("ctx")} onChange={(e) => { setContextWindow(e.target.value); setCtxTouched(true); }} onBlur={() => form.touch("ctx")} className="sm:max-w-[12rem]" />
          {form.error("ctx") ? <FieldError>{form.error("ctx")}</FieldError> : (
            <p className="mt-1.5 text-[12px] text-ink2">
              {!ctxTouched && ctxKnown
                ? "Defaulted from the model id — adjust it if your provider says otherwise."
                : "Tokens the model can take in one call — check the provider\u2019s model page."}
            </p>
          )}
        </div>
        <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
          <input type="checkbox" checked={supportsTools} onChange={(e) => setSupportsTools(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          Supports tool use — personas can only mount MCP tool servers on a tool-capable model; untick for a model without function calling.
        </label>
        <div>
          <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
            <input type="checkbox" required checked={licence} aria-invalid={!!form.error("licence")} onChange={(e) => setLicence(e.target.checked)} onBlur={() => form.touch("licence")} className="mt-0.5 accent-[var(--accent)]" />
            <span className="after:ml-0.5 after:text-crit after:content-['*']">I accept the model provider&apos;s terms of service for this key and usage.</span>
          </label>
          <FieldError>{form.error("licence")}</FieldError>
        </div>
        </DialogSection>
      </form>
    </Dialog>
  );
}

// Everything, identity included: rotating the key used to mean
// delete-and-recreate, which the delete guard refuses while a persona uses the
// model. Provider and model id are editable too — every persona on the config
// follows to the new model on save, which the dialog says out loud.
function EditModelDialog({ model, onClose, siblings }: { model: ModelConfig; onClose: () => void; siblings: ModelConfig[] }) {
  const [name, setName] = useState(model.name);
  const [provider, setProvider] = useState<string>(model.provider);

  const { data: catalog } = useOpenRouterModels();
  const matchingModels = useMemo(() => {
    if (!catalog) return [];
    if (!["anthropic", "openai", "google"].includes(provider)) return [];
    const prefix = provider + "/";
    return catalog
      .filter((m) => m.id.startsWith(prefix))
      .map((m) => ({
        id: m.id.slice(prefix.length),
        name: m.name.replace(/^[^:]+:\s*/, ""),
      }));
  }, [catalog, provider]);

  const [modelId, setModelId] = useState(model.model_id);
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState(model.api_base ?? "");
  const [description, setDescription] = useState(model.description ?? "");
  const [contextWindow, setContextWindow] = useState(String(model.context_window));
  const [caps, setCaps] = useState<Capabilities>({
    supports_tools: model.supports_tools, supports_streaming: model.supports_streaming,
    supports_vision: model.supports_vision, supports_audio: model.supports_audio,
  });
  const patch = usePatchModelConfig(onClose);
  const prov = providerOf(provider);
  // A native provider can still be proxied through api_base — keep it editable
  // whenever the provider allows one or a value is already set.
  const showsBase = (prov?.base ?? "optional") !== "none" || !!model.api_base;
  const identityChanged = provider !== model.provider || modelId.trim() !== model.model_id;

  const validateName = (v: string) => vName(v, { label: "model name", existing: siblings.map((m) => m.name), current: model.name });
  const validateBase = (v: string) => vUrl(v, { label: "the API base URL", required: prov?.base === "required" });
  const form = useFormErrors({
    name: [name, validateName(name)],
    id: [modelId, validateModelId(modelId)],
    base: [apiBase, showsBase ? validateBase(apiBase) : null],
    ctx: [contextWindow, validateContext(contextWindow)],
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (form.invalid) return form.touchAll();
    // Only what changed; a blank key field means "keep the current key".
    const payload: ModelConfigPatch = {
      ...(name.trim() !== model.name ? { name: name.trim() } : {}),
      ...(provider !== model.provider ? { provider } : {}),
      ...(modelId.trim() !== model.model_id ? { model_id: modelId.trim() } : {}),
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
      description="Changes apply to the next call — including a swapped provider or model id."
      icon={<Pencil size={17} strokeWidth={2} />}
      tone="info"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}><X size={14} strokeWidth={2} /> Cancel</Button>
          <Button type="submit" form="me-form" size="sm" variant="primary" disabled={form.invalid} loading={patch.isPending}><Check size={14} strokeWidth={2} /> Save changes</Button>
        </div>
      }
    >
      <form id="me-form" onSubmit={submit} noValidate className="flex flex-col">
        <DialogSection title="Identity" hint="Changing the provider or model id repoints every persona on this config.">
        <div>
          <Label htmlFor="me-name" required>Name</Label>
          <Input
            id="me-name"
            required
            autoFocus
            value={name}
            aria-invalid={!!form.error("name")}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => form.touch("name")}
            maxLength={100}
          />
          <FieldError>{form.error("name")}</FieldError>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="me-provider" required>Provider</Label>
            <select
              id="me-provider"
              required
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
              {!providerOf(model.provider) && <option value={model.provider}>{model.provider}</option>}
            </select>
          </div>
          <div>
            <Label htmlFor="me-id" required>Model id</Label>
            {matchingModels.length > 0 ? (
              <ModelCombobox id="me-id" value={modelId} options={matchingModels} error={!!form.error("id")} onChange={(v) => setModelId(v)} onBlur={() => form.touch("id")} />
            ) : (
              <Input
                id="me-id"
                required
                value={modelId}
                aria-invalid={!!form.error("id")}
                onChange={(e) => setModelId(e.target.value)}
                onBlur={() => form.touch("id")}
                className="font-mono"
              />
            )}
            <FieldError>{form.error("id")}</FieldError>
          </div>
        </div>
        {/* Repointing is the point of editing these — but it is silent for the
            personas involved, so say it before the save, not after. */}
        <p className={`rounded-[10px] border px-3 py-2 text-[12px] ${identityChanged ? "border-warn/40 bg-warn/10 text-warn" : "border-line bg-surface2/60 text-ink2"}`}>
          {identityChanged
            ? `Every persona on this model follows to ${provider}:${modelId.trim() || "…"} the moment you save.`
            : "Every persona on this model follows a changed provider or model id the moment you save."}
        </p>
        </DialogSection>
        <DialogSection title="Access" hint="Rotate the key here; the current one stays until you do.">
        <div>
          <Label htmlFor="me-key">New API key <span className="text-ink2">(optional)</span></Label>
          <Input id="me-key" type="password" autoComplete="off" placeholder={model.has_api_key ? "Leave blank to keep the current key" : "No key stored yet"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        {showsBase && (
          <div>
            <Label htmlFor="me-base" required={prov?.base === "required"}>API base{prov?.base !== "required" && <span className="text-ink2"> (optional)</span>}</Label>
            <Input id="me-base" required={prov?.base === "required"} inputMode="url" value={apiBase} aria-invalid={!!form.error("base")}
              onChange={(e) => setApiBase(e.target.value)}
              onBlur={() => form.touch("base")}
              className="font-mono" />
            <FieldError>{form.error("base")}</FieldError>
          </div>
        )}
        </DialogSection>
        <DialogSection title="Details">
        <div>
          <Label htmlFor="me-desc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="me-desc" placeholder="What is this model for?" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
        </div>
        <div>
          <Label htmlFor="me-ctx" required>Context window</Label>
          <Input id="me-ctx" type="number" required min={1} step={1} inputMode="numeric" value={contextWindow} aria-invalid={!!form.error("ctx")} onChange={(e) => setContextWindow(e.target.value)} onBlur={() => form.touch("ctx")} className="sm:max-w-[12rem]" />
          <FieldError>{form.error("ctx")}</FieldError>
        </div>
        <CapabilityChecks value={caps} onChange={setCaps} />
        </DialogSection>
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
      tone="info"
      footer={
        <div className="flex justify-end">
          <Button size="sm" onClick={onClose}><Check size={14} strokeWidth={2} /> Done</Button>
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
