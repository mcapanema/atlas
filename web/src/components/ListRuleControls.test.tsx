import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LabelsControl, StatesControl, TypeLabelsEditor } from "./ListRuleControls";

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

describe("LabelsControl", () => {
  it("emits the chosen label added to the current ones", async () => {
    const onChange = vi.fn();
    render(
      <LabelsControl
        label="Labels"
        value={["Blocked"]}
        labelOptions={["Bug"]}
        onChange={onChange}
      />,
    );

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Labels" }));
    fireEvent.click(await screen.findByTitle("Bug"));

    // antd passes the option objects as a second argument.
    expect(onChange.mock.lastCall?.[0]).toEqual(["Blocked", "Bug"]);
  });
});

describe("StatesControl", () => {
  it("emits state types in canonical order whatever the pick order", async () => {
    const onChange = vi.fn();
    render(<StatesControl label="States" value={["started"]} onChange={onChange} />);

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "States" }));
    fireEvent.click(await screen.findByTitle("Todo"));

    expect(onChange).toHaveBeenLastCalledWith(["unstarted", "started"]);
  });
});

describe("TypeLabelsEditor fields", () => {
  const rows = [{ label: "Bug", type: "bug" as const }];

  it("edits a row's label", () => {
    const onChange = vi.fn();
    render(<TypeLabelsEditor label="T" value={rows} labelOptions={[]} onChange={onChange} />);

    fireEvent.change(screen.getByRole("combobox", { name: "T: label 1" }), {
      target: { value: "Defect" },
    });

    expect(onChange).toHaveBeenLastCalledWith([{ label: "Defect", type: "bug" }]);
  });

  it("edits a row's type", async () => {
    const onChange = vi.fn();
    render(<TypeLabelsEditor label="T" value={rows} labelOptions={[]} onChange={onChange} />);

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "T: type 1" }));
    fireEvent.click(await screen.findByTitle("story"));

    expect(onChange).toHaveBeenLastCalledWith([{ label: "Bug", type: "story" }]);
  });
});
