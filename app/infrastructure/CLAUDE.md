# app/infrastructure/

Adapters. Everything database-, framework-, or connector-specific lives
here — this is the only layer allowed to import SQLAlchemy, aiosqlite, or
(in later phases) connector SDKs.

## Layout

- `database/base.py` — the single `DeclarativeBase` (`Base.metadata` is the
  one source of truth Alembic and tests build from).
- `database/session.py` — `build_sessionmaker(database_url, echo)`, built
  once per app lifecycle (in `app/main.py`'s lifespan), not per-request.
- `database/types.py` — cross-dialect column types. `UTCDateTime` wraps
  `DateTime(timezone=True)` to reattach UTC after SQLite's naive read;
  every persisted timestamp column uses it.
- `repositories/<concept>.py` — the ORM model (`<Concept>Model`) + the
  adapter class implementing the Domain `Protocol`. Include
  `to_domain()`/`from_domain()` mappers — an ORM instance must never leak
  out of this file as itself; always convert to/from the Domain entity.
- `repositories/__init__.py` — imports every concept submodule. This is
  load-bearing: it's how a model gets registered on `Base.metadata` for
  Alembic autogenerate and for `tests/conftest.py`'s
  `Base.metadata.create_all`. Forgetting to add the import here means your
  new table silently doesn't exist in tests or migrations.
- `connectors/<vendor>/` — one package per external system (today:
  `linear/`), containing the vendor API client, pure payload→`Source*`
  mapping functions, and the `DeliveryDataSource` adapter. Vendor payloads
  and SDK types must never leave this package.
- `ai/` — the LLM adapter (`OpenRouterAdvisor` implementing the Domain
  `AdvisorPort`, calling OpenRouter's chat-completions API with plain httpx —
  no provider SDK) plus `ai/knowledge/*.md`, the versioned knowledge base its
  system prompt is grounded in. OpenRouter must never be called outside this
  package, and Pydantic models here (`AdviceOut`, `GuidanceOut`) are wire format only —
  always convert to Domain entities before returning.
- `static.py` — `mount_spa(app)`, serves the compiled React build in
  production; a no-op when `web/dist` doesn't exist (dev mode). Must be the
  *last* thing registered in `create_app()` — it's a catch-all route and
  would otherwise swallow API 404s.

## Portability

Persistence must stay portable to PostgreSQL. Prefer SQLAlchemy-generic
column types (`Uuid`, `DateTime(timezone=True)`, `String(n)`) over
SQLite-specific ones — they render per-dialect. No raw SQL that only works
on SQLite.

## Testing

`tests/infrastructure/` runs each adapter against a real (in-memory)
SQLite DB via the `session`/`sessionmaker` fixtures in `tests/conftest.py`
— this is the layer where hitting a real database in tests is correct, not
a smell.
