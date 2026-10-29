import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { CodebasesTable } from "./CodebasesTable";

const ORG = teamFixture.organization_id;
const CODEBASE = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  organization_id: ORG,
  name: "acme/api",
  url: "https://github.com/acme/api",
  team_id: null,
  production_environment: "production",
  last_synced_at: null,
  pull_requests: 4,
  deployments: 2,
};

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url === `/api/codebases?organization_id=${ORG}`) return jsonResponse([CODEBASE]);
    if (url === "/api/teams")
      return jsonResponse([
        teamFixture,
        { ...teamFixture, id: "other", organization_id: "x", name: "Elsewhere" },
      ]);
    if (url === `/api/codebases/${CODEBASE.id}` && init?.method === "PUT")
      return jsonResponse({ ...CODEBASE, ...(JSON.parse(init.body as string) as object) });
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

const puts = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");

afterEach(() => vi.restoreAllMocks());

describe("CodebasesTable", () => {
  it("lists repositories with the help text", async () => {
    mockApi();

    renderWithClient(<CodebasesTable organizationId={ORG} />);

    const link = await screen.findByRole("link", { name: "acme/api" });
    expect(link).toHaveAttribute("href", "https://github.com/acme/api");
    expect(screen.getByText("Only repositories mapped to a team are synced.")).toBeInTheDocument();
  });

  it("maps a repository to a team", async () => {
    const fetchMock = mockApi();

    renderWithClient(<CodebasesTable organizationId={ORG} />);
    fireEvent.mouseDown(await screen.findByRole("combobox", { name: "Team for acme/api" }));
    expect(screen.queryByTitle("Elsewhere")).not.toBeInTheDocument();
    fireEvent.click(await screen.findByTitle("Platform"));

    await waitFor(() => expect(puts(fetchMock)).toHaveLength(1));
    const [input, init] = puts(fetchMock)[0];
    expect(requestUrl(input)).toBe(`/api/codebases/${CODEBASE.id}`);
    expect(JSON.parse(init?.body as string)).toEqual({
      team_id: teamFixture.id,
      production_environment: "production",
    });
  });

  it("saves the production environment on blur only when changed", async () => {
    const fetchMock = mockApi();

    renderWithClient(<CodebasesTable organizationId={ORG} />);
    const input = await screen.findByRole("textbox", {
      name: "Production environment for acme/api",
    });
    fireEvent.blur(input);
    expect(puts(fetchMock)).toHaveLength(0);

    fireEvent.change(input, { target: { value: "prod-eu" } });
    fireEvent.blur(input);

    await waitFor(() => expect(puts(fetchMock)).toHaveLength(1));
    expect(JSON.parse(puts(fetchMock)[0][1]?.body as string)).toEqual({
      team_id: null,
      production_environment: "prod-eu",
    });
  });

  it("shows an error when saving fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = requestUrl(input);
      if (init?.method === "PUT") return jsonResponse({ detail: "nope" }, 422);
      if (url.startsWith("/api/codebases")) return jsonResponse([CODEBASE]);
      return jsonResponse([teamFixture]);
    });

    renderWithClient(<CodebasesTable organizationId={ORG} />);
    const input = await screen.findByRole("textbox", {
      name: "Production environment for acme/api",
    });
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.blur(input);

    expect(await screen.findByText("nope")).toBeInTheDocument();
  });
});
