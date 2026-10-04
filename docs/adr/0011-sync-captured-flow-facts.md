# 11. Sync-captured flow facts

Date: 2026-10-04

## Status

Accepted. Extends ADR-0010 (per-team metric rules); amends ADR-0004
(idempotent, insert-only events) with one narrow exception.

## Context

ADR-0010 made every read-time interpretation a per-team rule, but seven
interpretations needed facts sync never stored: which labels mean blocked
(the workspace used Linear "blocks" relations, not a label), parent issues
(counted beside their sub-issues), state types (Triage/Backlog padding the
forecast; Done → Todo indistinguishable from Done → Deployed), and labels
for work-item types (everything was TASK).

## Decision

- Sync stores raw facts; rules interpret them at read time:
  - label changes as `LABEL_ADDED`/`LABEL_REMOVED` events carrying the
    label name (labels present at creation get an add at creation);
  - "blocked by" relation history as `BLOCKER_ADDED`/`BLOCKER_CLEARED`,
    from Linear's undocumented `IssueHistory.relationChanges` codes
    (decoded 2026-10-04: `ab`/`bo` open, `rb`/`br` close, on the blocked
    issue);
  - state types on transition events (`from_state_type`/`to_state_type`),
    and the current state type, labels and parent on work items.
- The Linear mapping no longer emits `BLOCKED`/`UNBLOCKED`; the stored
  derived ones were purged. REST-created blocked events still count.
- Blocked periods come from relation **history only**. Linear began
  recording relation changes around mid-2026; older relations contribute
  nothing rather than an approximation (creation → blocker done).
- **One exception to insert-only events:** a transition event's state-type
  columns, empty because the event predates them, are filled once by
  sync — only where `to_state_type IS NULL`, never changing a value.

## Consequences

- Built-in defaults reproduce the previous numbers; a workspace opts in on
  the Metric rules page, and the change recomputes snapshot history.
- Backtests use the state type as it was at each instant; parent links
  and labels-for-type are current facts applied to the past.
- Relation codes are undocumented: an unknown blocking code is logged and
  ignored, so a Linear change degrades blocked time rather than breaking
  sync.
