import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Project {
  id: string;
  team_id: string;
  name: string;
  external_id: string | null;
  created_at: string;
}

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => apiFetch<Project[]>("/api/projects"),
  });
}
