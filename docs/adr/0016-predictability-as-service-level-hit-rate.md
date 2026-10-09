# 16. Predictability as service-level hit rate

Date: 2026-10-09

## Status

Accepted. Replaces the lead-time spread score (and its log-scale
calibration from the same day's metrics review).

## Context

Delivery health scored predictability as the lead-time p95/p50 ratio. The
arithmetic was right, but the 2026-10-09 review on live data showed the
measure was wrong:

- A small median inflates the ratio. Forward Deployment finished every
  item within 6 days and scored 40; AI Team's 0.3-day cycle median read
  36x.
- p95 over 5-16 items is the slowest item: one outlier decides the score.
- A mix of quick bugs and long features reads as unpredictability.
- Lead time folds in backlog waits. Regras Auditoria's tail was 106 days
  in backlog followed by 5-day cycles.

No record explained why lead time had been chosen.

## Decision

Predictability is the share of the window's completed-and-started items
whose cycle time is within the team's service level: the
`aging_percentile` (P85) of cycle times completed in the
`aging_history_days` (90) before the window. It is the same line Aging WIP
and the risk component use, anchored before the window so the window
can't grade itself. A hit rate at the percentile's own rate or better
scores 100, falling linearly to 0 at `predictability_floor` (25% by
default). That rule replaces `predictability_worst_ratio`.

The component needs `health_min_sample` items on both sides (window and
history). A scope with less prior history leaves predictability out.

## Consequences

- The score answers "did we meet our own commitment?" ("74% of 91 items
  finished within 36d"). How wide the commitment is shows in the SLE and
  the lead/cycle stat tiles, not in the score.
- A team that slows down scores low even when it is steady at its new
  pace. That is the point: its track record stopped predicting its work.
- Scores moved on live data: Deployment 78 -> 28 (42% hit, against 77% the
  window before), Regras Auditoria 27 -> 100, AI Team 7 -> 100.
- On a view longer than the 30-day default (Last 180 days, or a custom
  range), the reference is the aging history before that whole view, so
  the score grades the view against an older commitment. A scope without
  that much history before the view leaves predictability out there.
- Migration `c4e7a2d9b1f3` drops any stored `predictability_worst_ratio`
  override. The write schema forbids unknown keys, so it could never be
  cleared, and the resolver logged it on every scope load. Health is
  computed on read, so no history is rewritten.
