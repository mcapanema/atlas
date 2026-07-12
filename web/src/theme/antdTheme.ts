import { theme } from "antd";
import type { MappingAlgorithm, ThemeConfig } from "antd";

import { FONT_MONO, FONT_UI, palette, type ThemeMode } from "./tokens";

/**
 * The compact algorithm rebases the entire font map on fontSizeSM — a 13px
 * seed derives a 10px app-wide base, below any readable floor. Compact is
 * here for its spacing and control heights, not to shrink type: this final
 * mapping step restores the font ramp the seed intends (13px base).
 */
const restoreTypeRamp: MappingAlgorithm = (seed, map) => {
  const fonts = theme.defaultAlgorithm(seed);
  const ramp = Object.fromEntries(
    Object.entries(fonts).filter(([key]) => /^(fontSize|fontHeight|lineHeight)/.test(key)),
  );
  return { ...(map ?? fonts), ...ramp };
};

/**
 * Maps the Atlas tokens onto Ant Design. The compact algorithm carries the
 * density this audience expects; dark mode stacks the dark algorithm under
 * it and swaps the palette. `cssVar` exposes every derived token as
 * `--ant-*` so index.css and one-off styles never restate a color.
 */
export function buildThemeConfig(mode: ThemeMode): ThemeConfig {
  const p = palette[mode];
  const dark = mode === "dark";
  return {
    // CSS-variables mode is AntD 6's default: every derived token is exposed
    // as --ant-*, which index.css and inline styles rely on.
    hashed: false,
    algorithm: dark
      ? [theme.darkAlgorithm, theme.compactAlgorithm, restoreTypeRamp]
      : [theme.compactAlgorithm, restoreTypeRamp],
    token: {
      colorPrimary: p.primary,
      colorInfo: p.primary,
      colorLink: p.primary,
      colorSuccess: p.success,
      colorWarning: p.warning,
      colorError: p.error,
      colorTextBase: p.ink,
      colorBgBase: p.bg,
      colorBgLayout: p.bg,
      // Light: white cards on white canvas, separated by border.
      // Dark: raised graphite panels on near-black.
      colorBgContainer: dark ? p.surface : p.bg,
      colorBorder: p.border,
      colorBorderSecondary: p.gridline,
      fontFamily: FONT_UI,
      fontFamilyCode: FONT_MONO,
      fontSize: 13,
      // The default curve derives SM=10 from a 13 seed (Tags, table filters
      // use SM) — hold it at base−2, AntD's own 14→12 relationship.
      fontSizeSM: 11,
      borderRadius: 4,
      fontWeightStrong: 600,
      // AntD's default back curves overshoot (OutBack) and anticipate
      // (InBack, y1 = -0.46) — both read as bounce. Instrument motion eases,
      // it doesn't wobble; InBack gets the mirror of the Out curve.
      motionEaseOutBack: "cubic-bezier(0.22, 1, 0.36, 1)",
      motionEaseInBack: "cubic-bezier(0.64, 0, 0.78, 0)",
    },
    components: {
      Layout: { siderBg: p.sidebar, bodyBg: p.bg },
      Menu: {
        itemBg: "transparent",
        activeBarBorderWidth: 0,
        itemHeight: 32,
        itemMarginInline: 8,
        itemColor: p.inkSecondary,
        // AntD derives the selected fill from the low-chroma primary and
        // lands on a muddy slab; a 10% tint keeps the needle crisp.
        itemSelectedBg: dark ? "rgba(65, 176, 188, 0.13)" : "rgba(0, 121, 132, 0.10)",
        itemSelectedColor: p.primary,
        groupTitleColor: p.inkMuted,
        groupTitleFontSize: 11,
      },
      Card: { headerFontSize: 13 },
      Table: { headerColor: p.inkSecondary },
      Statistic: { titleFontSize: 12, contentFontSize: 22 },
      // Dark primary is a bright needle (L 0.70): dark label text reads at
      // 7.6:1 where white would fail (2.6:1).
      ...(dark ? { Button: { primaryColor: p.bg } } : {}),
    },
  };
}
