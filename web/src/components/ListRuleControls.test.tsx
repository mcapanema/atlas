import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TypeLabelsEditor } from "./ListRuleControls";

describe("TypeLabelsEditor", () => {
  const rows = [
    { label: "Bug", type: "bug" as const },
    { label: "Feature", type: "story" as const },
  ];

  it("adds, moves up and removes mappings", () => {
    const onChange = vi.fn();
    render(
      <TypeLabelsEditor label="Type labels" value={rows} labelOptions={[]} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add mapping" }));
    expect(onChange).toHaveBeenLastCalledWith([...rows, { label: "", type: "bug" }]);

    fireEvent.click(screen.getAllByRole("button", { name: "Move up" })[1]);
    expect(onChange).toHaveBeenLastCalledWith([rows[1], rows[0]]);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(onChange).toHaveBeenLastCalledWith([rows[1]]);
  });

  it("disables moving the first row up", () => {
    render(
      <TypeLabelsEditor label="Type labels" value={rows} labelOptions={[]} onChange={vi.fn()} />,
    );
    expect(screen.getAllByRole("button", { name: "Move up" })[0]).toBeDisabled();
  });
});
