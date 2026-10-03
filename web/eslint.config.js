import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import { reactRefresh } from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  { ignores: ["dist", "coverage"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite(),
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        // vite.config.ts sits outside tsconfig.json's `src` include.
        projectService: { allowDefaultProject: ["vite.config.ts"] },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    // Complexity gates for product code. A violation means "split it" —
    // extract a subcomponent, hook, or pure helper in src/lib/ — not
    // "disable the rule". Tests are exempt: a describe() block is long by
    // design and flat test bodies don't benefit from extraction.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    rules: {
      complexity: ["error", 12],
      "max-depth": ["error", 4],
      "max-params": ["error", 4],
      "max-nested-callbacks": ["error", 3],
      "max-lines-per-function": ["error", { max: 120, skipBlankLines: true, skipComments: true }],
      "max-lines": ["error", { max: 400, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // fetch mocks are idiomatically `async (input) => jsonResponse(...)`.
    files: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    rules: { "@typescript-eslint/require-await": "off" },
  },
]);
