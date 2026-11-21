import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.core.rate_limit import auth_rate_limiter
from app.main import app
from app.models.game import Game
from app.models.user import User
from tests.api.conftest import get_test_database_url


@pytest.fixture
def mm_client() -> TestClient:
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


def _register_and_login(client: TestClient, prefix: str) -> tuple[str, str]:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    client.created_usernames.append(username)  # type: ignore[attr-defined]

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "StrongPassword123",
            "ui_language": "tr",
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": username, "password": "StrongPassword123"},
    )
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


def test_matchmaking_language_duration_isolation_and_ws_broadcast(mm_client: TestClient) -> None:
    p1_id, p1_token = _register_and_login(mm_client, "mmp1")
    p2_id, p2_token = _register_and_login(mm_client, "mmp2")
    p3_id, p3_token = _register_and_login(mm_client, "mmp3")

    p1_headers = {"Authorization": f"Bearer {p1_token}"}
    p2_headers = {"Authorization": f"Bearer {p2_token}"}
    p3_headers = {"Authorization": f"Bearer {p3_token}"}

    # P1 requests TR / 24h matchmaking -> creates a new waiting game
    mm1 = mm_client.post(
        "/api/v1/games/matchmaking",
        headers=p1_headers,
        json={"language": "tr", "turn_duration_hours": 24},
    )
    assert mm1.status_code == 200
    assert "X-Request-ID" in mm1.headers
    body1 = mm1.json()
    assert body1["matched"] is False
    game_tr_id = body1["game"]["id"]
    mm_client.created_game_ids.append(uuid.UUID(game_tr_id))  # type: ignore[attr-defined]
    assert body1["game"]["status"] == "waiting"

    # P1 calling matchmaking again with same criteria returns existing waiting game (no spam)
    mm1_repeat = mm_client.post(
        "/api/v1/games/matchmaking",
        headers=p1_headers,
        json={"language": "tr", "turn_duration_hours": 24},
    )
    assert mm1_repeat.status_code == 200
    assert mm1_repeat.json()["matched"] is False
    assert mm1_repeat.json()["game"]["id"] == game_tr_id

    # P2 requests EN / 24h -> must NOT match with P1's TR game
    mm2 = mm_client.post(
        "/api/v1/games/matchmaking",
        headers=p2_headers,
        json={"language": "en", "turn_duration_hours": 24},
    )
    assert mm2.status_code == 200
    body2 = mm2.json()
    assert body2["matched"] is False
    assert body2["game"]["id"] != game_tr_id
    mm_client.created_game_ids.append(uuid.UUID(body2["game"]["id"]))  # type: ignore[attr-defined]

    # P1 connects to WS, P3 requests TR / 24h -> matches P1 and broadcasts game_started
    with mm_client.websocket_connect(f"/api/v1/games/{game_tr_id}/ws?token={p1_token}") as ws:
        conn = ws.receive_json()
        assert conn["event"] == "connected"

        mm3 = mm_client.post(
            "/api/v1/games/matchmaking",
            headers=p3_headers,
            json={"language": "tr", "turn_duration_hours": 24},
        )
        assert mm3.status_code == 200
        body3 = mm3.json()
        assert body3["matched"] is True
        assert body3["game"]["id"] == game_tr_id
        assert body3["game"]["status"] == "active"
        assert body3["game"]["current_turn_user_id"] == p1_id
        assert {p["user_id"] for p in body3["game"]["players"]} == {p1_id, p3_id}

        started = ws.receive_json()
        assert started["event"] == "game_started"
        assert started["game_id"] == game_tr_id


def test_request_id_header_preserved_when_provided(mm_client: TestClient) -> None:
    res = mm_client.get("/", headers={"X-Request-ID": "custom-trace-123"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == "custom-trace-123"
