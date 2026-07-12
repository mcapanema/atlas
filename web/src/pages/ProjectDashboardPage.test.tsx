import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { jsonResponse, mockMetricsFetch } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ProjectDashboardPage } from "./ProjectDashboardPage";

const project = {
  id: "44444444-4444-4444-4444-444444444444",
  team_id: "22222222-2222-2222-2222-222222222222",
  name: "Apollo",
  external_id: null,
  created_at: "2026-07-01T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProjectDashboardPage", () => {
  it("shows the dashboard scoped to the selected project", async () => {
    mockMetricsFetch({ "/api/projects": [project] });

    renderWithClient(<ProjectDashboardPage />, ["/projects"]);

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByTitle("Apollo"));

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?project_id=${project.id}`);
  });

  it("shows an error when projects fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<ProjectDashboardPage />, ["/projects"]);

    await waitFor(() => expect(screen.getByText("Failed to load projects")).toBeInTheDocument());
  });
});
