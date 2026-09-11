"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Lock, ShieldCheck } from "lucide-react";
import { AboutDialog } from "@/components/shell/about-dialog";
import { CommandPalette } from "@/components/shell/command-palette";
import { PermissionsBanner } from "@/components/shell/permissions-banner";
import { TopBar } from "@/components/shell/top-bar";
import { Button } from "@/components/ui/button";
import { SectionHeader } from "@/components/ui/section-header";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import { FullPageLoader } from "@/components/ui/full-page-loader";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { useRoles, useSetRoleRights } from "@/hooks/use-roles";
import { usePermissions } from "@/hooks/use-permissions";
import { companyScope } from "@/lib/permissions";
import type { RightDef, RoleDef } from "@/lib/api/roles";
import { useConnectionStore } from "@/stores/connection.store";

// Readable headings for the object_type the server groups rights by. An
// unmapped one falls back to its own name rather than being hidden, so a new
// object type shows up here the day it is added server-side.
const GROUP_LABELS: Record<string, string> = {
  company: "Company",
  project: "Project",
  channel: "Channel",
  topic: "Topic",
  session: "Chat session",
  persona: "Personas",
  mcp_server: "MCP servers",
  model_config: "Model configs",
  schedule: "Schedules",
};

// Only the EDITS are state; what a role currently grants stays the server's
// answer. Deriving rather than copying the payload into state means there is
// no effect syncing the two, nothing to go stale after a save, and no window
// where the screen shows a set the server never had.
type Edits = Record<string, Set<string>>; // role id -> the set the user wants

export default function PermissionsPage() {
  const router = useRouter();
  const { token, serverUrl, hydrated } = useConnectionStore();
  const { can, loading: permsLoading } = usePermissions();
  const mayEdit = can("role.update", companyScope());

  const [about, setAbout] = useState(false);
  const { data, isLoading, error, refetch } = useRoles();
  const save = useSetRoleRights();
  const [edits, setEdits] = useState<Edits>({});

  useEffect(() => {
    if (!hydrated) return;
    if (!token) router.replace("/login");
    else if (!serverUrl) router.replace("/servers");
  }, [hydrated, token, serverUrl, router]);

  // Anyone without the right has no business here, and the server refuses them
  // anyway — send them back rather than render a screen of denials.
  useEffect(() => {
    if (!hydrated || permsLoading || !token || !serverUrl) return;
    if (!mayEdit) router.replace("/w");
  }, [hydrated, permsLoading, mayEdit, token, serverUrl, router]);

  const grouped = useMemo(() => {
    const by = new Map<string, RightDef[]>();
    for (const r of data?.rights ?? []) {
      if (!by.has(r.object_type)) by.set(r.object_type, []);
      by.get(r.object_type)!.push(r);
    }
    return [...by.entries()];
  }, [data]);

  // What each role would grant if saved: the user's edit if they made one,
  // otherwise exactly what the server says.
  const wanted = useMemo(() => {
    const out: Edits = {};
    for (const role of data?.roles ?? []) out[role.id] = edits[role.id] ?? new Set(role.rights);
    return out;
  }, [data, edits]);

  const dirty = useMemo(() => {
    if (!data) return [];
    return data.roles.filter((role) => {
      const next = wanted[role.id];
      return next.size !== role.rights.length || role.rights.some((c) => !next.has(c));
    });
  }, [data, wanted]);

  const showLoading = useDelayedLoading(isLoading);

  if (!hydrated || !token || !serverUrl || permsLoading || !mayEdit) {
    return <FullPageLoader />;
  }

  const toggle = (role: RoleDef, code: string) => {
    setEdits((e) => {
      const next = new Set(e[role.id] ?? role.rights);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return { ...e, [role.id]: next };
    });
  };

  const saveAll = async () => {
    const changed = dirty;
    await Promise.allSettled(
      changed.map((role) => save.mutateAsync({ roleId: role.id, rights: [...wanted[role.id]] })),
    );
    // Drop the edits for what was saved; the refetched payload is the answer
    // from here. A role that failed keeps its edit so it is not silently lost.
    setEdits((e) => {
      const rest = { ...e };
      changed.forEach((role) => delete rest[role.id]);
      return rest;
    });
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <TopBar onAbout={() => setAbout(true)} />
      <PermissionsBanner />
      <main className="nx-ambient min-w-0 flex-1 overflow-y-auto p-4 lg:px-6 lg:py-5">
        <div className="mx-auto max-w-5xl">
          <SectionHeader
            title="Rights and roles"
            blurb="What each role may do. A change takes effect for everyone holding that role, immediately."
            actions={
              <div className="flex items-center gap-2">
                {dirty.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setEdits({})}
                    className="cursor-pointer text-[12.5px] text-ink2 hover:text-ink"
                  >
                    Discard
                  </button>
                )}
                <Button
                  size="sm"
                  variant="primary"
                  disabled={dirty.length === 0 || save.isPending}
                  loading={save.isPending}
                  onClick={() => void saveAll()}
                >
                  <Check size={14} strokeWidth={2} />
                  {dirty.length === 0
                    ? "Saved"
                    : `Save ${dirty.length} role${dirty.length === 1 ? "" : "s"}`}
                </Button>
              </div>
            }
          />

          {showLoading && (
            <div className="mt-4 flex flex-col gap-2" role="status" aria-label="Loading roles">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}
            </div>
          )}

          {error && !showLoading && (
            <EmptyState
              title="Couldn't load roles"
              hint={error.message}
              action={<Button size="sm" onClick={() => refetch()}>Try again</Button>}
            />
          )}

          {!showLoading && !error && data && (
            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[640px] border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-line bg-surface2/50 text-left">
                    <th scope="col" className="px-3 py-2 font-mono text-[10.5px] uppercase tracking-wide text-ink2">Right</th>
                    <th scope="col" className="px-3 py-2 font-mono text-[10.5px] uppercase tracking-wide text-ink2">Scope</th>
                    {data.roles.map((role) => (
                      <th key={role.id} scope="col" className="px-3 py-2 text-center font-mono text-[10.5px] uppercase tracking-wide text-ink2">
                        {role.name}
                        {!role.editable && (
                          <span title="The Owner always holds every right" className="ml-1 inline-flex align-middle text-ink2/70">
                            <Lock size={10} strokeWidth={2.4} />
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grouped.map(([objectType, rights]) => (
                    <RightGroup
                      key={objectType}
                      label={GROUP_LABELS[objectType] ?? objectType}
                      rights={rights}
                      roles={data.roles}
                      wanted={wanted}
                      onToggle={toggle}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="mt-3 flex items-start gap-1.5 text-[12px] leading-relaxed text-ink2">
            <ShieldCheck size={13} strokeWidth={2} className="mt-[2px] flex-none" />
            Scope is the narrowest level a right can be granted at — a role held on one project
            still can&apos;t use a company-scoped right. Hiding a control is never the security
            boundary; the server checks every action regardless.
          </p>
        </div>
      </main>
      <AboutDialog open={about} onClose={() => setAbout(false)} />
      <CommandPalette onAbout={() => setAbout(true)} />
    </div>
  );
}

function RightGroup({ label, rights, roles, wanted, onToggle }: {
  label: string;
  rights: RightDef[];
  roles: RoleDef[];
  wanted: Edits;
  onToggle: (role: RoleDef, code: string) => void;
}) {
  return (
    <>
      <tr className="border-b border-line bg-surface2/30">
        <th scope="colgroup" colSpan={2 + roles.length} className="px-3 py-1.5 text-left font-mono text-[10.5px] uppercase tracking-wide text-ink2">
          {label}
        </th>
      </tr>
      {rights.map((right) => (
        <tr key={right.code} className="border-b border-line last:border-b-0 hover:bg-surface2/30">
          <td className="px-3 py-2 font-mono text-[12.5px]" title={right.description}>{right.code}</td>
          <td className="px-3 py-2 font-mono text-[11.5px] text-ink2">{right.scope}</td>
          {roles.map((role) => (
            <RightCell key={role.id} role={role} right={right} wanted={wanted} onToggle={onToggle} />
          ))}
        </tr>
      ))}
    </>
  );
}

function RightCell({ role, right, wanted, onToggle }: {
  role: RoleDef;
  right: RightDef;
  wanted: Edits;
  onToggle: (role: RoleDef, code: string) => void;
}) {
  const held = wanted[role.id]?.has(right.code) ?? false;
  // Locked only blocks GRANTING — a role that somehow holds one can still have
  // it taken away, which is what the server allows too.
  const lockedByRule = role.locked_rights.includes(right.code) && !held;
  const disabled = !role.editable || lockedByRule;
  const why = !role.editable
    ? `${role.name} always holds every right`
    : lockedByRule
      ? `Managing members stays with Owner and Admin, so ${role.name} can't be given ${right.code}`
      : undefined;

  return (
    <td className="px-3 py-2 text-center">
      <input
        type="checkbox"
        checked={held}
        disabled={disabled}
        onChange={() => onToggle(role, right.code)}
        title={why}
        aria-label={`${right.code} for ${role.name}`}
        className="size-[15px] cursor-pointer accent-accent disabled:cursor-not-allowed disabled:opacity-40"
      />
    </td>
  );
}
