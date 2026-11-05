import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithClient } from "../test/render";
import { CredentialsSection } from "./CredentialsSection";

const SAVED = new Date(Date.now() - 2 * 3600_000).toISOString();

function renderSection({
  configured = true,
  stored = "…y7ll",
  updatedAt = SAVED,
}: { configured?: boolean; stored?: string | null; updatedAt?: string | null } = {}) {
  return renderWithClient(
    <CredentialsSection
      integration="linear"
      label="Linear"
      fields={[{ name: "api_key", label: "Linear API key", secret: true, stored }]}
      initial={{}}
      status={{ configured, hint: stored, updated_at: updatedAt }}
    />,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("CredentialsSection", () => {
  it("keeps the relative time current while the page stays open", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = renderSection({ updatedAt: new Date().toISOString() });
    expect(screen.getByText("a few seconds ago")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(2 * 60_000));

    expect(screen.getByText("2 minutes ago")).toBeInTheDocument();
    const clear = vi.spyOn(globalThis, "clearInterval");
    unmount();
    expect(clear).toHaveBeenCalled();
  });

  it("shows which key is stored and when it was saved", () => {
    renderSection();

    expect(screen.getByText("…y7ll")).toHaveClass("fig");
    expect(screen.getByText("2 hours ago")).toBeInTheDocument();
  });

  it("labels the stored key apart from the field that replaces it", () => {
    renderSection();

    expect(screen.getByText("Stored Linear API key")).toBeInTheDocument();
  });

  it("says a short key is stored even when no characters can show", () => {
    renderSection({ stored: "…" });

    expect(screen.getByText("(key too short to show)")).toBeInTheDocument();
  });

  it("shows no stored key when none is configured", () => {
    renderSection({ configured: false, stored: null, updatedAt: null });

    expect(screen.queryByText("Key entered")).not.toBeInTheDocument();
  });

  it("shows a missing stored hint as a bare ellipsis", () => {
    renderSection({ stored: null });

    expect(screen.getByText("…")).toHaveClass("fig");
  });
});
