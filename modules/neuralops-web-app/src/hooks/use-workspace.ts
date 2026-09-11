"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { listMembers } from "@/lib/api/members";
import * as ws from "@/lib/api/workspace";
import { useConnectionStore } from "@/stores/connection.store";

export function useProjects() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return useQuery({ queryKey: ["projects", serverUrl], queryFn: ws.listProjects, enabled: !!serverUrl && !!token });
}

export function useTopics(projectId?: string, channelId?: string) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return useQuery({
    queryKey: ["topics", serverUrl, projectId, channelId],
    queryFn: () => ws.listTopics(projectId!, channelId!),
    enabled: !!serverUrl && !!token && !!projectId && !!channelId,
    refetchInterval: 30_000, // unread dots for closed topics (no user-level realtime channel exists)
    refetchOnWindowFocus: true,
  });
}

export function useMembers() {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return useQuery({ queryKey: ["members", serverUrl], queryFn: listMembers, enabled: !!serverUrl && !!token, staleTime: 300_000 });
}

function useInvalidate() {
  const qc = useQueryClient();
  return {
    projects: () => qc.invalidateQueries({ queryKey: ["projects"] }),
    topics: () => qc.invalidateQueries({ queryKey: ["topics"] }),
    // The rights payload is KEYED BY OBJECT ID, so creating a project or a
    // topic makes it stale in a way no other query is: the new id simply is
    // not in it, and every control scoped to that object reads as denied until
    // it is refetched. Awaited by the callers below so the object is never
    // handed to the UI before the rights that govern it.
    permissions: () => qc.invalidateQueries({ queryKey: ["permissions"] }),
  };
}

export function useCreateProject(onDone?: (p: ws.Project) => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) => ws.createProject(name, description),
    onSuccess: async (p) => {
      toast.success(`Project "${p.name}" created`);
      inv.projects();
      // Rights first: the new project's id is not in the cached payload, so
      // navigating before this lands shows the project with every control
      // denied. Awaited, not fired and forgotten.
      await inv.permissions();
      onDone?.(p);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useCreateChannel(projectId: string, onDone?: (c: ws.Channel) => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) => ws.createChannel(projectId, name, description),
    onSuccess: async (c) => {
      toast.success(`Channel "${c.name}" created`);
      inv.projects();
      await inv.permissions();
      onDone?.(c);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useCreateTopic(projectId?: string, channelId?: string, onDone?: (t: ws.Topic) => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (existingTitles: string[]) => ws.createTopic(projectId!, channelId!, ws.nextTopicTitle(existingTitles)),
    onSuccess: async (t) => {
      inv.topics();
      // The new topic's id keys the rights payload too, so without this every
      // topic-scoped control (rename, archive, @mention, session, schedule)
      // reads as denied in the chat we are about to open.
      await inv.permissions();
      onDone?.(t);
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useMarkTopicRead() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ projectId, channelId, topicId }: { projectId: string; channelId: string; topicId: string }) =>
      ws.markTopicRead(projectId, channelId, topicId),
    onSuccess: () => inv.topics(),
    // Background bookkeeping — a toast per topic-open would be noise. Retry
    // through transient blips instead; a persistent failure just leaves the
    // unread badge until the next visit.
    retry: 2,
  });
}

// Archive = soft-delete. Server checks the *.archive right per object; a 403
// surfaces as a toast rather than being pre-hidden for members.
export function useArchiveProject(onDone?: () => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (projectId: string) => ws.archiveProject(projectId),
    onSuccess: (r) => {
      toast.success(r.message || "Project archived.");
      inv.projects();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useArchiveChannel(projectId: string, onDone?: () => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (channelId: string) => ws.archiveChannel(projectId, channelId),
    onSuccess: (r) => {
      toast.success(r.message || "Channel archived.");
      inv.projects();
      inv.topics();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useArchiveTopic(projectId?: string, channelId?: string, onDone?: () => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (topicId: string) => ws.archiveTopic(projectId!, channelId!, topicId),
    onSuccess: (r) => {
      toast.success(r.message || "Chat archived.");
      inv.topics();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}
