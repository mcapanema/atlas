import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { HelpLabel } from "./HelpLabel";

it("renders the label and reveals its definition on focus", async () => {
  render(<HelpLabel label="Throughput" help="Items completed in the window." />);

  const trigger = screen.getByText("Throughput");
  expect(trigger).toHaveAttribute("tabindex", "0");

  fireEvent.focus(trigger);
  const tooltip = await screen.findByRole("tooltip");
  expect(tooltip).toHaveTextContent("Items completed in the window.");
});
