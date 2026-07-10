# web/

React 19 + TypeScript + Vite frontend. Ant Design for UI, TanStack Query
for server state, React Router for routing.

## Commands (run from `web/`, or via `make <target>` from the repo root)

`npm run dev` · `npm run build` · `npm run test` · `npm run typecheck` ·
`npm run lint`

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
- Tests use Vitest + React Testing Library. Any component using
  `useQuery`/`useMutation` needs a `QueryClientProvider` wrapper in its
  test (see `OrganizationsPage.test.tsx`'s `renderWithClient` helper) — a
  bare `render()` throws "No QueryClient set". Ant Design's `Table` needs
  `window.matchMedia`, polyfilled once in `src/test/setup.ts` — don't
  re-polyfill per test file.
- `tsconfig.json` intentionally has no `references` entry to
  `tsconfig.node.json` — adding one breaks `tsc -b` (TS6306/TS6310, since
  `tsconfig.node.json` isn't `composite: true`). Don't re-add it without
  also making `tsconfig.node.json` composite (which then needs
  `outDir`/`tsBuildInfoFile` to avoid leaking build artifacts into `web/`).
- Charts are Apache ECharts via `src/components/EChart.tsx` (lifecycle
  wrapper) + pure option builders in `src/lib/charts.ts`. jsdom has no
  canvas: tests that render a page containing charts must
  `vi.mock("../components/EChart")`; only `charts.test.ts` asserts on
  option contents. Chart colors in `charts.ts` are palette-validated —
  don't swap them casually, and keep the CFD's legend + end labels
  (contrast relief for the aqua/yellow bands).
