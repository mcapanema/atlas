import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture, jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AccountMenu } from "./AccountMenu";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = requestUrl(input);
    if (url === "/api/auth/session") {
      return Promise.resolve(jsonResponse(authFixture({ name: "Ana" })));
    }
    return Promise.resolve(new Response(null, { status: 204 }));
  });
}

describe("AccountMenu", () => {
  it("shows the user's name beside the account button when expanded", async () => {
    mockApi();
    renderWithClient(<AccountMenu collapsed={false} />);
    const button = await screen.findByRole("button", { name: "Account: Ana" });
    expect(button).toHaveTextContent("Ana");
  });

  it("shows only the icon when collapsed", async () => {
    mockApi();
    renderWithClient(<AccountMenu collapsed />);
    const button = await screen.findByRole("button", { name: "Account: Ana" });
    expect(button).not.toHaveTextContent("Ana");
  });

  it("offers Change password and opens its dialog", async () => {
    mockApi();
    renderWithClient(<AccountMenu collapsed={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Account: Ana" }));
    fireEvent.click(await screen.findByText("Change password"));
    expect(await screen.findByLabelText("Current password")).toBeInTheDocument();
  });

  it("signs out through the menu", async () => {
    const spy = mockApi();
    renderWithClient(<AccountMenu collapsed={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Account: Ana" }));
    fireEvent.click(await screen.findByText("Sign out"));
    const signOut = () =>
      spy.mock.calls.find(([input]) => requestUrl(input) === "/api/auth/sign-out");
    await waitFor(() => {
      expect(signOut()).toBeDefined();
    });
    expect(signOut()?.[1]?.method).toBe("POST");
  });
});
