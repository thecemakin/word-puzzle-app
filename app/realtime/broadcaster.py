from collections import defaultdict
from typing import Any, Protocol

from fastapi import WebSocket


class EventBroadcaster(Protocol):
    """Abstraction for game room real-time event broadcasting (InMemory now, Redis later)."""

    async def connect(self, game_id: str, websocket: WebSocket) -> None: ...

    async def disconnect(self, game_id: str, websocket: WebSocket) -> None: ...

    async def publish(self, game_id: str, event: dict[str, Any]) -> None: ...


class InMemoryBroadcaster:
    """Single-process WebSocket room manager backed by an in-memory dictionary."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, game_id: str, websocket: WebSocket) -> None:
        self._rooms[game_id].add(websocket)

    async def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        room = self._rooms.get(game_id)
        if room is None:
            return
        room.discard(websocket)
        if not room:
            del self._rooms[game_id]

    async def publish(self, game_id: str, event: dict[str, Any]) -> None:
        room = self._rooms.get(game_id)
        if not room:
            return

        stale: list[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_json(event)
            except Exception:
                stale.append(ws)

        for ws in stale:
            await self.disconnect(game_id, ws)

    def connection_count(self, game_id: str) -> int:
        return len(self._rooms.get(game_id, ()))
