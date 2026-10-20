# 17. Durations count working days

Date: 2026-10-19

## Status

Accepted. Amends ADR-0010 ("defaults reproduce the previous numbers") for
the duration metrics.

## Context

Duration metrics measured calendar time. A ticket picked up on Friday and
finished on Monday read three days of lead time, though the team worked one
day on it. Weekends inflated every duration and made them swing with the
weekday an item happened to cross.

## Decision

- Durations skip non-working whole days in the team's timezone. The
  `working_days` rule lists the ISO weekdays that count (1 = Monday to
  7 = Sunday) and defaults to Monday to Friday.
- The rule is per team, through the usual workspace and team override
  layers. Selecting all seven days restores calendar time.
- Lead, cycle, queue, touch and blocked time, flow efficiency, aging, the
  predictability and risk health components and the lead-time distribution
  all measure on this calendar, sample by sample.
- Migration `8b2d5f6a1c47` marks every organization's recompute "running",
  so the lifespan rewrites snapshot history on the next start.

## Consequences

- Every duration drops for items that spanned a non-working day, including
  snapshot history once the recompute finishes.
- Counts, windows and forecasts are unchanged: they stay calendar time.
- Time off beyond holidays is not modelled; a team's rule covers the
  weekly pattern and its holidays.

## Amendment (2026-10-19)

Holidays are now modelled: the `holidays` rule lists whole local days off
that durations skip like a non-working weekday.
