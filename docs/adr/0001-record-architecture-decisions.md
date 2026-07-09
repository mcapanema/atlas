# 1. Record architecture decisions

Date: 2026-07-08

## Status

Accepted

## Context

We need a lightweight, durable record of significant architectural decisions as Atlas evolves.

## Decision

We will use Architecture Decision Records, as described by Michael Nygard, stored in
`docs/adr/` and numbered sequentially. Each ADR captures context, the decision, and
consequences.

## Consequences

Decisions become traceable and reviewable. New contributors can understand why the
system is shaped the way it is without archaeology through git history.
