import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { OpenRouterCard } from "./OpenRouterCard";

const MODEL = "anthropic/claude-sonnet-5";

function mockApi({
  configured,
  status = jsonResponse({ configured, model: MODEL, hint: configured ? "…or00" : null }),
  removeResponse = jsonResponse({ configured: false, model: MODEL, hint: null }),
  putResponses = [],
}: {
  configured: boolean;
  status?: Response;
  removeResponse?: Response;
  /** PUT answers in order; once used up, the PUT succeeds. */
  putResponses?: Response[];
}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/openrouter") return status.clone();
    if (url === "/api/connectors/openrouter/credentials" && init?.method === "PUT")
      return (
        putResponses.shift() ?? jsonResponse({ configured: true, model: MODEL, hint: "…or-1" })
      );
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

  it("keeps password managers off the key and model fields", async () => {
    mockApi({ configured: false });

    renderWithClient(<OpenRouterCard />);

    expect(await screen.findByLabelText("OpenRouter API key")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(screen.getByLabelText("Model")).toHaveAttribute("autocomplete", "off");
  });

  it("empties the key after every save, even when the hint is unchanged", async () => {
    // The stored key and its replacement share their last 4 characters.
    const sameHint = () => jsonResponse({ configured: true, model: MODEL, hint: "…or00" });
    mockApi({ configured: true, putResponses: [sameHint(), sameHint()] });

    renderWithClient(<OpenRouterCard />);
    for (const key of ["sk-or-a-or00", "sk-or-b-or00"]) {
      const field = await screen.findByLabelText("OpenRouter API key");
      fireEvent.change(field, { target: { value: key } });
      fireEvent.click(screen.getByRole("button", { name: "Save key" }));

      await waitFor(() => expect(screen.getByLabelText("OpenRouter API key")).toHaveValue(""));
      expect(screen.getByText("Key saved")).toBeInTheDocument();
    }
  });

  it("keeps the typed key when a save is rejected", async () => {
    const detail = "Could not verify the OpenRouter credentials";
    mockApi({ configured: false, putResponses: [jsonResponse({ detail }, 422)] });

    renderWithClient(<OpenRouterCard />);
    fireEvent.change(await screen.findByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));

    expect(await screen.findByText("Could not save the OpenRouter key")).toBeInTheDocument();
    expect(screen.getByText(detail)).toBeInTheDocument();
    expect(screen.getByLabelText("OpenRouter API key")).toHaveValue("sk-or-bad");
  });

  it("keeps the typed key when a later save is rejected", async () => {
    const sameHint = jsonResponse({ configured: true, model: MODEL, hint: "…or00" });
    const rejected = jsonResponse({ detail: "Could not verify the OpenRouter credentials" }, 422);
    mockApi({ configured: true, putResponses: [sameHint, rejected] });

    renderWithClient(<OpenRouterCard />);
    fireEvent.change(await screen.findByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-good" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByText("Key saved")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));

    expect(await screen.findByText("Could not save the OpenRouter key")).toBeInTheDocument();
    expect(screen.getByLabelText("OpenRouter API key")).toHaveValue("sk-or-bad");
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
