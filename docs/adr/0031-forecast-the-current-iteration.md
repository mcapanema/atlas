# 31. Forecast the current iteration

Date: 2026-11-17

## Status

Proposed. Amends ADR-0010 (per-team metric rules) with one forecast rule;
built-in defaults reproduce the previous numbers.

## Context

The completion forecast counts every open item of the scope whose state type
the `remaining_state_types` rule counts. A team that plans its next cycle
early puts those issues in Todo, so they count as remaining work of the
current cycle, and the forecast reads later than the team's real
commitment.

A status cannot separate "planned for a later iteration" from "committed
now", in any tracker:

- Linear moves an issue in a Backlog-type status to Todo when it is added to
  a cycle, and an issue in Triage has no cycle.
- Jira has three status categories (To Do, In Progress, Done); a To Do issue
  in the active sprint and one in a future sprint look the same.

Atlas must stay generic across trackers (Linear, Jira, Azure DevOps, GitHub
Projects) and methods (Scrum, XP, Kanban). The timebox is common to most of
them under different names: Linear cycle, Jira sprint, Azure DevOps and
GitHub Projects iteration. Kanban has none.

## Decision

1. **Iteration is a tool-neutral fact on the work item.** `WorkItem.iteration`
   is an optional `Iteration` value (source id, name, start, end). Each
   connector maps its own timebox to it; the Linear connector maps the
   issue's cycle. Only the current iteration of an item is stored.
2. **One forecast rule, `remaining_iterations`**, with two values:
   - `any` (built-in default): every open item counts, as before.
   - `current`: an open item counts only when it is in its team's current
     iteration, or in no iteration (unplanned work).
   The rule narrows the `remaining_state_types` count; it never widens it.
3. **The current iteration is derived per team** from the iterations seen on
   the team's items: the one whose start is at or before the instant and
   whose end is after it. In a gap between iterations (a cooldown) it is
   the next one to start. A team with no iteration at all has none, and the
   rule has no effect for it: a Kanban team keeps its forecast.
4. **Per item, its own team's iteration.** A project with items from several
   teams uses each item's team's current iteration.
5. **Throughput history is not filtered.** The team's delivery rate does not
   depend on the iteration an item belonged to.
6. **The forecast says which iterations it counted** (`iterations` on the
   forecast), so the card can show "Counts only Cycle 38".

## Consequences

- A Scrum or XP team can plan the next iteration without moving the
  forecast. A Kanban team sees no change.
- Iterations are known only through their items: an iteration with no item
  is invisible, so an empty current iteration makes the next one current.
- Snapshot replays (`as_of`) use each item's current iteration, not the one
  it had then. An item that rolled over from cycle 37 to 38 reads as
  cycle 38 in a replay of cycle 37. The upgrade path is the tracker's
  history (Linear `IssueHistory.fromCycle`/`toCycle`).
- Out of scope: using the iteration end as the default target date of the
  forecast, and other metrics per iteration.
