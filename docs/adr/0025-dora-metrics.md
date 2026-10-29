# 25. DORA metrics

Date: 2026-10-29

## Status

Accepted. Completes ADR-0024 (codebases from a code host). Uses ADR-0003
(compute-on-read analytics).

## Context

ADR-0024 stored pull requests and deployments from a code host and left the
DORA computation to a second plan: deploy frequency, change lead time, change
failure rate and time to restore. It also decided that failures come from
both deployment status and incident issues, and left the incident rule to
this plan. The four metrics need exact definitions, so that the service, the
API, the AI advisor and the web read the same numbers.

## Decision

- **Incidents** are work items with a label named in the new metric rule
  `incident_label_names` (any case), editable per team on the Metric rules
  page. The default is `("incident", "incidente")`. Incidents come from the
  same items as every flow metric, so born-done and parent items are left
  out. A canceled incident is a false alarm and counts nowhere.
- **Team scope only.** A project scope answers 422. Item filters do not
  apply: a type filter must not hide incidents.
- **Surfaces:** a Team dashboard card, two Executive dashboard columns, the AI
  advisor context and an MCP `dora` tool. The AI never computes DORA; it
  receives the numbers and the bands.
- **Production deployment:** a deployment whose environment equals its
  codebase's production environment after `strip().casefold()` on both. Only
  SUCCESS and FAILURE deployments are finished; PENDING counts nowhere.
- **Window:** `(now - window_days, now]`, on each fact's own time: a
  deployment's finish time, an incident's restore time.
- **Deploy frequency:** successful production deployments finished in the
  window, per week.
- **Change lead time:** each successful production deployment D finished in
  the window ships the pull requests of its codebase merged after the
  previous successful deployment P started and at or before D started (no P:
  the `window_days` before D). Lead time is D's finish minus the pull
  request's first commit (or its opening). Reported as the median.
- **Change failure rate:** failed ÷ finished production deployments in the
  window. A deployment fails when its status is FAILURE, or when an incident
  blames it. An incident blames the latest successful production deployment
  of the team's codebases that finished at or before the incident's creation.
  A deployment fails once, however many incidents blame it, so the rate never
  passes 100%.
- **Time to restore:** the median over incidents restored in the window
  (creation to completion), and over each run of failed deployments of a
  codebase, from the run's first failure to the codebase's next success.
- **Wall-clock durations**, not the working calendar of ADR-0017: DORA bands
  are stated in clock time, and outages do not pause on weekends.
- **Bands** are the DORA report thresholds, as constants in
  `app/domain/metrics/dora.py`.
- **Evidence floor:** lead time, change failure rate and time to restore get
  a band only when their sample reaches the team's `health_min_sample`; the
  value still shows when the sample is above zero. Deploy frequency always
  has a band when the team has a mapped codebase: zero deployments is "low",
  a real answer. A team with no mapped codebase gets no band at all.

## Consequences

- DORA is computed on read (ADR-0003) and is not snapshotted.
- `incident_label_names` is an ordinary metric rule, so a change to it queues
  the usual snapshot recompute, which rewrites identical snapshots.
- Lead time attributes a pull request to a deployment by merge time, not by
  commit ancestry. A codebase that deploys out of merge order can assign a
  change to the wrong deployment. Matching `merge_commit_sha` ancestry is the
  upgrade path when the code host exposes it.
