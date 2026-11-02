import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture, jsonResponse } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AppLayout } from "./AppLayout";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderLayout(session: ReturnType<typeof authFixture>) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(session));
  renderWithClient(<AppLayout>content</AppLayout>);
}

describe("AppLayout", () => {
  it("offers Users to an administrator", async () => {
    renderLayout(authFixture());
    expect(await screen.findByRole("link", { name: "Users" })).toHaveAttribute("href", "/users");
  });

  it("hides Users from a member", async () => {
    renderLayout(authFixture({ is_admin: false }));
    await screen.findByRole("button", { name: /Account/ });
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
  });
});
