import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.user import User
from app.realtime.broadcaster import EventBroadcaster

router = APIRouter(tags=["websocket"])

MAX_WS_MESSAGE_BYTES = 1024


def _extract_ws_token(websocket: WebSocket, query_token: Optional[str]) -> Optional[str]:
    if query_token:
        return query_token
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


@router.websocket("/games/{game_id}/ws")
async def game_websocket(
    websocket: WebSocket,
    game_id: uuid.UUID,
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    raw_token = _extract_ws_token(websocket, token)
    if not raw_token:
        await db.close()
        await websocket.close(code=4401, reason="Authentication required")
        return

    try:
        claims = decode_token(raw_token, expected_type="access")
        user_id = uuid.UUID(claims["sub"])
    except (AppError, ValueError):
        await db.close()
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        await db.close()
        await websocket.close(code=4401, reason="User not found or inactive")
        return

    game = await db.get(Game, game_id)
    if game is None:
        await db.close()
        await websocket.close(code=4404, reason="Game not found")
        return

    is_participant = await db.scalar(
        select(GamePlayer.id).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user.id,
        )
    )
    if is_participant is None:
        await db.close()
        await websocket.close(code=4403, reason="Not a game participant")
        return

    initial_status = game.status
    initial_version = game.version
    initial_move_count = game.move_count

    # Release the DB connection before entering the long-lived WebSocket loop
    await db.close()

    broadcaster: EventBroadcaster = websocket.app.state.broadcaster
    room_id = str(game_id)

    await websocket.accept()
    await broadcaster.connect(room_id, websocket)

    try:
        await websocket.send_json(
            {
                "event": "connected",
                "game_id": room_id,
                "status": initial_status,
                "version": initial_version,
                "move_count": initial_move_count,
            }
        )
        while True:
            message = await websocket.receive_text()
            if len(message.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="Message too big")
                break
            if message.strip().lower() == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(room_id, websocket)
