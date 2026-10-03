# app/application/

Use cases / orchestration. Imports only stdlib, `app.domain`, and
`app.application` (`tests/test_architecture.py`) — never `app.infrastructure`
or a concrete adapter. No FastAPI/Pydantic either: services operate on
Domain entities, not DTOs.

## Shape

One subpackage per concept: `<concept>/service.py`, a plain
`<Concept>Service` class whose methods are the use cases. Its constructor
takes exactly the Domain ports those use cases need — a repository
`Protocol`, an external-system port, or sibling services it composes. The
concrete adapters are wired in by `app/api/deps.py` (the composition root),
never chosen here. Exemplars: `organizations/service.py` (CRUD over one
repository), `sync/service.py` (repositories + the `DeliveryDataSource`
port).

- Analytics services load a scope's items + events through `scope.py`'s
  `ScopeSampleLoader` — extend it rather than re-implementing that loop
  inside a service.
- `AdvisorService` assembles the advisor's inputs from sibling services;
  the `AdvisorPort` itself is called in Presentation, not in the service.

## Testing

Test services against the shared in-memory fakes in `tests/fakes.py` —
never the real SQLAlchemy adapter or a live DB. That's what proves this
layer doesn't secretly depend on Infrastructure.
