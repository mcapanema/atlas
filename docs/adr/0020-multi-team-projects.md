# 20. Multi-team projects

Date: 2026-10-28

## Status

Accepted. Refines ADR-0010 (metric rules) for project scopes.

## Context

A Linear project can span several teams. The numbers were never missing
items: sync links each issue to its project whatever the issue's team, and
each item is folded under its own team's rules. Five defects remained:

1. A project's scope-level rules (health scales and weights, calendar,
   windows, forecast history, remaining states) came from `Project.team_id`,
   Linear's first team. Linear's team order is not a contract, so the owner,
   and with it the rules, could flip between syncs.
2. A rules change on a team other than the project's home team did not
   rewrite the project's snapshot history.
3. A team sync captured the home team's projects even when other teams'
   items in them were stale, and never captured a project for a non-home
   team.
4. When Linear's first team was not synced in Atlas, the project was
   skipped and every item in it was stored without a project.
5. The UI and MCP showed one team per project.

## Decision

- A project's teams are derived from its items
  (`WorkItemRepository.team_ids_by_project()`). There is no join table and
  no schema change; a team with no items in the project changes no number.
- A project whose items sit in one team reads that team's rules, even when
  it is not the home team. A multi-team project reads the workspace rules
  (built-in plus the organization layer) for its scope-level rules. A
  project with no items reads its home team's rules.
- A team sync captures only the projects whose items are all in that team,
  plus its home projects with no items. A multi-team project is captured by
  the organization sync.
- The home team is the first team in Linear's list that Atlas has synced
  (`SourceProject.team_external_ids`), not simply the first one.
- Existing snapshot history of multi-team projects is rewritten once by the
  data migration `c4e8a2b7d913`, which marks the affected organizations'
  recompute as running (the mechanism of `f7a3c1d9e2b5`).

## Consequences

- No schema change. `ProjectRead.team_ids` lists every team a project
  spans; the Project page groups projects by home team and tags
  multi-team ones "Workspace rules", and MCP `list_scopes` shows
  "(teams ...)".
- Editing the workspace layer or any spanned team's rules recomputes the
  projects whose derived teams intersect the change.
- A multi-team project's snapshots refresh only on an organization sync;
  a team sync leaves them as they were.
- Open: a project that turns multi-team after an item moves teams keeps
  the history written under its earlier rules until the next rules change
  or rebuild sync (a `ponytail:` note in `MetricRulesResolver.resolve`).
