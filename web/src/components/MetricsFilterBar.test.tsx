import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MetricsFilterBar } from "./MetricsFilterBar";

function openSelect(label: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
}

describe("MetricsFilterBar", () => {
  it("emits a preset window change", () => {
    const onChange = vi.fn();
    render(<MetricsFilterBar filters={{}} onChange={onChange} />);
    openSelect("Analysis period");
    fireEvent.click(screen.getByText("Last 90 days"));
    expect(onChange).toHaveBeenCalledWith({ windowDays: 90 });
  });

  it("switches to a custom range seeded with the last 30 days", () => {
    const onChange = vi.fn();
    render(<MetricsFilterBar filters={{}} onChange={onChange} />);
    openSelect("Analysis period");
    fireEvent.click(screen.getByText("Custom range"));
    const next = onChange.mock.calls[0][0];
    expect(next.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(next.end).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("shows the range picker only when a range is active", () => {
    const { rerender } = render(<MetricsFilterBar filters={{}} onChange={vi.fn()} />);
    expect(screen.queryByLabelText("Custom date range")).toBeNull();
    rerender(
      <MetricsFilterBar
        filters={{ start: "2026-06-01", end: "2026-06-30" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Custom date range")).toBeInTheDocument();
  });

  it("emits type filters", () => {
    const onChange = vi.fn();
    render(<MetricsFilterBar filters={{}} onChange={onChange} />);
    openSelect("Work item types");
    fireEvent.click(screen.getByTitle("bug"));
    expect(onChange).toHaveBeenCalledWith({ types: ["bug"] });
  });
});
