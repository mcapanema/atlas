import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Person {
  id: string;
  organization_id: string;
  name: string;
  display_name: string | null;
  shown_name: string;
  email: string | null;
}

export function usePeople() {
  return useQuery({
    queryKey: ["people"],
    queryFn: () => apiFetch<Person[]>("/api/people"),
  });
}

export function useSetDisplayName() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, displayName }: { id: string; displayName: string | null }) =>
      apiFetch<Person>(`/api/people/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: displayName }),
      }),
    // Owner names appear on other pages (Aging WIP): refetch everything.
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
