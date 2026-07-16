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

  it("clears type filters back to undefined", () => {
    const onChange = vi.fn();
    render(<MetricsFilterBar filters={{ types: ["bug"] }} onChange={onChange} />);
    const clearIcon = document.querySelector(".ant-select-clear");
    expect(clearIcon).not.toBeNull();
    fireEvent.mouseDown(clearIcon as Element);
    expect(onChange).toHaveBeenCalledWith({ types: undefined });
  });

  it("emits excluded state tags", () => {
    const onChange = vi.fn();
    render(<MetricsFilterBar filters={{}} onChange={onChange} />);
    const input = screen.getByRole("combobox", { name: "Excluded states" });
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: "canceled," } });
    expect(onChange).toHaveBeenCalledWith({ excludeStates: ["canceled"] });
  });

  it("emits a custom range once both dates are picked", () => {
    const onChange = vi.fn();
    render(
      <MetricsFilterBar
        filters={{ start: "2026-06-01", end: "2026-06-30" }}
        onChange={onChange}
      />,
    );
    const startInput = screen.getByPlaceholderText("Start date");
    const endInput = screen.getByPlaceholderText("End date");
    fireEvent.mouseDown(startInput);
    fireEvent.focus(startInput);
    fireEvent.change(startInput, { target: { value: "2026-06-05" } });
    fireEvent.keyDown(startInput, { key: "Enter" });
    fireEvent.change(endInput, { target: { value: "2026-06-20" } });
    fireEvent.keyDown(endInput, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ start: "2026-06-05", end: "2026-06-20" });
  });
});
