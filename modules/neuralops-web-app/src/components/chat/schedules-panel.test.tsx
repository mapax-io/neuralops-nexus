import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { SchedulesPanel } from "./schedules-panel";

const BASE = "http://server.test:8096";
const SCHEDULES = `${BASE}/api/v1/projects/p1/channels/c1/topics/t1/schedules/`;

let posted: Record<string, unknown> | null = null;

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SchedulesPanel pid="p1" cid="c1" tid="t1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  posted = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(SCHEDULES, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/personas/`, () =>
      HttpResponse.json([{
        id: "pe1", name: "Layla", description: null, project_id: "p1",
        model: { id: "m1", name: "House", provider: "anthropic", model_id: "claude-sonnet-5", qualified_id: "anthropic:claude-sonnet-5", supports_tools: true },
        advisor_model: null, mcp_servers: [], temperature: 0.7, max_tokens: 4096, max_steps: 10, prompt: null, is_active: true, avatar: null,
      }]),
    ),
    http.post(SCHEDULES, async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: "sc1", topic_id: "t1", persona_id: "pe1", persona_name: "Layla", query_text: posted.query_text, label: "",
        schedule_kind: "crontab", schedule_summary: "Daily at 09:00", timezone: "UTC", trigger_visible: posted.trigger_visible,
        catch_up_missed: posted.catch_up_missed, is_paused: false, created_by_id: "u1", last_run_at: null, last_status: "", last_error: null,
      });
    }),
  );
});

const EXISTING = {
  id: "sc1", topic_id: "t1", persona_id: "pe1", persona_name: "Layla", query_text: "Summarize the day.", label: "Digest",
  schedule_kind: "crontab", schedule_summary: "Daily at 09:00", timezone: "UTC", trigger_visible: true, catch_up_missed: true,
  is_paused: false, created_by_id: "u1", last_run_at: null, last_status: "", last_error: null,
};

describe("CreateScheduleDialog — weekly and monthly", () => {
  it("weekly posts the ticked days as a crontab day_of_week", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /new schedule/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Persona"), { target: { value: "pe1" } });
    fireEvent.change(within(dialog).getByLabelText(/what should they do/i), { target: { value: "Weekly report." } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Weekly" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Mon" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Fri" }));
    fireEvent.change(within(dialog).getByLabelText("At"), { target: { value: "17:30" } });
    fireEvent.submit(document.getElementById("sc-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ schedule_kind: "crontab", crontab_minute: "30", crontab_hour: "17", crontab_day_of_week: "1,5" });
    expect(posted).not.toHaveProperty("crontab_day_of_month");
  });

  it("weekly refuses to submit with no day ticked", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /new schedule/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Persona"), { target: { value: "pe1" } });
    fireEvent.change(within(dialog).getByLabelText(/what should they do/i), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Weekly" }));
    fireEvent.submit(document.getElementById("sc-form")!);
    expect(await within(dialog).findByText(/pick at least one day/i)).toBeInTheDocument();
    expect(posted).toBeNull();
  });

  it("monthly posts the day of month", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /new schedule/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Persona"), { target: { value: "pe1" } });
    fireEvent.change(within(dialog).getByLabelText(/what should they do/i), { target: { value: "Monthly report." } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Monthly" }));
    fireEvent.change(within(dialog).getByLabelText("Day of month"), { target: { value: "15" } });
    fireEvent.submit(document.getElementById("sc-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ schedule_kind: "crontab", crontab_hour: "9", crontab_minute: "0", crontab_day_of_month: "15" });
    expect(posted).not.toHaveProperty("crontab_day_of_week");
  });
});

describe("EditScheduleDialog", () => {
  it("edits the label and instruction, sending only what changed", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.get(SCHEDULES, () => HttpResponse.json([EXISTING])),
      http.patch(`${SCHEDULES}:id/`, async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...EXISTING, ...patched });
      }),
    );
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Edit schedule for Layla" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(/what should they do/i)).toHaveValue("Summarize the day.");
    expect(within(dialog).getByLabelText(/label/i)).toHaveValue("Digest");
    fireEvent.change(within(dialog).getByLabelText(/what should they do/i), { target: { value: "Summarize the day and flag blockers." } });
    fireEvent.submit(document.getElementById("se-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ query_text: "Summarize the day and flag blockers." });
  });
});

describe("CreateScheduleDialog — run flags", () => {
  it("sends both server flags, defaulting on, and honours an unticked one", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /new schedule/i }));
    const dialog = screen.getByRole("dialog");
    const announce = within(dialog).getByRole("checkbox", { name: /post a visible/i }) as HTMLInputElement;
    const catchUp = within(dialog).getByRole("checkbox", { name: /run it once on restart/i }) as HTMLInputElement;
    expect(announce.checked).toBe(true);
    expect(catchUp.checked).toBe(true);
    fireEvent.click(announce);
    fireEvent.change(within(dialog).getByLabelText("Persona"), { target: { value: "pe1" } });
    fireEvent.change(within(dialog).getByLabelText(/what should they do/i), { target: { value: "Summarize the day." } });
    fireEvent.submit(document.getElementById("sc-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ persona_id: "pe1", schedule_kind: "crontab", trigger_visible: false, catch_up_missed: true });
  });

  it("marks the persona and instruction as required", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /new schedule/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Persona")).toBeRequired();
    expect(within(dialog).getByLabelText(/what should they do/i)).toBeRequired();
    expect(within(dialog).getByLabelText(/label/i)).not.toBeRequired();
  });
});
