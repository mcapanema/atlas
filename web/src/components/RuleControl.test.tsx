import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RULE_GROUPS, type RuleSpec } from "../lib/metricRules";
import { RuleControl } from "./RuleControl";

function spec(name: string): RuleSpec {
  const found = RULE_GROUPS.flatMap((group) => group.rules).find((rule) => rule.name === name);
  if (!found) throw new Error(`no rule ${name}`);
  return found;
}

describe("RuleControl", () => {
  it("shows the working days checked and reports a sorted list when one is added", () => {
    const onChange = vi.fn();
    render(<RuleControl spec={spec("working_days")} value={[1, 2, 3, 4, 5]} onChange={onChange} />);
    expect(screen.getByRole("checkbox", { name: "Mon" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Sat" })).not.toBeChecked();

    fireEvent.click(screen.getByRole("checkbox", { name: "Sat" }));

    expect(onChange).toHaveBeenLastCalledWith([1, 2, 3, 4, 5, 6]);
  });

  it("shows the holidays selected and reports an empty list when cleared", () => {
    const onChange = vi.fn();
    const { container } = render(
      <RuleControl spec={spec("holidays")} value={["2026-12-25"]} onChange={onChange} />,
    );
    expect(screen.getByText("25-12-2026")).toBeInTheDocument();

    const clear = container.querySelector(".ant-picker-clear");
    fireEvent.mouseDown(clear!);
    fireEvent.click(clear!);

    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("reports a typed number and ignores a cleared field", () => {
    const onChange = vi.fn();
    render(<RuleControl spec={spec("healthy_min")} value={70} onChange={onChange} />);
    const input = screen.getByRole("spinbutton", { name: "Healthy from score" });

    fireEvent.change(input, { target: { value: "80" } });
    expect(onChange).toHaveBeenLastCalledWith(80);

    onChange.mockClear();
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("opens no empty suggestion list for blocked state names", () => {
    render(<RuleControl spec={spec("blocked_state_names")} value={[]} onChange={vi.fn()} />);

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "More blocked states" }));

    expect(screen.queryAllByText("No data")).toHaveLength(0);
  });

  it("renders choice and time zone selects with the current value", () => {
    render(
      <>
        <RuleControl spec={spec("reopen_completion")} value="first" onChange={vi.fn()} />
        <RuleControl spec={spec("timezone")} value="UTC" onChange={vi.fn()} />
      </>,
    );
    expect(screen.getByTitle("First completion")).toBeInTheDocument();
    expect(screen.getByTitle("UTC")).toBeInTheDocument();
  });

  it("shows a date rule in the display format and clears it to unset", () => {
    const onChange = vi.fn();
    render(<RuleControl spec={spec("tracked_since")} value="2026-08-20" onChange={onChange} />);

    expect(screen.getByRole("textbox", { name: "Tracking started" })).toHaveValue("20-08-2026");

    fireEvent.mouseDown(screen.getByLabelText("close-circle"));
    fireEvent.mouseUp(screen.getByLabelText("close-circle"));
    fireEvent.click(screen.getByLabelText("close-circle"));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});
