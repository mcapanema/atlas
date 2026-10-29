import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { stateTimesFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { StateTimeCard } from "./StateTimeCard";

function row(state: string): HTMLElement {
  const cell = screen.getByText(state);
  const tr = cell.closest("tr");
  if (tr === null) throw new Error(`no row for ${state}`);
  return tr;
}

const [review] = stateTimesFixture.states;
const twoTeams = {
  ...stateTimesFixture,
  states: [
    { ...review, team: "Platform" },
    { ...review, team: "Growth", total_seconds: 432000, share: 0.4 },
  ],
  bottleneck: "In Review",
  bottleneck_team: "Platform",
};

afterEach(() => {
  vi.restoreAllMocks();
});

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

  it("marks only the bottleneck team's row", () => {
    renderWithClient(<StateTimeCard data={twoTeams} />);

    const [marker] = screen.getAllByText("Bottleneck");
    expect(screen.getAllByText("Bottleneck")).toHaveLength(1);
    expect(marker.closest("tr")).toHaveTextContent("Platform");
    expect(screen.getByText("Growth").closest("tr")).not.toHaveTextContent("Bottleneck");
  });

  it("renders same-named states without a duplicate key warning", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});

    renderWithClient(<StateTimeCard data={twoTeams} />);

    const messages = error.mock.calls.map((call) => call.map(String).join(" "));
    expect(messages.filter((message) => message.includes("same key"))).toEqual([]);
  });

  it("shows no team text when the scope is not split", () => {
    renderWithClient(<StateTimeCard data={stateTimesFixture} />);

    expect(screen.queryByText("Platform")).toBeNull();
  });

  it("flags the bottleneck after the state name, in the shared delta style", () => {
    renderWithClient(<StateTimeCard data={stateTimesFixture} />);

    const marker = screen.getByText("Bottleneck");
    // The house flag style (as Aging WIP's > P85), AA-tuned in both themes —
    // not a stock AntD Tag chip.
    expect(marker.closest(".delta")).toHaveClass("delta--bad");
    expect(marker.closest(".ant-tag")).toBeNull();
    // After the name, so every state name starts at one x.
    const text = row("In Review").textContent ?? "";
    expect(text.indexOf("In Review")).toBeLessThan(text.indexOf("Bottleneck"));
    // "wait" is a flag too: the 11px delta style at full text contrast.
    const wait = within(row("In Review")).getByText("wait");
    expect(wait).toHaveClass("delta");
    expect(wait.closest(".ant-typography-secondary")).toBeNull();
  });

  it("gives teams their own column only when the scope is split", () => {
    renderWithClient(<StateTimeCard data={twoTeams} />);

    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "State",
      "Team",
      "Share",
      "Total",
      "Median",
      "Queue",
    ]);
    const growth = screen.getByText("Growth");
    expect(growth.closest("td")).not.toHaveTextContent("In Review");
    // A team is data, like Aging WIP's owner: plain text, not the gray hint
    // style (2.8:1 in light mode, under AA).
    expect(growth.closest(".ant-typography-secondary")).toBeNull();
  });

  it("shows a share under 1% as <1%, and none as 0%", () => {
    const [first, second] = stateTimesFixture.states;
    renderWithClient(
      <StateTimeCard
        data={{
          ...stateTimesFixture,
          states: [
            { ...first, share: 0.004 },
            { ...second, share: 0 },
          ],
        }}
      />,
    );

    expect(within(row("In Review")).getByText("<1%")).toBeInTheDocument();
    expect(within(row("In Progress")).getByText("0%")).toBeInTheDocument();
  });
});
