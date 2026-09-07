"use client";

import { useEffect, useRef } from "react";
import { findRippleTarget, isHaloTarget, rippleGeometry, RIPPLE_MS, TOUCH_ARM_MS, TOUCH_CANCEL_PX } from "@/lib/ripple";

// One document-level listener paints a ripple for every press on anything
// clickable — buttons, button-like links, menu items, tabs, checkboxes —
// without touching the components themselves. The overlay is fixed and
// pointer-events-free and clips itself to the target's rect and corner
// radius, so no control ever needs overflow:hidden (which would clip the
// badges and popovers some of them render inside). Mounted once, in the root
// layout. Opt out with data-ripple="off"; opt a plain element in with data-ripple.
export function InteractionRipple() {
  const layerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    const isInline = (el: Element) => getComputedStyle(el).display === "inline";

    // Geometry and colour are read at press time and painting is a separate
    // step: a touch ripple is armed for TOUCH_ARM_MS, and the control may be
    // gone by then (menu items close their menu, buttons navigate) — a detached
    // element measures 0×0, which would paint nothing.
    const capture = (target: Element, point: { x: number; y: number } | null) => {
      const style = getComputedStyle(target);
      const g = rippleGeometry(target.getBoundingClientRect(), point, isHaloTarget(target));
      const radius = style.borderRadius
        ? { borderRadius: style.borderRadius }
        : {
            borderTopLeftRadius: style.borderTopLeftRadius,
            borderTopRightRadius: style.borderTopRightRadius,
            borderBottomRightRadius: style.borderBottomRightRadius,
            borderBottomLeftRadius: style.borderBottomLeftRadius,
          };
      return { g, radius, color: style.color };
    };

    const paint = ({ g, radius, color }: ReturnType<typeof capture>) => {
      const clip = document.createElement("div");
      clip.className = g.halo ? "nx-ripple-clip nx-ripple-clip--halo" : "nx-ripple-clip";
      clip.style.left = `${g.left}px`;
      clip.style.top = `${g.top}px`;
      clip.style.width = `${g.width}px`;
      clip.style.height = `${g.height}px`;
      if (!g.halo) Object.assign(clip.style, radius);
      const circle = document.createElement("span");
      circle.className = "nx-ripple";
      circle.style.width = `${g.diameter}px`;
      circle.style.height = `${g.diameter}px`;
      circle.style.left = `${g.x - g.diameter / 2}px`;
      circle.style.top = `${g.y - g.diameter / 2}px`;
      // The control's own text colour: ink on neutral buttons, accent-ink on
      // filled ones — theme-correct with no per-component configuration.
      circle.style.backgroundColor = color;
      clip.appendChild(circle);
      layer.appendChild(clip);
      let fallback = 0;
      const remove = () => {
        window.clearTimeout(fallback);
        clip.remove();
      };
      circle.addEventListener("animationend", remove, { once: true });
      // animationend never fires under reduced motion (0.01ms) in some engines,
      // nor in test DOMs — the timer guarantees the node goes away.
      fallback = window.setTimeout(remove, RIPPLE_MS + 250);
    };

    let armed: { point: { x: number; y: number }; timer: number } | null = null;
    const disarm = () => {
      if (!armed) return;
      window.clearTimeout(armed.timer);
      armed = null;
    };

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      const target = findRippleTarget(e.target instanceof Element ? e.target : null, { isInline });
      if (!target) return;
      const point = { x: e.clientX, y: e.clientY };
      const captured = capture(target, point);
      if (e.pointerType === "touch") {
        disarm();
        armed = {
          point,
          timer: window.setTimeout(() => {
            armed = null;
            paint(captured);
          }, TOUCH_ARM_MS),
        };
        return;
      }
      paint(captured);
    };
    const onPointerMove = (e: PointerEvent) => {
      if (armed && Math.hypot(e.clientX - armed.point.x, e.clientY - armed.point.y) > TOUCH_CANCEL_PX) disarm();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || (e.key !== "Enter" && e.key !== " ")) return;
      const active = document.activeElement;
      if (!active || active !== e.target) return;
      const target = findRippleTarget(active, { isInline });
      // Only the focused control itself — and Space does not activate links.
      if (!target || target !== active || (e.key === " " && target.tagName === "A")) return;
      paint(capture(target, null));
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointermove", onPointerMove, { capture: true, passive: true });
    document.addEventListener("pointercancel", disarm, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      disarm();
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("pointermove", onPointerMove, { capture: true });
      document.removeEventListener("pointercancel", disarm, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, []);

  return <div ref={layerRef} aria-hidden className="nx-ripple-layer" />;
}
