"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as api from "@/lib/api/schedules";
import { useConnectionStore } from "@/stores/connection.store";

export function useSchedules(pid?: string, cid?: string, tid?: string) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  return useQuery({
    queryKey: ["schedules", serverUrl, tid],
    queryFn: () => api.listSchedules(pid!, cid!, tid!),
    enabled: !!serverUrl && !!token && !!pid && !!cid && !!tid,
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["schedules"] });
}

export function useCreateSchedule(pid: string, cid: string, tid: string, onDone?: () => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (payload: api.ScheduleCreate) => api.createSchedule(pid, cid, tid, payload),
    onSuccess: (s) => {
      toast.success(`Scheduled: @${s.persona_name} — ${s.schedule_summary}`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useToggleSchedule(pid: string, cid: string, tid: string) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, pause }: { id: string; pause: boolean }) => api.updateSchedule(pid, cid, tid, id, { is_paused: pause }),
    onSuccess: (s) => {
      toast.success(s.is_paused ? "Schedule paused." : "Schedule resumed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}

// The server's PATCH takes query_text and label (plus is_paused, handled by
// useToggleSchedule); the clock itself is not editable — recreate for that.
export function useEditSchedule(pid: string, cid: string, tid: string, onDone?: () => void) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { query_text?: string; label?: string } }) => api.updateSchedule(pid, cid, tid, id, patch),
    onSuccess: (s) => {
      toast.success(`Schedule for @${s.persona_name} updated.`);
      inv();
      onDone?.();
    },
    onError: (e) => toast.error(e.message),
  });
}

export function useDeleteSchedule(pid: string, cid: string, tid: string) {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => api.deleteSchedule(pid, cid, tid, id),
    onSuccess: () => {
      toast.success("Schedule removed.");
      inv();
    },
    onError: (e) => toast.error(e.message),
  });
}
