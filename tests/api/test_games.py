import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.main import app
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.user import User
from tests.api.conftest import get_test_database_url


@pytest.fixture
def game_client() -> TestClient:
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
    token = login.json()["access_token"]
    return user_id, token


def test_game_options_and_creation_validation(game_client: TestClient) -> None:
    opts = game_client.get("/api/v1/games/options")
    assert opts.status_code == 200
    data = opts.json()
    assert {lang["code"] for lang in data["languages"]} == {"tr", "en"}
    assert data["turn_duration_hours"] == [12, 24, 48, 72]

    _, token = _register_and_login(game_client, "opt")
    headers = {"Authorization": f"Bearer {token}"}

    bad_lang = game_client.post(
        "/api/v1/games",
        headers=headers,
        json={"language": "zz", "turn_duration_hours": 12},
    )
    assert bad_lang.status_code == 400
    assert bad_lang.json()["error_code"] == "UNSUPPORTED_LANGUAGE"

    bad_dur = game_client.post(
        "/api/v1/games",
        headers=headers,
        json={"language": "tr", "turn_duration_hours": 5},
    )
    assert bad_dur.status_code == 400
    assert bad_dur.json()["error_code"] == "INVALID_TURN_DURATION"


def test_full_turn_based_game_flow_and_anti_cheat(game_client: TestClient) -> None:
    p1_id, p1_token = _register_and_login(game_client, "p1", ui_language="en")
    p2_id, p2_token = _register_and_login(game_client, "p2", ui_language="tr")
    p1_headers = {"Authorization": f"Bearer {p1_token}"}
    p2_headers = {"Authorization": f"Bearer {p2_token}"}

    # P1 creates a Turkish game with 24h turn duration (even though P1's UI language is EN)
    create_res = game_client.post(
        "/api/v1/games",
        headers=p1_headers,
        json={"language": "tr", "turn_duration_hours": 24},
    )
    assert create_res.status_code == 201
    game_data = create_res.json()
    game_id = uuid.UUID(game_data["id"])
    game_client.created_game_ids.append(game_id)  # type: ignore[attr-defined]
    assert game_data["language"] == "tr"
    assert game_data["turn_duration_hours"] == 24
    assert game_data["status"] == "waiting"

    # P2 joins the game
    join_res = game_client.post(f"/api/v1/games/{game_id}/join", headers=p2_headers)
    assert join_res.status_code == 200
    joined = join_res.json()
    assert joined["status"] == "active"
    assert joined["current_turn_user_id"] == p1_id
    assert joined["turn_expires_at"] is not None
    assert joined["bag_remaining"] == 86  # 100 - 7 - 7

    # Anti-cheat check: P2 sees own rack (7 tiles), P1's rack is hidden (None)
    p2_players = {p["user_id"]: p for p in joined["players"]}
    assert len(p2_players[p2_id]["rack"]) == 7
    assert p2_players[p1_id]["rack"] is None
    assert p2_players[p1_id]["rack_count"] == 7

    # List games shows the active game for P1
    list_res = game_client.get("/api/v1/games?status=active", headers=p1_headers)
    assert list_res.status_code == 200
    assert any(g["id"] == str(game_id) for g in list_res.json())

    # Set deterministic racks in DB so we can test valid PLAY moves cleanly
    async def _set_racks() -> None:
        async with game_client.session_factory() as session:  # type: ignore[attr-defined]
            await session.execute(
                update(GamePlayer)
                .where(GamePlayer.game_id == game_id, GamePlayer.user_id == uuid.UUID(p1_id))
                .values(rack=["E", "L", "M", "A", "K", "R", "T"])
            )
            await session.execute(
                update(GamePlayer)
                .where(GamePlayer.game_id == game_id, GamePlayer.user_id == uuid.UUID(p2_id))
                .values(rack=["A", "T", "S", "U", "B", "N", "Z"])
            )
            await session.commit()

    asyncio.run(_set_racks())

    # P2 tries to play out of turn
    not_turn = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p2_headers,
        json={"move_type": "PASS"},
    )
    assert not_turn.status_code == 409
    assert not_turn.json()["error_code"] == "NOT_YOUR_TURN"

    # P1 submits invalid word -> error_code INVALID_WORD
    bad_word = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p1_headers,
        json={
            "move_type": "PLAY",
            "placements": [
                {"row": 7, "col": 7, "letter": "K"},
                {"row": 7, "col": 8, "letter": "R"},
                {"row": 7, "col": 9, "letter": "T"},
            ],
        },
    )
    assert bad_word.status_code == 400
    assert bad_word.json()["error_code"] == "INVALID_WORD"

    # P1 submits stale version -> VERSION_CONFLICT
    stale_ver = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p1_headers,
        json={"move_type": "PASS", "expected_version": 1},
    )
    assert stale_ver.status_code == 409
    assert stale_ver.json()["error_code"] == "VERSION_CONFLICT"

    # P1 plays "ELMA" across center (7,6)-(7,9): E(1)+L(1)+M(2)+A(1) = 5 * 2 (START) = 10
    play_res = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p1_headers,
        json={
            "move_type": "PLAY",
            "expected_version": joined["version"],
            "placements": [
                {"row": 7, "col": 6, "letter": "e"},
                {"row": 7, "col": 7, "letter": "l"},
                {"row": 7, "col": 8, "letter": "m"},
                {"row": 7, "col": 9, "letter": "a"},
            ],
        },
    )
    assert play_res.status_code == 200
    after_p1 = play_res.json()
    assert after_p1["move_count"] == 1
    assert after_p1["current_turn_user_id"] == p2_id
    assert after_p1["bag_remaining"] == 82
    p1_view = {p["user_id"]: p for p in after_p1["players"]}
    assert p1_view[p1_id]["score"] == 10
    assert len(p1_view[p1_id]["rack"]) == 7

    # P2 passes
    pass_res = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p2_headers,
        json={"move_type": "PASS"},
    )
    assert pass_res.status_code == 200
    assert pass_res.json()["current_turn_user_id"] == p1_id

    # P1 swaps 2 tiles
    p1_rack_now = game_client.get(f"/api/v1/games/{game_id}", headers=p1_headers).json()["players"]
    my_tiles = next(p["rack"] for p in p1_rack_now if p["is_me"])
    swap_res = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p1_headers,
        json={"move_type": "SWAP", "tiles_to_swap": my_tiles[:2]},
    )
    assert swap_res.status_code == 200
    assert swap_res.json()["move_count"] == 3

    # Sync moves since move 1
    moves_res = game_client.get(
        f"/api/v1/games/{game_id}/moves?since_move_number=1",
        headers=p2_headers,
    )
    assert moves_res.status_code == 200
    moves = moves_res.json()
    assert [m["move_number"] for m in moves] == [2, 3]
    assert [m["move_type"] for m in moves] == ["PASS", "SWAP"]

    # P2 resigns -> P1 wins
    resign_res = game_client.post(
        f"/api/v1/games/{game_id}/moves",
        headers=p2_headers,
        json={"move_type": "RESIGN"},
    )
    assert resign_res.status_code == 200
    finished = resign_res.json()
    assert finished["status"] == "finished"
    assert finished["finish_reason"] == "RESIGN"
    assert finished["winner_id"] == p1_id
    assert finished["turn_expires_at"] is None
