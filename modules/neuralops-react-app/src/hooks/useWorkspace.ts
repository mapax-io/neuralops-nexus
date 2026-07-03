import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getProjects,
  createProject,
  getTopics,
  createChannel,
  createTopic,
  getTeam,
  addTeamMember,
  removeTeamMember,
  getAvailableUsers,
  getAvailablePersonas,
} from "@/services/workspace.service";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: getProjects });
}

export function useCreateProject(onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      toast.success("Project created");
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSuccess?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useTopics(projectId: string, channelId: string) {
  return useQuery({
    queryKey: ["topics", projectId, channelId],
    queryFn: () => getTopics(projectId, channelId),
    enabled: !!projectId && !!channelId,
  });
}

export function useCreateChannel(projectId: string, onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      createChannel(projectId, payload),
    onSuccess: () => {
      toast.success("Channel created");
      qc.invalidateQueries({ queryKey: ["projects"] });
      onSuccess?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useCreateTopic(
  projectId: string,
  channelId: string,
  onSuccess?: () => void,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { title: string }) =>
      createTopic(projectId, channelId, payload),
    onSuccess: () => {
      toast.success("Topic created");
      qc.invalidateQueries({ queryKey: ["topics", projectId, channelId] });
      onSuccess?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

// ── Team hooks ───────────────────────────────────────────────────────────────────

export function useTeam(projectId: string) {
  return useQuery({
    queryKey: ["team", projectId],
    queryFn: () => getTeam(projectId),
    enabled: !!projectId,
  });
}

export function useAddTeamMember(projectId: string, onSuccess?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { user_id: string; role?: string }) =>
      addTeamMember(projectId, payload),
    onSuccess: () => {
      toast.success("Member added");
      qc.invalidateQueries({ queryKey: ["team", projectId] });
      onSuccess?.();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useRemoveTeamMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeTeamMember(projectId, userId),
    onSuccess: () => {
      toast.success("Member removed");
      qc.invalidateQueries({ queryKey: ["team", projectId] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useAvailableUsers(projectId: string, search = "") {
  return useQuery({
    queryKey: ["available-users", projectId, search],
    queryFn: () => getAvailableUsers(projectId, search),
    enabled: !!projectId,
  });
}

export function useAvailablePersonas(projectId: string) {
  return useQuery({
    queryKey: ["available-personas", projectId],
    queryFn: () => getAvailablePersonas(projectId),
    enabled: !!projectId,
  });
}
