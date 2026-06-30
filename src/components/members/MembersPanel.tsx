import { useState } from "react";
import { Trash2, UserPlus, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useMembers, useRemoveMember } from "@/hooks/useMembers";
import type { Member } from "@/services/members.service";
import { InviteDialog } from "./InviteDialog";

const ROLE_BADGE: Record<Member["role"], string> = {
  owner: "bg-violet-100 text-violet-700",
  admin: "bg-blue-100 text-blue-700",
  member: "bg-emerald-100 text-emerald-700",
  viewer: "bg-muted text-muted-foreground",
};

function initials(email: string) {
  const name = email.split("@")[0] ?? email;
  return name.slice(0, 2).toUpperCase();
}

function formatJoined(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function MembersPanel() {
  const [inviteOpen, setInviteOpen] = useState(false);
  const { data: members, isLoading } = useMembers();
  const removeMutation = useRemoveMember();
  const currentUserId = useAuthStore((s) => s.userId);

  return (
    <div className="rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Members</h2>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setInviteOpen(true)}
          className="border-primary/30 text-primary hover:bg-primary/5 hover:text-primary"
        >
          <UserPlus />
          Invite
        </Button>
      </div>

      <div className="divide-y">
        {isLoading && (
          <>
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-3 w-24" />
                </div>
                <Skeleton className="h-6 w-16 rounded-md" />
              </div>
            ))}
          </>
        )}

        {!isLoading && members && members.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            No members yet. Send an invite to get started.
          </div>
        )}

        {!isLoading &&
          members?.map((m) => {
            const isSelf = currentUserId === m.user_id;
            const canRemove = !isSelf && m.role !== "owner";
            return (
              <div
                key={m.user_id}
                className="flex items-center gap-3 px-4 py-3"
              >
                <Avatar className="h-9 w-9">
                  <AvatarFallback className="text-xs font-medium">
                    {initials(m.email)}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{m.email}</div>
                  <div className="text-xs text-muted-foreground">
                    Joined {formatJoined(m.joined_at)}
                  </div>
                </div>
                <span
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs font-medium capitalize",
                    ROLE_BADGE[m.role],
                  )}
                >
                  {m.role}
                </span>
                {canRemove && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`Remove ${m.email}`}
                      >
                        <Trash2 />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Remove {m.email}?</AlertDialogTitle>
                        <AlertDialogDescription>
                          They will lose access immediately.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => removeMutation.mutate(m.user_id)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          Remove
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </div>
            );
          })}
      </div>

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
    </div>
  );
}

export default MembersPanel;
