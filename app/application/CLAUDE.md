# app/application/

Use cases / orchestration. Depends on `app/domain/` only — never import
`app.infrastructure` or a concrete adapter (e.g.
`SqlAlchemyOrganizationRepository`) here. A service takes a Domain
`Protocol` (the repository port) as a constructor argument; the concrete
adapter is wired in by Presentation (`app/api/deps.py`), not chosen here.

## Shape

One subpackage per concept: `<concept>/service.py`, a plain class named
`<Concept>Service` whose constructor takes the concept's repository
Protocol and whose methods are the use cases (`create_organization`,
`list_organizations`, ...). No FastAPI/Pydantic here either — services
operate on Domain entities, not DTOs.

## Testing

Test services against a hand-written in-memory fake implementing the same
Protocol (see `tests/application/test_organization_service.py`'s
`InMemoryOrganizationRepository`) — never against the real SQLAlchemy
adapter or a live DB. That's what proves this layer doesn't secretly depend
on Infrastructure.
