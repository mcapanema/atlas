import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { RulesSharingButtons } from "./RulesSharingButtons";

const ORG = { id: teamFixture.organization_id, name: "Acme", created_at: "2026-07-01T00:00:00Z" };
const BASE = `/api/organizations/${ORG.id}/metric-rules`;

const SHARED = {
  format: "atlas-metric-rules",
  version: 1,
  exported_at: "2026-10-23T14:05:00Z",
  workspace: { aging_percentile: 80 },
  teams: [{ name: "Ghost", external_id: null, overrides: { aging_percentile: 70 } }],
};

const IMPORTED = { imported_teams: [], skipped_teams: ["Ghost"], ambiguous_teams: [], rules: {} };
const SUMMARY = "Imported the workspace default. Skipped 1 team not found here: Ghost.";

function mockFetch(
  importResponse: Response = jsonResponse({}),
  exportResponse: Response = jsonResponse(SHARED),
) {
  // Each call gets a fresh body: a Response can be read only once.
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    (input) =>
      Promise.resolve(
        (requestUrl(input).endsWith("/import") ? importResponse : exportResponse).clone(),
      ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function posts(fetchMock: ReturnType<typeof mockFetch>) {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
}

function chooseFile(container: HTMLElement, text: string) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  fireEvent.change(input, { target: { files: [new File([text], "rules.json")] } });
}

describe("RulesSharingButtons", () => {
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:rules");

  beforeEach(() => {
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    createObjectURL.mockClear();
  });

  it("exports the workspace rules as a named JSON file", async () => {
    const fetchMock = mockFetch();
    renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /export/i }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    expect(requestUrl(fetchMock.mock.calls[0][0])).toBe(`${BASE}/export`);
  });

  it("imports a chosen file after confirming and shows the summary", async () => {
    const fetchMock = mockFetch(
      jsonResponse({
        imported_teams: [],
        skipped_teams: ["Ghost"],
        ambiguous_teams: [],
        rules: {},
      }),
    );
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    chooseFile(container, JSON.stringify(SHARED));
    fireEvent.click(await screen.findByRole("button", { name: "Import and replace" }));

    expect(
      await screen.findByText(
        "Imported the workspace default. Skipped 1 team not found here: Ghost.",
      ),
    ).toBeInTheDocument();
    const [call] = posts(fetchMock);
    expect(requestUrl(call[0])).toBe(`${BASE}/import`);
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual(SHARED);
  });

  it("shows an error for a non-JSON file without calling the API", async () => {
    const fetchMock = mockFetch();
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    chooseFile(container, "not json");

    expect(await screen.findByText("This file isn't valid JSON.")).toBeInTheDocument();
    expect(posts(fetchMock)).toHaveLength(0);
  });

  it("shows the API's 422 detail", async () => {
    mockFetch(
      jsonResponse({ detail: "Team Platform: aging_percentile must be between 50 and 99" }, 422),
    );
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    chooseFile(container, JSON.stringify(SHARED));
    fireEvent.click(await screen.findByRole("button", { name: "Import and replace" }));

    expect(
      await screen.findByText("Team Platform: aging_percentile must be between 50 and 99"),
    ).toBeInTheDocument();
  });

  it("disables Export and Import while the form has unsaved edits", () => {
    mockFetch();
    renderWithClient(<RulesSharingButtons organization={ORG} disabled onImported={vi.fn()} />);

    expect(screen.getByRole("button", { name: /import$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /export$/i })).toBeDisabled();
  });

  it("offers exactly one control per action", () => {
    mockFetch();
    renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Export",
      "Import",
    ]);
  });

  it("clears a failed export's error when an import succeeds", async () => {
    mockFetch(jsonResponse(IMPORTED), jsonResponse({ detail: "export broke" }, 500));
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /export$/i }));
    expect(await screen.findByText("export broke")).toBeInTheDocument();
    chooseFile(container, JSON.stringify(SHARED));
    fireEvent.click(await screen.findByRole("button", { name: "Import and replace" }));

    expect(await screen.findByText(SUMMARY)).toBeInTheDocument();
    expect(screen.queryByText("export broke")).not.toBeInTheDocument();
  });

  it("clears an import's summary when exporting", async () => {
    mockFetch(jsonResponse(IMPORTED));
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );
    chooseFile(container, JSON.stringify(SHARED));
    fireEvent.click(await screen.findByRole("button", { name: "Import and replace" }));
    expect(await screen.findByText(SUMMARY)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /export$/i }));

    await waitFor(() => expect(screen.queryByText(SUMMARY)).not.toBeInTheDocument());
  });

  it("opens the file picker from the Import button", () => {
    mockFetch();
    const pick = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /import$/i }));

    expect(pick).toHaveBeenCalledTimes(1);
  });

  it("lets you choose the same file again", () => {
    mockFetch();
    // A browser fires no change for an unchanged value; jsdom can't show
    // that, so assert the input is cleared after each read.
    const setValue = vi.spyOn(HTMLInputElement.prototype, "value", "set");
    const { container } = renderWithClient(
      <RulesSharingButtons organization={ORG} disabled={false} onImported={vi.fn()} />,
    );

    chooseFile(container, JSON.stringify(SHARED));

    expect(setValue).toHaveBeenCalledWith("");
  });
});
