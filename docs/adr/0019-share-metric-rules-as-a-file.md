# 19. Share metric rules as a file

Date: 2026-10-23

## Status

Accepted. Builds on ADR-0010 (per-team metric rules).

## Context

Engineering Managers tune metric rules (working days, wait states, blocked
labels, health weights) and want to hand that configuration to a colleague
running their own Atlas. Each install has its own database, so Atlas's team
UUIDs differ between installs and can't identify a team in a shared file.

## Decision

- `GET /api/organizations/{id}/metric-rules/export` returns a JSON file:
  `{"format": "atlas-metric-rules", "version": 1, "exported_at", "workspace",
  "teams": [{"name", "external_id", "overrides"}]}`. It carries the workspace
  override layer and every team's non-empty layer, in the same value shapes
  `PATCH …/metric-rules` takes. Atlas UUIDs, the sync schedule, personas and
  API keys are never written.
- `POST /api/organizations/{id}/metric-rules/import` takes that file. A team
  matches by `external_id` first (the Linear team id, the same in every
  install synced from that Linear workspace), then by name (any case,
  trimmed) when exactly one local team has it.
- Import replaces: the workspace layer becomes the file's, and each matched
  team's layer becomes the file's for it. Teams the file doesn't name keep
  their layers. Teams the file names but this install lacks are skipped and
  listed in the response.
- Import is atomic: an unknown rule, an invalid value, a wrong `format` or
  `version`, two entries for one team, or a workspace layer that conflicts
  with an unnamed team's own overrides is a 422, and nothing is written.
  A successful import recomputes the history of the teams whose effective
  rules changed, the same way a PATCH does.

## Consequences

- Colleagues on the same Linear workspace share rules with no renaming, and
  a rename in Linear doesn't break the match. Across Linear workspaces only
  team names can match.
- A new rule needs no format change: an older file simply doesn't name it.
  Renaming or reshaping a rule's value is a breaking change and needs
  `version` 2 plus an upgrade path for version-1 files.
- Re-importing an install's own export is a no-op: no row is rewritten and
  no history is recomputed.
