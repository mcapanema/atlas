# 10. Per-team metric rules

Date: 2026-10-03

## Status

Accepted. Amends ADR-0008 (persisted analytics snapshots).

## Context

Each metrics audit ended in a global decision about how to read delivery
data: born-done items excluded, reopens measured first start to last done,
moving back to backlog ends WIP, Done → Canceled stays delivered, health
cut-offs at 70/40, UTC day boundaries. The 2026-10-03 audit found teams that
behave differently — 201 in-progress items had been parked in Backlog and
restarted, inflating aging under a "first start" clock that suits teams that
never park work. No single rule set fits every team.

## Decision

Every rule that changes a computed number is a field of the domain's
`MetricRules` (`app/domain/metric_rules/`), whose defaults are the previous
built-in behavior. Overrides are sparse JSON layers in
`metric_rule_overrides`: one per organization (the editable workspace
default) and one per team. Effective rules = built-in ⊕ workspace ⊕ team.

- Lifecycle rules apply per item, by the item's team; health, calendar and
  window rules come from the scope's team (a project's owning team).
  `ScopeSampleLoader` resolves them once per load, so every analytics path
  — dashboards, forecasts, snapshots, advisor, MCP — follows them.
- A rule change rewrites the affected scopes' snapshot history in place,
  each snapshot re-derived as of its capture instant (event streams
  truncated there). Forecast snapshots are re-run too, so forecast
  accuracy becomes a backtest of the current rules.
- The rewrite is an in-process asyncio task (no queue, ADR-0002) run by
  `RecomputeRunner` (`app/api/recompute.py`). A save cancels the running
  task before it writes (the runner's async `paused()` context; SQLite
  allows one writer), then the runner restarts with the union of pending
  scopes. Each scope is rewritten in its own transaction.
- Recompute status lives on the organization's override row and is written
  only through `save_recompute`, separately from the override columns, so a
  PATCH and the runner's finish cannot overwrite each other. The lifespan
  resumes an interrupted rewrite.
- Rules that need facts Atlas doesn't store yet (blocked relations, parent
  issues, state types) are out of scope here (sub-project B).

## Consequences

- Teams can be measured by their own working agreements; a "Custom rules"
  tag marks dashboards whose rules differ from the workspace default.
- Snapshots are no longer immutable records of what Atlas said: they say
  what the current rules say about each past day. Forecast accuracy no
  longer measures what Atlas actually predicted.
- Comparing teams with different rules compares different definitions —
  the tag is the warning.
- A workspace change that would make a team's own overrides invalid is
  rejected with the team named.
- A rewrite costs one Monte Carlo run per stored forecast snapshot; it runs
  in the background and the settings page polls its status.
