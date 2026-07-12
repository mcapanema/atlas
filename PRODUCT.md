# Product

## Register

product

## Users

Engineering Managers (and the directors/VPs above them) responsible for
software delivery across teams and projects. They arrive mid-workflow —
between meetings, before a standup, preparing a status review — to answer
one question fast: "how is delivery actually going, and where is the risk?"
They are data-fluent, live in tools like Linear, GitHub, and Grafana, and
have zero patience for dashboards that decorate instead of inform.

## Product Purpose

Atlas is a Delivery Intelligence Platform: it observes delivery data
(issues, deployments), computes flow metrics, forecasts outcomes
(Monte Carlo), scores delivery health, and gives AI-powered advisory
guidance. It sits on top of project-management tools as an intelligence
layer. Success looks like an EM trusting Atlas's numbers enough to bring
them into a leadership conversation — and acting on a risk before it
becomes a slip.

## Brand Personality

Sharp, analytical, dense. A power tool for data people — high information
density handled with taste, terminal-adjacent confidence, numbers first.
The tone is a senior analyst who has already done the work: precise,
direct, never breathless. Emotional goal: the calm competence of an
instrument you trust, not the excitement of a pitch deck.

Reference points (specifically):
- **Linear** — tight type scale, keyboard-fast feel, dense lists that stay
  legible, restraint as identity.
- **Grafana / Datadog** — chart-first ops density: panels of time series,
  thresholds, and status readable at a glance.
- **Stripe Dashboard** — financial-grade data presentation: impeccable
  tables, quiet color, figures you trust at face value.

## Anti-references

- **Generic admin template** — the stock Ant Design look: undifferentiated
  AntD blue, default cards, template feel (roughly the current state; the
  thing to design away from).
- **Executive BI gloss** — PowerBI/Tableau-style glossy KPI tiles, gradient
  hero metrics, dashboard-as-poster.
- **Jira / enterprise chrome** — crowded toolbars, nested menus,
  configuration crowding out content.
- **Startup landing aesthetics** — gradients, glassmorphism, oversized
  display type leaking into app UI.

## Design Principles

1. **Numbers are the interface.** Every screen exists to answer an EM's
   question; data leads, chrome recedes. If an element doesn't help read a
   number or act on it, it goes.
2. **Density with hierarchy.** Dense is a feature for this audience — but
   only when hierarchy makes it scannable. Earn each row of density with
   clear structure; never trade legibility for compactness.
3. **Honest uncertainty.** Forecasts are probabilistic (percentiles, not
   promises) and health scores have reasons. Show confidence and its
   limits; never let decoration inflate false certainty.
4. **Earned familiarity.** Standard affordances, consistent component
   vocabulary, no invented controls. The tool disappears into the task.
5. **Signal over status.** Lead with what changed and what's at risk, not
   vanity metrics. A flat "everything is fine" screen should be quiet;
   risk should be impossible to miss.

## Accessibility & Inclusion

WCAG 2.1 AA: ≥4.5:1 contrast for body text (≥3:1 for large text), full
keyboard navigability, visible focus states, `prefers-reduced-motion`
alternatives for all animation. Charts and status indicators should not
rely on color alone where practical (labels, shapes, thresholds) — this is
a metrics product; color-blind EMs must be able to read it.
