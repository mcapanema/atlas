import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { ApiError, apiFetch } from "./client";

export interface ConnectorStatus {
  configured: boolean;
  /** The sync job running right now, started by anyone. */
  running: SyncJob | null;
}

export interface SyncSummary {
  teams: number;
  projects: number;
  work_items: number;
  events: number;
  divergences: number;
  deleted: number;
}

export interface SyncJob {
  id: string;
  organization_id: string;
  kind: "organization" | "team";
  trigger: "manual" | "auto";
  state: "running" | "succeeded" | "failed";
  phase: string | null;
  error: string | null;
  summary: SyncSummary | null;
}

export interface SyncAction {
  start: (organizationId?: string) => void;
  /** The start request is in flight or its job is still running. */
  running: boolean;
  outcome: SyncSummary | undefined;
  error: string | undefined;
  reset: () => void;
}

const INTERRUPTED = "Sync was interrupted: Atlas restarted before it finished. Run it again.";

export function useLinearStatus() {
  return useQuery({
    queryKey: ["connectors", "linear"],
    queryFn: () => apiFetch<ConnectorStatus>("/api/connectors/linear"),
    // Polled so a scheduled sync that starts while the page is open shows up.
    refetchInterval: 15_000,
  });
}

function useOncePerJob(succeeded: boolean, jobId: string | undefined, run: () => unknown) {
  const handled = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (succeeded && jobId !== handled.current) {
      handled.current = jobId;
      void run();
    }
  }, [succeeded, jobId, run]);
}

/**
 * Starts a sync job (the POST answers 202 at once), then polls it until it
 * leaves "running". `onSucceeded` runs once per job that succeeds.
 */
function useSyncAction(
  post: (organizationId?: string) => Promise<SyncJob>,
  onSucceeded: () => unknown,
): SyncAction {
  const start = useMutation({ mutationFn: post });
  const jobId = start.data?.id;
  const poll = useQuery({
    queryKey: ["sync-job", jobId],
    queryFn: () => apiFetch<SyncJob>(`/api/connectors/linear/jobs/${jobId}`),
    enabled: jobId !== undefined,
    // Stop on an error too: data still holds the last "running" poll.
    refetchInterval: (query) =>
      query.state.status !== "error" && query.state.data?.state === "running" ? 1000 : false,
    retry: retryPoll,
  });
  const job = poll.data ?? start.data;

  const succeeded = job?.state === "succeeded";
  useOncePerJob(succeeded, jobId, onSucceeded);

  return {
    start: (organizationId) => start.mutate(organizationId),
    reset: start.reset,
    ...syncView(job, start.isPending, start.error, poll.error),
  };
}

function syncView(
  job: SyncJob | undefined,
  starting: boolean,
  startError: Error | null,
  pollError: Error | null,
): Pick<SyncAction, "running" | "outcome" | "error"> {
  return {
    running: starting || (job?.state === "running" && !pollError),
    outcome: job?.state === "succeeded" ? (job.summary ?? undefined) : undefined,
    error: startError?.message ?? job?.error ?? pollErrorMessage(pollError),
  };
}

// A 404 means the job is gone (restart): retrying cannot bring it back.
function retryPoll(count: number, error: Error): boolean {
  return !(error instanceof ApiError && error.status === 404) && count < 3;
}

function pollErrorMessage(error: Error | null): string | undefined {
  if (error instanceof ApiError && error.status === 404) return INTERRUPTED;
  return error?.message;
}

export function useLinearSync(): SyncAction {
  const queryClient = useQueryClient();
  // The organization list may have been bootstrapped, and the schedule row
  // now carries this sync's time (last_manual_sync_at).
  const onSucceeded = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["organizations"] }),
      queryClient.invalidateQueries({ queryKey: ["sync-schedule"] }),
      queryClient.invalidateQueries({ queryKey: ["connectors", "linear"] }),
    ]);
  return useSyncAction(
    // organization_id: null lets the server bootstrap the organization
    // from the Linear workspace on first sync.
    (organizationId) =>
      apiFetch<SyncJob>("/api/connectors/linear/sync", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId ?? null }),
      }),
    onSucceeded,
  );
}

export function useTeamSync(teamId: string): SyncAction {
  const queryClient = useQueryClient();
  return useSyncAction(
    () => apiFetch<SyncJob>(`/api/connectors/linear/teams/${teamId}/sync`, { method: "POST" }),
    // Any of the team's numbers may have moved: refetch whatever is on screen.
    () => queryClient.invalidateQueries(),
  );
}
