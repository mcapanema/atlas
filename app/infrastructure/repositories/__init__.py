# Importing each repository module registers its ORM model on Base.metadata,
# so a single `import app.infrastructure.repositories` makes the whole schema
# visible to Alembic autogenerate and to test table creation.
from app.infrastructure.repositories import organizations, projects, teams

__all__ = ["organizations", "projects", "teams"]
