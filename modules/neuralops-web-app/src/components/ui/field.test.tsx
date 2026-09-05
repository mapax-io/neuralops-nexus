import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Input, Label } from "./field";

describe("Label — required marker", () => {
  it("marks a required field with the asterisk styling and keeps the accessible name clean", () => {
    render(
      <>
        <Label htmlFor="a" required>Name</Label>
        <Input id="a" required />
      </>,
    );
    const label = screen.getByText("Name");
    // The asterisk is CSS-generated (::after), so it never pollutes the label's
    // text; the data attribute is the hook both CSS and tests key on.
    expect(label).toHaveAttribute("data-required", "true");
    expect(label.className).toMatch(/after:content-\['\*'\]/);
    // Assistive tech learns "required" from the control itself.
    expect(screen.getByLabelText("Name")).toBeRequired();
  });

  it("leaves optional fields unmarked", () => {
    render(
      <>
        <Label htmlFor="b">Description</Label>
        <Input id="b" />
      </>,
    );
    expect(screen.getByText("Description")).not.toHaveAttribute("data-required");
    expect(screen.getByLabelText("Description")).not.toBeRequired();
  });
});
