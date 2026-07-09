# app/domain/

Pure Python. Zero framework imports — no FastAPI, SQLAlchemy, Pydantic,
aiosqlite, or connector-specific code (Linear, GitHub, Slack, etc.), ever.
This is the one rule in this repo that isn't negotiable.

## Shape

Each concept gets its own subpackage: `<concept>/entities.py` +
`<concept>/repository.py`.

- `entities.py` — a plain `@dataclass` per aggregate/entity. Invariants live
  in `__post_init__` and raise `ValueError` on violation (see
  `organizations/entities.py`'s stripped/non-empty `name` check). IDs are
  `uuid4()`-generated `UUID`s, timestamps are timezone-aware UTC `datetime`s
  via a small `_utcnow()` helper.
- `repository.py` — a `typing.Protocol` per aggregate describing the
  persistence port (`add`, `list`, `get`, ...), all `async`. This is an
  interface only — no implementation lives here. Infrastructure implements
  it; Application depends on it.

## Before committing

Grep your diff for `fastapi`, `sqlalchemy`, `pydantic`, `sqlite`
(case-insensitive) — none should match. `tests/domain/` mirrors this
package 1:1 and asserts on entity behavior only (no DB, no HTTP).

## Adding a new concept

Copy the `organizations/` shape: `entities.py` with the dataclass +
invariants, `repository.py` with the Protocol. Nothing here should ever
need to change when Infrastructure or Presentation changes — if it does,
the dependency is pointing the wrong way.
