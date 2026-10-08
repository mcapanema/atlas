import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SyncSchedule } from "../api/syncSchedule";
import { defaultSchedule } from "../lib/syncSchedule";
import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AutoSyncCard } from "./AutoSyncCard";

const ORG = "11111111-1111-1111-1111-111111111111";
const SCHEDULE_URL = `/api/organizations/${ORG}/sync-schedule`;
const NEXT_RUN = "2026-10-08T09:00:00Z";

const saved: SyncSchedule = {
  enabled: true,
  days: [1, 3],
  window_start: "09:00:00",
  window_end: "17:00:00",
  interval_minutes: 60,
  timezone: "UTC",
  updated_at: "2026-10-07T12:00:00Z",
  last_run: null,
  last_manual_sync_at: null,
  next_run_at: NEXT_RUN,
};

function mockSchedule(schedule: SyncSchedule | null, onPut?: () => Response) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url !== SCHEDULE_URL) throw new Error(`Unexpected fetch: ${url}`);
    if (init?.method !== "PUT") return jsonResponse(schedule);
    if (onPut) return onPut();
    const body = JSON.parse(init.body as string) as object;
    return jsonResponse({ ...saved, ...body, updated_at: "2026-10-07T13:00:00Z" });
  });
}

function putBody(fetchMock: ReturnType<typeof mockSchedule>): unknown {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return call ? JSON.parse(call[1]?.body as string) : undefined;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("AutoSyncCard", () => {
  it("shows the saved schedule", async () => {
    mockSchedule(saved);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    expect(await screen.findByDisplayValue("09:00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("17:00")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Mon" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Tue" })).not.toBeChecked();
    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("starts a new schedule on weekdays in the browser's zone and saves it", async () => {
    const fetchMock = mockSchedule(null);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    await screen.findByRole("button", { name: "Save schedule" });
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(screen.getByText("Schedule saved")).toBeInTheDocument());
    expect(putBody(fetchMock)).toEqual(defaultSchedule());
  });

  it("saves the days as ISO weekdays, Sunday as 7", async () => {
    const fetchMock = mockSchedule(saved);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "Sun" }));
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(putBody(fetchMock)).toMatchObject({
        days: [1, 3, 7],
        window_start: "09:00",
        window_end: "17:00",
        interval_minutes: 60,
        timezone: "UTC",
      }),
    );
  });

  it("shows the server's reason when a save is rejected", async () => {
    mockSchedule(saved, () =>
      jsonResponse({ detail: "An enabled auto sync needs at least one day" }, 422),
    );

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "Mon" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Wed" }));
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    expect(
      await screen.findByText("An enabled auto sync needs at least one day"),
    ).toBeInTheDocument();
  });

  it("keeps an overnight window as picked so the server can reject it", async () => {
    const fetchMock = mockSchedule(saved, () =>
      jsonResponse(
        { detail: "The window must start before it ends; overnight windows aren't supported" },
        422,
      ),
    );

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    const start = await screen.findByDisplayValue("09:00");
    const end = screen.getByDisplayValue("17:00");
    fireEvent.mouseDown(start);
    fireEvent.change(start, { target: { value: "22:00" } });
    fireEvent.keyDown(start, { key: "Enter", code: "Enter" });
    fireEvent.mouseDown(end);
    fireEvent.change(end, { target: { value: "02:00" } });
    fireEvent.keyDown(end, { key: "Enter", code: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(putBody(fetchMock)).toMatchObject({ window_start: "22:00", window_end: "02:00" }),
    );
    expect(await screen.findByText(/overnight windows aren't supported/)).toBeInTheDocument();
  });

  it("refreshes the next and last run while the page stays open", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockSchedule(saved);
    const reads = () => fetchMock.mock.calls.filter(([, init]) => init?.method !== "PUT").length;

    renderWithClient(<AutoSyncCard organizationId={ORG} />);
    await waitFor(() => expect(reads()).toBe(1));

    await vi.advanceTimersByTimeAsync(60_000);

    await waitFor(() => expect(reads()).toBe(2));
  });

  it("shows a saved time as is on the browser's own DST-change day", async () => {
    // 02:30 doesn't exist in New York on 2026-03-08: a picker value anchored
    // to "today" there became 03:30 and would be re-saved that way.
    vi.stubEnv("TZ", "America/New_York");
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-03-08T12:00:00Z"));
    mockSchedule({ ...saved, window_start: "02:30:00" });

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    expect(await screen.findByDisplayValue("02:30")).toBeInTheDocument();
  });

  it("labels the switch on its own row", async () => {
    mockSchedule(saved);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    expect(await screen.findByRole("switch", { name: "Sync automatically" })).toBeChecked();
  });

  it("greys out the schedule while auto sync is off, but still saves it", async () => {
    const fetchMock = mockSchedule(saved);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    const mon = await screen.findByRole("checkbox", { name: "Mon" });
    expect(mon).toBeEnabled();
    fireEvent.click(screen.getByRole("switch", { name: "Sync automatically" }));

    await waitFor(() => expect(mon).toBeDisabled());
    expect(screen.getByDisplayValue("09:00")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(putBody(fetchMock)).toMatchObject({
        enabled: false,
        days: [1, 3],
        window_start: "09:00",
        window_end: "17:00",
      }),
    );
  });

  it("opens a switched-off schedule with its fields greyed out", async () => {
    mockSchedule({ ...saved, enabled: false, next_run_at: null });

    renderWithClient(<AutoSyncCard organizationId={ORG} />);

    expect(await screen.findByRole("checkbox", { name: "Mon" })).toBeDisabled();
  });

  it("confirms a save beside the Save button", async () => {
    mockSchedule(saved);

    renderWithClient(<AutoSyncCard organizationId={ORG} />);
    fireEvent.click(await screen.findByRole("button", { name: "Save schedule" }));

    const confirmation = await screen.findByText("Schedule saved");
    // Re-queried: the saved schedule's new updated_at remounts the form.
    const button = screen.getByRole("button", { name: "Save schedule" });
    expect(button.parentElement).toContainElement(confirmation);
  });
});
