import { describe, expect, it } from "vitest";

import { sampleNoteText, showsFloorNote } from "./sampleNote";

describe("sampleNoteText", () => {
  it("names the noun, the sample and the floor", () => {
    expect(sampleNoteText(2, 5, "fixed bugs")).toBe("Too few fixed bugs (2 of 5)");
  });
});

describe("showsFloorNote", () => {
  it("is true only for a sample above zero and below the floor", () => {
    expect(showsFloorNote(0, 5)).toBe(false);
    expect(showsFloorNote(1, 5)).toBe(true);
    expect(showsFloorNote(4, 5)).toBe(true);
    expect(showsFloorNote(5, 5)).toBe(false);
  });
});
