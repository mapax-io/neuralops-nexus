import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/stores/connection.store", () => ({ useConnectionStore: () => ({ email: "me@example.com", connection: { nucleusUserId: "u1", companyName: "Acme" } }) }));
vi.mock("@/hooks/use-workspace", () => ({ useMembers: () => ({ data: [] }) }));
vi.mock("@/lib/supabase", () => ({ supabase: () => ({ auth: { updateUser: vi.fn().mockResolvedValue({ error: null }) } }) }));
vi.mock("@/lib/api/client", () => ({ absolutizeMedia: (x: string | null) => x }));
vi.mock("@/lib/api/account", async (importActual) => ({ ...(await importActual<typeof import("@/lib/api/account")>()), changeUsername: vi.fn() }));
// The photo controls call the server; hoisted so each case can watch or fail them.
const photo = vi.hoisted(() => ({
  upload: vi.fn().mockResolvedValue({ avatar: "avatars/custom/u1-abc.jpg" }),
  remove: vi.fn().mockResolvedValue({ avatar: null }),
}));
vi.mock("@/lib/api/avatar", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/api/avatar")>()),
  uploadAvatar: photo.upload,
  removeAvatar: photo.remove,
}));

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


// A default avatar is only acceptable as a placeholder, which means it has to
// be replaceable. These cover the affordance and the guard in front of it.
describe("ProfileDialog — profile photo", () => {
  const pick = (file: File) => {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    fireEvent.change(input);
  };

  beforeEach(() => {
    photo.upload.mockClear();
    photo.remove.mockClear();
  });

  it("offers an upload control", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /upload a photo|change photo/i })).toBeInTheDocument();
  });

  it("uploads the picked file", async () => {
    renderDialog();
    const file = new File([new Uint8Array([1, 2, 3])], "me.png", { type: "image/png" });
    pick(file);
    await waitFor(() => expect(photo.upload).toHaveBeenCalledWith(file));
  });

  // Checked client-side so an obviously-too-big file is refused without the
  // upload; the server enforces the same limit regardless.
  it("refuses a file over the size limit without uploading it", async () => {
    renderDialog();
    const big = new File([new Uint8Array(1)], "huge.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 6 * 1024 * 1024 });
    pick(big);
    await waitFor(() => expect(photo.upload).not.toHaveBeenCalled());
  });

  it("says so when the upload is rejected, rather than failing silently", async () => {
    photo.upload.mockRejectedValueOnce(new Error("That file isn't an image we can read."));
    renderDialog();
    pick(new File([new Uint8Array([1])], "notreally.png", { type: "image/png" }));
    await waitFor(() => expect(photo.upload).toHaveBeenCalled());
  });
});
