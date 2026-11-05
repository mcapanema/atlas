import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { ApiError, apiFetch } from "./client";

export interface ConnectorStatus {
  configured: boolean;
  /** "…" plus the stored key's last 4 characters; null when unconfigured. */
  hint: string | null;
  /** When the stored key was last entered; null when unconfigured. */
  updated_at: string | null;
  /** The sync job running right now, started by anyone. */
  running: SyncJob | null;
}

export interface OpenRouterStatus {
  configured: boolean;
  /** The stored advisor model, or the default when unconfigured. */
  model: string;
  hint: string | null;
  /** When the stored key was last entered; null when unconfigured. */
  updated_at: string | null;
}

export type Integration = "linear" | "github" | "datadog" | "openrouter";

export interface SyncSummary {
  teams: number;
  projects: number;
  work_items: number;
  events: number;
  divergences: number;
  deleted: number;
}

export interface CodeSummary {
  codebases: number;
  pull_requests: number;
  deployments: number;
  events: number;
}

export interface DatadogSummary {
  codebases: number;
  deployments: number;
  incidents: number;
}

export interface GitHubStatus extends ConnectorStatus {
  owner: string | null;
}

export interface DatadogStatus extends ConnectorStatus {
  /** The stored Datadog site; null when unconfigured. */
  site: string | null;
  /** "…" plus the stored application key's last 4 characters; null when unconfigured. */
  application_key_hint: string | null;
}

export interface SyncJob {
  id: string;
  organization_id: string;
  kind: "organization" | "team" | "code" | "datadog";
  trigger: "manual" | "auto";
  state: "running" | "succeeded" | "failed";
  phase: string | null;
  error: string | null;
  summary: SyncSummary | null;
  code_summary?: CodeSummary | null;
  datadog_summary?: DatadogSummary | null;
}

export interface SyncAction {
  start: (organizationId?: string) => void;
  /** The start request is in flight or its job is still running. */
  running: boolean;
  outcome: SyncSummary | undefined;
  /** What a GitHub sync wrote; undefined for Linear syncs. */
  codeOutcome: CodeSummary | undefined;
  /** What a Datadog sync wrote; undefined for other syncs. */
  datadogOutcome: DatadogSummary | undefined;
  error: string | undefined;
  reset: () => void;
}

const LINEAR_JOBS = "/api/connectors/linear/jobs";
const INTERRUPTED = "Sync was interrupted: Atlas restarted before it finished. Run it again.";

export function useGitHubStatus() {
  return useQuery({
    queryKey: ["connectors", "github"],
    queryFn: () => apiFetch<GitHubStatus>("/api/connectors/github"),
    refetchInterval: 15_000,
  });
}

export function useDatadogStatus() {
  return useQuery({
    queryKey: ["connectors", "datadog"],
    queryFn: () => apiFetch<DatadogStatus>("/api/connectors/datadog"),
    refetchInterval: 15_000,
  });
}

export function useLinearStatus() {
  return useQuery({
    queryKey: ["connectors", "linear"],
    queryFn: () => apiFetch<ConnectorStatus>("/api/connectors/linear"),
    // Polled so a scheduled sync that starts while the page is open shows up.
    refetchInterval: 15_000,
  });
}

export function useOpenRouterStatus() {
  return useQuery({
    queryKey: ["connectors", "openrouter"],
    queryFn: () => apiFetch<OpenRouterStatus>("/api/connectors/openrouter"),
  });
}

const credentialsPath = (integration: Integration) => `/api/connectors/${integration}/credentials`;

/**
 * Refetch every status a stored credential decides: the connectors' and the
 * advisor's, and for GitHub and Datadog the codebases table (the owner or site may have changed).
 */
function useRefreshCredentialed(integration: Integration) {
  const queryClient = useQueryClient();
  const keys = [["connectors"], ["advisor", "status"]];
  if (integration === "github" || integration === "datadog") keys.push(["codebases"]);
  return () => Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

/** Stores credentials after the server checks them with the provider. */
export function useSaveCredentials(integration: Integration) {
  const refresh = useRefreshCredentialed(integration);
  return useMutation({
    mutationFn: (values: Record<string, string>) =>
      apiFetch<unknown>(credentialsPath(integration), {
        method: "PUT",
        body: JSON.stringify(values),
      }),
    onSuccess: refresh,
  });
}

export function useRemoveCredentials(integration: Integration) {
  const refresh = useRefreshCredentialed(integration);
  return useMutation({
    mutationFn: () => apiFetch<unknown>(credentialsPath(integration), { method: "DELETE" }),
    onSuccess: refresh,
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
 * leaves "running". `onSucceeded` runs once per job that succeeds; the
 * connector statuses refetch once per job that ends, however it ends.
 */
function useSyncAction(
  post: (organizationId?: string) => Promise<SyncJob>,
  onSucceeded: () => unknown,
  jobsPath: string,
): SyncAction {
  const queryClient = useQueryClient();
  const start = useMutation({ mutationFn: post });
  const jobId = start.data?.id;
  const poll = useQuery({
    queryKey: ["sync-job", jobId],
    queryFn: () => apiFetch<SyncJob>(`${jobsPath}/${jobId}`),
    enabled: jobId !== undefined,
    // Stop on an error too: data still holds the last "running" poll.
    refetchInterval: (query) =>
      query.state.status !== "error" && query.state.data?.state === "running" ? 1000 : false,
    retry: retryPoll,
  });
  const job = poll.data ?? start.data;

  const succeeded = job?.state === "succeeded";
  useOncePerJob(succeeded, jobId, onSucceeded);
  // Any end, failure included: the connector statuses still show the job running.
  const finished = (job !== undefined && job.state !== "running") || poll.error !== null;
  useOncePerJob(finished, jobId, () => queryClient.invalidateQueries({ queryKey: ["connectors"] }));

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
): Pick<SyncAction, "running" | "outcome" | "codeOutcome" | "datadogOutcome" | "error"> {
  return {
    ...summaries(job),
    running: starting || (job?.state === "running" && !pollError),
    error: startError?.message ?? job?.error ?? pollErrorMessage(pollError),
  };
}

function summaries(
  job: SyncJob | undefined,
): Pick<SyncAction, "outcome" | "codeOutcome" | "datadogOutcome"> {
  if (job?.state !== "succeeded")
    return { outcome: undefined, codeOutcome: undefined, datadogOutcome: undefined };
  return {
    outcome: job.summary ?? undefined,
    codeOutcome: job.code_summary ?? undefined,
    datadogOutcome: job.datadog_summary ?? undefined,
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
    LINEAR_JOBS,
  );
}

export function useTeamSync(teamId: string): SyncAction {
  const queryClient = useQueryClient();
  return useSyncAction(
    () => apiFetch<SyncJob>(`/api/connectors/linear/teams/${teamId}/sync`, { method: "POST" }),
    // Any of the team's numbers may have moved: refetch whatever is on screen.
    () => queryClient.invalidateQueries(),
    LINEAR_JOBS,
  );
}

export function useGitHubSync(): SyncAction {
  const queryClient = useQueryClient();
  return useSyncAction(
    (organizationId) =>
      apiFetch<SyncJob>("/api/connectors/github/sync", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId ?? null }),
      }),
    // Codebase counts, the status and work item timelines may all have moved.
    () => queryClient.invalidateQueries(),
    "/api/connectors/github/jobs",
  );
}

export function useDatadogSync(): SyncAction {
  const queryClient = useQueryClient();
  return useSyncAction(
    (organizationId) =>
      apiFetch<SyncJob>("/api/connectors/datadog/sync", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId ?? null }),
      }),
    // Services, deployments, incidents and the DORA numbers may all have moved.
    () => queryClient.invalidateQueries(),
    "/api/connectors/datadog/jobs",
  );
}
