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
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    coverage: {
      provider: "v8",
      include: ["src/**"],
      // main.tsx is bootstrap-only (createRoot().render()); test helpers
      // aren't product code.
      exclude: ["src/test/**", "src/**/*.test.*", "src/main.tsx"],
      // Floors a few points under the 2026-07-11 measurement (97.1% lines,
      // 93.8% branches, 96.7% funcs) — a regression guard, not a target.
      thresholds: {
        lines: 95,
        statements: 95,
        branches: 91,
        functions: 94,
      },
    },
  },
});
