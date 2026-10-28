import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { stateTimesFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { StateTimeCard } from "./StateTimeCard";

function row(state: string): HTMLElement {
  const cell = screen.getByText(state);
  const tr = cell.closest("tr");
  if (tr === null) throw new Error(`no row for ${state}`);
  return tr;
}

describe("StateTimeCard", () => {
  it("marks the bottleneck row with text, not only color", () => {
    renderWithClient(<StateTimeCard data={stateTimesFixture} />);

    expect(within(row("In Review")).getByText("Bottleneck")).toBeInTheDocument();
    expect(within(row("In Progress")).queryByText("Bottleneck")).toBeNull();
    expect(within(row("In Review")).getByText("wait")).toBeInTheDocument();
    expect(within(row("In Progress")).queryByText("wait")).toBeNull();
  });

  it("shows share, total, median and queue", () => {
    renderWithClient(<StateTimeCard data={stateTimesFixture} />);

    const review = within(row("In Review"));
    expect(review.getByText("73%")).toBeInTheDocument();
    expect(review.getByText("8d")).toBeInTheDocument();
    expect(review.getByText("2d")).toBeInTheDocument();
    expect(review.getByText("4")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "State",
      "Share",
      "Total",
      "Median",
      "Queue",
    ]);
  });

  it("says why there is no bottleneck", () => {
    renderWithClient(
      <StateTimeCard data={{ ...stateTimesFixture, bottleneck: null, measured: 1 }} />,
    );

    expect(screen.queryByText("Bottleneck")).toBeNull();
    expect(
      screen.getByText("No bottleneck yet: 1 of 5 completed items measured."),
    ).toBeInTheDocument();
  });

  it("names no bottleneck when enough items were measured but none holds time", () => {
    renderWithClient(
      <StateTimeCard data={{ ...stateTimesFixture, bottleneck: null, measured: 5 }} />,
    );

    expect(screen.getByText("No bottleneck yet: no in-cycle time measured.")).toBeInTheDocument();
  });
});
