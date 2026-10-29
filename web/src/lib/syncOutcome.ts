import type { CodeSummary, SyncSummary } from "../api/connectors";

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** One line on what a GitHub sync wrote. */
export function codeSyncOutcome(summary: CodeSummary): string {
  const parts = [
    count(summary.codebases, "codebase"),
    count(summary.pull_requests, "pull request"),
    count(summary.deployments, "deployment"),
    count(summary.events, "work item event"),
  ];
  return `Updated ${parts.join(" · ")}`;
}

/** One line on what a sync wrote: non-zero counts, then removals, or "Already up to date". */
export function syncOutcome(summary: SyncSummary): string {
  const parts = [
    [summary.teams, "team"],
    [summary.projects, "project"],
    [summary.work_items, "work item"],
    [summary.events, "event"],
  ] as const;
  const changed = parts.filter(([n]) => n > 0).map(([n, noun]) => count(n, noun));
  const segments = [
    ...(changed.length > 0 ? [`Updated ${changed.join(" · ")}`] : []),
    ...(summary.deleted > 0 ? [`${count(summary.deleted, "work item")} removed`] : []),
  ];
  return segments.length === 0 ? "Already up to date" : segments.join(" · ");
}
