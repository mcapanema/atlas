import { focusManager } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { GitHubConnectorCard } from "./GitHubConnectorCard";

const ORG = "11111111-1111-1111-1111-111111111111";

const job = (state: string, extra: object = {}) => ({
  id: "job1",
  organization_id: ORG,
  kind: "code",
  trigger: "manual",
  state,
  phase: null,
  error: null,
  summary: null,
  code_summary: null,
  ...extra,
});

const SUCCEEDED = job("succeeded", {
  code_summary: { codebases: 2, pull_requests: 5, deployments: 1, events: 7 },
});

function mockApi({
  configured,
  running = null,
  polled = SUCCEEDED,
}: {
  configured: boolean;
  running?: object | null;
  polled?: object;
}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/github")
      return jsonResponse({ configured, owner: configured ? "acme" : null, running });
    if (url === "/api/connectors/github/sync") return jsonResponse(job("running"), 202);
    if (url === "/api/connectors/github/jobs/job1") return jsonResponse(polled);
    if (url.startsWith("/api/codebases")) return jsonResponse([]);
    if (url === "/api/teams") return jsonResponse([]);
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  focusManager.setFocused(undefined);
});

describe("GitHubConnectorCard", () => {
  it("shows the setup alert while GitHub is unconfigured", async () => {
    mockApi({ configured: false });

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);

    expect(await screen.findByText("GitHub isn't configured")).toBeInTheDocument();
    expect(screen.getByText("ATLAS_GITHUB_TOKEN")).toBeInTheDocument();
    expect(screen.getByText("ATLAS_GITHUB_OWNER")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Sync GitHub/ })).toBeDisabled();
  });

  it("syncs and shows the outcome", async () => {
    const fetchMock = mockApi({ configured: true });

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);
    const button = await screen.findByRole("button", { name: /Sync GitHub/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(
      await screen.findByText(
        "Updated 2 codebases · 5 pull requests · 1 deployments · 7 work item events",
      ),
    ).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => requestUrl(input));
    expect(urls).toContain("/api/connectors/github/sync");
    expect(urls).toContain("/api/connectors/github/jobs/job1");
  });

  it("shows a running GitHub sync", async () => {
    mockApi({ configured: true, running: job("running") });

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);

    expect(await screen.findByText("A GitHub sync is running.")).toBeInTheDocument();
  });

  it("disables the button while a Linear sync runs", async () => {
    mockApi({ configured: true, running: job("running", { kind: "organization" }) });

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);

    expect(await screen.findByText(/Another sync is running/)).toBeInTheDocument();
    expect(screen.queryByText("A GitHub sync is running.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sync GitHub/ })).toBeDisabled();
  });

  it("shows the job's error when the sync fails", async () => {
    mockApi({ configured: true, polled: job("failed", { error: "bad token" }) });

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);
    const button = await screen.findByRole("button", { name: /Sync GitHub/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByText("bad token")).toBeInTheDocument();
  });

  it("clears the running note and enables the button after its own sync fails", async () => {
    // The status poll caught this card's job running; the job then failed.
    let serverRunning: object | null = null;
    let polls = 0;
    let failed = false;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/github")
        return jsonResponse({ configured: true, owner: "acme", running: serverRunning });
      if (url === "/api/connectors/github/sync") {
        serverRunning = job("running");
        return jsonResponse(job("running"), 202);
      }
      if (url === "/api/connectors/github/jobs/job1") {
        polls += 1;
        if (!failed) return jsonResponse(job("running"));
        serverRunning = null;
        return jsonResponse(job("failed", { error: "bad token" }));
      }
      if (url.startsWith("/api/codebases")) return jsonResponse([]);
      if (url === "/api/teams") return jsonResponse([]);
      throw new Error(`Unexpected fetch: ${url}`);
    });
    const statusCalls = () =>
      fetchMock.mock.calls.filter(([input]) => requestUrl(input) === "/api/connectors/github")
        .length;

    renderWithClient(<GitHubConnectorCard organizationId={ORG} />);
    const button = await screen.findByRole("button", { name: /Sync GitHub/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(polls).toBe(1));
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await waitFor(() => expect(statusCalls()).toBe(2));
    failed = true;

    expect(await screen.findByText("bad token", {}, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByText("A GitHub sync is running.")).not.toBeInTheDocument();
    expect(statusCalls()).toBe(3);
  });
});
