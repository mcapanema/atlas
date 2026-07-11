# web/

React 19 + TypeScript + Vite frontend. Ant Design for UI, TanStack Query
for server state, React Router for routing.

## Commands (run from `web/`, or via `make <target>` from the repo root)

`npm run dev` · `npm run build` · `npm run test` · `npm run test:coverage` ·
`npm run typecheck` · `npm run lint`

## Shape

- `src/api/<concept>.ts` — a `use<Concept>s()` TanStack Query hook + the
  concept's TS type, built on `src/api/client.ts`'s `apiFetch<T>(path)`.
- `src/pages/<Concept>Page.tsx` — one page per concept, an Ant Design
  component consuming the query hook.
- `src/components/AppLayout.tsx` — the sidebar shell; add new pages to its
  `Menu` items and to the `<Routes>` in `App.tsx`.

## Conventions

- ESLint (flat config, `eslint.config.js`) + `tsc --noEmit` both gate CI —
  run `npm run lint` and `npm run typecheck` before committing (`make
  check` runs both, both sides).
- `npm run test:coverage` is what `make test` and CI run — v8 coverage
  with thresholds (95% lines/statements, 91% branches, 94% functions,
  configured in `vite.config.ts`; `src/main.tsx` and `src/test/` helpers
  excluded as non-product code). Plain `npm run test` skips coverage for
  fast local loops. If the gate trips, add tests; only lower a threshold
  with a reviewed justification.
- Tests use Vitest + React Testing Library. Any component using
  `useQuery`/`useMutation` needs a provider wrapper in
  its test — use `renderWithClient(ui, initialEntries?)` from
  `src/test/render.tsx` (fresh QueryClient with retries off + MemoryRouter);
  a bare `render()` throws "No QueryClient set". Shared response fixtures
  (`jsonResponse`, `teamFixture`, `mockMetricsFetch(extraRoutes?)`) live in
  `src/test/fixtures.ts` — don't re-declare them per file. Ant Design's `Table` needs
  `window.matchMedia`, polyfilled once in `src/test/setup.ts` — don't
  re-polyfill per test file.
- `tsconfig.json` intentionally has no `references` entry to
  `tsconfig.node.json` — adding one breaks `tsc -b` (TS6306/TS6310, since
  `tsconfig.node.json` isn't `composite: true`). Don't re-add it without
  also making `tsconfig.node.json` composite (which then needs
  `outDir`/`tsBuildInfoFile` to avoid leaking build artifacts into `web/`).
- Charts are Apache ECharts via `src/components/EChart.tsx` (lifecycle
  wrapper) + pure option builders in `src/lib/charts.ts`. `EChart.tsx`
  imports from `echarts/core` and registers only the modules the builders
  use — a new chart/component type in `charts.ts` needs its module
  registered in `EChart.tsx` (missing registration fails at runtime, not
  in jsdom tests). Type-only imports from `"echarts"` are fine; runtime
  imports of the full `"echarts"` package are not. jsdom has no
  canvas: tests that render a page containing charts must
  `vi.mock("../components/EChart")`; only `charts.test.ts` asserts on
  option contents. Chart colors in `charts.ts` are palette-validated —
  don't swap them casually, and keep the CFD's legend + end labels
  (contrast relief for the aqua/yellow bands).
