import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_db
from app.core.rate_limit import auth_rate_limiter
from app.main import app
from app.models.game import Game, GameStatus
from app.models.move import Move, MoveType
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.realtime.broadcaster import InMemoryBroadcaster
from app.services.notification_service import LoggingNotificationHook
from app.services.timeout_service import process_expired_games, purge_expired_refresh_tokens
from tests.api.conftest import get_test_database_url


@pytest.fixture
def ws_client() -> TestClient:
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


def _register_and_login(
    client: TestClient,
    prefix: str,
    ui_language: str = "tr",
) -> tuple[str, str]:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    client.created_usernames.append(username)  # type: ignore[attr-defined]

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "StrongPassword123",
            "ui_language": ui_language,
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


def test_websocket_auth_and_live_game_events(ws_client: TestClient) -> None:
    p1_id, p1_token = _register_and_login(ws_client, "wsp1", "tr")
    p2_id, p2_token = _register_and_login(ws_client, "wsp2", "en")
    _, outsider_token = _register_and_login(ws_client, "wsout", "tr")

    create_res = ws_client.post(
        "/api/v1/games",
        headers={"Authorization": f"Bearer {p1_token}"},
        json={"language": "tr", "turn_duration_hours": 12},
    )
    assert create_res.status_code == 201
    game_id = create_res.json()["id"]
    ws_client.created_game_ids.append(uuid.UUID(game_id))  # type: ignore[attr-defined]

    # Missing/invalid token rejected
    with pytest.raises(WebSocketDisconnect) as exc_no_tok:
        with ws_client.websocket_connect(f"/api/v1/games/{game_id}/ws"):
            pass
    assert exc_no_tok.value.code == 4401

    # Non-participant rejected
    with pytest.raises(WebSocketDisconnect) as exc_out:
        with ws_client.websocket_connect(f"/api/v1/games/{game_id}/ws?token={outsider_token}"):
            pass
    assert exc_out.value.code == 4403

    # P1 connects to WS, then P2 joins and P1 passes -> P1 receives game_started & move_made
    with ws_client.websocket_connect(f"/api/v1/games/{game_id}/ws?token={p1_token}") as ws:
        conn_msg = ws.receive_json()
        assert conn_msg["event"] == "connected"
        assert conn_msg["game_id"] == game_id

        ws.send_text("ping")
        assert ws.receive_json() == {"event": "pong"}

        join_res = ws_client.post(
            f"/api/v1/games/{game_id}/join",
            headers={"Authorization": f"Bearer {p2_token}"},
        )
        assert join_res.status_code == 200

        started_event = ws.receive_json()
        assert started_event["event"] == "game_started"
        assert started_event["current_turn_user_id"] == p1_id
        # Anti-cheat: no rack or tile_bag leaked in WS payload
        assert "tile_bag" not in started_event
        assert all("rack" not in p for p in started_event["players"])

        pass_res = ws_client.post(
            f"/api/v1/games/{game_id}/moves",
            headers={"Authorization": f"Bearer {p1_token}"},
            json={"move_type": "PASS"},
        )
        assert pass_res.status_code == 200

        move_event = ws.receive_json()
        assert move_event["event"] == "move_made"
        assert move_event["move_type"] == "PASS"
        assert move_event["current_turn_user_id"] == p2_id
        assert all("rack" not in p for p in move_event["players"])


def test_timeout_worker_expires_overdue_game(ws_client: TestClient) -> None:
    p1_id, p1_token = _register_and_login(ws_client, "top1", "tr")
    p2_id, p2_token = _register_and_login(ws_client, "top2", "en")

    create_res = ws_client.post(
        "/api/v1/games",
        headers={"Authorization": f"Bearer {p1_token}"},
        json={"language": "en", "turn_duration_hours": 12},
    )
    game_id = uuid.UUID(create_res.json()["id"])
    ws_client.created_game_ids.append(game_id)  # type: ignore[attr-defined]

    join_res = ws_client.post(
        f"/api/v1/games/{game_id}/join",
        headers={"Authorization": f"Bearer {p2_token}"},
    )
    assert join_res.status_code == 200

    # Force turn_expires_at into the past
    async def _expire_and_process() -> tuple[list[uuid.UUID], Game, list[Move]]:
        async with ws_client.session_factory() as session:  # type: ignore[attr-defined]
            await session.execute(
                update(Game)
                .where(Game.id == game_id)
                .values(turn_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))
            )
            await session.commit()

            processed = await process_expired_games(
                db=session,
                broadcaster=InMemoryBroadcaster(),
                notifier=LoggingNotificationHook(),
            )
            updated_game = await session.get(Game, game_id)
            moves = list(
                (
                    await session.scalars(
                        select(Move).where(Move.game_id == game_id).order_by(Move.move_number)
                    )
                ).all()
            )
            return processed, updated_game, moves

    processed_ids, updated_game, moves = asyncio.run(_expire_and_process())
    assert game_id in processed_ids
    assert updated_game.status == GameStatus.FINISHED.value
    assert updated_game.finish_reason == MoveType.TIMEOUT.value
    assert updated_game.winner_id == uuid.UUID(p2_id)
    assert updated_game.current_turn_user_id is None
    assert len(moves) == 1
    assert moves[0].move_type == MoveType.TIMEOUT.value
    assert moves[0].user_id == uuid.UUID(p1_id)


def test_submit_move_lazy_expires_overdue_game_and_purges_tokens(ws_client: TestClient) -> None:
    p1_id, p1_token = _register_and_login(ws_client, "lzp1", "tr")
    p2_id, p2_token = _register_and_login(ws_client, "lzp2", "tr")

    create_res = ws_client.post(
        "/api/v1/games",
        headers={"Authorization": f"Bearer {p1_token}"},
        json={"language": "tr", "turn_duration_hours": 12},
    )
    game_id = uuid.UUID(create_res.json()["id"])
    ws_client.created_game_ids.append(game_id)  # type: ignore[attr-defined]
    ws_client.post(
        f"/api/v1/games/{game_id}/join",
        headers={"Authorization": f"Bearer {p2_token}"},
    )

    async def _expire_turn_and_add_stale_token() -> None:
        async with ws_client.session_factory() as session:  # type: ignore[attr-defined]
            await session.execute(
                update(Game)
                .where(Game.id == game_id)
                .values(turn_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10))
            )
            session.add(
                RefreshToken(
                    user_id=uuid.UUID(p1_id),
                    jti=f"stale-{uuid.uuid4().hex}",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(_expire_turn_and_add_stale_token())

    # Submitting a move on an expired game immediately closes it as TIMEOUT
    move_res = ws_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers={"Authorization": f"Bearer {p1_token}"},
        json={"move_type": "PASS"},
    )
    assert move_res.status_code == 409
    assert move_res.json()["error_code"] == "GAME_EXPIRED"

    detail = ws_client.get(
        f"/api/v1/games/{game_id}",
        headers={"Authorization": f"Bearer {p1_token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "finished"
    assert detail.json()["finish_reason"] == "TIMEOUT"
    assert detail.json()["winner_id"] == p2_id

    # Verify pagination on GET /games
    paginated = ws_client.get(
        "/api/v1/games?limit=1&offset=0",
        headers={"Authorization": f"Bearer {p1_token}"},
    )
    assert paginated.status_code == 200
    assert len(paginated.json()) == 1

    # Verify expired refresh token purge
    async def _purge() -> int:
        async with ws_client.session_factory() as session:  # type: ignore[attr-defined]
            return await purge_expired_refresh_tokens(session)

    assert asyncio.run(_purge()) >= 1
