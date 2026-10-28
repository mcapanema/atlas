import { describe, expect, it } from "vitest";

import { pollWhileRunning, runView } from "./runs";

describe("pollWhileRunning", () => {
  it("polls while the latest run is running", () => {
    expect(pollWhileRunning({ state: { status: "success", data: { status: "running" } } })).toBe(
      2000,
    );
  });

  it("stops once the run left running or there is none", () => {
    expect(pollWhileRunning({ state: { status: "success", data: { status: "failed" } } })).toBe(
      false,
    );
    expect(pollWhileRunning({ state: { status: "success", data: null } })).toBe(false);
  });

  it("stops after a fetch error even though data still says running", () => {
    expect(pollWhileRunning({ state: { status: "error", data: { status: "running" } } })).toBe(
      false,
    );
  });
});

describe("runView", () => {
  it("is not running when the read failed, so the button can restart", () => {
    const view = runView(
      { status: "running", error: null },
      { isPending: false, error: null },
      new Error("boom"),
    );
    expect(view.running).toBe(false);
    expect(view.error).toBe("boom");
  });
});
