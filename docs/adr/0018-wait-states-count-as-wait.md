# 18. Wait states count as wait

Date: 2026-10-21

## Status

Accepted. Extends ADR-0015 (the blocked signal) for flow efficiency, queue
time and touch time.

## Context

Flow efficiency read close to 100% for every team. Blocked periods were its
only wait signal, so time an item spent waiting in a state such as In Review
or Waiting for Deploy counted as active work. Linear gives In Progress, In
Review and Waiting for Deploy the same `started` state type, so only state
names can separate work from wait.

Faturamento & Glosa, trailing 14 days to 2026-10-21: flow efficiency 0.97,
queue time p50 0.2 working days. Of the started-state time of the 158 items
it completed since 2026-10-07, In Review held 59% and Waiting for Deploy
12%; In Progress held 29%.

## Decision

- A per-team `wait_state_names` rule lists the workflow states whose time
  counts as wait (exact name, any case), through the usual workspace and
  team override layers.
- There is no built-in name pattern, and the list is empty by default.
  State names vary too much across teams; the team knows which of its
  stages are waiting. No team's numbers or snapshot history change until
  its rules are edited, and saving rules already recomputes the history,
  so there is no migration.
- In-cycle wait is the union of blocked periods and wait-state stays,
  clipped to the cycle on the working calendar (ADR-0017). A state both
  blocked and waiting counts once. Flow efficiency, queue time and touch
  time read it; blocked time stays blocked-only.

## Consequences

- Listing In Review and Waiting for Deploy for Faturamento & Glosa moved
  its trailing-14-day flow efficiency from 0.97 to 0.41, queue time p50
  from 0.2 to 1.8 working days and touch time p50 from 1.4 to 0.2 working
  days. An unconfigured team's numbers were unchanged.
- The advisor context (and the MCP brief) adds a wait-time total when it
  exceeds blocked time, so advice can attribute low efficiency to waiting
  stages rather than to blockers.
- Teams that list no wait states still read blocked-only efficiency, near
  100%. `weight_efficiency` stays 0: re-weighting the efficiency health
  component needs calibration once enough teams are configured.
