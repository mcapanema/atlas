import { describe, expect, it } from "vitest";

import { belowFloor, sampleNoteText } from "./sampleNote";

describe("sampleNoteText", () => {
  it("names the noun, the sample and the floor", () => {
    expect(sampleNoteText(2, 5, "fixed bugs")).toBe("Too few fixed bugs (2 of 5)");
  });
});

describe("belowFloor", () => {
  it("is true only for a sample above zero and below the floor", () => {
    expect(belowFloor(0, 5)).toBe(false);
    expect(belowFloor(1, 5)).toBe(true);
    expect(belowFloor(4, 5)).toBe(true);
    expect(belowFloor(5, 5)).toBe(false);
  });
});
