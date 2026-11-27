# 33. Count only top-level issues

Date: 2026-11-27

## Status

Accepted. Amends ADR-0010 (per-team metric rules) with one lifecycle rule;
built-in defaults reproduce the previous numbers.

## Context

Atlas counts every issue as a work item: a parent and each of its
sub-issues. The `count_parent_issues` rule can drop the parents, so a team
can count tasks only. Some teams write each top-level issue as a user story
and split it into sub-issues for the work. For them the story is the unit of
value, and a mixed count distorts every metric:

- A story with 12 sub-issues weighs 13 items in throughput and in the
  forecast's remaining work; a story with none weighs 1.
- Sub-issues finish fast, so cycle time and throughput read better than the
  delivery of stories does.
- Linear's cycle view hides sub-issues, so the forecast's remaining count
  (61 for one team) did not match what the team sees (29).

A story's own status often lags its work: a story stays in Todo while a
sub-issue is in progress. Counting stories by their own status alone would
start their cycle late and hide them from Aging WIP.

## Decision

A per-team flag, `count_sub_issues` (built-in on). Off:

- An item leaves every metric, remaining included, when its parent is in
  the same scope (the scope's unfiltered items). Grandchildren leave too.
- A sub-issue whose parent is outside the scope (another team or project,
  or never synced) still counts: it is the scope's only record of that work.
- A parent's cycle starts at the earliest of its own start and the start of
  any in-scope descendant, as of the replay instant, when that is before the
  parent's completion (`derive_flow_sample(earliest_start=...)`). Each
  descendant is folded with its own team's rules, and only one that is not
  canceled and not moved back counts, so abandoned work can't hold a story
  in WIP. The rolled start is never before the parent's arrival (creation,
  or Triage exit), so queue time can't go negative. Descendants come from
  the unfiltered scope, so a type filter keeps the roll-up.
- Completion, cancel and the blocked signal still come from the parent's own
  events; blocked and wait time clip to the longer cycle. The parent's
  stream gets a synthetic `STARTED` at the rolled start, so the CFD and
  state time see it in progress from the same instant (its time in Todo
  then counts as in-progress state time).
- The drop reads the sub-issue's team's rules; the roll-up reads the
  parent's team's rules, like `count_parent_issues`.
- `count_parent_issues` and `count_sub_issues` cannot both be off: almost
  nothing would count.

Parent links follow history, for both parent rules. The Linear sync stores
each parent change (`IssueHistory.fromParentId/toParentId`) as a non-flow
`PARENT_CHANGED` event (detail: the new parent's Linear id), plus the parent
an issue was created with. Each replay instant reads the links of that
instant (`app/application/parent_links.py`):

- An issue with `PARENT_CHANGED` events has the parent its last change up
  to that instant names; an issue without them (synced before these events
  existed, or created through the REST API) has its current parent.
- A link counts only when the parent already existed at that instant.
- `count_parent_issues` asks whether an item had a child, in any team, at
  that instant: the scope loads its items' current and former children and
  their parent history (two filtered queries, only when a team in the scope
  has that rule off).

The rule is enforced in one place, `ScopeData._fold`, which every metric,
forecast and snapshot reads through. Changing it queues the snapshot
recompute like any metric rule.

## Consequences

- A team that writes stories gets throughput, cycle time, Aging WIP and a
  forecast in stories, and the remaining count matches Linear's cycle view.
- Fewer, larger items: weekly throughput is smaller and less even, so the
  forecast range is wider. Stories must be right-sized for the forecast to
  hold.
- Bugs filed as sub-issues leave the Bugs section under this rule.
- A re-parented issue counts under its parent of each day in the recomputed
  history, and an issue that gets its first sub-issue later counts as its
  own item until then.
- Parent history reaches older issues only after a Linear sync, so after
  deploying, run a sync and then "Recompute history". Until then, older
  issues read their current parent, never one created after the replayed
  day.
