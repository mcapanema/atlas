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

  it("defines the forecast method and each figure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(jsonResponse(forecastFixture)),
    );

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Completion forecast")).toBeInTheDocument());
    fireEvent.focus(screen.getByText("Completion forecast"));
    expect(
      await screen.findByText(/2,000 simulations of the remaining work/),
    ).toBeInTheDocument();

    fireEvent.focus(screen.getByText("P85 finish"));
    expect(await screen.findByText(/85% of simulations finished by then/)).toBeInTheDocument();
  });

  it("re-forecasts against an assumed backlog size and labels it as assumed", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("remaining=40")) {
        return Promise.resolve(jsonResponse({ ...forecastFixture, remaining: 40 }));
      }
      return Promise.resolve(jsonResponse(forecastFixture));
    });

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());

    const input = screen.getByLabelText("Assume remaining items");
    fireEvent.change(input, { target: { value: "40" } });
    fireEvent.blur(input);

    await waitFor(() =>
      expect(screen.getByText("Remaining items (assumed)")).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText("40")).toBeInTheDocument());
  });

  it("keeps the card (and the input's focus target) mounted while a scenario re-forecast is in flight", async () => {
    let resolveScenario: (() => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("remaining=40")) {
        return new Promise((resolve) => {
          resolveScenario = () => resolve(jsonResponse({ ...forecastFixture, remaining: 40 }));
        });
      }
      return Promise.resolve(jsonResponse(forecastFixture));
    });

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());

    const input = screen.getByLabelText("Assume remaining items");
    fireEvent.change(input, { target: { value: "40" } });
    fireEvent.blur(input);

    // The re-forecast request for remaining=40 is still in flight here. If the
    // query has no data yet, the card must not unmount — an unmount here would
    // recreate this input and drop a real user's keyboard focus mid-entry.
    expect(screen.getByLabelText("Assume remaining items")).toBeInTheDocument();

    resolveScenario?.();
    await waitFor(() =>
      expect(screen.getByText("Remaining items (assumed)")).toBeInTheDocument(),
    );
  });

  it("does not re-forecast on every keystroke, only once the value is committed", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input) =>
        Promise.resolve(
          jsonResponse(
            String(input).includes("remaining=40")
              ? { ...forecastFixture, remaining: 40 }
              : forecastFixture,
          ),
        ),
      );

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());
    fetchSpy.mockClear();

    const input = screen.getByLabelText("Assume remaining items");
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.change(input, { target: { value: "40" } });

    // Two intermediate values were typed but neither should have re-run the
    // backend's Monte Carlo simulation — only a blur/Enter commit does.
    expect(fetchSpy).not.toHaveBeenCalled();

    fireEvent.blur(input);

    await waitFor(() =>
      expect(screen.getByText("Remaining items (assumed)")).toBeInTheDocument(),
    );
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls.filter((u) => u.includes("remaining="))).toEqual([
      expect.stringContaining("remaining=40"),
    ]);
  });

  it("returns to the measured backlog when the assumption is cleared", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      Promise.resolve(
        jsonResponse(
          String(input).includes("remaining=40")
            ? { ...forecastFixture, remaining: 40 }
            : forecastFixture,
        ),
      ),
    );

    renderWithClient(<ForecastCard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());
    const input = screen.getByLabelText("Assume remaining items");
    fireEvent.change(input, { target: { value: "40" } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(screen.getByText("Remaining items (assumed)")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    await waitFor(() => expect(screen.getByText("Remaining items")).toBeInTheDocument());
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
