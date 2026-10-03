/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    // formatDateTime renders local time; pin the zone so timestamp
    // assertions don't depend on the machine running the suite.
    env: { TZ: "UTC" },
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    coverage: {
      provider: "v8",
      include: ["src/**"],
      // main.tsx is bootstrap-only (createRoot().render()); test helpers
      // aren't product code.
      exclude: ["src/test/**", "src/**/*.test.*", "src/main.tsx"],
      // Floors ~1.5 points under the 2026-10-02 measurement (99.2% lines,
      // 98.6% statements, 97.6% funcs, 92.0% branches) — a regression
      // guard, not a target. Branches stay at 91: they were 91.01% before
      // the complexity refactor and need real tests, not a padded floor.
      thresholds: {
        lines: 97,
        statements: 97,
        branches: 91,
        functions: 96,
      },
    },
  },
});
