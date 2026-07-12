import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, test, vi } from "vitest";

vi.mock("./EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { forecastFixture, jsonResponse, mockMetricsFetch } from "../test/fixtures";
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
    expect(screen.getByText("2026-07-22")).toBeInTheDocument(); // P50 finish
    expect(screen.getByText("2026-08-04")).toBeInTheDocument(); // P95 finish
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
    fireEvent.change(input, { target: { value: "2026-09-01" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("82%")).toBeInTheDocument());
  });
});

test("shows forecast accuracy once past forecasts resolved", async () => {
  mockMetricsFetch();
  renderWithClient(<ForecastCard scope={{ teamId: "t-1" }} />);

  expect(await screen.findByText("Past forecasts within P85")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
});
