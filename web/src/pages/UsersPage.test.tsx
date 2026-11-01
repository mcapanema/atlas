import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture, jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { UsersPage } from "./UsersPage";

afterEach(() => {
  vi.restoreAllMocks();
});

const admin = authFixture().user!;
const ana = {
  id: "66666666-6666-6666-6666-666666666666",
  email: "ana@acme.com",
  name: "Ana",
  is_admin: false,
  created_at: "2026-10-31T10:30:00Z",
};

function mockApi(session = authFixture()) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = requestUrl(input);
    if (url === "/api/auth/session") return Promise.resolve(jsonResponse(session));
    if (url === "/api/users" && !init?.method) return Promise.resolve(jsonResponse([admin, ana]));
    if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

describe("UsersPage", () => {
  it("lists the accounts with a text role", async () => {
    mockApi();
    renderWithClient(<UsersPage />);
    const row = (await screen.findByText("ana@acme.com")).closest("tr")!;
    expect(within(row).getByText("Member")).toBeInTheDocument();
    const adminRow = screen.getByText("admin@atlas.local").closest("tr")!;
    expect(within(adminRow).getAllByRole("cell")[2]).toHaveTextContent("Admin");
    for (const header of ["Name", "Email", "Role", "Created"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
  });

  it("marks the signed-in admin's row You and offers no Remove there", async () => {
    mockApi();
    renderWithClient(<UsersPage />);
    const adminRow = (await screen.findByText("admin@atlas.local")).closest("tr")!;
    expect(within(adminRow).getByText("You")).toBeInTheDocument();
    expect(within(adminRow).queryByRole("button", { name: "Remove" })).toBeNull();
    const anaRow = screen.getByText("ana@acme.com").closest("tr")!;
    expect(within(anaRow).getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(within(anaRow).getByRole("button", { name: "Reset password" })).toBeInTheDocument();
  });

  it("removes an account after confirmation", async () => {
    const spy = mockApi();
    renderWithClient(<UsersPage />);
    const row = (await screen.findByText("ana@acme.com")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText("Remove Ana? Their sessions end now.")).toBeInTheDocument();
    expect(spy.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    await waitFor(() => {
      const call = spy.mock.calls.find(([, init]) => init?.method === "DELETE");
      expect(requestUrl(call![0])).toBe(`/api/users/${ana.id}`);
    });
  });

  it("opens the reset dialog for the chosen account", async () => {
    mockApi();
    renderWithClient(<UsersPage />);
    const row = (await screen.findByText("ana@acme.com")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText("Reset password for Ana")).toBeInTheDocument();
  });

  it("opens the add dialog", async () => {
    mockApi();
    renderWithClient(<UsersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Add user" }));
    expect(await screen.findByLabelText("Administrator")).toBeInTheDocument();
  });

  it("tells a member the page is for administrators and sends no request", async () => {
    const spy = mockApi(authFixture({ is_admin: false }));
    renderWithClient(<UsersPage />);
    expect(await screen.findByText("Only administrators manage users.")).toBeInTheDocument();
    expect(spy.mock.calls.some(([input]) => requestUrl(input) === "/api/users")).toBe(false);
  });

  it("shows the server's reason when the list fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      Promise.resolve(
        requestUrl(input) === "/api/auth/session"
          ? jsonResponse(authFixture())
          : jsonResponse({ detail: "boom" }, 500),
      ),
    );
    renderWithClient(<UsersPage />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("shows the reason when a removal fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = requestUrl(input);
      if (url === "/api/auth/session") return Promise.resolve(jsonResponse(authFixture()));
      if (init?.method === "DELETE") {
        return Promise.resolve(jsonResponse({ detail: "Cannot remove yourself" }, 409));
      }
      return Promise.resolve(jsonResponse([admin, ana]));
    });
    renderWithClient(<UsersPage />);
    const row = (await screen.findByText("ana@acme.com")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));
    fireEvent.click(await screen.findByRole("button", { name: "OK" }));
    expect(await screen.findByText("Cannot remove yourself")).toBeInTheDocument();
  });
});
