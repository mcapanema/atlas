# 29. Datadog connector

Date: 2026-11-04

## Status

Accepted. Extends ADR-0024 (codebases from a code host), ADR-0025 (DORA
metrics) and ADR-0027 (credentials in the database).

## Context

Some teams ship and run their services with Datadog, not only with GitHub and
Linear. Datadog knows the services (Software Catalog), the deployments (DORA
Metrics) and the incidents (Incident Management). Atlas can use these facts for
deploy frequency, change failure rate and time to restore, without a new
computation.

## Decision

- A Datadog service is a `Codebase`. `Codebase.source` (`github` or `datadog`,
  default `github`) names its origin. The external id is
  `datadog:service:<name>`, so it never collides with a GitHub node id. The
  name is the catalog entity `attributes.name`. The `url` is empty.
- A sync fetches only its own codebases. `CodeHostSource.source` names the
  source. `CodeSyncService` stamps new codebases with it and fetches only the
  mapped codebases whose `source` matches.
- Services come from the Software Catalog (`GET /api/v2/catalog/entity`, kind
  `service`, discovered entities included), page by page until a page is short.
- Deployments come from `POST /api/v2/dora/deployments`, filtered by service
  and by `since`. A deployment with `finished_at` is `SUCCESS`. Any other is
  `PENDING`: Datadog DORA has no failed-deployment status, so failures come
  from incidents. The external id is `datadog:deployment:<id>`.
- Datadog gives no pull requests. A Datadog-only team has no lead-time sample.
  ponytail: to add one, attach a Datadog deployment to the GitHub codebase
  whose URL matches `git.repository_id`.
- Incidents come from `GET /api/v2/incidents`. Test incidents are skipped, and
  so are incidents modified before the 180-day backfill window of the code
  sync. `opened_at` is `customer_impact_start` or `created`. `restored_at` is
  `customer_impact_end` or `resolved`, and it is empty while the incident is
  open. The services come from `attributes.fields.services`.
- The team of an incident is decided at read time (ADR-0011). An incident
  counts for each team that has a mapped Datadog codebase whose name equals one
  of its services after `strip().casefold()`. An incident with no match counts
  nowhere.
- A team uses one incident source, never both. The new choice metric rule
  `incident_source` is `auto` (default), `linear` or `datadog`, and a user sets
  it for each team on the Metric rules page. `linear` reads only
  incident-labelled work items. `datadog` reads only Datadog incidents. `auto`
  reads Datadog incidents when at least one stored Datadog incident matches the
  mapped Datadog services of the team (at any time, not only in the window).
  Otherwise it reads Linear.
- The credentials are the integration `datadog`: an API key, an application key
  and a site. Both keys are required on each save. Atlas checks them with
  `GET /api/v1/validate` and then a one-entity catalog read.
- One sync kind, `datadog`, runs the code sync (Datadog source) and then the
  incident sync. Auto sync runs it after a successful Linear sync and GitHub
  sync when Datadog is set up. A failure of this run is only logged.
- A release that both tools report counts once. Before the DORA computation,
  a Datadog production deployment is dropped when a GitHub production
  deployment of the same team has the same commit SHA. The GitHub copy stays
  because it holds the failure status and the pull requests behind lead time.
  `DoraMetrics.duplicate_deployments` reports how many were dropped.

## Consequences

- A team that uses only Datadog has no lead time.
- A Datadog deployment without a commit SHA cannot be matched, so it can count
  twice with its GitHub deployment.
- `incident_source = auto` picks one incident source for each team. It does not
  merge the two sources, so one outage in both tools counts once.
- A failed deployment that also opens an incident still counts twice, as in
  ADR-0025: the incident blames the latest successful deployment. This is the
  same for Linear incidents.
- Monitors and SLOs are not read. A separate plan can add them.
- Atlas only reads from Datadog. It adds no Datadog usage charge, but Datadog
  rate limits apply.
