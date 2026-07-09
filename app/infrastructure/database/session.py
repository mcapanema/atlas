from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def build_sessionmaker(database_url: str, echo: bool = False) -> async_sessionmaker[AsyncSession]:
    """Build an async session factory bound to a fresh engine for ``database_url``."""
    engine = create_async_engine(database_url, echo=echo)
    return async_sessionmaker(engine, expire_on_commit=False)
