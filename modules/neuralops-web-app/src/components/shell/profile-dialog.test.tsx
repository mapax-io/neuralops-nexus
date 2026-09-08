import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/stores/connection.store", () => ({ useConnectionStore: () => ({ email: "me@example.com", connection: { nucleusUserId: "u1", companyName: "Acme" } }) }));
vi.mock("@/hooks/use-workspace", () => ({ useMembers: () => ({ data: [] }) }));
vi.mock("@/lib/supabase", () => ({ supabase: () => ({ auth: { updateUser: vi.fn().mockResolvedValue({ error: null }) } }) }));
vi.mock("@/lib/api/client", () => ({ absolutizeMedia: (x: string | null) => x }));
vi.mock("@/lib/api/account", async (importActual) => ({ ...(await importActual<typeof import("@/lib/api/account")>()), changeUsername: vi.fn() }));

import { ProfileDialog } from "./profile-dialog";

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProfileDialog open onClose={() => {}} onSignOut={() => {}} />
    </QueryClientProvider>,
  );
}

describe("ProfileDialog — each form follows its own rules", () => {
  it("Save waits for a valid display name and explains a bad one once visited", () => {
    renderDialog();
    const save = screen.getByRole("button", { name: /^save$/i });
    expect(save).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // a blank form is not covered in red
    const name = screen.getByLabelText(/display name/i);
    fireEvent.change(name, { target: { value: "has space" } });
    expect(save).toBeDisabled();
    fireEvent.blur(name);
    expect(screen.getByRole("alert")).toHaveTextContent(/letters, numbers and underscores/);
    fireEvent.change(name, { target: { value: "tauqeer_h" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(save).toBeEnabled();
  });

  it("Update password waits for eight characters that match, judging each field as it is left", () => {
    renderDialog();
    const update = screen.getByRole("button", { name: /update password/i });
    expect(update).toBeDisabled();
    const pw = screen.getByLabelText("New password");
    const pw2 = screen.getByLabelText("Confirm new password");
    fireEvent.change(pw, { target: { value: "short" } });
    fireEvent.blur(pw);
    expect(screen.getByRole("alert")).toHaveTextContent("Use at least 8 characters.");
    fireEvent.change(pw, { target: { value: "longenough" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(update).toBeDisabled(); // the confirmation is still blank
    fireEvent.change(pw2, { target: { value: "longenougx" } });
    fireEvent.blur(pw2);
    expect(screen.getByRole("alert")).toHaveTextContent("The two passwords don't match.");
    fireEvent.change(pw2, { target: { value: "longenough" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(update).toBeEnabled();
  });
});
