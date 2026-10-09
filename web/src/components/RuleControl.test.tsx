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
});
