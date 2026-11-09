import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./EChart", () => ({ EChart: () => <div data-testid="echart" /> }));

import type { MetricsFilters } from "../api/metrics";
import { bugMetricsFixture, mockMetricsFetch, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { BugsSection } from "./BugsSection";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderSection(overrides: Record<string, unknown> = {}, filters: MetricsFilters = {}) {
  mockMetricsFetch({ "/api/metrics/bugs": bugMetricsFixture(overrides) });
  return renderWithClient(<BugsSection teamId="team-1" filters={filters} />);
}

const fixRow = (fixed: number, open: number) => ({
  fixed,
  median_seconds: fixed > 0 ? 172800 : null,
  open,
  oldest_open_seconds: open > 0 ? 432000 : null,
});

describe("BugsSection", () => {
  it("shows the ratios, the chart and the lead-time table when the state is ok", async () => {
    renderSection();

    expect(await screen.findByText("Bugs (30d)")).toBeInTheDocument();
    expect(screen.getByText("0.31")).toBeInTheDocument();
    expect(screen.getByText("14 bugs / 45 non-bug items")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("30 of 75")).toBeInTheDocument();
    expect(screen.getByText("Created vs. completed")).toBeInTheDocument();
    expect(screen.getByTestId("echart")).toBeInTheDocument();
    expect(screen.getByText("Counts as bug: bug")).toBeInTheDocument();
    expect(screen.queryByText(/Too few (non-bug|completed) items/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for a mapping, with a link to the team's rules, when no label maps to bug", async () => {
    renderSection({ state: "no_mapping", bug_labels: [], priorities: [] });

    expect(await screen.findByText("No label counts as a bug for this team.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Metric rules/ })).toHaveAttribute(
      "href",
      "/metric-rules?team=team-1",
    );
    expect(screen.queryByText("Bug share")).not.toBeInTheDocument();
  });

  it("names the mapped labels when no item carries them", async () => {
    renderSection({ state: "no_matches", bug_labels: ["defeito", "Bug"], priorities: [] });

    expect(
      await screen.findByText(
        "No item carries the label(s) defeito, Bug. Does the team mark bugs with another label?",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Bug lead time by priority")).not.toBeInTheDocument();
  });

  it("flags a main number below the evidence floor", async () => {
    renderSection({ created: 1, non_bug_completed: 3, per_item: 0.33 });

    expect(await screen.findByText("Too few non-bug items (3 of 5)")).toBeInTheDocument();
    expect(screen.getByText("0.33")).toBeInTheDocument();
  });

  it("flags a bug share below the evidence floor", async () => {
    renderSection({ completed: 1, all_completed: 2, share: 0.5 });

    expect(await screen.findByText("Too few completed items (2 of 5)")).toBeInTheDocument();
  });

  it("flags a lead-time row below the evidence floor", async () => {
    renderSection();

    expect(await screen.findByText("Too few fixed bugs (2 of 5)")).toBeInTheDocument();
  });

  it("shows a dash for a null ratio and keeps its counts", async () => {
    renderSection({ created: 12, non_bug_completed: 0, per_item: null });

    expect(await screen.findByText("12 bugs / 0 non-bug items")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("Too few non-bug items (0 of 5)")).not.toBeInTheDocument();
  });

  it("lists All bugs first, then each priority, with No priority for none", async () => {
    renderSection();

    await screen.findByText("Bug lead time by priority");
    const firstCells = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.querySelector("td")?.textContent);
    expect(firstCells).toEqual(["All bugs", "Urgent", "High", "Medium", "Low", "No priority"]);
  });

  it("notes bugs with an unknown priority", async () => {
    renderSection({
      unknown_priority: 4,
      all_bugs: fixRow(30, 6),
    });

    expect(
      await screen.findByText(
        "Priority unknown for 4 bugs (not synced yet, or not sent by the source).",
      ),
    ).toBeInTheDocument();
  });

  it("says the type filter does not apply only when one is set", async () => {
    const plain = renderSection();
    await screen.findByText("Bugs (30d)");
    expect(screen.queryByText(/type filter does not apply/)).not.toBeInTheDocument();
    plain.unmount();
    vi.restoreAllMocks();

    renderSection({}, { types: ["story"] });

    expect(
      await screen.findByText("The type filter does not apply to this section."),
    ).toBeInTheDocument();
  });

  it("never sends the type filter, but keeps the period and excluded states", async () => {
    renderSection({}, { types: ["story"], windowDays: 90, excludeStates: ["Canceled"] });

    await screen.findByText("Bugs (90d)");
    const urls = vi.mocked(fetch).mock.calls.map(([input]) => requestUrl(input));
    expect(urls).toEqual([
      "/api/metrics/bugs?team_id=team-1&window_days=90&exclude_states=Canceled",
    ]);
  });

  it("hides the label line when no label maps to bug", async () => {
    renderSection({ bug_labels: [] });

    await screen.findByText("Bugs (30d)");
    expect(screen.queryByText(/Counts as bug/)).not.toBeInTheDocument();
  });

  it("ends the card help with the data date", async () => {
    renderSection();

    fireEvent.focus(await screen.findByText("Bugs (30d)"));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/Data as of \S+ \d\d:\d\d\.$/);
  });

  it.each([
    ["Created vs. completed", "Windows of 21 days or fewer bucket per day"],
    ["Bug lead time by priority", "in working days on the team calendar"],
    ["Priority", "current priority in Linear"],
    ["Median", "Half of them took less."],
    ["Fixed", "Bugs completed in the window."],
    ["Open", "Bugs not completed or canceled at the end of the period"],
    ["Oldest open", "reads lower than its calendar age in Linear"],
  ])("explains %s on focus", async (label, help) => {
    renderSection();

    fireEvent.focus(await screen.findByText(label));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(help);
  });

  it("hides the chart for a single bucket", async () => {
    renderSection({ buckets: [bugMetricsFixture().buckets[0]] });

    await screen.findByText("Bugs (30d)");
    expect(screen.queryByTestId("echart")).not.toBeInTheDocument();
  });

  it("renders nothing and fetches nothing without a team", () => {
    mockMetricsFetch();
    const { container } = renderWithClient(<BugsSection teamId={undefined} filters={{}} />);

    expect(container).toBeEmptyDOMElement();
    const urls = vi.mocked(fetch).mock.calls.map(([input]) => requestUrl(input));
    expect(urls).toEqual([]);
  });
});
