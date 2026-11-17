import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { CreateMcpTokenModal } from "./CreateMcpTokenModal";

afterEach(() => {
  vi.restoreAllMocks();
});

const issued = {
  id: "t1",
  name: "Claude Code",
  access: "read",
  hint: "wxyz",
  created_at: "2026-11-17T10:00:00Z",
  last_used_at: null,
  token: "atlas_mcp_secretwxyz",
};

function submitDefault() {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claude Code" } });
  fireEvent.click(screen.getByRole("button", { name: "Create token" }));
}

describe("CreateMcpTokenModal", () => {
  it("posts a read token by default and shows the token with the connect commands", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(issued, 201));
    renderWithClient(<CreateMcpTokenModal onClose={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /^Read(?! and)/ })).toBeChecked();
    submitDefault();
    expect(await screen.findByText(/Copy this token now/)).toBeInTheDocument();
    expect(requestUrl(spy.mock.calls[0][0])).toBe("/api/mcp-tokens");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ name: "Claude Code", access: "read" }),
    );
    const origin = window.location.origin;
    expect(
      screen.getByText(`claude mcp add --transport http atlas ${origin}/mcp/atlas_mcp_secretwxyz/`),
    ).toBeInTheDocument();
    expect(screen.getByText(`cloudflared tunnel --url ${origin}`)).toBeInTheDocument();
    expect(screen.getByText("https://<tunnel-host>/mcp/atlas_mcp_secretwxyz/")).toBeInTheDocument();
    expect(screen.getByText(`${origin}/mcp/atlas_mcp_secretwxyz/`)).toBeInTheDocument();
  });

  it("can ask for read and change settings access", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(issued, 201));
    renderWithClient(<CreateMcpTokenModal onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Read and change settings/ }));
    submitDefault();
    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    expect(JSON.parse(spy.mock.calls[0][1]?.body as string)).toMatchObject({
      access: "read_write",
    });
  });

  it("closes from Done", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(issued, 201));
    const onClose = vi.fn();
    renderWithClient(<CreateMcpTokenModal onClose={onClose} />);
    submitDefault();
    fireEvent.click(await screen.findByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a failure and stays on step 1", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "nope" }, 500));
    renderWithClient(<CreateMcpTokenModal onClose={vi.fn()} />);
    submitDefault();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/Copy this token now/)).toBeNull();
  });
});
