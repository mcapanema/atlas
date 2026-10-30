# 26. Explicit blocked signal

Date: 2026-10-29

## Status

Accepted. Amends ADR-0015 (blocked signal on by default) for the label
pattern and "blocked by" relations.

## Context

Engineering managers reported items flagged blocked that were being worked
on. The 2026-10-29 data showed two sources behind them:

- **Linear "blocked by" relations.** All five reported items carried a
  relation added within one second of the issue's creation — planned
  order, written when the issues were created as a batch — and the team
  started them while the blocker was still open. In one team,
  27 of the 31 items blocked in the last seven days came from relations,
  and none was a stop inside the cycle.
- **The built-in label pattern.** `Bloqueante` (60 adds) and `Bloqueada`
  (28 adds) name billing-rule outcomes on three teams ("a rule that blocks
  the bill"), not work status.

The workflow state **Blocked** (341 transitions) was clean: entering it is
an explicit team choice. One team does use a label for real blocks: it adds
`Bloqueada` while work is in progress and removes it later.

## Decision

- `blocked_label_pattern` defaults to off: a label blocks only when the
  team lists it in `blocked_label_names`.
- `blocked_by_relations` defaults to off.
- `blocked_state_pattern` stays on, and explicit BLOCKED/UNBLOCKED events
  still always count.
- Migration `259c45818cf8` marks every organization's recompute "running",
  so the lifespan rewrites snapshot history under the new defaults.

## Consequences

- Blocked time, flow efficiency and the efficiency/risk health components
  fall for teams that relied on relations or pattern labels, including
  snapshot history once the recompute finishes.
- A team that uses a blocked label lists it in "More blocked labels" (or
  turns the pattern back on); a team that uses relations as real stops
  turns them on. Overrides win over the defaults, so a team that stored
  either rule keeps it.
- A team whose label means a real block lists it as a team override, so
  its blocks stay counted.
