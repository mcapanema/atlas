import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DeliveryHealth } from "../api/metrics";
import { healthFixture } from "../test/fixtures";
import { HealthPanel } from "./HealthPanel";

const health = healthFixture as DeliveryHealth;
const PERIOD = "Last 30 days · 10-06-2026 – 10-07-2026";

const tiles = () => document.querySelectorAll(".health-tile");
const tileFor = (label: string) => screen.getByText(label).closest(".health-tile") as HTMLElement;

describe("HealthPanel", () => {
  it("shows the overall score and every component's score and reason, even when healthy", () => {
    render(<HealthPanel health={health} periodText={PERIOD} />);

    const panel = screen.getByRole("region", { name: "Delivery health" });
    expect(within(panel).getByText(PERIOD)).toBeInTheDocument();
    expect(tiles()).toHaveLength(6); // overall + 5 components
    expect(tileFor("Health")).toHaveTextContent("82/100");
    expect(tileFor("Health")).toHaveTextContent("healthy");
    expect(tileFor("predictability")).toHaveTextContent("74/100");
    expect(tileFor("predictability")).toHaveTextContent("lead time p95 is 1.8x p50");
  });

  it("names a weak component's band in words on a healthy team", () => {
    // Audit on live data: 70 healthy overall, predictability 33.
    render(
      <HealthPanel
        health={{
          ...health,
          score: 70,
          band: "healthy",
          components: [
            {
              name: "predictability",
              score: 33,
              band: "critical",
              reason: "lead time p95 is 7.5x p50",
            },
            {
              name: "flow",
              score: 100,
              band: "healthy",
              reason: "completed 51 recently vs 44 in the prior half-window",
            },
          ],
        }}
        periodText={PERIOD}
      />,
    );

    const weak = tileFor("predictability");
    expect(weak).toHaveClass("health-tile--critical");
    expect(weak).toHaveTextContent("critical"); // the word, not color alone
    // Healthy components stay quiet: no band word, no tint.
    const fine = tileFor("flow");
    expect(fine).not.toHaveTextContent("healthy");
    expect(fine).toHaveClass("health-tile--healthy");
  });

  it("renders only the components that were scored, with no holes", () => {
    render(
      <HealthPanel
        health={{
          ...health,
          score: 57,
          band: "warning",
          components: [
            {
              name: "risk",
              score: 57,
              band: "warning",
              reason: "6 of 14 in-progress items blocked or aging past cycle p85",
            },
          ],
        }}
        periodText={PERIOD}
      />,
    );

    expect(tiles()).toHaveLength(2);
    expect(tileFor("risk")).toHaveTextContent("warning");
  });

  it("says health isn't scored yet when too few items back it", () => {
    render(
      <HealthPanel
        health={{ ...health, score: null, band: null, components: [] }}
        periodText={PERIOD}
      />,
    );

    const panel = screen.getByRole("region", { name: "Delivery health" });
    expect(panel).toHaveTextContent(/Health not scored yet/);
    expect(panel).toHaveTextContent(PERIOD);
    expect(tiles()).toHaveLength(0);
  });

  it("still shows a component it has no definition for", () => {
    // A newer backend may add a component this build doesn't know.
    render(
      <HealthPanel
        health={{
          ...health,
          components: [{ name: "cadence", score: 50, band: "warning", reason: "new signal" }],
        }}
        periodText={null}
      />,
    );

    const tile = tileFor("cadence");
    expect(tile).toHaveTextContent("50/100");
    expect(tile).toHaveTextContent("new signal");
    expect(tile.querySelector(".th-help")).toBeNull(); // plain label, no tooltip
  });
});
