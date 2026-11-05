import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ConnectorsPage } from "./ConnectorsPage";

const ACME = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Acme",
  created_at: "2026-07-01T00:00:00Z",
};
const GLOBEX = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Globex",
  created_at: "2026-07-02T00:00:00Z",
};

const job = (state: string, trigger = "manual", extra: object = {}) => ({
  id: "job1",
  organization_id: ACME.id,
  kind: "organization",
  trigger,
  state,
  phase: null,
  error: null,
  summary: null,
  ...extra,
});

function succeededJob() {
  return jsonResponse(
    job("succeeded", "manual", {
      summary: { teams: 1, projects: 2, work_items: 3, events: 42, divergences: 7, deleted: 9 },
    }),
  );
}

const THREE_DAYS_AGO = new Date(Date.now() - 3 * 24 * 3600_000).toISOString();

const OUTCOME = "Updated 1 team · 2 projects · 3 work items · 42 events · 9 work items removed";

const GITHUB = {
  configured: true,
  owner: "acme",
  hint: "…abcd",
  updated_at: THREE_DAYS_AGO,
  running: null,
};
const DATADOG = {
  configured: true,
  site: "datadoghq.com",
  hint: "…aaaa",
  application_key_hint: "…bbbb",
  updated_at: THREE_DAYS_AGO,
  running: null,
};

/** Configured GitHub and Datadog: their status, credentials save and empty tables. */
function codeHostResponse(url: string): Response | undefined {
  if (url.startsWith("/api/connectors/github")) return jsonResponse(GITHUB);
  if (url.startsWith("/api/connectors/datadog")) return jsonResponse(DATADOG);
  if (url.startsWith("/api/codebases") || url === "/api/teams") return jsonResponse([]);
  return undefined;
}

function mockApi({
  configured,
  codeHosts = false,
  running = false,
  syncPolls = [],
  organizations = [ACME],
  statusPending = false,
  organizationsAfterSync = organizations,
  scheduleAfterSync = null,
  githubRunning = null,
  hint = configured ? "…abcd" : null,
  putResponse,
  calls = [],
}: {
  /** GitHub and Datadog configured (default: GitHub unconfigured, Datadog unanswered). */
  codeHosts?: boolean;
  githubRunning?: object | null;
  hint?: string | null;
  /** What PUT …/linear/credentials answers; default: stores the key. */
  putResponse?: Response;
  /** Records every credentials request as "METHOD url body". */
  calls?: string[];
  configured: boolean;
  running?: boolean;
  /** Job poll answers in order; the last one repeats. Default: succeeded. */
  syncPolls?: Response[];
  organizations?: (typeof ACME)[];
  statusPending?: boolean;
  /** What the server returns once a Sync now has finished. */
  organizationsAfterSync?: (typeof ACME)[];
  scheduleAfterSync?: object | null;
}) {
  let synced = false;
  let linear = { configured, hint, updated_at: configured ? THREE_DAYS_AGO : null };
  const polls = syncPolls.length > 0 ? [...syncPolls] : [succeededJob()];
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    const codeHost = codeHosts ? codeHostResponse(url) : undefined;
    if (codeHost) return codeHost;
    if (url === "/api/connectors/linear")
      return statusPending
        ? new Promise<Response>(() => {})
        : jsonResponse({ ...linear, running: running ? job("running", "auto") : githubRunning });
    if (url === "/api/connectors/linear/credentials") {
      calls.push(`${init?.method} ${url} ${(init?.body as string | undefined) ?? ""}`.trim());
      if (init?.method === "DELETE") linear = { configured: false, hint: null, updated_at: null };
      else if (putResponse) return putResponse;
      else {
        const { api_key } = JSON.parse(init?.body as string) as { api_key: string };
        linear = {
          configured: true,
          hint: `…${api_key.slice(-4)}`,
          updated_at: new Date().toISOString(),
        };
      }
      return jsonResponse({ ...linear, running: null });
    }
    if (url === "/api/connectors/openrouter")
      return jsonResponse({
        configured: true,
        model: "anthropic/claude-sonnet-5",
        hint: "…or00",
        updated_at: THREE_DAYS_AGO,
      });
    if (url === "/api/connectors/github")
      return jsonResponse({ configured: false, owner: null, running: githubRunning });
    if (url === "/api/organizations")
      return jsonResponse(synced ? organizationsAfterSync : organizations);
    if (url === "/api/connectors/linear/sync") {
      synced = true;
      return jsonResponse(job("running"), 202);
    }
    if (url === "/api/connectors/linear/jobs/job1") {
      const next = polls.length > 1 ? polls.shift() : polls[0];
      return (next as Response).clone();
    }
    if (url.endsWith("/sync-schedule") && init?.method === "PUT")
      return jsonResponse({
        ...(JSON.parse(init.body as string) as object),
        updated_at: "2026-10-07T13:00:00Z",
        last_run: null,
        last_manual_sync_at: null,
        next_run_at: null,
      });
    if (url.endsWith("/sync-schedule")) return jsonResponse(synced ? scheduleAfterSync : null);
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** The Linear card: GitHub and OpenRouter have "Not configured" badges of their own. */
function linearCard(): HTMLElement {
  return screen.getByText("Linear").closest(".ant-card") as HTMLElement;
}

/** The Linear card's credentials form. */
function linearForm(): HTMLElement {
  return screen.getByLabelText("Linear API key").closest("form") as HTMLElement;
}

describe("ConnectorsPage", () => {
  it("saves a Linear key", async () => {
    const calls: string[] = [];
    mockApi({ configured: false, calls });

    renderWithClient(<ConnectorsPage />);
    const field = await screen.findByLabelText("Linear API key");
    fireEvent.change(field, { target: { value: "lin_api_new1" } });
    fireEvent.click(within(linearForm()).getByRole("button", { name: "Save key" }));

    expect(await within(linearCard()).findByText("…new1")).toBeInTheDocument();
    expect(within(linearCard()).getByText("Configured")).toBeInTheDocument();
    expect(calls).toEqual(['PUT /api/connectors/linear/credentials {"api_key":"lin_api_new1"}']);
    expect(screen.getByLabelText("Linear API key")).toHaveValue("");
    expect(screen.getByText("Key saved")).toBeInTheDocument();
  });

  it("shows why a key was rejected", async () => {
    const detail = "Could not verify the Linear credentials: Linear API returned HTTP 400";
    mockApi({ configured: false, putResponse: jsonResponse({ detail }, 422) });

    renderWithClient(<ConnectorsPage />);
    const field = await screen.findByLabelText("Linear API key");
    fireEvent.change(field, { target: { value: "lin_api_bad" } });
    fireEvent.click(within(linearForm()).getByRole("button", { name: "Save key" }));

    expect(await screen.findByText("Could not save the Linear key")).toBeInTheDocument();
    expect(screen.getByText(detail)).toBeInTheDocument();
    expect(within(linearCard()).getByText("Not configured")).toBeInTheDocument();
  });

  it("removes a stored key after confirming", async () => {
    const calls: string[] = [];
    mockApi({ configured: true, calls });

    renderWithClient(<ConnectorsPage />);
    await screen.findByLabelText("Linear API key");
    fireEvent.click(within(linearForm()).getByRole("button", { name: "Remove key" }));
    expect(await screen.findByText("Remove the Linear key?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(await within(linearCard()).findByText("Not configured")).toBeInTheDocument();
    expect(calls).toEqual(["DELETE /api/connectors/linear/credentials"]);
    expect(within(linearCard()).queryByText("…abcd")).not.toBeInTheDocument();
    expect(within(linearCard()).queryByText("Key entered")).not.toBeInTheDocument();
  });

  it("shows the new save time when a key with the same ending replaces the stored one", async () => {
    mockApi({ configured: true, hint: "…abcd" });

    renderWithClient(<ConnectorsPage />);
    expect(await within(linearCard()).findByText("3 days ago")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Linear API key"), {
      target: { value: "lin_api_other_abcd" },
    });
    fireEvent.click(within(linearForm()).getByRole("button", { name: "Save key" }));

    expect(await within(linearCard()).findByText("a few seconds ago")).toBeInTheDocument();
    expect(within(linearCard()).getByText("Key entered")).toBeInTheDocument();
    expect(within(linearCard()).getByText("…abcd")).toBeInTheDocument();
  });

  it("never shows the stored key", async () => {
    mockApi({ configured: true, hint: "…abcd" });

    renderWithClient(<ConnectorsPage />);

    const field = await screen.findByLabelText("Linear API key");
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", "Enter a new key to replace the stored one");
  });

  it("shows the AI advisor card", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("AI advisor (OpenRouter)")).toBeInTheDocument();
    expect(await screen.findByText("…or00")).toBeInTheDocument();
  });

  it("shows configured status and the sync outcome in one line", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    expect(await within(linearCard()).findByText("…abcd")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    expect(await screen.findByText(OUTCOME)).toBeInTheDocument();
  });

  it("shows the job's error when the sync fails", async () => {
    mockApi({
      configured: true,
      syncPolls: [jsonResponse(job("failed", "manual", { error: "Linear timed out" }))],
    });

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByText("Linear timed out")).toBeInTheDocument();
  });

  it("says the sync was interrupted when the job is gone after a restart", async () => {
    mockApi({ configured: true, syncPolls: [jsonResponse({ detail: "Not found" }, 404)] });

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByText(/Sync was interrupted: Atlas restarted/)).toBeInTheDocument();
  });

  it("shows the sync status and the auto-sync card for the selected organization", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Next run")).toBeInTheDocument();
    expect(await screen.findByText("Not scheduled")).toBeInTheDocument();
    expect(screen.getByText("Auto sync")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save schedule" })).toBeInTheDocument();
  });

  it("says a running sync's result shows on Sync now", async () => {
    mockApi({ configured: true, running: true });

    renderWithClient(<ConnectorsPage />);

    expect(
      await screen.findByText("A sync is running; Sync now shows its result."),
    ).toBeInTheDocument();
  });

  it("shows the GitHub card and keeps a running GitHub job off the Linear card", async () => {
    mockApi({ configured: true, githubRunning: job("running", "manual", { kind: "code" }) });

    renderWithClient(<ConnectorsPage />);

    // The card remounts once the organization list loads (its key changes).
    await screen.findByRole("combobox", { name: "Organization" });
    expect(await screen.findByText("A GitHub sync is running.")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.queryByText(/Sync now shows its result/)).not.toBeInTheDocument();
  });

  it("renders each connector card once, also after the page updates", async () => {
    mockApi({ configured: true });

    const { container } = renderWithClient(<ConnectorsPage />);
    await screen.findByRole("combobox", { name: "Organization" });
    await screen.findByText("Auto sync");
    // A saved key refetches the statuses and renders the cards again.
    fireEvent.change(screen.getByLabelText("Linear API key"), {
      target: { value: "lin_api_new1" },
    });
    fireEvent.click(within(linearForm()).getByRole("button", { name: "Save key" }));
    await screen.findByText("Key saved");

    const titles = [...container.querySelectorAll(".ant-card-head-title")].map(
      (title) => title.textContent,
    );
    expect(titles).toEqual(["Linear", "GitHub", "Datadog", "Auto sync", "AI advisor (OpenRouter)"]);
  });

  it("hides the running-sync hint once this page's own sync has finished", async () => {
    mockApi({ configured: true, running: true });

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(await screen.findByText(OUTCOME)).toBeInTheDocument();
    expect(screen.queryByText(/A sync is running/)).not.toBeInTheDocument();
  });

  it("polls the Linear status so a running auto sync shows up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockApi({ configured: true });
    const statusCalls = () =>
      fetchMock.mock.calls.filter(([input]) => requestUrl(input) === "/api/connectors/linear")
        .length;

    renderWithClient(<ConnectorsPage />);
    await waitFor(() => expect(statusCalls()).toBe(1));

    await vi.advanceTimersByTimeAsync(15_000);

    await waitFor(() => expect(statusCalls()).toBe(2));
  });

  it("does not carry a saved message over to another organization", async () => {
    mockApi({ configured: true, organizations: [ACME, GLOBEX] });

    renderWithClient(<ConnectorsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Save schedule" }));
    expect(await screen.findByText("Schedule saved")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Organization" }));
    fireEvent.click(await screen.findByTitle("Globex"));

    // Globex has no schedule: wait for its form, not the loading skeleton.
    expect(await screen.findByText("Not scheduled")).toBeInTheDocument();
    expect(screen.queryByText("Schedule saved")).not.toBeInTheDocument();
  });

  it("does not carry a GitHub or Datadog save message over to another organization", async () => {
    mockApi({ configured: true, organizations: [ACME, GLOBEX], codeHosts: true });
    const card = (title: string) =>
      screen
        .getByText(title, { selector: ".ant-card-head-title" })
        .closest(".ant-card") as HTMLElement;

    renderWithClient(<ConnectorsPage />);
    await screen.findByRole("combobox", { name: "Organization" });
    // GitHub keeps its stored token; Datadog needs both keys on every save.
    fireEvent.click(await within(card("GitHub")).findByRole("button", { name: "Save" }));
    expect(await within(card("GitHub")).findByText("Saved")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Datadog API key"), {
      target: { value: "dd_api_key_0000aaaa" },
    });
    fireEvent.change(screen.getByLabelText("Application key"), {
      target: { value: "dd_app_key_0000bbbb" },
    });
    fireEvent.click(within(card("Datadog")).getByRole("button", { name: "Save" }));
    expect(await within(card("Datadog")).findByText("Saved")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Organization" }));
    fireEvent.click(await screen.findByTitle("Globex"));

    await waitFor(() =>
      expect(within(card("GitHub")).queryByText("Saved")).not.toBeInTheDocument(),
    );
    expect(within(card("Datadog")).queryByText("Saved")).not.toBeInTheDocument();
  });

  it("warns once, at page level, and disables sync when not configured", async () => {
    mockApi({ configured: false });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Linear isn't configured")).toBeInTheDocument();
    expect(screen.getAllByText(/Add a Linear personal API key below/)).toHaveLength(1);
    expect(screen.getByText(/Security & access → Personal API keys/)).toBeInTheDocument();
    expect(screen.getByText(/scheduled syncs fail/)).toBeInTheDocument();
    expect(within(linearCard()).getByText("Not configured")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Sync now/ })).toBeDisabled();
  });

  it("neither warns nor says 'Not configured' while the status is unknown", async () => {
    mockApi({ configured: false, statusPending: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Connectors")).toBeInTheDocument();
    expect(screen.queryByText("Linear isn't configured")).not.toBeInTheDocument();
    expect(within(linearCard()).queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("refreshes the last sync after Sync now", async () => {
    mockApi({
      configured: true,
      scheduleAfterSync: {
        enabled: false,
        days: [1],
        window_start: "09:00:00",
        window_end: "17:00:00",
        interval_minutes: 60,
        timezone: "UTC",
        updated_at: "2026-10-07T12:00:00Z",
        last_run: null,
        last_manual_sync_at: "2026-10-08T12:00:00Z",
        next_run_at: null,
      },
    });

    renderWithClient(<ConnectorsPage />);
    expect(await screen.findByText("Not recorded")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    expect(await screen.findByText("08-10-2026 12:00 (UTC) · manual")).toBeInTheDocument();
  });

  it("clears the sync outcome when another organization is picked", async () => {
    mockApi({ configured: true, organizations: [ACME, GLOBEX] });

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    const outcome = /^Updated 1 team/;
    expect(await screen.findByText(outcome)).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Organization" }));
    fireEvent.click(await screen.findByTitle("Globex"));

    await waitFor(() => expect(screen.queryByText(outcome)).not.toBeInTheDocument());
  });

  it("keeps the outcome of a first sync that created the organization", async () => {
    mockApi({ configured: true, organizations: [], organizationsAfterSync: [ACME] });

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    // The new organization becomes the selection without anyone picking it.
    expect(await screen.findByRole("combobox", { name: "Organization" })).toBeInTheDocument();
    expect(screen.getByText(/^Updated 1 team/)).toBeInTheDocument();
  });

  it("shows an error when sync fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") return jsonResponse({ configured: true });
      if (url === "/api/organizations")
        return jsonResponse([
          {
            id: "11111111-1111-1111-1111-111111111111",
            name: "Acme",
            created_at: "2026-07-01T00:00:00Z",
          },
        ]);
      if (url === "/api/connectors/linear/sync") return jsonResponse({ detail: "boom" }, 500);
      if (url.endsWith("/sync-schedule")) return jsonResponse(null);
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText("Sync failed")).toBeInTheDocument());
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("shows an error instead of 'Not configured' when the status fetch fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") {
        return jsonResponse({ detail: "boom" }, 500);
      }
      if (url === "/api/organizations") return jsonResponse([]);
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() =>
      expect(screen.getByText("Failed to load connector status")).toBeInTheDocument(),
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("enables sync with no organizations and bootstraps one from Linear", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") return jsonResponse({ configured: true });
      if (url === "/api/organizations") return jsonResponse([]);
      if (url === "/api/connectors/linear/sync") {
        expect(JSON.parse(init?.body as string)).toEqual({ organization_id: null });
        return jsonResponse(job("running"), 202);
      }
      if (url === "/api/connectors/linear/jobs/job1")
        return jsonResponse(
          job("succeeded", "manual", {
            summary: {
              teams: 1,
              projects: 0,
              work_items: 0,
              events: 0,
              divergences: 0,
              deleted: 0,
            },
          }),
        );
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() => expect(screen.getByText(/first sync will create/i)).toBeInTheDocument());
    expect(screen.queryByRole("combobox", { name: "Organization" })).not.toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Sync now/ });
    expect(button).toBeEnabled();

    fireEvent.click(button);

    expect(await screen.findByText("Updated 1 team")).toBeInTheDocument();
    const orgCalls = fetchMock.mock.calls.filter(
      (call) => requestUrl(call[0]) === "/api/organizations",
    );
    expect(orgCalls.length).toBeGreaterThan(1); // invalidated + refetched after sync
  });
});
