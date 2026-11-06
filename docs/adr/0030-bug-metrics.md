# 30. Bug metrics

Date: 2026-11-06

## Status

Accepted. Amends ADR-0010 and ADR-0011 (built-in defaults reproduce the
previous numbers) for the `type_labels` rule. Uses ADR-0003
(compute-on-read analytics) and ADR-0017 (working days).

## Context

An Engineering Manager wants to know if the team's growing capacity and
velocity come with quality: are new bugs keeping pace with delivery, how
much of the completed work is bug fixes, and how fast does the team fix
urgent bugs compared with low-priority ones.

Linear has no issue type, so teams mark bugs with a label (`Bug` on the
pilot team). Atlas already classifies types at read time with the
`type_labels` rule (ADR-0011), but its built-in list was empty, so every
Linear item read as a task and the `types=bug` filter showed nothing.
Linear also has a priority (0 = none, 1 = urgent … 4 = low), which Atlas did
not store.

Bugs are not incidents. Most bugs are not production failures: counting
them as DORA incidents would raise change failure rate, put weeks of backlog
wait into time to restore, and blame a deployment that a months-old bug has
nothing to do with (ADR-0025).

## Decision

### What a bug is

- A bug is an item whose effective type is `bug`:
  `MetricRules.type_of(item)`, the first `type_labels` match among the
  item's labels (after `strip().casefold()`), else its stored type. The
  type filter, the Work items page, the Bugs section and the aging bug icon
  all use this one call, so they agree. A second rule such as
  `bug_label_names` was rejected: two definitions of "bug" could disagree.
- The built-in `type_labels` changes from `()` to `(("bug", bug),)`. This is
  the one default that differs from the previous numbers: for a team with no
  `type_labels` override, items labelled `bug` move from `task` to `bug` in
  the `types=` filter of the Team, Project and Executive dashboards, the type
  column and filter of the Work items page, and `types=` on the aging and
  forecast endpoints. Snapshots are not filtered by type, so they do not
  change.
- A workspace or team `type_labels` list replaces the default whole
  (`resolve_rules`). No data migration adds `bug` to existing lists: those
  lists were set on purpose, and the `no_mapping` state tells the user what
  to add.
- Classification stays at read time. Setting the type at sync time was
  rejected: each rule edit would need a full re-sync.

### The Bugs section

- A section of the Team page, after the flow charts, served by
  `GET /api/metrics/bugs`. Team scope only: a project scope answers 422, as
  `/api/metrics/dora` does.
- **Computed on read** (ADR-0003), from the flow samples that the team's
  rules produce (ADR-0010). Born-done items and, when the team says so,
  parent issues are already left out. Not snapshotted: a snapshot would
  need a recompute on each `type_labels` edit and would freeze the bucket
  of a bug that gets its label later.
- **Filters:** `exclude_states` applies (hidden states are a choice of what
  work to look at, for bugs and non-bugs alike). The type filter does not
  apply, because it would remove one side of each ratio; the section says
  so when a type filter is set.
- **One window** for the whole section: the page's period, by default the
  stats window (`STATS_WINDOW_DAYS`, 30 days). The window is
  `(now - window_days, now]`, with `now` the period end. This is a
  deliberate exception to the chart-window policy in
  `app/domain/metrics/windows.py`, with no planned fix: the bug chart
  follows the stats window so that the chart and its ratios cover the same
  days. At the default period, the bug chart covers 30 days while the
  Throughput chart covers 90; the card title names its window. A rolling
  window, a fixed 90-day window for the priority table, and one endpoint
  with two windows were rejected for the same reason: one card, one
  window.
- **Buckets** use the throughput bucketing (daily up to
  `daily_bucket_max_days`, else weekly with the oldest bucket clipped), so
  they match the Throughput chart for the same window.

### The numbers

- **Bugs created:** bugs with `created_at` in the window. The creation date,
  not the arrival (`lead_time_start`) and not the day the label was added:
  it puts a bug in the week it was reported and needs no label history.
- **Bugs completed:** bugs completed in the window.
- **A canceled bug** (canceled with no completion) counts nowhere: it can be
  a duplicate or "not a bug". Cancellation is read at the period end.
- **New bugs per non-bug item completed** (the main number): bugs created ÷
  non-bug items completed. Bugs are left out of the denominator, so a bug
  sprint does not lower the ratio with no change in bug inflow. Names such
  as "defect rate" were rejected: they suggest that the completed items
  caused the bugs, which the data cannot show.
- **Bug share** (the second number): bugs completed ÷ all items completed.
  It is not the main number because it goes down when a team ignores bugs
  and goes up during a bug sprint.
- **Bug lead time by priority:** the lead time (`lead_times`, working days on
  the team calendar, from `arrived_at`) of the bugs completed in the window,
  as the median, in an "All bugs" row and one row per priority (urgent,
  high, medium, low, none = "No priority"). The Lead time card's
  calculation, so the two agree; a mean was rejected because a few slow
  bugs would decide it, and the name "MTTR" because it is a DORA term. Each
  row also has the bugs open at the period end and the age of the oldest
  open one (from `arrived_at`). "No priority" is its own row: on the pilot
  team it held 30% of the bugs.
- **Evidence floor:** a ratio's sample is its denominator, a median's is its
  fixed count. A value shows whenever its sample is above zero, with
  "Too few {noun} (n of min)" below `health_min_sample`, as DORA shows
  (ADR-0025). Hiding the value was rejected: bug metrics have no band, so a
  hidden value removes the only output.
- **States:** `ok` when any item of the team (in its whole history up to the
  period end, after `exclude_states`) has the effective type `bug`;
  otherwise `no_mapping` when no `type_labels` entry maps to `bug`, else
  `no_matches`. The last two show a message and a link to Metric rules, no
  numbers: a mapping that matches nothing is the likeliest setup mistake,
  and a silent 0 would hide it. No label-coverage number: none can find a
  bug that has no label, so the help text says the numbers are a lower
  bound.

### Priority

- A new domain enum `WorkItemPriority` (`urgent`, `high`, `medium`, `low`,
  `none`) and a nullable `work_items.priority` column. NULL means
  "unknown": not synced yet, an unknown source value, or an item created
  through the REST API. `none` means the source says "no priority". A
  non-null default was rejected because it makes "not synced" look like "no
  priority". Linear's raw numbers stay in the connector: 0 → none,
  1 → urgent, 2 → high, 3 → medium, 4 → low.
- A bug with an unknown priority counts in "All bugs" and in no priority
  row; the section shows how many such bugs there are.
- The Linear sync writes the priority on create and on update. The first
  sync after deploy rewrites each Linear row once.

### Aging

- Each aging item carries its effective `type`; the web shows a bug icon next
  to the blocked icon when the type is `bug`. A `bug: bool` field was
  rejected: the API reports a fact about the item, as `WorkItemRead.type`
  does, and the web decides which types get an icon.

## Consequences

- Teams with no `type_labels` override get bug metrics and a working
  `types=bug` filter with no setup. Teams with their own list see the
  `no_mapping` state until they add a `bug` entry.
- Accepted limits, each marked with a `ponytail:` comment in the code:
  - **Current labels.** Atlas reads current labels, so a label added later
    moves a bug back to its creation bucket. Upgrade path: label history
    (`LABEL_ADDED` / `LABEL_REMOVED` events).
  - **Current priority.** A bug escalated after its fix reads under its new
    priority. Upgrade path: Linear history `fromPriority` / `toPriority`.
  - **Moved items.** A bug moved into the team does not count as created
    there, and one moved out disappears from its numbers, as for every flow
    metric. Upgrade path: team-change history from the Linear issue history.
- "Open" and "Oldest open" are read at the period end and age from arrival;
  the aging table always shows today and ages from the start of work, so the
  two can differ.
- The endpoint adds one scope load per Team page view, the same load as
  `/api/metrics`. No new query and no new index.
- Rollback: run the migration downgrade (it drops the column), then revert
  the code, which restores the empty `type_labels` default. `type_labels`
  overrides that users saved stay.
