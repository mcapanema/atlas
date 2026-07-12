import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "./Sparkline";

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
});
