import { describe, expect, it } from "vitest";

import { sampleNoteText } from "./sampleNote";

describe("sampleNoteText", () => {
  it("names the noun, the sample and the floor", () => {
    expect(sampleNoteText(2, 5, "fixed bugs")).toBe("Too few fixed bugs (2 of 5)");
  });
});
