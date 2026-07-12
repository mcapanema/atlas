import { createContext, useContext } from "react";

import type { ThemeMode } from "./tokens";

export interface ThemeModeValue {
  mode: ThemeMode;
  toggle: () => void;
}

// The default lets components render without a provider (tests, Storybook);
// the live value comes from ThemeProvider, mounted once in main.tsx.
export const ThemeModeContext = createContext<ThemeModeValue>({
  mode: "light",
  toggle: () => {},
});

export function useThemeMode(): ThemeModeValue {
  return useContext(ThemeModeContext);
}
