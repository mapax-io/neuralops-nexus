import { apiJson } from "./client";

export interface Schedule {
  id: string;
  topic_id: string;
  persona_id: string;
  persona_name: string;
  query_text: string;
  label: string;
  schedule_kind: "interval" | "crontab" | "clocked";
  schedule_summary: string; // human-readable, server-built
  timezone: string;
  trigger_visible: boolean;
  catch_up_missed: boolean;
  is_paused: boolean;
  created_by_id: string | null;
  last_run_at: string | null;
  last_status: string;
  last_error: string | null;
}

const base = (pid: string, cid: string, tid: string) =>
  `/api/v1/projects/${pid}/channels/${cid}/topics/${tid}/schedules/`;

export const listSchedules = (pid: string, cid: string, tid: string) => apiJson<Schedule[]>(base(pid, cid, tid));

export interface ScheduleCreate {
  persona_id: string;
  query_text: string;
  label?: string;
  schedule_kind: "interval" | "crontab" | "clocked";
  interval_every?: number;
  interval_period?: "minutes" | "hours" | "days" | "weeks";
  crontab_minute?: string;
  crontab_hour?: string;
  crontab_day_of_week?: string;   // "1,3,5" — cron numbering, 0 = Sunday
  crontab_day_of_month?: string;  // "15"
  crontab_month_of_year?: string;
  clocked_time?: string; // ISO 8601, one-time fire
  timezone?: string;
  trigger_visible?: boolean; // post a visible "Scheduled: …" message before the run (server default true)
  catch_up_missed?: boolean; // a run missed while the server was down fires once on restart (server default true)
}

export const createSchedule = (pid: string, cid: string, tid: string, payload: ScheduleCreate) =>
  apiJson<Schedule>(base(pid, cid, tid), { method: "POST", body: JSON.stringify(payload) });

export const updateSchedule = (pid: string, cid: string, tid: string, scheduleId: string, patch: { is_paused?: boolean; label?: string; query_text?: string }) =>
  apiJson<Schedule>(`${base(pid, cid, tid)}${scheduleId}/`, { method: "PATCH", body: JSON.stringify(patch) });

export const deleteSchedule = (pid: string, cid: string, tid: string, scheduleId: string) =>
  apiJson<undefined>(`${base(pid, cid, tid)}${scheduleId}/`, { method: "DELETE" });
