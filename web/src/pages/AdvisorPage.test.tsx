import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl, runFixture, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AdvisorPage } from "./AdvisorPage";

const advice = {
  generated_at: "2026-07-10T00:00:00Z",
  summary: "Flow is healthy.",
  recommendations: [
    {
      title: "Lower WIP",
      priority: "high",
      problem: "WIP is 12 while weekly throughput is 3",
      root_cause: "Work is started faster than it finishes",
      action: "Set a WIP limit of 6",
      evidence: ["wip=12", "completed=3"],
    },
  ],
};

const succeededRun = () => runFixture({ advice });

/** GET answers the stored run; POST stores and answers `onPost()` (a succeeded run by default). */
interface MockOptions {
  configured?: boolean;
  stored?: object | null;
  onPost?: () => object;
}

function mockFetch({ configured = true, stored = null, onPost = succeededRun }: MockOptions = {}) {
  let latest = stored;
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = requestUrl(input);
    if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
    if (url.startsWith("/api/recommendations/status")) {
      return Promise.resolve(jsonResponse({ configured }));
    }
    if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
      return Promise.resolve(jsonResponse([]));
    }
    if (url.startsWith("/api/personas") && url.endsWith("/feedback")) {
      return Promise.resolve(
        jsonResponse(
          {
            id: "f-1",
            persona: "agile_coach",
            rating: "up",
            comment: null,
            advice_summary: "Flow is healthy.",
            created_at: "2026-07-12T00:00:00Z",
          },
          201,
        ),
      );
    }
    if (url.startsWith("/api/recommendations")) {
      if (init?.method === "POST") {
        latest = onPost();
        return Promise.resolve(jsonResponse(latest, 202));
      }
      return Promise.resolve(jsonResponse(latest));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

function renderPage(initialEntry = "/advisor") {
  return renderWithClient(<AdvisorPage />, [initialEntry]);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AdvisorPage", () => {
  it("warns when the advisor is not configured", async () => {
    mockFetch({ configured: false });

    renderPage();

    await waitFor(() => expect(screen.getByText(/Advisor is not configured/)).toBeInTheDocument());
  });

  it("shows the stored advice on load without a click", async () => {
    mockFetch({ stored: succeededRun() });

    renderPage(`/advisor?team=${teamFixture.id}`);

    expect(await screen.findByText("Flow is healthy.")).toBeInTheDocument();
    expect(screen.getByText(/Generated .* ago/)).toBeInTheDocument();
    const posts = vi.mocked(globalThis.fetch).mock.calls.filter((c) => c[1]?.method === "POST");
    expect(posts).toHaveLength(0);
  });

  it("posts and polls until the run succeeds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let polls = 0;
      vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
        const url = requestUrl(input);
        if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
        if (url.startsWith("/api/recommendations/status")) {
          return Promise.resolve(jsonResponse({ configured: true }));
        }
        if (url.startsWith("/api/personas")) return Promise.resolve(jsonResponse([]));
        if (init?.method === "POST") {
          return Promise.resolve(jsonResponse(runFixture({ status: "running" }), 202));
        }
        polls += 1;
        const latest =
          polls === 1 ? null : polls === 2 ? runFixture({ status: "running" }) : succeededRun();
        return Promise.resolve(jsonResponse(latest));
      });

      renderPage(`/advisor?team=${teamFixture.id}`);
      await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
      fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
      expect(screen.queryByText("Flow is healthy.")).not.toBeInTheDocument();

      await vi.advanceTimersByTimeAsync(2100);
      await vi.advanceTimersByTimeAsync(2100);

      expect(await screen.findByText("Flow is healthy.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the run error when the run failed", async () => {
    mockFetch({ stored: runFixture({ status: "failed", error: "LLM unavailable" }) });

    renderPage(`/advisor?team=${teamFixture.id}`);

    expect(await screen.findByText("Failed to generate advice")).toBeInTheDocument();
    expect(screen.getByText("LLM unavailable")).toBeInTheDocument();
  });

  it("re-enables the button when a poll fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let gets = 0;
      vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
        const url = requestUrl(input);
        if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
        if (url.startsWith("/api/recommendations/status")) {
          return Promise.resolve(jsonResponse({ configured: true }));
        }
        if (url.startsWith("/api/personas")) return Promise.resolve(jsonResponse([]));
        gets += 1;
        return Promise.resolve(
          gets === 1
            ? jsonResponse(runFixture({ status: "running" }))
            : jsonResponse({ detail: "poll boom" }, 500),
        );
      });

      renderPage(`/advisor?team=${teamFixture.id}`);
      await waitFor(() =>
        expect(screen.getByRole("button", { name: /Get advice/ })).toBeDisabled(),
      );
      await vi.advanceTimersByTimeAsync(2100);

      expect(await screen.findByText("poll boom")).toBeInTheDocument();
      await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
      await vi.advanceTimersByTimeAsync(6000);
      expect(gets).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("drops a start failure when another persona is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/recommendations/status")) {
        return Promise.resolve(jsonResponse({ configured: true }));
      }
      if (url.startsWith("/api/personas")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(
        init?.method === "POST" ? jsonResponse({ detail: "no key" }, 409) : jsonResponse(null),
      );
    });

    renderPage(`/advisor?team=${teamFixture.id}`);
    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
    expect(await screen.findByText("no key")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getAllByRole("combobox")[1]);
    fireEvent.click(await screen.findByTitle("Delivery Analyst"));

    await waitFor(() => expect(screen.queryByText("no key")).not.toBeInTheDocument());
  });

  it("disables the button while a run is running", async () => {
    mockFetch({ stored: runFixture({ status: "running" }) });

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeDisabled());
  });

  it("renders summary and recommendations after clicking Get advice", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());
    expect(screen.getByText("Lower WIP")).toBeInTheDocument();
    expect(screen.getByText(/Work is started faster/)).toBeInTheDocument();
    expect(screen.getByText("wip=12")).toBeInTheDocument();
  });

  it("surfaces a failure to start a run", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/recommendations/status")) {
        return Promise.resolve(jsonResponse({ configured: true }));
      }
      if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.startsWith("/api/recommendations")) {
        return Promise.resolve(
          init?.method === "POST"
            ? jsonResponse({ detail: "LLM unavailable" }, 409)
            : jsonResponse(null),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByText("Failed to generate advice")).toBeInTheDocument());
    expect(screen.getByText("LLM unavailable")).toBeInTheDocument();
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderPage();

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });

  it("picks a team from the select and reflects it in the URL", async () => {
    mockFetch();

    renderPage();

    fireEvent.mouseDown((await screen.findAllByRole("combobox"))[0]);
    fireEvent.click(await screen.findByTitle(teamFixture.name));

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
  });

  it("sends the selected persona with the advice request", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}&persona=delivery_analyst`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() =>
      expect(vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]))).toContain(
        `/api/recommendations?team_id=${teamFixture.id}&persona=delivery_analyst`,
      ),
    );
  });

  it("surfaces an advisor status failure instead of silently disabling the button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Failed to load advisor status")).toBeInTheDocument(),
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("submits thumbs-up feedback for the rendered advice", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));

    await waitFor(() => expect(screen.getByText(/Thanks for the feedback/)).toBeInTheDocument());
    const call = vi
      .mocked(globalThis.fetch)
      .mock.calls.find((c) => requestUrl(c[0]).endsWith("/feedback"));
    expect(requestUrl(call![0])).toBe("/api/personas/agile_coach/feedback");
    expect(call![1]!.method).toBe("POST");
    expect(JSON.parse(call![1]!.body as string)).toEqual({
      rating: "up",
      comment: null,
      advice_summary: "Flow is healthy.",
    });
  });

  it("sends the optional comment with thumbs-down feedback", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("Optional comment"), {
      target: { value: "too generic" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));

    await waitFor(() => expect(screen.getByText(/Thanks for the feedback/)).toBeInTheDocument());
    const call = vi
      .mocked(globalThis.fetch)
      .mock.calls.find((c) => requestUrl(c[0]).endsWith("/feedback"));
    expect(JSON.parse(call![1]!.body as string)).toEqual({
      rating: "down",
      comment: "too generic",
      advice_summary: "Flow is healthy.",
    });
  });

  it("surfaces a feedback submission failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/recommendations/status")) {
        return Promise.resolve(jsonResponse({ configured: true }));
      }
      if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/feedback")) {
        return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      }
      if (url.startsWith("/api/recommendations"))
        return Promise.resolve(jsonResponse(succeededRun()));
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));

    await waitFor(() => expect(screen.getByText("Failed to submit feedback")).toBeInTheDocument());
  });

  it("re-arms feedback with an empty comment when advice is requested again", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));
    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("Optional comment"), {
      target: { value: "too generic" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(screen.getByText(/Thanks for the feedback/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByPlaceholderText("Optional comment")).toHaveValue(""));
    expect(screen.queryByText(/Thanks for the feedback/)).not.toBeInTheDocument();
  });
});
