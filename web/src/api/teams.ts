import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Team {
  id: string;
  organization_id: string;
  name: string;
  external_id: string | null;
  created_at: string;
}

export function useTeams() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: () => apiFetch<Team[]>("/api/teams"),
  });
}
