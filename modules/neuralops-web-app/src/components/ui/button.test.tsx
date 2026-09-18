import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";
import { EntityCard } from "@/components/intelligence/shared";

// A control that moves on hover slides out from under a cursor resting on
// its edge, un-hovers, slides back, and flickers. Feedback is colour, shadow
// and brightness only — never geometry.
describe("hover feedback never moves the control", () => {
  it.each(["primary", "secondary", "ghost", "danger", "link"] as const)("Button %s", (variant) => {
    render(<Button variant={variant}>Go</Button>);
    const cls = screen.getByRole("button", { name: "Go" }).className;
    expect(cls).not.toMatch(/hover:-?translate|hover:scale|active:-?translate|active:scale/);
  });

  it("EntityCard", () => {
    const { container } = render(<EntityCard icon={<span />} title="Card" />);
    expect(container.firstElementChild?.className).not.toMatch(/hover:-?translate|hover:scale/);
  });
});

describe("Button link variant", () => {
  it("reads as a link at rest: accent text, no chrome, underline on hover", () => {
    render(<Button variant="link">View all</Button>);
    const tokens = screen.getByRole("button", { name: "View all" }).className.split(/\s+/);
    expect(tokens).toContain("text-accent");
    expect(tokens).toContain("hover:underline");
    expect(tokens).not.toContain("border");
    expect(tokens.some((t) => t.startsWith("bg-"))).toBe(false);
  });
});
