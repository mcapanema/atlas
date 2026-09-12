import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatCard } from "./StatCard";

describe("StatCard", () => {
  it("renders the plain title when no help text is given", () => {
    render(<StatCard title="WIP (now)" value={12} />);
    expect(screen.getByText("WIP (now)")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("renders an accessible help label when help text is given", () => {
    render(<StatCard title="Lead time P50" value="3d" help="Median time from created to done." />);
    expect(screen.getByText("Lead time P50", { selector: ".th-help" })).toBeInTheDocument();
  });
});
