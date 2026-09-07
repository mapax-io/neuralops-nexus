import { describe, expect, it } from "vitest";
import { findRippleTarget, isHaloTarget, rippleGeometry } from "./ripple";

function el(html: string): Element {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host.firstElementChild!;
}

describe("findRippleTarget — what counts as clickable", () => {
  it("resolves the nearest button from a click on its icon", () => {
    const btn = el('<button><svg><path /></svg></button>');
    expect(findRippleTarget(btn.querySelector("path"))).toBe(btn);
  });

  it("covers the interactive roles and controls the app uses", () => {
    for (const html of [
      '<div role="button">x</div>', '<div role="menuitem">x</div>', '<div role="tab">x</div>', '<div role="option">x</div>',
      '<summary>x</summary>', '<input type="checkbox" />', '<input type="radio" />', '<input type="submit" />', '<div data-ripple>x</div>',
    ]) {
      const node = el(html);
      expect(findRippleTarget(node), html).toBe(node);
    }
  });

  it("never ripples typing surfaces, disabled controls, or opt-outs", () => {
    for (const html of [
      '<input type="text" />', '<textarea></textarea>', '<div contenteditable="true">x</div>', '<div class="ProseMirror"><p>x</p></div>',
      '<button disabled>x</button>', '<button aria-disabled="true">x</button>', '<button data-ripple="off">x</button>', '<div>x</div>',
    ]) {
      const node = el(html);
      expect(findRippleTarget(node.querySelector("p") ?? node), html).toBeNull();
    }
  });

  it("ripples button-like links but not inline text links", () => {
    const inline = el('<a href="/x">read more</a>');
    const block = el('<a href="/x">Open</a>');
    const isInline = (a: Element) => a === inline;
    expect(findRippleTarget(inline, { isInline })).toBeNull();
    expect(findRippleTarget(block, { isInline })).toBe(block);
  });

  it("stops at an editor even when a button wraps it", () => {
    const wrap = el('<button><div class="ProseMirror"><p>typing</p></div></button>');
    expect(findRippleTarget(wrap.querySelector("p"))).toBeNull();
  });
});

describe("rippleGeometry — the circle reaches the farthest corner", () => {
  const rect = { left: 10, top: 20, width: 100, height: 40 };

  it("from a pointer near the top-left, the radius is the distance to the bottom-right corner", () => {
    const g = rippleGeometry(rect, { x: 15, y: 25 }, false);
    expect(g).toMatchObject({ left: 10, top: 20, width: 100, height: 40, x: 5, y: 5, halo: false });
    expect(g.diameter).toBeCloseTo(2 * Math.hypot(95, 35), 5);
  });

  it("without a pointer (keyboard) it starts from the centre", () => {
    const g = rippleGeometry(rect, null, false);
    expect(g.x).toBe(50);
    expect(g.y).toBe(20);
    expect(g.diameter).toBeCloseTo(2 * Math.hypot(50, 20), 5);
  });

  it("a halo target gets a round clip centred on the control, 2.4× its size", () => {
    const g = rippleGeometry({ left: 100, top: 100, width: 16, height: 16 }, { x: 101, y: 101 }, true);
    expect(g.halo).toBe(true);
    expect(g.width).toBeCloseTo(16 * 2.4, 5);
    expect(g.height).toBeCloseTo(16 * 2.4, 5);
    // The clip box is centred on the control's centre (108, 108).
    expect(g.left + g.width / 2).toBeCloseTo(108, 5);
    expect(g.top + g.height / 2).toBeCloseTo(108, 5);
    expect(g.x).toBeCloseTo(g.width / 2, 5);
    expect(g.diameter).toBeCloseTo(g.width, 5);
  });

  it("knows which controls take a halo", () => {
    expect(isHaloTarget(el('<input type="checkbox" />'))).toBe(true);
    expect(isHaloTarget(el('<input type="radio" />'))).toBe(true);
    expect(isHaloTarget(el('<button role="switch">x</button>'))).toBe(true);
    expect(isHaloTarget(el('<button>x</button>'))).toBe(false);
  });
});
