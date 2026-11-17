import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

const MCP_TOKENS_KEY = ["mcp-tokens"] as const;

export type McpAccess = "read" | "read_write";

export type McpToken = {
  id: string;
  name: string;
  access: McpAccess;
  hint: string;
  created_at: string;
  last_used_at: string | null;
};

/** The one response that carries the secret. */
export type IssuedMcpToken = McpToken & { token: string };

/** The signed-in user's own tokens. */
export function useMcpTokens() {
  return useQuery({
    queryKey: MCP_TOKENS_KEY,
    queryFn: () => apiFetch<McpToken[]>("/api/mcp-tokens"),
  });
}

export function useCreateMcpToken() {
  const queryClient = useQueryClient();
  return useMutation({
    // The result holds the secret: drop it from the MutationCache when the modal unmounts.
    gcTime: 0,
    mutationFn: (values: { name: string; access: McpAccess }) =>
      apiFetch<IssuedMcpToken>("/api/mcp-tokens", {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MCP_TOKENS_KEY }),
  });
}

export function useRevokeMcpToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<undefined>(`/api/mcp-tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MCP_TOKENS_KEY }),
  });
}
