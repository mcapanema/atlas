# app/application/

Use cases / orchestration. Depends on `app/domain/` only — never import
`app.infrastructure` or a concrete adapter (e.g.
`SqlAlchemyOrganizationRepository`) here. A service takes the Domain ports
its use cases need as constructor arguments; the concrete adapters are
wired in by Presentation (`app/api/deps.py`, the composition root), not
chosen here.

## Shape

One subpackage per concept: `<concept>/service.py`, a plain class named
`<Concept>Service` whose methods are the use cases. Constructor shapes
vary with the use case — the rule is "the ports this use case needs", not
"one repository":

- CRUD services take their concept's repository Protocol.
- `SyncService` takes the repositories it upserts into plus the
  `DeliveryDataSource` port.
- `MetricsService` and `ForecastService` take repositories and share the
  scope-loading assembler below.
- `AdvisorService` composes sibling services (`MetricsService`,
  `ForecastService`). The `AdvisorPort` is called at the presentation layer,
  not in the service.

No FastAPI/Pydantic here either — services operate on Domain entities,
not DTOs.

One shared exception: `scope.py` holds `ScopeSampleLoader`/`ScopeSamples`,
the single scope-load assembler the metrics, forecasting, and advisor
services share. Extend it rather than re-implementing the items+events
loading loop inside a service — a semantic drift between two copies of
that loop is how remaining-count bugs hide.

## Testing

Test services against a hand-written in-memory fake implementing the same
Protocol (the shared fakes live in tests/fakes.py) — never against the real
SQLAlchemy adapter or a live DB. That's what proves this layer doesn't
secretly depend on Infrastructure.
