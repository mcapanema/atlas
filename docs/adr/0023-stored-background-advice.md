# 23. Stored background advice

Date: 2026-10-28

## Status

Accepted. Amends ADR-0003 for advice and meeting prep only; the runner
shares ADR-0014's one-process ceiling.

## Context

Advice and meeting prep were computed on read: every `GET` called the LLM
and held the request open for tens of seconds, and the answer was gone on
the next page load. Two `ponytail:` notes marked this as a deliberate
simplification. A scheduled digest needs a stored result to read, so the
result has to outlive the request that produced it.

## Decision

- **History, not latest-only.** Every generation appends one `advice_runs`
  row; `GET` reads the newest row for the key. Finished rows are never
  updated or deleted. No history endpoint or UI: the rows make one possible.
- **Run key.** Scope (`team_id` xor `project_id`) + `persona` + a canonical
  `params` string of the request options (`window_days`; for meetings also
  `remaining`, `target_date`). Meeting prep uses the meeting's `Persona`
  value, so one table serves both.
- **One table, JSON result.** The persona says which shape it holds.
- **No duplicate LLM calls.** A start for a key whose newest run is
  `running` returns that run (`202`). A `running` row older than 15 minutes
  is abandoned: marked failed, and a new run starts. `AdviceRunner`
  (`app/api/advice_runner.py`) serializes begin + commit with a lock.
- **Restart mid-run: fail, never resume.** On startup every `running` row
  becomes `failed` ("Interrupted by a restart; generate again."). No
  automatic retry: it costs money and the context is stale. In a single
  process `fail_interrupted` runs before any start can take the lock, so it
  cannot fail a live run.
- **API shape.** `POST /api/recommendations` and `POST /api/meetings/prep`
  answer `202` with the run; `GET` on the same paths answers `200` with the
  newest run or `null`. `GET` needs no `ATLAS_OPENROUTER_API_KEY`; `POST`
  keeps the 409-until-configured rule (ADR-0005), checked before scope
  validation.
- **No transaction across the LLM call.** The task builds context and
  commits, calls the port with no open session, then stores the outcome in
  a new session. Cancellation writes nothing. A blank advisor error message
  falls back to the exception type name.
- **UI.** While a run is `running` the page shows a spinner and no older
  result; a finished result shows "Generated <relative time>".
- **MCP unchanged.** It reads `GET /api/recommendations/context`, which
  keeps computing on read.

## Consequences

- Advice survives reloads and stays readable without an API key.
- Advice rows grow without bound until a history or pruning feature exists.
- A run lost to a restart must be started again by hand.
- Atlas must still run as a single uvicorn worker: the lock and the tasks
  are per process (as ADR-0014).
