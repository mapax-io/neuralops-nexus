"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, ServerCog } from "lucide-react";
import { toast } from "sonner";
import { validateName as vName } from "@/lib/validation";
import { Constellation } from "@/components/brand/constellation";
import { Nebula } from "@/components/brand/nebula";
import { Wordmark } from "@/components/brand/wordmark";
import { ServerChooser, type ChooserEntry } from "@/components/servers/server-chooser";
import { InsecureContextNotice } from "@/components/security/insecure-context-notice";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { FullPageLoader } from "@/components/ui/full-page-loader";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { connectToServer, fetchServerConfig, type ServerConfig } from "@/lib/api/servers";
import { clearAccountScopedState } from "@/lib/auth/session-cleanup";
import { pullServers, pushServersDebounced } from "@/lib/servers-sync";
import { supabase } from "@/lib/supabase";
import { compareServerVersion } from "@/lib/version";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelectionStore } from "@/stores/selection.store";
import { useServersStore, type SavedServer } from "@/stores/servers.store";

export default function ServersPage() {
  const router = useRouter();
  const { token, email, hydrated } = useConnectionStore();
  const { servers, removed, add, remove, touch } = useServersStore();
  const [configs, setConfigs] = useState<Record<string, ServerConfig | null>>({});
  const [connecting, setConnecting] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<SavedServer | null>(null);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const [syncing, setSyncing] = useState(true);
  // Always visible for a beat (delay 0, min 400ms): the list either appears
  // once, settled — or the empty CTA appears once. Never empty→list pop.
  const showSync = useDelayedLoading(syncing, { delay: 0, minDuration: 400 });

  useEffect(() => {
    if (hydrated && !token) router.replace("/login");
  }, [hydrated, token, router]);

  // Account-level server list: pull once when signed in, mirror every change.
  useEffect(() => {
    if (!hydrated || !token) return;
    void pullServers().finally(() => {
      setSyncing(false);
      // Close the add-during-pull race: a server added while the pull was in
      // flight was gated off the mirror; mirror the merged state now.
      const s = useServersStore.getState();
      if (s.servers.length || Object.keys(s.removed).length) pushServersDebounced(s.servers, s.removed);
    });
  }, [hydrated, token]);
  useEffect(() => {
    if (token) pushServersDebounced(servers, removed);
  }, [token, servers, removed]);

  useEffect(() => {
    servers.forEach((s) => {
      if (!(s.id in configs)) {
        fetchServerConfig(s.url).then((cfg) => setConfigs((c) => ({ ...c, [s.id]: cfg })));
      }
    });
  }, [servers, configs]);

  const connect = async (s: SavedServer) => {
    if (!token) return;
    setErrors((e) => ({ ...e, [s.id]: "" }));
    if (compareServerVersion(configs[s.id]?.server_version) === "breaking") return;
    setConnecting(s.id);
    const out = await connectToServer(s.url, token);
    setConnecting(null);
    switch (out.kind) {
      case "ok": {
        // The card's pre-fetched config can be missing (endpoint blocked,
        // transient outage) — the verify response is the authority, and a
        // BREAKING server must be blocked here too, not only at listing time.
        if (compareServerVersion(out.connection.serverVersion) === "breaking") {
          setErrors((e) => ({
            ...e,
            [s.id]: `This server runs v${out.connection.serverVersion}, which this app can't talk to. Update the server, then come back.`,
          }));
          return;
        }
        touch(s.id);
        useConnectionStore.getState().connect(out.connection);
        if (compareServerVersion(out.connection.serverVersion) === "minor")
          toast.warning("Server version differs slightly from this app — consider updating the server.");
        router.push("/w");
        return;
      }
      case "not-member":
        setErrors((e) => ({ ...e, [s.id]: "You're not a member of this server. Ask the owner to invite you — they need your sign-in email." }));
        return;
      case "not-set-up":
        setErrors((e) => ({ ...e, [s.id]: "This server isn't set up yet — its owner still needs to run the setup command on it." }));
        return;
      case "unreachable":
        setErrors((e) => ({
          ...e,
          [s.id]:
            "Could not reach the server. Check the address and that it's running. On a private network (Tailscale/LAN), open the server URL directly in a tab once, then retry.",
        }));
        return;
      case "error":
        setErrors((e) => ({ ...e, [s.id]: out.message }));
    }
  };

  const signOut = async () => {
    clearAccountScopedState(); // one shared cleanup — stores, drafts, query cache, realtime
    try {
      await supabase().auth.signOut();
    } catch {
      /* local state is cleared regardless — the session dies on this device */
    }
    router.replace("/login");
  };

  const entries: ChooserEntry[] = servers.map((s) => ({
    server: s,
    config: configs[s.id],
    checking: !(s.id in configs),
    connecting: connecting === s.id,
    error: errors[s.id],
  }));

  const firstName = (email ?? "").split("@")[0].replace(/[._-]+/g, " ").replace(/\d+$/, "").trim();

  // Same guard as every other protected page: nothing of the launcher —
  // greeting, email, saved servers — renders before the session is known.
  if (!hydrated || !token) {
    return (
      <FullPageLoader />
    );
  }

  return (
    <div className="grid min-h-screen bg-bg lg:grid-cols-[1fr_1.35fr]">
      {/* Brand panel — same visual system as sign-in. */}
      <div className="relative hidden overflow-hidden border-r border-line bg-bg2 lg:block">
        <Nebula />
        <Constellation />
        <div className="relative flex h-full flex-col p-10">
          <Link href="/servers" aria-label="Your servers"><Wordmark className="text-[19px]" /></Link>
          <div className="flex-1" />
          <blockquote className="max-w-md">
            <p className="font-display text-[30px] font-extrabold leading-tight">
              Every server is its own world —<br />
              <em className="bg-gradient-to-r from-accent to-live bg-clip-text not-italic text-transparent">private, sovereign, yours.</em>
            </p>
            <p className="mt-4 text-[14px] text-ink2">
              Conversations, personas, and knowledge never leave the server they live on.
            </p>
          </blockquote>
          <div className="flex-1" />
          <p className="font-mono text-[11.5px] text-ink2">humans ∙ personas ∙ one conversation</p>
        </div>
      </div>

      {/* Launcher */}
      <div className="relative flex min-w-0 flex-col px-6 py-6 sm:px-10 lg:px-14">
        <div className="flex items-center gap-1">
          <Link href="/servers" className="lg:hidden" aria-label="Your servers"><Wordmark className="text-[17px]" /></Link>
          <span className="flex-1" />
          <ThemeToggle />
          <Button size="sm" variant="ghost" onClick={() => setConfirmingSignOut(true)}>
            <LogOut size={14} strokeWidth={2} /> Sign out
          </Button>
        </div>

        <div className="flex flex-1 flex-col justify-center py-10">
          <div className="mx-auto w-full max-w-2xl">
            <p className="font-mono text-[11.5px] font-semibold uppercase tracking-[.16em] text-accent">
              Welcome back{firstName ? `, ${firstName}` : ""}
            </p>
            <h1 className="mt-2 font-display text-[28px] font-extrabold">Where are you working today?</h1>
            <p className="mb-7 mt-1.5 text-[14px] text-ink2">Signed in as {email}</p>

            <InsecureContextNotice className="mb-5" />
            <ServerChooser entries={entries} loading={syncing || showSync} onConnect={connect} onRemove={setRemoving} onAdd={() => setAdding(true)} />

            <p className="mt-5 text-center text-[12.5px] text-ink2">
              A server is a self-hosted NeuralOps deployment — yours, your team&apos;s, or a client&apos;s.
            </p>
          </div>
        </div>

        <footer className="pb-2 pt-6 text-center text-[12px] text-ink2">
          © 2026 NeuralOps, Inc. · Free software under AGPL-3.0
        </footer>
      </div>

      <AddServerDialog
        open={adding}
        onClose={() => setAdding(false)}
        onAdd={(name, url) => {
          try {
            add(name, url);
            setAdding(false);
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not add server.");
          }
        }}
      />

      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) {
            remove(removing.id);
            useSelectionStore.getState().clearSelection(removing.url); // no workspace ids left behind
          }
          setRemoving(null);
        }}
        title="Remove server?"
        body={
          <p>
            Remove <b className="text-ink">{removing?.name}</b> from your list? This only forgets it on this
            device — nothing on the server is touched, and you can add it back anytime.
          </p>
        }
        confirmLabel="Remove"
        cancelLabel="Keep it"
      />

      <ConfirmDialog
        open={confirmingSignOut}
        onClose={() => setConfirmingSignOut(false)}
        onConfirm={() => {
          setConfirmingSignOut(false);
          void signOut();
        }}
        title="Sign out?"
        body={<p>You&apos;ll be signed out on this device. Your saved servers stay with your account — they&apos;ll be back when you sign in again.</p>}
        confirmLabel="Sign out"
        tone="neutral"
      />
    </div>
  );
}

// Forgiving address validation: auto-prepends http:// when the scheme is
// missing, rejects non-http(s) schemes, requires a host, strips paths.
export function normalizeServerAddress(raw: string): { url: string } | { error: string } {
  let input = raw.trim();
  if (!input) return { error: "Enter the server's address." };
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(input)) input = `http://${input}`;
  let parsed: URL;
  try {
    parsed = new URL(input);
  } catch {
    return { error: "That doesn't look like a valid address — try something like http://192.168.1.90:8096" };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { error: "Only http:// and https:// servers are supported." };
  }
  if (!parsed.hostname) return { error: "The address needs a host — an IP or a domain." };
  if (parsed.username || parsed.password) return { error: "Don't put credentials in the address." };
  if ((parsed.pathname !== "/" && parsed.pathname !== "") || parsed.search || parsed.hash) {
    return { error: "Use just the server's base address — no path after the port." };
  }
  return { url: parsed.origin };
}

function AddServerDialog({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (name: string, url: string) => void }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [urlErr, setUrlErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const validateName = (v: string) => vName(v, { label: "server name", max: 40 });
  const validateUrl = (v: string) => {
    const out = normalizeServerAddress(v);
    return "error" in out ? out.error : null;
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    const ne = validateName(name);
    const ue = validateUrl(url);
    setNameErr(ne);
    setUrlErr(ue);
    if (ne || ue) return;
    const normalized = normalizeServerAddress(url) as { url: string };
    onAdd(name.trim(), normalized.url);
    setName("");
    setUrl("");
    setTouched(false);
    setNameErr(null);
    setUrlErr(null);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a server"
      description="Point the app at a self-hosted NeuralOps deployment — yours, your team's, or a client's."
      icon={<ServerCog size={17} strokeWidth={2} />}
      footer={<Button type="submit" form="sv-form" variant="primary" className="w-full">Add server</Button>}
    >
      <form id="sv-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="sname" required>Name</Label>
          <Input
            id="sname"
            required
            autoFocus
            placeholder="e.g. Office, Home lab"
            value={name}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validateName(e.target.value));
            }}
            onBlur={() => {
              setTouched(true);
              setNameErr(validateName(name));
            }}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
        <div>
          <Label htmlFor="surl" required>Address</Label>
          <Input
            id="surl"
            required
            inputMode="url"
            placeholder="http://192.168.1.90:8096"
            value={url}
            aria-invalid={!!urlErr}
            onChange={(e) => {
              setUrl(e.target.value);
              if (touched) setUrlErr(validateUrl(e.target.value));
            }}
            onBlur={() => {
              setTouched(true);
              setUrlErr(validateUrl(url));
            }}
          />
          {urlErr ? (
            <FieldError>{urlErr}</FieldError>
          ) : (
            <p className="mt-1.5 text-[12px] text-ink2">A LAN IP, Tailscale address, or domain — http:// is assumed if you skip it.</p>
          )}
        </div>
      </form>
    </Dialog>
  );
}
