import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DoraMetrics } from "../api/metrics";
import { doraFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { DoraCard } from "./DoraCard";

const data = doraFixture as DoraMetrics;

describe("DoraCard", () => {
  it("shows the four metrics with band text", () => {
    renderWithClient(<DoraCard data={data} />);
    expect(screen.getByText("Delivery performance (DORA)")).toBeInTheDocument();
    expect(screen.getByText("Deploy frequency")).toBeInTheDocument();
    expect(screen.getByText("1.4 / week")).toBeInTheDocument();
    expect(screen.getByText("18.0 h")).toBeInTheDocument();
    expect(screen.getByText("2.0 h")).toBeInTheDocument();
    expect(screen.getAllByText("High")).toHaveLength(3);
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  it("shows long durations in days", () => {
    renderWithClient(<DoraCard data={{ ...data, lead_time_median_seconds: 4 * 86400 }} />);
    expect(screen.getByText("4.0 d")).toBeInTheDocument();
  });

  it("says why a band is missing", () => {
    renderWithClient(<DoraCard data={{ ...data, lead_time_band: null, lead_time_changes: 2 }} />);
    expect(screen.getByText("Too few changes (2 of 5)")).toBeInTheDocument();
  });

  it("names the sample for deployments and restores too", () => {
    renderWithClient(
      <DoraCard data={{ ...data, change_failure_band: null, restore_band: null, restores: 1 }} />,
    );
    expect(screen.getByText("Too few deployments (8 of 5)")).toBeInTheDocument();
    expect(screen.getByText("Too few restores (1 of 5)")).toBeInTheDocument();
  });

  it("shows a dash for a metric with no sample", () => {
    renderWithClient(
      <DoraCard
        data={{
          ...data,
          lead_time_median_seconds: null,
          lead_time_changes: 0,
          lead_time_band: null,
          change_failure_rate: null,
          finished_deployments: 0,
          failed_deployments: 0,
          change_failure_band: null,
        }}
      />,
    );
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("shows only the mapping hint without codebases", () => {
    renderWithClient(<DoraCard data={{ ...data, codebases: 0, restores: 2 }} />);
    const link = screen.getByRole("link", {
      name: /Map a repository to this team on the Connectors page/,
    });
    expect(link).toHaveAttribute("href", "/connectors");
    expect(screen.queryByText("Deploy frequency")).not.toBeInTheDocument();
    expect(screen.queryByText("1.4 / week")).not.toBeInTheDocument();
  });
});
