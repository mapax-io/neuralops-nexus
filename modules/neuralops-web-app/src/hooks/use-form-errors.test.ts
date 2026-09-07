import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { afterPress, useFormErrors } from "./use-form-errors";

describe("useFormErrors", () => {
  it("gates on every rule at once but shows a message only for a judged field", () => {
    const { result, rerender } = renderHook(({ name, url }: { name: string; url: string }) =>
      useFormErrors({ name: [name, name.trim() ? null : "Enter a name."], url: [url, url ? null : "Enter a URL."] }),
    { initialProps: { name: "", url: "" } });
    expect(result.current.invalid).toBe(true);
    expect(result.current.error("name")).toBeNull(); // untouched: no red on a blank form
    act(() => result.current.touch("name"));
    expect(result.current.error("name")).toBeNull(); // a pristine empty field stays quiet when left
    rerender({ name: "L", url: "" });
    rerender({ name: "", url: "" }); // typed, then emptied — it has held a value
    act(() => result.current.touch("name"));
    expect(result.current.error("name")).toBe("Enter a name.");
    expect(result.current.error("url")).toBeNull();
    rerender({ name: "Layla", url: "http://x" }); // judged once: live from then on
    expect(result.current.error("name")).toBeNull();
    expect(result.current.invalid).toBe(false);
  });

  it("a field pre-filled from a record counts as having held a value", () => {
    const { result, rerender } = renderHook(({ role }: { role: string }) => useFormErrors({ role: [role, role ? null : "Write the role."] }),
      { initialProps: { role: "You analyse." } });
    rerender({ role: "" });
    act(() => result.current.touch("role"));
    expect(result.current.error("role")).toBe("Write the role.");
  });

  it("a rule without a value always judges on touch; touchAll reveals everything; reset hides it again", () => {
    const { result } = renderHook(() => useFormErrors({ a: "A is off.", b: "B is off.", c: null }));
    act(() => result.current.touch("a"));
    expect(result.current.error("a")).toBe("A is off.");
    act(() => result.current.touchAll());
    expect(result.current.error("b")).toBe("B is off.");
    expect(result.current.error("c")).toBeNull();
    act(() => result.current.reset());
    expect(result.current.error("a")).toBeNull();
    expect(result.current.invalid).toBe(true);
  });

  it("a reveal during a press waits until the press has ended and the click has been dispatched", async () => {
    const calls: string[] = [];
    document.dispatchEvent(new Event("pointerdown"));
    afterPress(() => calls.push("deferred"));
    expect(calls).toEqual([]); // blur mid-press: nothing moves yet
    document.dispatchEvent(new Event("pointerup"));
    expect(calls).toEqual([]); // not even on release — the click comes after
    await new Promise((r) => setTimeout(r, 0));
    expect(calls).toEqual(["deferred"]);
    afterPress(() => calls.push("immediate"));
    expect(calls).toEqual(["deferred", "immediate"]); // no press: straight away (keyboard)
  });
});
