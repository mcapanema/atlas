import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, test, vi } from "vitest";

vi.mock("./EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { accuracyFixture, forecastFixture, jsonResponse, mockMetricsFetch } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ForecastCard } from "./ForecastCard";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ForecastCard", () => {
  it("renders remaining scope, percentile dates, and the outcome chart", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(jsonResponse(forecastFixture)),
    );

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("22-07-2026")).toBeInTheDocument(); // P50 finish
    expect(screen.getByText("04-08-2026")).toBeInTheDocument(); // P95 finish
    expect(screen.getByTestId("echart")).toBeInTheDocument();
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain("/api/forecasts?team_id=team-1");
  });

  it("explains when there is no history to forecast from", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(jsonResponse({ ...forecastFixture, completion: null })),
    );

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);

    await waitFor(() =>
      expect(
        screen.getByText("Not enough delivery history to forecast."),
      ).toBeInTheDocument(),
    );
  });

  it("fetches confidence for a picked target date", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("target_date=2026-09-01")) {
        return Promise.resolve(jsonResponse({ ...forecastFixture, confidence: 0.82 }));
      }
      return Promise.resolve(jsonResponse(forecastFixture));
    });

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());

    const input = screen.getByPlaceholderText("Select date");
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: "01-09-2026" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("82%")).toBeInTheDocument());
  });

  it("shows an error when the forecast fails to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Failed to load forecast")).toBeInTheDocument());
  });

  it("forwards the page's item filters but never its period", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(jsonResponse(forecastFixture)),
    );

    renderWithClient(
      <ForecastCard
        scope={{ teamId: "team-1" }}
        filters={{ windowDays: 7, start: "2026-01-01", end: "2026-02-01", excludeStates: ["trash"] }}
      />,
    );

    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());
    const url = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]))[0];
    expect(url).toContain("exclude_states=trash");
    expect(url).not.toContain("start=");
    expect(url).not.toContain("window_days=");
  });
});

test("shows forecast accuracy once past forecasts resolved", async () => {
  mockMetricsFetch();
  renderWithClient(<ForecastCard scope={{ teamId: "t-1" }} />);

  expect(await screen.findByText("Past forecasts within P85")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
});

test("shows a placeholder when accuracy has no evaluated hit rate yet", async () => {
  mockMetricsFetch({
    "/api/forecasts/accuracy": { ...accuracyFixture, p85_hit_rate: null },
  });
  renderWithClient(<ForecastCard scope={{ teamId: "t-1" }} />);

  expect(await screen.findByText("Past forecasts within P85")).toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
});
