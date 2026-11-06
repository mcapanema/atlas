import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SampleNote } from "./SampleNote";

describe("SampleNote", () => {
  it("names the noun, the sample and the floor", () => {
    render(<SampleNote sample={3} min={5} noun="fixed bugs" />);

    expect(screen.getByText("Too few fixed bugs (3 of 5)")).toBeInTheDocument();
  });

  it("renders a sample of zero", () => {
    render(<SampleNote sample={0} min={5} noun="deployments" />);

    expect(screen.getByText("Too few deployments (0 of 5)")).toBeInTheDocument();
  });
});
