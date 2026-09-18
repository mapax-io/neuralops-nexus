import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { useConnectionStore } from "@/stores/connection.store";

type Listener = (event: string, session: { access_token: string; user: { id: string; email: string } } | null) => void;
let getSession: () => Promise<{ data: { session: { access_token: string; user: { id: string; email: string } } | null } }>;
let listener: Listener | null = null;

vi.mock("@/lib/supabase", () => ({
  supabase: () => ({
    auth: {
      getSession: () => getSession(),
      onAuthStateChange: (fn: Listener) => {
        listener = fn;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  }),
}));
vi.mock("@/lib/auth/session-cleanup", () => ({ clearAccountScopedState: vi.fn() }));

import { SupabaseSessionSync } from "./supabase-session";

const session = { access_token: "jwt", user: { id: "u1", email: "o@acme.test" } };

beforeEach(() => {
  vi.useFakeTimers();
  listener = null;
  useConnectionStore.setState({ hydrated: false, token: null, userId: null, email: null });
});
afterEach(() => vi.useRealTimers());

describe("SupabaseSessionSync — the app never waits on the session forever", () => {
  it("hydrates with the identity when the session comes back", async () => {
    getSession = () => Promise.resolve({ data: { session } });
    render(<SupabaseSessionSync />);
    await act(async () => { await Promise.resolve(); });
    expect(useConnectionStore.getState()).toMatchObject({ hydrated: true, token: "jwt", email: "o@acme.test" });
  });

  // supabase-js guards the session with navigator.locks; a lock left held by
  // another tab makes getSession() hang. That must not hold the loader.
  it("gives up on a session read that never answers, and lets the page go on without a token", async () => {
    getSession = () => new Promise(() => {});
    render(<SupabaseSessionSync />);
    await act(async () => { vi.advanceTimersByTime(7_900); });
    expect(useConnectionStore.getState().hydrated).toBe(false);
    await act(async () => { vi.advanceTimersByTime(200); });
    expect(useConnectionStore.getState()).toMatchObject({ hydrated: true, token: null });
  });

  it("treats a rejected session read the same way", async () => {
    getSession = () => Promise.reject(new Error("lock"));
    render(<SupabaseSessionSync />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(useConnectionStore.getState()).toMatchObject({ hydrated: true, token: null });
  });

  it("still picks up a session that arrives late through the auth listener", async () => {
    getSession = () => new Promise(() => {});
    render(<SupabaseSessionSync />);
    await act(async () => { vi.advanceTimersByTime(8_100); });
    expect(useConnectionStore.getState().token).toBeNull();
    act(() => listener!("SIGNED_IN", session));
    expect(useConnectionStore.getState()).toMatchObject({ hydrated: true, token: "jwt" });
  });
});
