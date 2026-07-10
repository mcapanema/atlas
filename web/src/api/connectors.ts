import { useMutation, useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface ConnectorStatus {
  configured: boolean;
}

export interface SyncSummary {
  teams: number;
  projects: number;
  work_items: number;
  events: number;
}

export function useLinearStatus() {
  return useQuery({
    queryKey: ["connectors", "linear"],
    queryFn: () => apiFetch<ConnectorStatus>("/api/connectors/linear"),
  });
}

export function useLinearSync() {
  return useMutation({
    mutationFn: (organizationId: string) =>
      apiFetch<SyncSummary>("/api/connectors/linear/sync", {
        method: "POST",
        body: JSON.stringify({ organization_id: organizationId }),
      }),
  });
}
