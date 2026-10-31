import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { OpenRouterCard } from "./OpenRouterCard";

const MODEL = "anthropic/claude-sonnet-5";

function mockApi({
  configured,
  status = jsonResponse({ configured, model: MODEL, hint: configured ? "…or00" : null }),
  removeResponse = jsonResponse({ configured: false, model: MODEL, hint: null }),
}: {
  configured: boolean;
  status?: Response;
  removeResponse?: Response;
}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/openrouter") return status.clone();
    if (url === "/api/connectors/openrouter/credentials" && init?.method === "PUT")
      return jsonResponse({ configured: true, model: MODEL, hint: "…or-1" });
    if (url === "/api/connectors/openrouter/credentials") return removeResponse;
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OpenRouterCard", () => {
  it("prefills the model and saves", async () => {
    const fetchMock = mockApi({ configured: false });

    renderWithClient(<OpenRouterCard />);

    expect(await screen.findByText("OpenRouter isn't configured")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "openrouter.ai/keys" })).toHaveAttribute(
      "href",
      "https://openrouter.ai/keys",
    );
    expect(screen.getByLabelText("Model")).toHaveValue(MODEL);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));

    expect(await screen.findByText("Key saved")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ api_key: "sk-or-1", model: MODEL });
  });

  it("shows why a key could not be removed", async () => {
    mockApi({ configured: true, removeResponse: jsonResponse({ detail: "boom" }, 500) });

    renderWithClient(<OpenRouterCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    expect(await screen.findByText("Could not remove the OpenRouter key")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByText("Configured · …or00")).toBeInTheDocument();
  });

  it("shows an error instead of a badge when the status fails to load", async () => {
    mockApi({ configured: false, status: jsonResponse({ detail: "down" }, 500) });

    renderWithClient(<OpenRouterCard />);

    expect(await screen.findByText("Failed to load OpenRouter status")).toBeInTheDocument();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });
});
