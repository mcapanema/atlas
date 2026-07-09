import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Organization {
  id: string;
  name: string;
  created_at: string;
}

export function useOrganizations() {
  return useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiFetch<Organization[]>("/api/organizations"),
  });
}
