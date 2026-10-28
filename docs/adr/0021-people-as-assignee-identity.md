# 21. People as assignee identity

Date: 2026-10-28

## Status

Accepted. Builds on ADR-0004 (idempotent sync by external id) and ADR-0013
(rebuild source events).

## Context

A work item's owner was a free-text name copied from Linear onto
`work_items.assignee`. Linear can report an email or handle as the name, so
the same person could read differently across items, and nothing let an
Engineering Manager correct how a name shows. The name belongs to a person,
not to each item.

## Decision

- **Ownership display only.** No per-person metrics, filters or leaderboard.
  `Person` exists to name an owner correctly.
- **`Person` is a persisted aggregate.** An Organization owns People
  (`app/domain/people/`, `people` table); a Work Item points at its assignee
  through the nullable, indexed FK `work_items.assignee_id`. `Person.name`
  and `email` come from the source; `Person.display_name` is the manager's
  override, and `shown_name` is the override when set, else `name`. A blank
  override means no override and is stored as `NULL`.
- **People come from issue nodes, not a users query.** Every organization
  sync fetches every issue, so each sync sees each assignee's current name.
  There is no new `DeliveryDataSource` method; `SourceWorkItem.assignee` is a
  `SourcePerson(external_id, name, email)`. An assignee with a blank name reads as
  unassigned. People who own no item are not stored.
- **Sync upserts people by `external_id`.** It writes `name` and `email` and
  never `display_name`, so the override survives every sync and every
  rebuild. People are never pruned: a person who no longer appears keeps
  their row, and only the item's `assignee_id` changes.
- **People are looked up across organizations.** `get_by_external_ids` does
  not filter by organization, because `people.external_id` is globally unique
  (like `teams.external_id`). A Linear user id seen by a second organization
  reuses the first organization's Person. This is the same
  one-Linear-workspace-per-deployment assumption as the team sync.
- **Read-side resolution in Infrastructure.** `WorkItem.assignee: str | None`
  keeps its meaning ("who to show") and is filled on load by a correlated
  scalar subquery (a `column_property`); writes go through
  `WorkItem.assignee_id`. The `work_items.assignee` column is dropped.
- **No assignment events.** `EventType.ASSIGNED` stays unused and the Linear
  mapper emits none. History of who held an item is out of scope.
- **Backfill by a normal sync, not a rebuild.** The migration drops the name
  column, so items read "Unassigned" until the next sync (manual **Sync now**
  or Auto sync) sets `assignee_id`. Events don't change, so ADR-0013's
  rebuild is not needed.
- **Override UI.** A People table on the Organizations page with an
  inline-editable "Display name" cell, served by `GET /api/people` and
  `PATCH /api/people/{id}`.
- **Identity-linking hook.** `Person.external_id` (the Linear user id) plus
  `Person.email`. A second connector adds a `person_identities` table
  (`source`, `external_id` → `person_id`) and matches on email first. No
  table for it exists until then.

## Consequences

- A manager fixes one name once and every item, on every page, shows it; a
  rename in Linear updates `name` without touching the override.
- Owners read "Unassigned" after the upgrade until the first sync.
- A second Linear workspace in one deployment would share Persons by user id
  and could surface another workspace's names; separating workspaces needs
  the `person_identities` table keyed by source.
- Because ownership is display only, nothing aggregates by person; adding
  per-person analytics is a new decision, not an extension of this one.
