import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";
import { EntityCard } from "@/components/intelligence/shared";

// A control that moves on hover slides out from under a cursor resting on
// its edge, un-hovers, slides back, and flickers. Feedback is colour, shadow
// and brightness only — never geometry.
describe("hover feedback never moves the control", () => {
  it.each(["primary", "secondary", "ghost", "danger"] as const)("Button %s", (variant) => {
    render(<Button variant={variant}>Go</Button>);
    const cls = screen.getByRole("button", { name: "Go" }).className;
    expect(cls).not.toMatch(/hover:-?translate|hover:scale|active:-?translate|active:scale/);
  });

  it("EntityCard", () => {
    const { container } = render(<EntityCard icon={<span />} title="Card" />);
    expect(container.firstElementChild?.className).not.toMatch(/hover:-?translate|hover:scale/);
  });
});
