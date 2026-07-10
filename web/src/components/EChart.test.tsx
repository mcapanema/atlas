import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// vi.mock is hoisted above imports and above plain consts — the factory may
// only reference variables created with vi.hoisted.
const chart = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}));
vi.mock("echarts", () => ({ init: vi.fn(() => chart) }));

import * as echarts from "echarts";

import { EChart } from "./EChart";

describe("EChart", () => {
  it("initializes a chart, applies the option, and disposes on unmount", () => {
    const option = { series: [] };

    const { unmount } = render(<EChart option={option} />);

    expect(echarts.init).toHaveBeenCalledTimes(1);
    expect(chart.setOption).toHaveBeenCalledWith(option, true);

    unmount();
    expect(chart.dispose).toHaveBeenCalledTimes(1);
  });
});
