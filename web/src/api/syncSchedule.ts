import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface SyncScheduleInput {
  enabled: boolean;
  /** ISO weekdays: 1 = Monday … 7 = Sunday (not JS getDay()). */
  days: number[];
  /** "HH:MM" (sent) or "HH:MM:SS" (read), wall-clock time in `timezone`. */
  window_start: string;
  window_end: string;
  interval_minutes: number;
  /** IANA zone, e.g. "America/Sao_Paulo". */
  timezone: string;
}

interface SyncRun {
  slot_at: string;
  finished_at: string;
  error: string | null;
}

export interface SyncSchedule extends SyncScheduleInput {
  updated_at: string;
  last_run: SyncRun | null;
  next_run_at: string | null;
}

const scheduleKey = (organizationId: string) => ["sync-schedule", organizationId];
const schedulePath = (organizationId: string) =>
  `/api/organizations/${organizationId}/sync-schedule`;

/** The organization's schedule; null until one is saved (manual sync only). */
export function useSyncSchedule(organizationId: string) {
  return useQuery({
    queryKey: scheduleKey(organizationId),
    queryFn: () => apiFetch<SyncSchedule | null>(schedulePath(organizationId)),
    // Polled so Next run / Last run stay current on a page left open.
    refetchInterval: 60_000,
  });
}

export function useSaveSyncSchedule(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SyncScheduleInput) =>
      apiFetch<SyncSchedule>(schedulePath(organizationId), {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: (saved) => queryClient.setQueryData(scheduleKey(organizationId), saved),
  });
}
