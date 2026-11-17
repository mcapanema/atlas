import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture, jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AiAccessPage } from "./AiAccessPage";

afterEach(() => {
  vi.restoreAllMocks();
});

const tokens = [
  {
    id: "t1",
    name: "Claude Code",
    access: "read",
    hint: "wxyz",
    created_at: "2026-11-17T10:00:00Z",
    last_used_at: null,
  },
  {
    id: "t2",
    name: "Desktop",
    access: "read_write",
    hint: "abcd",
    created_at: "2026-11-16T10:00:00Z",
    last_used_at: "2026-11-17T09:00:00Z",
  },
];

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = requestUrl(input);
    if (url === "/api/auth/session") return Promise.resolve(jsonResponse(authFixture()));
    if (url === "/api/mcp-tokens" && init?.method === "POST") {
      return Promise.resolve(jsonResponse({ ...tokens[0], token: "atlas_mcp_secretwxyz" }, 201));
    }
    if (url.startsWith("/api/mcp-tokens/")) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(jsonResponse(tokens));
  });
}

describe("AiAccessPage", () => {
  it("lists tokens with access, hint and last use", async () => {
    mockApi();
    renderWithClient(<AiAccessPage />);
    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Read")).toBeInTheDocument();
    expect(screen.getByText("Read and change settings")).toBeInTheDocument();
    expect(screen.getByText("…wxyz")).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("revokes a token after confirmation", async () => {
    const spy = mockApi();
    renderWithClient(<AiAccessPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Revoke Claude Code" }));
    expect(
      screen.getByText("Revoke Claude Code? Its client loses access now."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    await waitFor(() => {
      expect(
        spy.mock.calls.some(
          ([input, init]) =>
            requestUrl(input) === "/api/mcp-tokens/t1" && init?.method === "DELETE",
        ),
      ).toBe(true);
    });
  });

  it("drops the secret from the page when Done is clicked", async () => {
    mockApi();
    renderWithClient(<AiAccessPage />);
    await screen.findByText("Claude Code");
    fireEvent.click(screen.getByRole("button", { name: "Create token" }));
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Claude Code" } });
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Create token" }),
    );
    expect(await screen.findByText(/claude mcp add .*atlas_mcp_secretwxyz/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => {
      expect(screen.queryByText(/atlas_mcp_secretwxyz/)).toBeNull();
    });
  });

  it("drops the secret when step 2 closes with Escape or the Close button", async () => {
    mockApi();
    renderWithClient(<AiAccessPage />);
    await screen.findByText("Claude Code");
    for (const close of ["escape", "button"]) {
      fireEvent.click(screen.getByRole("button", { name: "Create token" }));
      fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Claude Code" } });
      fireEvent.click(
        within(screen.getByRole("dialog")).getByRole("button", { name: "Create token" }),
      );
      await screen.findByText(/claude mcp add .*atlas_mcp_secretwxyz/);
      if (close === "escape") {
        fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", keyCode: 27 });
      } else {
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
      }
      await waitFor(() => {
        expect(screen.queryByText(/atlas_mcp_secretwxyz/)).toBeNull();
      });
    }
  });

  it("shows a load error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "boom" }, 500));
    renderWithClient(<AiAccessPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
