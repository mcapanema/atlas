import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "./Sparkline";

/** The polyline's y coordinates, in drawing order. */
function yValues(container: HTMLElement): number[] {
  const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
  return points.split(" ").map((pair) => Number(pair.split(",")[1]));
}

describe("Sparkline", () => {
  it("renders a decorative polyline for a series", () => {
    const { container } = render(<Sparkline points={[3, 1, 4, 1, 5]} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("polyline")?.getAttribute("points")).toContain(",");
  });

  it("renders nothing for fewer than two points", () => {
    const { container } = render(<Sparkline points={[42]} />);
    expect(container.firstChild).toBeNull();
  });

  it("survives a flat series without dividing by zero", () => {
    const { container } = render(<Sparkline points={[5, 5, 5]} />);
    expect(container.querySelector("polyline")?.getAttribute("points")).not.toContain("NaN");
  });

  it("draws a small drift as a near-flat line, not a full-height swing", () => {
    // +3% — leadTimePulse calls this "steady" (< 5%); the line must agree.
    const { container } = render(<Sparkline points={[100, 103]} />);
    const [first, last] = yValues(container);
    // Default plot height is 20 - 2*2 padding = 16px; min-max scaling drew 16.
    expect(Math.abs(first - last)).toBeLessThan(4);
  });

  it("still spends the full height on a large move", () => {
    const { container } = render(<Sparkline points={[100, 200]} />);
    const [first, last] = yValues(container);
    expect(Math.abs(first - last)).toBeCloseTo(16, 0);
  });
});
