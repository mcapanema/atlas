/** The strings a user pastes into an MCP client. The token rides in the URL path; the slash at the end is required. */
export function connectSnippets(origin: string, token: string) {
  const endpoint = `${origin}/mcp/${token}/`;
  return {
    endpoint,
    claudeCode: `claude mcp add --transport http atlas ${endpoint}`,
    tunnelUrl: `https://<tunnel-host>/mcp/${token}/`,
    tunnelCommand: `cloudflared tunnel --url ${origin}`,
  };
}
