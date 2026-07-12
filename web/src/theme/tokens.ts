/**
 * Atlas design tokens — single source of truth for both theme modes.
 *
 * Palette composed in OKLCH (seed hue 205, "flight-deck instrument":
 * graphite neutrals, one teal needle, amber for attention) and exported
 * as hex because Ant Design's theme algorithm and ECharts' canvas
 * renderer both need concrete sRGB values. The oklch() provenance of
 * every value is kept in the comment beside it; contrast pairs are
 * WCAG-verified (ink/bg ≥ 7:1, secondary text ≥ 4.5:1).
 *
 * `index.css` mirrors bg/ink literals for correct first paint before
 * React mounts — change them together.
 */

export type ThemeMode = "light" | "dark";

export interface Palette {
  bg: string; // page + content canvas
  surface: string; // raised panels (dark-mode cards, light-mode sidebar)
  sidebar: string; // the second neutral layer behind navigation
  border: string;
  ink: string; // primary text
  inkSecondary: string; // supporting text, ≥ 4.5:1 on bg
  inkMuted: string; // axis labels, captions, ≥ 4.5:1 on bg
  primary: string; // the teal needle — actions, selection, links
  accent: string; // amber — attention, matches the chart "to do" band
  success: string;
  warning: string;
  error: string;
  gridline: string; // chart gridlines / secondary borders
  baseline: string; // chart axis lines
}

export const palette: Record<ThemeMode, Palette> = {
  light: {
    bg: "#ffffff", // oklch(1 0 0)
    surface: "#f3f6f8", // oklch(0.972 0.004 220)
    sidebar: "#f3f6f8", // second neutral layer = surface in light
    border: "#dadfe1", // oklch(0.90 0.006 220)
    ink: "#1a2224", // oklch(0.245 0.012 220) — 16.2:1 on bg
    inkSecondary: "#444f53", // oklch(0.42 0.015 220) — 8.4:1
    inkMuted: "#646f73", // oklch(0.535 0.015 220) — 5.2:1
    primary: "#007984", // oklch(0.52 0.10 205) — white text 5.2:1
    accent: "#d28f0e", // oklch(0.70 0.145 75) — ink text 5.8:1
    success: "#118659", // oklch(0.55 0.12 160)
    warning: "#c8800d", // oklch(0.66 0.14 70)
    error: "#c9302d", // oklch(0.55 0.19 27)
    gridline: "#e3e7e8", // oklch(0.925 0.004 220)
    baseline: "#babfc0", // oklch(0.80 0.006 220)
  },
  dark: {
    bg: "#0a0d0e", // oklch(0.155 0.006 230)
    surface: "#121617", // oklch(0.195 0.007 230)
    sidebar: "#0e1112", // between bg and surface — flat, border-separated
    border: "#2a2f31", // oklch(0.30 0.008 230)
    ink: "#dbdfe0", // oklch(0.90 0.005 220) — 14.5:1 on bg
    inkSecondary: "#acb2b5", // oklch(0.76 0.008 220) — 9.1:1
    inkMuted: "#8c9496", // oklch(0.66 0.010 220) — 6.3:1
    primary: "#41b0bc", // oklch(0.70 0.10 205) — dark text 7.6:1, 7.6:1 on bg
    accent: "#dda227", // oklch(0.75 0.145 80)
    success: "#44b782", // oklch(0.70 0.13 160)
    warning: "#de9c31", // oklch(0.74 0.14 75)
    error: "#e85854", // oklch(0.65 0.18 25)
    gridline: "#212628", // oklch(0.265 0.008 230)
    baseline: "#3e4346", // oklch(0.38 0.008 230)
  },
};

/**
 * One superfamily carries the whole identity: Red Hat Text at UI sizes,
 * Red Hat Display for headings/wordmark, Red Hat Mono for figures.
 * Loaded as variable fonts in `main.tsx`; system stacks as fallback.
 */
export const FONT_UI =
  "'Red Hat Text Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
export const FONT_DISPLAY =
  "'Red Hat Display Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
export const FONT_MONO =
  "'Red Hat Mono Variable', ui-monospace, SFMono-Regular, Menlo, monospace";
