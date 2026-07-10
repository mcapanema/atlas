import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface WorkItemEvent {
  id: string;
  work_item_id: string;
  type: string;
  occurred_at: string;
  from_state: string | null;
  to_state: string | null;
  external_id: string | null;
  recorded_at: string;
}

export function useWorkItemEvents(workItemId: string) {
  return useQuery({
    queryKey: ["events", workItemId],
    queryFn: () => apiFetch<WorkItemEvent[]>(`/api/events?work_item_id=${workItemId}`),
  });
}
