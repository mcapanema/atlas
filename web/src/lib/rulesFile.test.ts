import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricRulesView, RulesImportResult } from "../api/metricRules";
import { downloadJson, importSummary, parseRulesFile, rulesFileName } from "./rulesFile";

const rules = {} as MetricRulesView;

function result(imported: string[], skipped: string[]): RulesImportResult {
  return { imported_teams: imported, skipped_teams: skipped, rules };
}

describe("rulesFileName", () => {
  it("slugs the organization name and dates the file", () => {
    expect(rulesFileName("Acme Corp!", "2026-10-23T14:05:00Z")).toBe(
      "atlas-metric-rules-acme-corp-2026-10-23.json",
    );
  });

  it("falls back to 'workspace' when the name has no letters or digits", () => {
    expect(rulesFileName("***", "2026-10-23T14:05:00Z")).toBe(
      "atlas-metric-rules-workspace-2026-10-23.json",
    );
  });
});

describe("parseRulesFile", () => {
  it("parses JSON", () => {
    expect(parseRulesFile('{"version": 1}')).toEqual({ version: 1 });
  });

  it("rejects text that isn't JSON", () => {
    expect(() => parseRulesFile("not json")).toThrow("This file isn't valid JSON.");
  });
});

describe("importSummary", () => {
  it("lists the imported teams", () => {
    expect(importSummary(result(["Alpha", "Beta"], []))).toBe(
      "Imported the workspace default and 2 teams: Alpha, Beta.",
    );
  });

  it("names the skipped teams", () => {
    expect(importSummary(result([], ["Ghost"]))).toBe(
      "Imported the workspace default. Skipped 1 team not found here: Ghost.",
    );
  });

  it("uses the singular for one imported team", () => {
    expect(importSummary(result(["Alpha"], ["Ghost", "Ghoul"]))).toBe(
      "Imported the workspace default and 1 team: Alpha. Skipped 2 teams not found here: Ghost, Ghoul.",
    );
  });
});

describe("downloadJson", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("saves pretty-printed JSON under the given name", async () => {
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:rules");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    downloadJson("rules.json", { version: 1 });

    const blob = createObjectURL.mock.calls[0]?.[0];
    expect(await blob?.text()).toBe('{\n  "version": 1\n}\n');
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("rules.json");
    expect(anchor.href).toBe("blob:rules");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:rules");
    click.mockRestore();
  });
});
