import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limiter
from app.main import app
from app.models.game import Game
from app.models.user import User


def get_test_database_url() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}_test"
    )


@pytest.fixture
def api_client() -> TestClient:
    auth_rate_limiter.reset()
    test_engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_usernames: list[str] = []
    created_game_ids: list[uuid.UUID] = []

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.created_usernames = created_usernames  # type: ignore[attr-defined]
            client.created_game_ids = created_game_ids  # type: ignore[attr-defined]
            client.session_factory = session_factory  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.clear()

        async def _cleanup() -> None:
            async with session_factory() as session:
                if created_game_ids:
                    await session.execute(delete(Game).where(Game.id.in_(created_game_ids)))
                if created_usernames:
                    await session.execute(
                        delete(User).where(User.username.in_(created_usernames))
                    )
                await session.commit()
            await test_engine.dispose()

        asyncio.run(_cleanup())
