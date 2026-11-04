import logging
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.credentials.entities import Credential, Integration
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime

logger = logging.getLogger(__name__)


class CredentialModel(Base):
    __tablename__ = "credentials"

    integration: Mapped[str] = mapped_column(String(32), primary_key=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    site: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class SqlAlchemyCredentialRepository:
    """SQLAlchemy adapter for the CredentialRepository port; secrets are Fernet-encrypted."""

    def __init__(self, session: AsyncSession, cipher: Fernet) -> None:
        self._session = session
        self._cipher = cipher

    async def get(self, integration: Integration) -> Credential | None:
        model = await self._session.get(CredentialModel, integration.value)
        if model is None:
            return None
        try:
            secret = self._cipher.decrypt(model.secret_ciphertext.encode()).decode()
        except InvalidToken:
            return self._unreadable(integration)
        application_key = None
        if model.application_key_ciphertext is not None:
            try:
                application_key = self._cipher.decrypt(
                    model.application_key_ciphertext.encode()
                ).decode()
            except InvalidToken:
                return self._unreadable(integration)
        return Credential(
            integration=integration,
            secret=secret,
            owner=model.owner,
            model=model.model,
            application_key=application_key,
            site=model.site,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _unreadable(integration: Integration) -> None:
        logger.warning(
            "Stored %s credential cannot be decrypted with the current key file; "
            "enter it again on the Connectors page",
            integration.value,
        )

    async def save(self, credential: Credential) -> None:
        await self._session.merge(
            CredentialModel(
                integration=credential.integration.value,
                secret_ciphertext=self._cipher.encrypt(credential.secret.encode()).decode(),
                owner=credential.owner,
                model=credential.model,
                application_key_ciphertext=(
                    self._cipher.encrypt(credential.application_key.encode()).decode()
                    if credential.application_key is not None
                    else None
                ),
                site=credential.site,
                updated_at=credential.updated_at,
            )
        )
        await self._session.flush()

    async def delete(self, integration: Integration) -> None:
        model = await self._session.get(CredentialModel, integration.value)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()
