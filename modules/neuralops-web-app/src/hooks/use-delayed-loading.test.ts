import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSlowAfter } from "./use-delayed-loading";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useSlowAfter — a wait that has gone on too long", () => {
  it("turns on once the wait has lasted the threshold, and off the moment it ends", () => {
    const { result, rerender } = renderHook(({ active }) => useSlowAfter(active, 1_000), { initialProps: { active: true } });
    expect(result.current).toBe(false);
    act(() => { vi.advanceTimersByTime(999); });
    expect(result.current).toBe(false);
    act(() => { vi.advanceTimersByTime(1); });
    expect(result.current).toBe(true);
    rerender({ active: false });
    expect(result.current).toBe(false);
  });

  it("starts the clock again for a new wait", () => {
    const { result, rerender } = renderHook(({ active }) => useSlowAfter(active, 1_000), { initialProps: { active: true } });
    act(() => { vi.advanceTimersByTime(1_000); });
    expect(result.current).toBe(true);
    rerender({ active: false });
    rerender({ active: true });
    expect(result.current).toBe(false);
    act(() => { vi.advanceTimersByTime(999); });
    expect(result.current).toBe(false);
    act(() => { vi.advanceTimersByTime(1); });
    expect(result.current).toBe(true);
  });

  it("never turns on while nothing is being waited for", () => {
    const { result } = renderHook(() => useSlowAfter(false, 1_000));
    act(() => { vi.advanceTimersByTime(5_000); });
    expect(result.current).toBe(false);
  });
});
