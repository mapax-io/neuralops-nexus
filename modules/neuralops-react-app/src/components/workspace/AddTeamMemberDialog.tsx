import { useState } from "react";
import { Bot, User, Search, Plus, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
  useAddTeamMember,
  useAvailableUsers,
  useAvailablePersonas,
} from "@/hooks/useWorkspace";
import { inviteToProject } from "@/services/workspace.service";

type Tab = "human" | "persona";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: string;
}

export function AddTeamMemberDialog({ open, onOpenChange, projectId }: Props) {
  const [tab, setTab] = useState<Tab>("human");
  const [search, setSearch] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);

  const addMember = useAddTeamMember(projectId, () => onOpenChange(false));

  const { data: users, isLoading: usersLoading } = useAvailableUsers(
    projectId,
    search,
  );
  const { data: personas, isLoading: personasLoading } =
    useAvailablePersonas(projectId);

  function handleAdd(userId: string) {
    addMember.mutate({ user_id: userId, role: "member" });
  }

  async function handleInviteByEmail() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await inviteToProject(projectId, {
        email: inviteEmail.trim(),
        scope: "project",
        role: "member",
      });
      toast.success(`Invite sent to ${inviteEmail.trim()}`);
      setInviteEmail("");
      onOpenChange(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to send invite";
      toast.error(msg);
    } finally {
      setInviting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add to Team</DialogTitle>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex gap-1 rounded-md border border-border bg-muted p-1">
          {(["human", "persona"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t === "human" ? (
                <User className="h-3.5 w-3.5" />
              ) : (
                <Bot className="h-3.5 w-3.5" />
              )}
              {t === "human" ? "Add Human" : "Add Persona"}
            </button>
          ))}
        </div>

        {/* Human tab */}
        {tab === "human" && (
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by name or email..."
                className="pl-8"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <MemberList
              loading={usersLoading}
              empty="All workspace members are already in this project."
              items={users?.map((u) => ({
                id: u.user_id,
                name: u.name,
                subtitle: u.email,
                avatar: u.avatar,
                type: "human" as const,
              }))}
              onAdd={handleAdd}
              adding={addMember.isPending}
            />

            {/* Divider */}
            <div className="flex items-center gap-2 pt-1">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs text-muted-foreground">or invite by email</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            {/* Email invite */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Mail className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="email@example.com"
                  type="email"
                  className="pl-8"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleInviteByEmail()}
                />
              </div>
              <Button
                size="sm"
                disabled={!inviteEmail.trim() || inviting}
                onClick={handleInviteByEmail}
              >
                {inviting ? "Sending…" : "Send Invite"}
              </Button>
            </div>
          </div>
        )}

        {/* Persona tab */}
        {tab === "persona" && (
          <MemberList
            loading={personasLoading}
            empty="All personas are already in this project."
            items={personas?.map((p) => ({
              id: p.user_id,
              name: p.name,
              subtitle: p.source_type === "agent" ? "Agent" : "Model",
              avatar: p.avatar,
              type: "persona" as const,
            }))}
            onAdd={handleAdd}
            adding={addMember.isPending}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function MemberList({
  loading,
  empty,
  items,
  onAdd,
  adding,
}: {
  loading: boolean;
  empty: string;
  items?: { id: string; name: string; subtitle: string; avatar: string | null; type: "human" | "persona" }[];
  onAdd: (id: string) => void;
  adding: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>
    );
  }

  return (
    <div className="max-h-64 space-y-1 overflow-y-auto">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-muted"
        >
          <Avatar name={item.name} avatar={item.avatar} type={item.type} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-foreground">
              {item.name}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {item.subtitle}
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            disabled={adding}
            onClick={() => onAdd(item.id)}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
    </div>
  );
}

function Avatar({
  name,
  avatar,
  type,
}: {
  name: string;
  avatar: string | null;
  type: "human" | "persona";
}) {
  if (avatar) {
    return (
      <img
        src={avatar}
        alt={name}
        className="h-8 w-8 rounded-full object-cover"
      />
    );
  }
  return (
    <div
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
        type === "persona"
          ? "bg-accent text-accent-foreground"
          : "bg-primary-tint text-primary"
      }`}
    >
      {type === "persona" ? (
        <Bot className="h-4 w-4" />
      ) : (
        name.slice(0, 1).toUpperCase()
      )}
    </div>
  );
}
