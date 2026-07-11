# 6. LLM access goes through OpenRouter, called with plain httpx

Date: 2026-07-11 (backfilled; decided in Phase 6, 2026-07-10)

## Status

Accepted

## Context

The AI advisor needs a chat-completions LLM. Options considered: a provider
SDK (anthropic, openai), a provider-agnostic gateway (OpenRouter), or a
homegrown abstraction. Provider SDKs pin the platform to one vendor and add
a fast-churning dependency; the domain already isolates the capability
behind `AdvisorPort`, so the adapter is the only place wire details may
live.

## Decision

- The single LLM adapter (`app/infrastructure/ai/advisor.py`) calls
  OpenRouter's OpenAI-compatible `/chat/completions` endpoint with plain
  httpx (already a dependency). No provider SDK.
- Model choice is configuration (`ATLAS_ADVISOR_MODEL`): switching vendors
  or models is an env change, not a code change.
- Responses are constrained by a strict JSON schema
  (`response_format: json_schema`) and validated by a wire-format Pydantic
  model before conversion to Domain entities.
- The system prompt is grounded in a versioned knowledge file
  (`app/infrastructure/ai/knowledge/flow_coaching.md`). The LLM explains
  and prioritizes; every number it sees was computed by the
  metrics/forecasting engines and passed in via `DeliveryContext` — the AI
  never calculates.

## Consequences

- No SDK lock-in; one adapter file owns the wire format.
- Envelope drift or an off-schema reply surfaces as `AdvisorError` → 502 —
  never a 422 blaming the client.
- Requires models that support structured outputs (noted in `.env.example`).
