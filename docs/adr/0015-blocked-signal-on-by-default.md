# 15. Blocked signal on by default

Date: 2026-10-08

## Status

Accepted. Amends ADR-0010 ("defaults reproduce the previous numbers") and
ADR-0011 (relations opt-in) for the blocked rules and the health floor.

## Context

Blocked time read 0m, and flow efficiency 100%, for every team in the
workspace. The 2026-10-08 data held plenty of blocked signal:

- 331 transitions into a workflow state named **Blocked** — counted since
  #116 (`blocked_state_pattern`, on by default);
- 59 **Bloqueante** labels — the built-in pattern matched only English
  "block…" words;
- 287 Linear "blocked by" relation openings — `blocked_by_relations`
  defaulted to off (ADR-0011).

Relation history closes reliably: 196 of the openings were later cleared
(relation removed, or blocker resolved), and of the 103 still open only 1
sat on an in-progress item whose blocker was done; the rest wait on
blockers still in backlog, todo or progress.

#116 also added `health_min_sample` (a component backed by fewer items is
left out), defaulting to 3.

## Decision

- One built-in whole-word pattern for labels and workflow states matches
  Portuguese too: Bloqueado/a(s), Bloqueante(s), Bloqueio(s), alongside
  Blocked, Blocker(s), Blocking. "Desbloqueado" and "Blockly" don't match.
- `blocked_by_relations` defaults to on. Relation history still counts
  only from when Linear began recording it (ADR-0011).
- `health_min_sample` defaults to 5: a component needs at least five items
  behind it (window completions; in-progress items for risk).
- Every source and the floor stay editable on the Metric rules page.
- Migration `f7a3c1d9e2b5` marks every organization's recompute
  "running", so the lifespan rewrites snapshot history under the new
  defaults on the next start.

## Consequences

- Blocked time, flow efficiency and the efficiency/risk health components
  change for every team using any blocked source, including snapshot
  history once the recompute finishes.
- More small teams read "not scored yet"; a stalled team with five or more
  stuck items still reads critical.
- A workflow state or label that matches the pattern but doesn't mean
  blocked now counts. Turn the pattern off and list the real names.
