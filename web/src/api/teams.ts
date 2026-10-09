import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Team {
  id: string;
  organization_id: string;
  name: string;
  external_id: string | null;
  created_at: string;
  has_custom_rules: boolean;
  /** The team's effective sprint_length_days rule: a retrospective's default window. */
  sprint_length_days: number;
}

export function useTeams() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: () => apiFetch<Team[]>("/api/teams"),
  });
}
