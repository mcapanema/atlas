import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Persona } from "./advisor";
import { apiFetch } from "./client";

export interface PersonaGuidance {
  persona: Persona;
  version: number;
  guidance: string;
  created_at: string;
}

export interface AdviceFeedback {
  id: string;
  persona: Persona;
  rating: "up" | "down";
  comment: string | null;
  advice_summary: string;
  created_at: string;
}

export interface FeedbackPayload {
  rating: "up" | "down";
  comment: string | null;
  advice_summary: string;
}

const guidanceKey = (persona: Persona) => ["personas", persona, "guidance"] as const;

export function useGuidance(persona: Persona) {
  return useQuery({
    queryKey: guidanceKey(persona),
    queryFn: () => apiFetch<PersonaGuidance[]>(`/api/personas/${persona}/guidance`),
  });
}

export function useSendFeedback(persona: Persona) {
  return useMutation({
    mutationFn: (payload: FeedbackPayload) =>
      apiFetch<AdviceFeedback>(`/api/personas/${persona}/feedback`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  });
}

export function useReflect(persona: Persona) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<PersonaGuidance>(`/api/personas/${persona}/reflect`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: guidanceKey(persona) }),
  });
}

export function useRestoreGuidance(persona: Persona) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (version: number) =>
      apiFetch<PersonaGuidance>(`/api/personas/${persona}/guidance/${version}/restore`, {
        method: "POST",
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: guidanceKey(persona) }),
  });
}
