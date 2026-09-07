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

// Browser credential autofill belongs to the login page only. Chrome ignores
// autocomplete="off" on password fields and offers saved logins to any of
// them, so the primitive has to speak the values browsers honour.
describe("Input — autofill is opt-in", () => {
  const optOuts = ["data-1p-ignore", "data-lpignore", "data-bwignore", "data-form-type"];

  it("defaults a plain field to autocomplete off with the password-manager opt-outs", () => {
    render(<Input aria-label="Model id" />);
    const el = screen.getByLabelText("Model id");
    expect(el).toHaveAttribute("autocomplete", "off");
    for (const a of optOuts) expect(el).toHaveAttribute(a);
  });

  it("defaults a password field to new-password (the value browsers honour) with the opt-outs", () => {
    render(<Input aria-label="API key" type="password" />);
    const el = screen.getByLabelText("API key");
    expect(el).toHaveAttribute("autocomplete", "new-password");
    for (const a of optOuts) expect(el).toHaveAttribute(a);
  });

  it("upgrades an explicit off on a password field to new-password — off is ignored by browsers", () => {
    render(<Input aria-label="Secret" type="password" autoComplete="off" />);
    expect(screen.getByLabelText("Secret")).toHaveAttribute("autocomplete", "new-password");
  });

  it("passes credential hints through untouched and without opt-outs — the login page keeps autofill", () => {
    render(
      <>
        <Input aria-label="Email" type="email" autoComplete="email" />
        <Input aria-label="Password" type="password" autoComplete="current-password" />
        <Input aria-label="New password" type="password" autoComplete="new-password" />
      </>,
    );
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    for (const name of ["Email", "Password", "New password"]) {
      for (const a of optOuts) expect(screen.getByLabelText(name)).not.toHaveAttribute(a);
    }
  });
});
