from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.auth.entities import AuthSession, User
from app.domain.auth.repository import SetupAlreadyClaimedError
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> User:
        return User(
            id=self.id,
            email=self.email,
            name=self.name,
            password_hash=self.password_hash,
            is_admin=self.is_admin,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, user: User) -> "UserModel":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=user.password_hash,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> AuthSession:
        return AuthSession(
            token_hash=self.token_hash,
            user_id=self.user_id,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, session: AuthSession) -> "AuthSessionModel":
        return cls(
            token_hash=session.token_hash,
            user_id=session.user_id,
            expires_at=session.expires_at,
            created_at=session.created_at,
        )


class AuthSetupModel(Base):
    """One row, ever: the primary key makes a second first-run setup fail to insert."""

    __tablename__ = "auth_setup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class SqlAlchemyUserRepository:
    """SQLAlchemy adapter for the UserRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(UserModel.from_domain(user))
        await self._session.flush()

    async def get(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return model.to_domain() if model is not None else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(UserModel).where(UserModel.email == email))
        model = result.scalar_one_or_none()
        return model.to_domain() if model is not None else None

    async def list(self) -> list[User]:
        result = await self._session.execute(select(UserModel).order_by(UserModel.created_at))
        return [model.to_domain() for model in result.scalars()]

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(UserModel))
        return result.scalar_one()

    async def update(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            raise LookupError(f"User {user.id} not found")
        model.name = user.name
        model.password_hash = user.password_hash
        model.is_admin = user.is_admin
        await self._session.flush()

    async def delete(self, user_id: UUID) -> None:
        # Bulk delete: the database cascades the user's sessions (FK ON DELETE CASCADE).
        await self._session.execute(delete(UserModel).where(UserModel.id == user_id))
        await self._session.flush()

    async def claim_setup(self, now: datetime) -> None:
        # A savepoint, so a lost claim leaves the outer transaction usable.
        try:
            async with self._session.begin_nested():
                self._session.add(AuthSetupModel(id=1, completed_at=now))
        except IntegrityError as exc:
            raise SetupAlreadyClaimedError("first-run setup is already done") from exc


class SqlAlchemyAuthSessionRepository:
    """SQLAlchemy adapter for the AuthSessionRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: AuthSession) -> None:
        self._session.add(AuthSessionModel.from_domain(session))
        await self._session.flush()

    async def get(self, token_hash: str) -> AuthSession | None:
        # A query, not session.get: a row the database cascaded away must not
        # come back from the identity map.
        result = await self._session.execute(
            select(AuthSessionModel).where(AuthSessionModel.token_hash == token_hash)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model is not None else None

    async def delete(self, token_hash: str) -> None:
        await self._session.execute(
            delete(AuthSessionModel).where(AuthSessionModel.token_hash == token_hash)
        )
        await self._session.flush()

    async def delete_for_user(self, user_id: UUID, keep_token_hash: str | None = None) -> None:
        statement = delete(AuthSessionModel).where(AuthSessionModel.user_id == user_id)
        if keep_token_hash is not None:
            statement = statement.where(AuthSessionModel.token_hash != keep_token_hash)
        await self._session.execute(statement)
        await self._session.flush()

    async def delete_expired(self, now: datetime) -> None:
        await self._session.execute(
            delete(AuthSessionModel).where(AuthSessionModel.expires_at <= now)
        )
        await self._session.flush()
