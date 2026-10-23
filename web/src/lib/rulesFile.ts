import type { RulesImportResult } from "../api/metricRules";

function teams(n: number): string {
  return `${n} team${n === 1 ? "" : "s"}`;
}

/** e.g. "atlas-metric-rules-acme-corp-2026-10-23.json". */
export function rulesFileName(organizationName: string, exportedAt: string): string {
  const slug = organizationName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `atlas-metric-rules-${slug || "workspace"}-${exportedAt.slice(0, 10)}.json`;
}

export function parseRulesFile(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("This file isn't valid JSON.");
  }
}

/** One line on what an import changed and which of the file's teams this install lacks. */
export function importSummary(result: RulesImportResult): string {
  const imported = result.imported_teams;
  const skipped = result.skipped_teams;
  const head =
    imported.length > 0
      ? `Imported the workspace default and ${teams(imported.length)}: ${imported.join(", ")}.`
      : "Imported the workspace default.";
  return skipped.length > 0
    ? `${head} Skipped ${teams(skipped.length)} not found here: ${skipped.join(", ")}.`
    : head;
}

/** Hands the browser `data` as a pretty-printed JSON file to save. */
export function downloadJson(fileName: string, data: unknown): void {
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}
