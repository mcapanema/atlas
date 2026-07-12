import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DeliveryHealth } from "../api/metrics";
import { healthFixture } from "../test/fixtures";
import { HealthBadge } from "./HealthBadge";

const health = healthFixture as DeliveryHealth;

describe("HealthBadge", () => {
  it("renders score and band word with an accessible name", () => {
    render(<HealthBadge health={health} />);
    const badge = screen.getByRole("button", {
      name: "Health 82 of 100 — healthy. Show component reasons",
    });
    expect(badge).toHaveTextContent("82");
    expect(badge).toHaveTextContent("healthy");
  });

  it("opens component reasons on click and closes on Escape", () => {
    render(<HealthBadge health={health} />);
    const badge = screen.getByRole("button");
    fireEvent.click(badge);
    expect(screen.getByText("lead time p95 is 1.8x p50")).toBeInTheDocument();
    // Component scores state their scale — a critical "risk 0" must read as
    // 0-out-of-100, not "zero risk".
    expect(screen.getAllByText(/\/100/)).toHaveLength(health.components.length);
    expect(badge).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(badge, { key: "Escape" });
    expect(badge).toHaveAttribute("aria-expanded", "false");
  });

  it("falls back to neutral styling for an unknown band instead of vanishing", () => {
    render(<HealthBadge health={{ ...health, band: "degraded" as never }} />);
    const badge = screen.getByRole("button");
    expect(badge.className).toContain("health-badge--unknown");
    expect(badge).toHaveTextContent("degraded");
  });

  it("renders an em dash without health data", () => {
    render(<HealthBadge health={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    render(<HealthBadge health={{ ...health, score: null, band: null }} />);
    expect(screen.getAllByText("—")).toHaveLength(2);
  });
});
