export type RunStatus = "running" | "succeeded" | "failed";

const POLL_MS = 2000;

/**
 * `refetchInterval` for a stored-run query: poll while the latest run is
 * running. Also stop on a fetch error — data still holds the last "running"
 * poll, so checking it alone would poll forever.
 */
export function pollWhileRunning(query: {
  state: { status: string; data: { status: RunStatus } | null | undefined };
}): number | false {
  return query.state.status !== "error" && query.state.data?.status === "running" ? POLL_MS : false;
}

/** What a page shows for a stored run plus its start mutation and read query. */
export function runView(
  run: { status: RunStatus; error: string | null } | null | undefined,
  start: { isPending: boolean; error: Error | null },
  readError: Error | null,
): { running: boolean; error: string | undefined } {
  const failed = run?.status === "failed" ? (run.error ?? "The run failed") : undefined;
  return {
    running: start.isPending || run?.status === "running",
    error: start.error?.message ?? readError?.message ?? failed,
  };
}
