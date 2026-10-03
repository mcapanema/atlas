# web/

React 19 + TypeScript + Vite frontend. Ant Design for UI, TanStack Query
for server state, React Router for routing.

**Before any UI/UX design change, read `../PRODUCT.md`.** Register:
**product** — a sharp, analytical, dense instrument for Engineering Managers
(references: Linear, Grafana/Datadog, Stripe Dashboard). Numbers are the
interface; density with hierarchy; honest uncertainty; earned familiarity;
signal over status. WCAG 2.1 AA; charts/status must not rely on color
alone. Avoid: stock-AntD admin-template look, executive BI gloss,
enterprise chrome, landing-page aesthetics.

## Commands (from `web/`, or `make <target>` from the repo root)

`npm run dev` · `build` · `test` (fast, no coverage) · `test:coverage`
(what `make test`/CI run) · `typecheck` · `lint` · `format` /
`format:check` · `knip`

## Shape

- `src/api/<concept>.ts` — a `use<Concept>s()` TanStack Query hook + the
  concept's TS type, built on `src/api/client.ts`'s `apiFetch<T>(path)`.
- `src/pages/<Concept>Page.tsx` — one page per concept.
- `src/components/AppLayout.tsx` — the sidebar shell; a new page goes in
  its grouped `NAV` items and in `App.tsx`'s `<Routes>`.
- `src/theme/` — the design system. `tokens.ts` is the single source of
  truth for both modes' palette and font stacks; `antdTheme.ts` maps it
  onto AntD; `src/index.css` uses AntD's `--ant-*` variables. Never
  hard-code a color. Mode comes from `useThemeMode()`.
- Fonts: Red Hat superfamily only (`@fontsource-variable/*` in `main.tsx`)
  — Text for UI, Display for headings, Mono for metric figures.
- Charts: Apache ECharts — pure option builders in `src/lib/charts.ts`,
  rendered by `src/components/EChart.tsx`. Read both files' header
  comments before adding a chart or series type.

## Gates

- Formatting is Prettier: run `make format`, never hand-fix style.
- ESLint (type-aware) enforces complexity ceilings on product code
  (`eslint.config.js`). Over one? Extract a subcomponent, hook, or pure
  helper in `src/lib/` (pattern: `FlowDashboard.tsx` + `lib/teamRows.ts`) —
  don't disable the rule.
- Coverage floors live in `vite.config.ts`; PRs also need ≥ 90% of changed
  `src/` lines covered. If a gate trips, add tests — only lower a floor
  with a reviewed justification.
- `knip`: no unused files, dependencies, or exports — delete dead code
  rather than ignoring it.

## Tests

Vitest + React Testing Library.

- A component using `useQuery`/`useMutation` renders via
  `renderWithClient(ui, initialEntries?)` from `src/test/render.tsx` — a
  bare `render()` throws "No QueryClient set".
- Shared fixtures (`jsonResponse`, `teamFixture`,
  `mockMetricsFetch(extraRoutes?)`, `requestUrl()`) live in
  `src/test/fixtures.ts` — don't re-declare them per file. Read a fetch
  mock's URL with `requestUrl()`, never `String(input)`.
- `window.matchMedia` (needed by AntD's `Table`) is polyfilled once in
  `src/test/setup.ts` — don't re-polyfill.
- jsdom has no canvas: a test rendering a page with charts must
  `vi.mock("../components/EChart")`; only `charts.test.ts` asserts on
  option contents.
