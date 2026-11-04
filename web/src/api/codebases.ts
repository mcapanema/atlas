import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Codebase {
  id: string;
  organization_id: string;
  name: string;
  url: string | null;
  team_id: string | null;
  production_environment: string;
  last_synced_at: string | null;
  pull_requests: number;
  deployments: number;
  source: "github" | "datadog";
}

interface CodebaseInput {
  team_id: string | null;
  production_environment: string;
}

export function useCodebases(organizationId: string, source: Codebase["source"]) {
  return useQuery({
    queryKey: ["codebases", organizationId, source],
    queryFn: () =>
      apiFetch<Codebase[]>(`/api/codebases?organization_id=${organizationId}&source=${source}`),
  });
}

export function useUpdateCodebase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: CodebaseInput & { id: string }) =>
      apiFetch<Codebase>(`/api/codebases/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["codebases"] }),
  });
}
