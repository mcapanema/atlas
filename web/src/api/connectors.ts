import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface ConnectorStatus {
  configured: boolean;
}

export interface SyncSummary {
  teams: number;
  projects: number;
  work_items: number;
  events: number;
  divergences: number;
}

export function useLinearStatus() {
  return useQuery({
    queryKey: ["connectors", "linear"],
    queryFn: () => apiFetch<ConnectorStatus>("/api/connectors/linear"),
  });
}

export function useLinearSync() {
  const queryClient = useQueryClient();
  return useMutation({
    // organization_id: null lets the server bootstrap the organization
    // from the Linear workspace on first sync.
    mutationFn: (organizationId?: string) =>
      apiFetch<SyncSummary>("/api/connectors/linear/sync", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId ?? null }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["organizations"] }),
  });
}
