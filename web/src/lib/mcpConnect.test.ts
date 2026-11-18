import { describe, expect, it } from "vitest";

import { connectSnippets } from "./mcpConnect";

describe("connectSnippets", () => {
  it("builds the endpoint and the client commands from the origin and token", () => {
    expect(connectSnippets("http://localhost:8000", "atlas_mcp_abc")).toEqual({
      endpoint: "http://localhost:8000/mcp/atlas_mcp_abc/",
      claudeCode: "claude mcp add --transport http atlas http://localhost:8000/mcp/atlas_mcp_abc/",
      tunnelUrl: "https://<tunnel-host>/mcp/atlas_mcp_abc/",
      tunnelCommand: "cloudflared tunnel --url http://localhost:8000",
    });
  });
});
