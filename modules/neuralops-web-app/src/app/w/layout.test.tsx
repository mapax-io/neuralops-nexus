import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useConnectionStore } from "@/stores/connection.store";
import WorkspaceLayout from "./layout";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/w",
}));

beforeEach(() => {
  useConnectionStore.setState({ hydrated: false, token: null, serverUrl: null, connection: null });
});

describe("WorkspaceLayout — before the session is known", () => {
  it("shows the full-page loader with the app mark, never a bare skeleton box", () => {
    const { container } = render(
      <WorkspaceLayout>
        <div>workspace content</div>
      </WorkspaceLayout>,
    );
    const status = screen.getByRole("status", { name: /loading/i });
    expect(status).toBeInTheDocument();
    expect(status.querySelector("svg")).not.toBeNull(); // the mark, not an empty rectangle
    expect(container.querySelector(".nx-shimmer")).toBeNull();
    expect(screen.queryByText("workspace content")).not.toBeInTheDocument();
  });
});
