import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { TeamSyncButton } from "./TeamSyncButton";

const syncedTeam = { ...teamFixture, external_id: "lt1" };
const summary = {
  teams: 0,
  projects: 0,
  work_items: 3,
  events: 12,
  divergences: 0,
  deleted: 0,
};

const JOB_URL = "/api/connectors/linear/jobs/job1";
const job = (state: "running" | "succeeded" | "failed", extra: object = {}) => ({
  id: "job1",
  organization_id: "org1",
  kind: "team",
  trigger: "manual",
  state,
  phase: null,
  error: null,
  summary: null,
  ...extra,
});

/** Status, the team-sync POST (202) and the job polls, one queued answer per poll. */
function mockApi({
  running = null,
  polls = [],
  post = () => jsonResponse(job("running"), 202),
}: { running?: object | null; polls?: (() => Response)[]; post?: () => Response } = {}) {
  const queue = [...polls];
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/linear")
      return Promise.resolve(jsonResponse({ configured: true, running }));
    if (url === JOB_URL)
      return Promise.resolve((queue.shift() ?? (() => jsonResponse(job("running"))))());
    return Promise.resolve(post());
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("TeamSyncButton", () => {
  it("starts a job, polls it and reports what changed", async () => {
    const fetchMock = mockApi({
      polls: [
        () => jsonResponse(job("running")),
        () => jsonResponse(job("succeeded", { summary })),
      ],
    });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    const button = screen.getByRole("button", { name: /Sync team/ });
    fireEvent.click(button);

    // Two polls, one second apart.
    expect(
      await screen.findByText("Updated 3 work items · 12 events", {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post && requestUrl(post[0])).toBe(`/api/connectors/linear/teams/${syncedTeam.id}/sync`);
    await waitFor(() => expect(button).not.toHaveClass("ant-btn-loading"));
    expect(screen.queryByText(/A sync is running/)).not.toBeInTheDocument();
  });

  it("says when the team was already up to date", async () => {
    mockApi({
      polls: [
        () => jsonResponse(job("succeeded", { summary: { ...summary, work_items: 0, events: 0 } })),
      ],
    });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Already up to date")).toBeInTheDocument();
  });

  it("shows the server's reason when the start is refused", async () => {
    mockApi({ post: () => jsonResponse({ detail: "Linear is not configured" }, 409) });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Linear is not configured")).toBeInTheDocument();
  });

  it("shows the job's error when it fails", async () => {
    mockApi({ polls: [() => jsonResponse(job("failed", { error: "Linear timed out" }))] });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Linear timed out")).toBeInTheDocument();
  });

  it("says the sync was interrupted when the job is gone after a restart", async () => {
    mockApi({ polls: [() => jsonResponse({ detail: "Not found" }, 404)] });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(
      await screen.findByText(
        "Sync was interrupted: Atlas restarted before it finished. Run it again.",
      ),
    ).toBeInTheDocument();
  });

  it("stops polling once a poll fails after a running one", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockApi({
      polls: [() => jsonResponse(job("running")), () => jsonResponse({ detail: "Not found" }, 404)],
    });
    const jobCalls = () =>
      fetchMock.mock.calls.filter(([input]) => requestUrl(input) === JOB_URL).length;

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));
    await waitFor(() => expect(jobCalls()).toBe(1));
    await vi.advanceTimersByTimeAsync(1000);

    expect(await screen.findByText(/Sync was interrupted/)).toBeInTheDocument();
    expect(jobCalls()).toBe(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(jobCalls()).toBe(2);
  });

  it("is disabled for a team made in Atlas", () => {
    mockApi();

    renderWithClient(<TeamSyncButton team={teamFixture} />);

    expect(screen.getByRole("button", { name: /Sync team/ })).toBeDisabled();
  });

  it("says a running sync's result shows here", async () => {
    mockApi({ running: job("running", { trigger: "auto" }) });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);

    expect(
      await screen.findByText("A sync is running; Sync team shows its result."),
    ).toBeInTheDocument();
  });
});
