import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useThemeMode } from "./context";
import { ThemeProvider } from "./ThemeProvider";

function ModeProbe() {
  const { mode, toggle } = useThemeMode();
  return (
    <button type="button" onClick={toggle}>
      mode:{mode}
    </button>
  );
}

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.restoreAllMocks();
});

describe("ThemeProvider", () => {
  it("defaults to light and stamps data-theme on the root element", () => {
    render(
      <ThemeProvider>
        <ModeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("mode:light")).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("honors a stored dark preference", () => {
    window.localStorage.setItem("atlas-theme", "dark");
    render(
      <ThemeProvider>
        <ModeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("mode:dark")).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("ignores garbage in storage and falls back to the OS preference", () => {
    window.localStorage.setItem("atlas-theme", "solarized");
    const original = window.matchMedia;
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      ...original(query),
      matches: query === "(prefers-color-scheme: dark)",
    }));
    render(
      <ThemeProvider>
        <ModeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("mode:dark")).toBeInTheDocument();
  });

  it("toggle flips the mode and persists the explicit choice", () => {
    render(
      <ThemeProvider>
        <ModeProbe />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByText("mode:light"));
    expect(screen.getByText("mode:dark")).toBeInTheDocument();
    expect(window.localStorage.getItem("atlas-theme")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");

    fireEvent.click(screen.getByText("mode:dark"));
    expect(screen.getByText("mode:light")).toBeInTheDocument();
    expect(window.localStorage.getItem("atlas-theme")).toBe("light");
  });
});
