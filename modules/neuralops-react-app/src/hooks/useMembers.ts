import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getMembers, inviteMember, removeMember } from "@/services/members.service";

export function useMembers() {
  return useQuery({ queryKey: ["members"], queryFn: getMembers });
}

export function useInviteMember(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: inviteMember,
    onSuccess: () => {
      toast.success("Invitation sent successfully");
      qc.invalidateQueries({ queryKey: ["members"] });
      onSuccess?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeMember,
    onSuccess: () => {
      toast.success("Member removed");
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
