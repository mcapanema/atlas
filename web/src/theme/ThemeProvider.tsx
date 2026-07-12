import { ConfigProvider } from "antd";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { buildThemeConfig } from "./antdTheme";
import { ThemeModeContext } from "./context";
import type { ThemeMode } from "./tokens";

const STORAGE_KEY = "atlas-theme";

function initialMode(): ThemeMode {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialMode);

  // index.html sets these pre-paint; keep them in sync after toggles so
  // global CSS ([data-theme]) and native widgets (color-scheme) follow.
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
  }, [mode]);

  const value = useMemo(
    () => ({
      mode,
      toggle: () =>
        setMode((current) => {
          const next: ThemeMode = current === "light" ? "dark" : "light";
          // Persist only explicit choices — first visits keep following
          // the OS preference.
          window.localStorage.setItem(STORAGE_KEY, next);
          return next;
        }),
    }),
    [mode],
  );

  return (
    <ThemeModeContext.Provider value={value}>
      <ConfigProvider theme={buildThemeConfig(mode)}>{children}</ConfigProvider>
    </ThemeModeContext.Provider>
  );
}
