import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getProjects,
  createProject,
  getTopics,
  createChannel,
  createTopic,
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
