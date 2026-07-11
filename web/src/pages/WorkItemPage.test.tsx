import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkItemPage } from "./WorkItemPage";

const WORK_ITEM_ID = "11111111-1111-1111-1111-111111111111";

const workItem = {
  id: WORK_ITEM_ID,
  team_id: "22222222-2222-2222-2222-222222222222",
  project_id: null,
  title: "Fix login flow",
  type: "bug",
  state: "In Progress",
  external_id: null,
  created_at: "2026-01-01T00:00:00Z",
};

const events = [
  {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    work_item_id: WORK_ITEM_ID,
    type: "created",
    occurred_at: "2026-01-01T00:00:00Z",
    from_state: null,
    to_state: null,
    external_id: null,
    recorded_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    work_item_id: WORK_ITEM_ID,
    type: "started",
    occurred_at: "2026-01-03T00:00:00Z",
    from_state: "Backlog",
    to_state: "In Progress",
    external_id: null,
    recorded_at: "2026-01-03T00:00:00Z",
  },
];

const timeline = {
  state_periods: [
    { state: "Backlog", entered_at: "2026-01-01T00:00:00Z", exited_at: "2026-01-03T00:00:00Z" },
    { state: "In Progress", entered_at: "2026-01-03T00:00:00Z", exited_at: null },
  ],
  blocked_periods: [{ started_at: "2026-01-04T00:00:00Z", ended_at: null }],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/work-items/${WORK_ITEM_ID}`]}>
        <Routes>
          <Route path="/work-items/:id" element={<WorkItemPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkItemPage", () => {
  it("renders the event timeline, state periods, and blocked periods", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/timeline")) return Promise.resolve(jsonResponse(timeline));
      if (url.startsWith("/api/events")) return Promise.resolve(jsonResponse(events));
      return Promise.resolve(jsonResponse(workItem));
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Fix login flow")).toBeInTheDocument());
    expect(screen.getByText(/started: Backlog → In Progress/)).toBeInTheDocument();
    expect(screen.getAllByText("Backlog").length).toBeGreaterThan(0);
    expect(screen.getByText("still blocked")).toBeInTheDocument();
  });

  it("shows an error when the work item does not exist", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 404));

    renderPage();

    await waitFor(() => expect(screen.getByText("Work item not found")).toBeInTheDocument());
  });

  it("shows per-section errors instead of false empty states when secondary queries fail", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/timeline") || url.startsWith("/api/events")) {
        return Promise.resolve(jsonResponse({ detail: "database is locked" }, 500));
      }
      return Promise.resolve(jsonResponse(workItem));
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Failed to load events")).toBeInTheDocument());
    expect(screen.getAllByText("Failed to load timeline")).toHaveLength(2);
    expect(screen.getAllByText("database is locked").length).toBeGreaterThan(0);
    expect(screen.queryByText("No events recorded yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Never blocked.")).not.toBeInTheDocument();
  });
});
