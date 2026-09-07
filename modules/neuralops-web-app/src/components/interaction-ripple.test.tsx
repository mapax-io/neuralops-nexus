import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { InteractionRipple } from "./interaction-ripple";
import { RIPPLE_MS, TOUCH_ARM_MS } from "@/lib/ripple";

const rect = (left: number, top: number, width: number, height: number) => () =>
  ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect;

function mount(html: string) {
  render(<InteractionRipple />);
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host.firstElementChild as HTMLElement;
}

function press(target: Element, init: { x?: number; y?: number; button?: number; pointerType?: string } = {}) {
  const ev = new MouseEvent("pointerdown", { bubbles: true, cancelable: true, clientX: init.x ?? 0, clientY: init.y ?? 0, button: init.button ?? 0 });
  Object.defineProperty(ev, "pointerType", { value: init.pointerType ?? "mouse" });
  target.dispatchEvent(ev);
}

const layer = () => document.querySelector(".nx-ripple-layer")!;
const clips = () => [...document.querySelectorAll(".nx-ripple-clip")] as HTMLElement[];

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("InteractionRipple — a press leaves a visible trace", () => {
  it("spawns a ripple clipped to the pressed button, in its colour and radius, and cleans it up", () => {
    const btn = mount('<button style="color: rgb(1, 2, 3); border-radius: 8px"><span>Go</span></button>');
    btn.getBoundingClientRect = rect(10, 20, 100, 40);
    press(btn.querySelector("span")!, { x: 15, y: 25 });
    expect(layer()).toBeTruthy();
    const [clip] = clips();
    expect(clip).toBeTruthy();
    expect(clip.style.left).toBe("10px");
    expect(clip.style.top).toBe("20px");
    expect(clip.style.width).toBe("100px");
    expect(clip.style.height).toBe("40px");
    expect(clip.style.borderRadius).toBe("8px");
    const circle = clip.querySelector(".nx-ripple") as HTMLElement;
    expect(circle.style.backgroundColor).toBe("rgb(1, 2, 3)");
    expect(parseFloat(circle.style.width)).toBeCloseTo(2 * Math.hypot(95, 35), 3);
    // Centred on the press point: left = x - r.
    expect(parseFloat(circle.style.left)).toBeCloseTo(5 - Math.hypot(95, 35), 3);
    vi.advanceTimersByTime(RIPPLE_MS + 300);
    expect(clips()).toHaveLength(0);
  });

  it("removes the ripple as soon as its animation ends", () => {
    const btn = mount("<button>Go</button>");
    btn.getBoundingClientRect = rect(0, 0, 50, 20);
    press(btn, { x: 5, y: 5 });
    const [clip] = clips();
    clip.querySelector(".nx-ripple")!.dispatchEvent(new Event("animationend", { bubbles: true }));
    expect(clips()).toHaveLength(0);
  });

  it("stacks ripples for rapid presses instead of dropping any", () => {
    const btn = mount("<button>Go</button>");
    btn.getBoundingClientRect = rect(0, 0, 50, 20);
    press(btn, { x: 5, y: 5 });
    press(btn, { x: 40, y: 10 });
    expect(clips()).toHaveLength(2);
  });

  it("gives nothing to typing surfaces, disabled controls, secondary buttons, or opt-outs", () => {
    const wrap = mount(
      '<div><input type="text" aria-label="t" /><textarea aria-label="a"></textarea><div contenteditable="true">e</div><button disabled>d</button><button data-ripple="off">o</button><button id="ok">ok</button><p>plain</p></div>',
    );
    for (const sel of ["input", "textarea", "[contenteditable]", "button[disabled]", '[data-ripple="off"]', "p"]) {
      press(wrap.querySelector(sel)!, { x: 1, y: 1 });
    }
    press(wrap.querySelector("#ok")!, { x: 1, y: 1, button: 2 }); // right-click
    expect(clips()).toHaveLength(0);
  });

  it("ripples from the centre on keyboard activation of the focused control, ignoring key repeat", () => {
    const btn = mount("<button>Go</button>");
    btn.getBoundingClientRect = rect(0, 0, 100, 40);
    btn.focus();
    btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, repeat: true }));
    expect(clips()).toHaveLength(0);
    btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    btn.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    expect(clips()).toHaveLength(2);
    const circle = clips()[0].querySelector(".nx-ripple") as HTMLElement;
    const r = Math.hypot(50, 20);
    expect(parseFloat(circle.style.left)).toBeCloseTo(50 - r, 3);
    expect(parseFloat(circle.style.top)).toBeCloseTo(20 - r, 3);
  });

  it("does not ripple Enter typed into a text field", () => {
    const input = mount('<input type="text" aria-label="q" />');
    input.focus();
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(clips()).toHaveLength(0);
  });

  it("waits out a touch so a scroll that starts on a button does not ripple", () => {
    const btn = mount("<button>Go</button>");
    btn.getBoundingClientRect = rect(0, 0, 100, 40);
    press(btn, { x: 10, y: 10, pointerType: "touch" });
    expect(clips()).toHaveLength(0);
    vi.advanceTimersByTime(TOUCH_ARM_MS + 1);
    expect(clips()).toHaveLength(1);
  });

  it("cancels an armed touch that moves before it fires", () => {
    const btn = mount("<button>Go</button>");
    btn.getBoundingClientRect = rect(0, 0, 100, 40);
    press(btn, { x: 10, y: 10, pointerType: "touch" });
    const move = new MouseEvent("pointermove", { bubbles: true, clientX: 10, clientY: 40 });
    document.dispatchEvent(move);
    vi.advanceTimersByTime(TOUCH_ARM_MS + 1);
    expect(clips()).toHaveLength(0);
  });

  it("still paints a touch ripple for a control that unmounted while the touch was settling (menu items, navigating buttons)", () => {
    const item = mount('<button role="menuitem" style="color: rgb(9, 9, 9)">Personas</button>');
    item.getBoundingClientRect = rect(0, 100, 200, 40);
    press(item, { x: 30, y: 120, pointerType: "touch" });
    item.remove(); // the menu closed on tap, before the ripple was due
    vi.advanceTimersByTime(TOUCH_ARM_MS + 1);
    const [clip] = clips();
    expect(clip).toBeTruthy();
    expect(clip.style.width).toBe("200px");
    expect(clip.style.top).toBe("100px");
    expect((clip.querySelector(".nx-ripple") as HTMLElement).style.backgroundColor).toBe("rgb(9, 9, 9)");
  });

  it("draws a round halo around a checkbox instead of clipping to its tiny box", () => {
    const box = mount('<input type="checkbox" aria-label="c" />');
    box.getBoundingClientRect = rect(100, 100, 16, 16);
    press(box, { x: 101, y: 101 });
    const [clip] = clips();
    expect(clip.className).toMatch(/nx-ripple-clip--halo/);
    expect(parseFloat(clip.style.width)).toBeCloseTo(16 * 2.4, 3);
  });

  it("tears its listeners down on unmount", () => {
    const { unmount } = render(<InteractionRipple />);
    unmount();
    const host = document.createElement("div");
    host.innerHTML = "<button>Go</button>";
    document.body.appendChild(host);
    press(host.firstElementChild!, { x: 1, y: 1 });
    expect(clips()).toHaveLength(0);
  });
});
