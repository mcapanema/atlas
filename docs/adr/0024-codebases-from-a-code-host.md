# 24. Codebases from a code host

Date: 2026-10-28

## Status

Accepted. Extends ADR-0004 (idempotent sync by external id) and ADR-0022
(background sync jobs).

## Context

`docs/VISION.md` promises pull request and deployment events, but Atlas only
reads an issue tracker. DORA-style delivery measures (deploy frequency, change
lead time, change failure rate, time to restore) need code-host data. The
existing `DeliveryDataSource` port is shaped for trackers: teams, projects and
work items. A code host has repositories, pull requests and deployments.

## Decision

- Two plans. The first adds the connector, storage and sync. The second
  computes DORA and shows it.
- A repository (a `Codebase`) maps to one Atlas team manually, on the
  Connectors page. An unmapped codebase is listed but never fetched.
- Codebases are matched by external id across all organizations, as the
  Linear sync matches teams. The first organization to sync a repository owns
  it; another organization's sync renames it but never re-inserts it, and
  fetches pull requests and deployments only for its own mapped codebases.
- A pull request links to a work item when a work-item key (for example
  `ENG-123`) appears in its branch name, title or body. A link adds `REVIEW`
  (opened) and `MERGED` events to that item. Every pull request is stored,
  linked or not. These code events (`CODE_EVENT_TYPES`) change no flow
  metric: they never anchor an item's creation, born-done, first state or
  blocked period, or its place on the CFD, so a pull request opened before
  its ticket leaves the metrics (and stored snapshots) unchanged.
- Failures come from both deployment status (failure or error) and Linear
  incident issues. Sync stores each deployment's normalized status and finish
  time. The incident rule belongs to the second plan.
- A second port, `CodeHostSource`, with platform-neutral `Source*` types. We
  do not widen `DeliveryDataSource`: the two systems share no fetch shape, and
  a tracker adapter should not have to stub code-host methods.
- `Deployment` is a mutable aggregate, because its status changes after
  creation (pending, then success or failure). `PullRequest` is mutable for
  the same reason: it merges or closes later.
- Sync stores raw facts (ADR-0011). The production environment is a setting on
  the codebase and is chosen at read time, so a change needs no re-sync.

## Consequences

- A Linear rebuild (ADR-0013) drops the pull request events from work items
  until the next GitHub sync restores them.
- The second plan owns the DORA computation. This plan stores the facts only.
- Another code host (for example GitLab) needs only a new adapter for
  `CodeHostSource`.
