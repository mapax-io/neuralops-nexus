"use client";

import { useState } from "react";
import { CalendarClock, Pause, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName } from "@/lib/validation";
import { SectionHeader } from "@/components/ui/section-header";
import { Skeleton } from "@/components/ui/surfaces";
import { usePersonas } from "@/hooks/use-intelligence";
import { useCreateSchedule, useDeleteSchedule, useEditSchedule, useSchedules, useToggleSchedule } from "@/hooks/use-schedules";
import type { Schedule } from "@/lib/api/schedules";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";

// The Schedules tab: recurring persona runs in THIS chat, executed by the
// server (celery-beat) whether anyone is online or not.
export function SchedulesPanel({ pid, cid, tid }: { pid: string; cid: string; tid: string }) {
  const { data: schedules, isLoading, error, refetch } = useSchedules(pid, cid, tid);
  const role = useConnectionStore((s) => s.connection?.role);
  const selfId = useConnectionStore((s) => s.connection?.nucleusUserId);
  // schedule.manage is Admin-tier and project-reachable.
  const canManage = isCompanyAdmin(role);
  // schedule.create rides the PROJECT tier now (DECISIONS §23).
  const canCreate = role !== "viewer";
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<Schedule | null>(null);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const toggle = useToggleSchedule(pid, cid, tid);
  const del = useDeleteSchedule(pid, cid, tid);
  // Members may manage only schedules they created (ownership check server-side).
  const canTouch = (s: Schedule) => canManage || (!!selfId && s.created_by_id === selfId);

  // Empty is the common first visit — it gets a real hero, not a bare line.
  if (!isLoading && !error && schedules?.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl border border-line bg-surface2 text-ink2">
          <CalendarClock size={26} strokeWidth={1.8} />
        </span>
        <div>
          <h2 className="font-display text-[18px] font-extrabold">Put a persona on a clock</h2>
          <p className="mx-auto mt-1.5 max-w-sm text-[13.5px] leading-relaxed text-ink2">
            A Monday digest, an hourly log check, a one-time reminder — the server runs it in this chat on
            time, whether anyone is online or not.
          </p>
        </div>
        {canCreate ? (
          <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
            <Plus size={14} strokeWidth={2} /> Schedule the first run
          </Button>
        ) : (
          <p className="text-[12.5px] text-ink2">Members can schedule persona runs in this chat.</p>
        )}
        <CreateScheduleDialog open={creating} onClose={() => setCreating(false)} pid={pid} cid={cid} tid={tid} />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-2xl">
        <SectionHeader
          title="Schedules"
          blurb="Recurring runs for this chat's personas — the server fires them on time, online or not."
          actions={canCreate && (
            <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
              <Plus size={14} strokeWidth={2} /> New schedule
            </Button>
          )}
        />

        {isLoading && (
          <div className="mt-4 flex flex-col gap-2.5" role="status" aria-label="Loading schedules">
            <Skeleton className="h-16" />
            <Skeleton className="h-16 w-3/4" />
          </div>
        )}
        {!!error && (
          <p className="mt-5 text-[13.5px] text-crit">
            Couldn&apos;t load schedules. <Button size="sm" variant="ghost" onClick={() => refetch()}>Retry</Button>
          </p>
        )}

        {!!schedules?.length && (
          <ul className="mt-4 overflow-hidden rounded-xl border border-line bg-surface">
            {schedules.map((s) => (
              <li key={s.id} className="group flex items-start gap-3.5 border-b border-line px-4 py-3 last:border-b-0">
                <span className="mt-0.5 flex size-9 flex-none items-center justify-center rounded-[10px] border border-line bg-surface2 text-ink2">
                  <CalendarClock size={16} strokeWidth={2} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">
                    @{s.persona_name}
                    {s.label && <span className="font-normal text-ink2">· {s.label}</span>}
                    {s.is_paused && <span className="rounded-full border border-warn/30 bg-warn/10 px-2 py-px text-[10.5px] font-semibold text-warn">paused</span>}
                    {s.last_status === "error" && (
                      <span title={s.last_error ?? undefined} className="rounded-full border border-crit/30 bg-crit/10 px-2 py-px text-[10.5px] font-semibold text-crit">last run failed</span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-[12.5px] text-ink2" title={s.query_text}>&ldquo;{s.query_text}&rdquo;</p>
                  <p className="mt-0.5 text-[12px] text-ink2">
                    {s.schedule_summary}
                    {s.last_run_at && <span> · last ran {new Date(s.last_run_at).toLocaleString()}</span>}
                  </p>
                </div>
                {canTouch(s) && (
                  <span className="flex flex-none gap-0.5 opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-within:opacity-100">
                    <button
                      aria-label={`Edit schedule for ${s.persona_name}`}
                      title="Edit instruction and label"
                      onClick={() => setEditing(s)}
                      className="flex size-8 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink"
                    >
                      <Pencil size={14} strokeWidth={2} />
                    </button>
                    <button
                      aria-label={s.is_paused ? `Resume schedule for ${s.persona_name}` : `Pause schedule for ${s.persona_name}`}
                      title={s.is_paused ? "Resume" : "Pause"}
                      disabled={toggle.isPending}
                      onClick={() => toggle.mutate({ id: s.id, pause: !s.is_paused })}
                      className="flex size-8 items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink disabled:opacity-40"
                    >
                      {s.is_paused ? <Play size={14} strokeWidth={2} /> : <Pause size={14} strokeWidth={2} />}
                    </button>
                    <button
                      aria-label={`Remove schedule for ${s.persona_name}`}
                      title="Remove schedule"
                      onClick={() => setRemoving(s)}
                      className="flex size-8 items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <CreateScheduleDialog open={creating} onClose={() => setCreating(false)} pid={pid} cid={cid} tid={tid} />
      {editing && <EditScheduleDialog key={editing.id} schedule={editing} pid={pid} cid={cid} tid={tid} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) del.mutate(removing.id);
          setRemoving(null);
        }}
        title="Remove this schedule?"
        body={
          <p>
            <b className="text-ink">@{removing?.persona_name}</b> stops running &ldquo;{removing?.query_text.slice(0, 60)}&rdquo;
            on a clock. Past results stay in the chat.
          </p>
        }
        confirmLabel="Remove schedule"
        loading={del.isPending}
      />
    </div>
  );
}

type Mode = "interval" | "daily" | "weekly" | "monthly" | "once";
// Cron numbering: 0 = Sunday … 6 = Saturday.
const WEEKDAYS: { n: number; label: string }[] = [1, 2, 3, 4, 5, 6, 0].map((n) => ({ n, label: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][n] }));

function CreateScheduleDialog({ open, onClose, pid, cid, tid }: { open: boolean; onClose: () => void; pid: string; cid: string; tid: string }) {
  const { data: personas } = usePersonas(pid);
  const [personaId, setPersonaId] = useState("");
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState("");
  const [mode, setMode] = useState<Mode>("daily");
  const [every, setEvery] = useState(1);
  const [period, setPeriod] = useState<"minutes" | "hours" | "days" | "weeks">("hours");
  const [dailyTime, setDailyTime] = useState("09:00");
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [monthDay, setMonthDay] = useState("1");
  const [onceAt, setOnceAt] = useState("");
  // Server defaults: announce each run in the chat; make up a run missed
  // while the server was down.
  const [triggerVisible, setTriggerVisible] = useState(true);
  const [catchUpMissed, setCatchUpMissed] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const reset = () => {
    setPersonaId("");
    setQuery("");
    setLabel("");
    setMode("daily");
    setEvery(1);
    setPeriod("hours");
    setDailyTime("09:00");
    setWeekdays([]);
    setMonthDay("1");
    setOnceAt("");
    setTriggerVisible(true);
    setCatchUpMissed(true);
    setErr(null);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateSchedule(pid, cid, tid, close);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!personaId) return setErr("Pick the persona that runs.");
    if (!query.trim()) return setErr("Say what they should do each run — it's sent as their instruction.");
    if (label.trim()) { const le = vName(label, { label: "label", max: 80 }); if (le) return setErr(le); }
    if (mode === "interval" && (!Number.isFinite(every) || every < 1)) return setErr("Repeat interval must be at least 1.");
    const clocked = mode === "daily" || mode === "weekly" || mode === "monthly";
    if (clocked && !/^\d{2}:\d{2}$/.test(dailyTime)) return setErr("Pick a time of day.");
    if (mode === "weekly" && weekdays.length === 0) return setErr("Pick at least one day of the week.");
    if (mode === "monthly" && !/^([1-9]|[12]\d|3[01])$/.test(monthDay)) return setErr("Day of month must be between 1 and 31.");
    if (mode === "once") {
      if (!onceAt) return setErr("Pick when it should fire.");
      if (new Date(onceAt).getTime() <= Date.now()) return setErr("That time is in the past.");
    }
    const [hh, mm] = dailyTime.split(":");
    create.mutate({
      persona_id: personaId,
      query_text: query.trim(),
      label: label.trim() || undefined,
      timezone: tz,
      trigger_visible: triggerVisible,
      catch_up_missed: catchUpMissed,
      ...(mode === "interval"
        ? { schedule_kind: "interval" as const, interval_every: every, interval_period: period }
        : clocked
          ? {
              schedule_kind: "crontab" as const, crontab_minute: String(Number(mm)), crontab_hour: String(Number(hh)),
              ...(mode === "weekly" ? { crontab_day_of_week: [...weekdays].sort((a, b) => a - b).join(",") } : {}),
              ...(mode === "monthly" ? { crontab_day_of_month: String(Number(monthDay)) } : {}),
            }
          : { schedule_kind: "clocked" as const, clocked_time: new Date(onceAt).toISOString() }),
    });
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      size="lg"
      title="New schedule"
      description={`The persona runs your instruction in this chat on the clock you set (times in ${tz}).`}
      icon={<CalendarClock size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="sc-form" size="sm" variant="primary" loading={create.isPending}>Create schedule</Button>
        </div>
      }
    >
      <form id="sc-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="sc-persona" required>Persona</Label>
          <select id="sc-persona" required autoFocus value={personaId} onChange={(e) => setPersonaId(e.target.value)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
            <option value="" disabled>Choose a persona…</option>
            {personas?.map((p) => (
              <option key={p.id} value={p.id}>@{p.name}</option>
            ))}
          </select>
          {personas?.length === 0 && <p className="mt-1.5 text-[12px] text-warn">This project has no personas yet — create one under Intelligence.</p>}
        </div>
        <div>
          <Label htmlFor="sc-query" required>What should they do each run?</Label>
          <textarea
            id="sc-query"
            required
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Summarize yesterday's messages in this chat and flag anything blocking the launch."
            className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[14px] leading-relaxed outline-none focus:border-accent"
          />
        </div>
        <div>
          <Label>When</Label>
          <div
            className="flex gap-2"
            role="radiogroup"
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              e.preventDefault();
              const btns = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button[role=radio]"));
              const idx = btns.findIndex((b) => b.getAttribute("aria-checked") === "true");
              const next = btns[(idx + (e.key === "ArrowRight" ? 1 : -1) + btns.length) % btns.length];
              next?.focus();
              next?.click();
            }} aria-label="When">
            {([["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["interval", "Repeating"], ["once", "Once"]] as const).map(([m, l]) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-[10px] border px-3 py-2 text-[13px] font-semibold transition-colors ${mode === m ? "border-accent bg-accent/10 text-accent" : "border-line bg-surface text-ink2 hover:border-accent/50"}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        {mode === "weekly" && (
          <fieldset>
            <legend className="mb-1.5 block text-[13px] font-medium text-ink2">On these days</legend>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS.map((d) => {
                const on = weekdays.includes(d.n);
                return (
                  <label key={d.n} className={`flex cursor-pointer items-center gap-1.5 rounded-[10px] border px-2.5 py-1.5 text-[13px] ${on ? "border-accent bg-accent/10" : "border-line bg-surface hover:border-accent/50"}`}>
                    <input type="checkbox" checked={on} onChange={() => setWeekdays((cur) => (cur.includes(d.n) ? cur.filter((x) => x !== d.n) : [...cur, d.n]))} className="accent-[var(--accent)]" />
                    {d.label}
                  </label>
                );
              })}
            </div>
          </fieldset>
        )}
        {mode === "monthly" && (
          <div className="max-w-[180px]">
            <Label htmlFor="sc-monthday" required>Day of month</Label>
            <Input id="sc-monthday" type="number" required min={1} max={31} step={1} inputMode="numeric" value={monthDay} onChange={(e) => setMonthDay(e.target.value)} />
            <p className="mt-1.5 text-[12px] text-ink2">Months without that day are skipped (e.g. the 31st).</p>
          </div>
        )}
        {(mode === "daily" || mode === "weekly" || mode === "monthly") && (
          <div className="max-w-[180px]">
            <Label htmlFor="sc-time" required>At</Label>
            <Input id="sc-time" type="time" required value={dailyTime} onChange={(e) => setDailyTime(e.target.value)} />
          </div>
        )}
        {mode === "interval" && (
          <div className="grid max-w-sm grid-cols-2 gap-3">
            <div>
              <Label htmlFor="sc-every" required>Every</Label>
              <Input id="sc-every" type="number" required min={1} value={every} onChange={(e) => setEvery(Number(e.target.value))} />
            </div>
            <div>
              <Label htmlFor="sc-period">Period</Label>
              <select id="sc-period" value={period} onChange={(e) => setPeriod(e.target.value as typeof period)} className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]">
                <option value="minutes">minutes</option>
                <option value="hours">hours</option>
                <option value="days">days</option>
                <option value="weeks">weeks</option>
              </select>
            </div>
          </div>
        )}
        {mode === "once" && (
          <div className="max-w-[260px]">
            <Label htmlFor="sc-once" required>Fire at</Label>
            <Input id="sc-once" type="datetime-local" required value={onceAt} onChange={(e) => setOnceAt(e.target.value)} />
          </div>
        )}
        <div>
          <Label htmlFor="sc-label">Label <span className="text-ink2">(optional)</span></Label>
          <Input id="sc-label" placeholder="e.g. Morning digest" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
        </div>
        <div className="flex flex-col gap-2">
          <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
            <input type="checkbox" checked={triggerVisible} onChange={(e) => setTriggerVisible(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
            Post a visible &ldquo;Scheduled: …&rdquo; message in the chat before each run
          </label>
          <label className="flex items-start gap-2.5 text-[12.5px] text-ink2">
            <input type="checkbox" checked={catchUpMissed} onChange={(e) => setCatchUpMissed(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
            If the server was down at run time, run it once on restart
          </label>
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}

// What the server lets a schedule change after creation: the instruction and
// the label. The clock is fixed — pause, or recreate with a new one.
function EditScheduleDialog({ schedule, pid, cid, tid, onClose }: { schedule: Schedule; pid: string; cid: string; tid: string; onClose: () => void }) {
  const [query, setQuery] = useState(schedule.query_text);
  const [label, setLabel] = useState(schedule.label ?? "");
  const [err, setErr] = useState<string | null>(null);
  const edit = useEditSchedule(pid, cid, tid, onClose);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!query.trim()) return setErr("Say what they should do each run — it's sent as their instruction.");
    if (label.trim()) { const le = vName(label, { label: "label", max: 80 }); if (le) return setErr(le); }
    const patch = {
      ...(query.trim() !== schedule.query_text ? { query_text: query.trim() } : {}),
      ...(label.trim() !== (schedule.label ?? "") ? { label: label.trim() } : {}),
    };
    if (Object.keys(patch).length === 0) return onClose(); // nothing changed
    edit.mutate({ id: schedule.id, patch });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Edit schedule for @${schedule.persona_name}`}
      description={`${schedule.schedule_summary} — the clock stays; change the instruction or the label.`}
      icon={<Pencil size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="se-form" size="sm" variant="primary" disabled={!query.trim()} loading={edit.isPending}>Save changes</Button>
        </div>
      }
    >
      <form id="se-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="se-query" required>What should they do each run?</Label>
          <textarea
            id="se-query"
            required
            autoFocus
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full resize-y rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[14px] leading-relaxed outline-none focus:border-accent"
          />
        </div>
        <div>
          <Label htmlFor="se-label">Label <span className="text-ink2">(optional)</span></Label>
          <Input id="se-label" placeholder="e.g. Morning digest" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
        </div>
        <FieldError>{err}</FieldError>
      </form>
    </Dialog>
  );
}
