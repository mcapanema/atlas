import { describe, expect, it } from "vitest";

import { syncOutcome } from "./syncOutcome";

const nothing = { teams: 0, projects: 0, work_items: 0, events: 0, divergences: 0, deleted: 0 };

describe("syncOutcome", () => {
  it("is up to date when nothing was written", () => {
    expect(syncOutcome(nothing)).toBe("Already up to date");
  });

  it("lists only what changed", () => {
    expect(syncOutcome({ ...nothing, work_items: 3, events: 12 })).toBe(
      "Updated 3 work items · 12 events",
    );
  });

  it("counts a sync that only created a project as an update", () => {
    expect(syncOutcome({ ...nothing, projects: 1 })).toBe("Updated 1 project");
  });

  it("names teams too", () => {
    expect(syncOutcome({ ...nothing, teams: 2, projects: 2 })).toBe("Updated 2 teams · 2 projects");
  });

  it("uses the singular for one", () => {
    expect(syncOutcome({ ...nothing, work_items: 1, events: 1 })).toBe(
      "Updated 1 work item · 1 event",
    );
  });
});
