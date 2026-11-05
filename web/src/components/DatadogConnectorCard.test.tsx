import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { DatadogConnectorCard } from "./DatadogConnectorCard";

const ORG = "11111111-1111-1111-1111-111111111111";

const job = (state: string, extra: object = {}) => ({
  id: "job1",
  organization_id: ORG,
  kind: "datadog",
  trigger: "manual",
  state,
  phase: null,
  error: null,
  summary: null,
  code_summary: null,
  datadog_summary: null,
  ...extra,
});

const SUCCEEDED = job("succeeded", {
  datadog_summary: { codebases: 1, deployments: 0, incidents: 1 },
});

const DATADOG_CODEBASE = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  organization_id: ORG,
  name: "checkout",
  url: null,
  team_id: null,
  production_environment: "prod",
  last_synced_at: null,
  pull_requests: 0,
  deployments: 3,
  source: "datadog",
};

function mockApi({ configured, running = null }: { configured: boolean; running?: object | null }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/datadog")
      return jsonResponse({
        configured,
        site: configured ? "datadoghq.com" : null,
        hint: configured ? "…aaaa" : null,
        application_key_hint: configured ? "…bbbb" : null,
        updated_at: configured ? "2026-11-01T12:00:00Z" : null,
        running,
      });
    if (url === "/api/connectors/datadog/credentials" && init?.method === "PUT")
      return jsonResponse({ configured: true, site: "datadoghq.eu", hint: "…p_x", running: null });
    if (url === "/api/connectors/datadog/sync") return jsonResponse(job("running"), 202);
    if (url === "/api/connectors/datadog/jobs/job1") return jsonResponse(SUCCEEDED);
    if (url.startsWith("/api/codebases")) return jsonResponse([DATADOG_CODEBASE]);
    if (url === "/api/teams") return jsonResponse([]);
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => vi.restoreAllMocks());

describe("DatadogConnectorCard", () => {
  it("shows the site in the badge and both stored keys", async () => {
    mockApi({ configured: true });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);

    expect(await screen.findByText("Configured · datadoghq.com")).toBeInTheDocument();
    expect(screen.getByText("…aaaa")).toHaveClass("fig");
    expect(screen.getByText("…bbbb")).toHaveClass("fig");
  });

  it("shows the setup alert and disables Sync Datadog while unconfigured", async () => {
    mockApi({ configured: false });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);

    expect(await screen.findByText("Datadog isn't configured")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sync Datadog/ })).toBeDisabled();
  });

  it("saves both keys and the site", async () => {
    const fetchMock = mockApi({ configured: false });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);
    fireEvent.change(await screen.findByLabelText("Datadog API key"), { target: { value: "k1" } });
    fireEvent.change(screen.getByLabelText("Application key"), { target: { value: "k2" } });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Site" }));
    fireEvent.click(await screen.findByTitle("datadoghq.eu"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({
      api_key: "k1",
      application_key: "k2",
      site: "datadoghq.eu",
    });
  });

  it("lists the seven sites in order", async () => {
    mockApi({ configured: false });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);
    fireEvent.mouseDown(await screen.findByRole("combobox", { name: "Site" }));

    await screen.findAllByTitle("ddog-gov.com");
    const titles = Array.from(document.querySelectorAll(".ant-select-item-option")).map((el) =>
      el.getAttribute("title"),
    );
    expect(titles).toEqual([
      "datadoghq.com",
      "us3.datadoghq.com",
      "us5.datadoghq.com",
      "datadoghq.eu",
      "ap1.datadoghq.com",
      "ap2.datadoghq.com",
      "ddog-gov.com",
    ]);
  });

  it("requires both keys even when configured", async () => {
    mockApi({ configured: true });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);
    const key = await screen.findByLabelText("Datadog API key");

    expect(key).not.toHaveAttribute("placeholder", "Leave blank to keep the stored key");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Datadog API key is required")).toBeInTheDocument();
  });

  it("syncs and shows the outcome", async () => {
    const fetchMock = mockApi({ configured: true });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);
    const button = await screen.findByRole("button", { name: /Sync Datadog/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    expect(
      await screen.findByText("Updated 1 service · 0 deployments · 1 incident"),
    ).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => requestUrl(input));
    expect(urls).toContain("/api/connectors/datadog/jobs/job1");
  });

  it("disables the button while another kind of sync runs", async () => {
    mockApi({ configured: true, running: job("running", { kind: "code" }) });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);

    expect(await screen.findByText(/Another sync is running/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sync Datadog/ })).toBeDisabled();
  });

  it("lists only Datadog services, without a Pull requests column", async () => {
    const fetchMock = mockApi({ configured: true });

    renderWithClient(<DatadogConnectorCard organizationId={ORG} />);

    expect(await screen.findByText("checkout")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: "Service" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("Pull requests")).not.toBeInTheDocument();
    expect(screen.getByText("Only services mapped to a team are synced.")).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => requestUrl(input));
    expect(urls).toContain(`/api/codebases?organization_id=${ORG}&source=datadog`);
  });
});
