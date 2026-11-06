import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AgingItem } from "../api/metrics";
import { agingWipFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AgingWipCard } from "./AgingWipCard";

const fresh: AgingItem = {
  ...agingWipFixture.items[0],
  work_item_id: "55555555-5555-5555-5555-555555555555",
  title: "Fresh item",
  blocked: false,
  over_percentile: false,
  over_median: false,
};

function renderCard(items: AgingItem[]) {
  return renderWithClient(
    <AgingWipCard
      items={items}
      percentile={85}
      historyDays={90}
      thresholdSeconds={259200}
      medianSeconds={86400}
    />,
  );
}

describe("AgingWipCard", () => {
  it("marks blocked aging items with an icon before their state", async () => {
    renderCard([{ ...agingWipFixture.items[0], blocked: true }]);

    const icon = await screen.findByRole("img", { name: "Blocked" });
    // Light-mode AA fix for the warning color lives on this class (index.css).
    expect(icon).toHaveClass("aging-blocked");
    const cell = icon.closest("td")!;
    // The state reads alone: no "Blocked" text beside it, the icon leads it.
    expect(cell).toHaveTextContent(/^in_progress$/);
    const pair = icon.closest(".aging-state")!;
    expect(pair.firstElementChild).toHaveClass("aging-blocked-slot");
    expect(pair.firstElementChild).toContainElement(icon);
    expect(pair.lastChild?.textContent).toBe("in_progress");
    expect(cell).not.toBe(screen.getByLabelText("over P85").closest("td"));
    // Keyboard users reach the tooltip too.
    expect(icon).toHaveAttribute("tabindex", "0");
    fireEvent.focus(icon);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Blocked");
  });

  it("reserves the blocked icon slot on unblocked rows when any row is blocked", async () => {
    renderCard([{ ...agingWipFixture.items[0], blocked: true }, fresh]);

    const icon = await screen.findByRole("img", { name: "Blocked" });
    expect(icon.closest(".aging-blocked-slot")).not.toBeNull();
    // The unblocked row keeps an empty slot, so its state starts where the blocked one does.
    const slot = screen
      .getByText("Fresh item")
      .closest("tr")!
      .querySelector(".aging-state")!.firstElementChild;
    expect(slot).toHaveClass("aging-blocked-slot");
    expect(slot).toBeEmptyDOMElement();
  });

  it("reserves no blocked slot when nothing is blocked", async () => {
    renderCard(agingWipFixture.items);

    await screen.findByText("Stuck item");
    expect(document.querySelector(".aging-state")).not.toBeNull();
    expect(document.querySelector(".aging-blocked-slot")).toBeNull();
  });

  it("marks a bug with a bug icon", async () => {
    renderCard([{ ...fresh, type: "bug" }]);

    const icon = await screen.findByRole("img", { name: "Bug" });
    expect(icon).toHaveClass("aging-bug");
    expect(icon.closest(".aging-bug-slot")).not.toBeNull();
    expect(icon).toHaveAttribute("tabindex", "0");
    fireEvent.focus(icon);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Bug");
  });

  it("puts a blocked bug's bug icon after its blocked icon", async () => {
    renderCard([{ ...fresh, type: "bug", blocked: true }]);

    const bug = await screen.findByRole("img", { name: "Bug" });
    const pair = bug.closest(".aging-state")!;
    expect([...pair.children].map((child) => child.className)).toEqual([
      "aging-blocked-slot",
      "aging-bug-slot",
    ]);
    expect(pair.lastChild?.textContent).toBe("in_progress");
  });

  it("reserves the bug slot on other rows when any row is a bug", async () => {
    renderCard([{ ...agingWipFixture.items[0], type: "bug" }, fresh]);

    await screen.findByRole("img", { name: "Bug" });
    const slot = screen.getByText("Fresh item").closest("tr")!.querySelector(".aging-bug-slot");
    expect(slot).toBeEmptyDOMElement();
  });

  it("renders no bug slot when no row is a bug", async () => {
    renderCard([fresh]);

    await screen.findByText("Fresh item");
    expect(document.querySelector(".aging-bug-slot")).toBeNull();
  });

  it("explains the bug icon in the card help", async () => {
    renderCard([fresh]);

    fireEvent.focus(await screen.findByText("Aging WIP"));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "A bug icon marks an item that the team's type rules classify as a bug.",
    );
  });
});
