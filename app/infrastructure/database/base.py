from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; ``Base.metadata`` is the single source of truth for schema."""
