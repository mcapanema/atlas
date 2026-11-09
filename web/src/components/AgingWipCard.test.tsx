import { fireEvent, screen, within } from "@testing-library/react";
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
    expect(pair.firstElementChild).toHaveClass("aging-flags");
    expect(pair.firstElementChild).toContainElement(icon);
    expect(pair.lastChild?.textContent).toBe("in_progress");
    expect(cell).not.toBe(screen.getByLabelText("over P85").closest("td"));
    // Keyboard users reach the tooltip too.
    expect(icon).toHaveAttribute("tabindex", "0");
    fireEvent.focus(icon);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Blocked");
  });

  it("marks a bug with a bug icon", async () => {
    renderCard([{ ...fresh, type: "bug" }]);

    const icon = await screen.findByRole("img", { name: "Bug" });
    expect(icon).toHaveClass("aging-bug");
    expect(icon.closest(".aging-flags")).not.toBeNull();
    expect(icon).toHaveAttribute("tabindex", "0");
    fireEvent.focus(icon);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Bug");
  });

  it("puts a lone icon first in its slot, whatever its kind", async () => {
    renderCard([
      { ...agingWipFixture.items[0], blocked: true },
      { ...fresh, type: "bug" },
    ]);

    const blocked = await screen.findByRole("img", { name: "Blocked" });
    const bug = screen.getByRole("img", { name: "Bug" });
    // One slot packs its icons to the left, so a lone icon of either kind sits at one x.
    for (const icon of [blocked, bug]) {
      const flags = icon.closest(".aging-flags")!;
      expect(flags.firstElementChild).toContainElement(icon);
    }
  });

  it("reserves one icon width, not one per icon kind, so a lone icon sits by its state", async () => {
    renderCard([
      { ...agingWipFixture.items[0], blocked: true },
      { ...fresh, type: "bug" },
      { ...fresh, work_item_id: "66666666-6666-6666-6666-666666666666", title: "Plain item" },
    ]);

    await screen.findByRole("img", { name: "Blocked" });
    // The slot's width is CSS's one-icon minimum (index.css), never sized to both icon kinds.
    const slots = document.querySelectorAll(".aging-flags");
    expect(slots).toHaveLength(3);
    for (const slot of slots) expect(slot).not.toHaveAttribute("style");
    expect(
      screen.getByText("Plain item").closest("tr")!.querySelector(".aging-flags"),
    ).toBeEmptyDOMElement();
  });

  it("orders a blocked bug's icons blocked, then bug", async () => {
    renderCard([{ ...fresh, type: "bug", blocked: true }]);

    const flags = (await screen.findByRole("img", { name: "Bug" })).closest(".aging-flags")!;
    expect(
      within(flags as HTMLElement)
        .getAllByRole("img")
        .map((icon) => icon.getAttribute("aria-label")),
    ).toEqual(["Blocked", "Bug"]);
    expect(flags.parentElement!.lastChild?.textContent).toBe("in_progress");
  });

  it("reserves one icon slot when only blocked rows exist", async () => {
    renderCard([{ ...agingWipFixture.items[0], blocked: true }, fresh]);

    await screen.findByRole("img", { name: "Blocked" });
    // The other row keeps an empty slot, so its state starts where the blocked one does.
    const empty = screen.getByText("Fresh item").closest("tr")!.querySelector(".aging-flags");
    expect(empty).toBeEmptyDOMElement();
  });

  it("renders no icon slot when no row is blocked or a bug", async () => {
    renderCard([fresh]);

    await screen.findByText("Fresh item");
    expect(document.querySelector(".aging-state")).not.toBeNull();
    expect(document.querySelector(".aging-flags")).toBeNull();
  });

  it("explains the bug icon in the card help", async () => {
    renderCard([fresh]);

    fireEvent.focus(await screen.findByText("Aging WIP"));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "A bug icon marks an item that the team's type rules classify as a bug.",
    );
  });
});
