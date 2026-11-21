import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.game import Game, GameStatus
from app.models.game_player import GamePlayer
from app.models.move import Move, MoveType
from app.models.refresh_token import RefreshToken
from app.realtime.broadcaster import EventBroadcaster
from app.realtime.events import build_public_players_payload
from app.services.notification_service import NotificationHook

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpiredGameEvent:
    game_id: uuid.UUID
    timed_out_user_id: Optional[uuid.UUID]
    winner_id: Optional[uuid.UUID]
    move_number: int
    version: int
    players_payload: list[dict[str, Any]]
    notification_targets: tuple[tuple[uuid.UUID, str], ...]


def apply_timeout_to_game(
    db: AsyncSession,
    game: Game,
    now: datetime,
) -> ExpiredGameEvent:
    """Marks a locked active game as finished due to turn timeout and records a TIMEOUT move."""
    timed_out_user_id = game.current_turn_user_id
    winner_player = next(
        (p for p in game.players if p.user_id != timed_out_user_id),
        None,
    )
    winner_id = winner_player.user_id if winner_player is not None else None

    game.status = GameStatus.FINISHED.value
    game.winner_id = winner_id
    game.finish_reason = MoveType.TIMEOUT.value
    game.current_turn_user_id = None
    game.turn_expires_at = None
    game.finished_at = now
    game.move_count += 1
    game.version += 1

    db.add(
        Move(
            game_id=game.id,
            user_id=timed_out_user_id,
            move_number=game.move_count,
            move_type=MoveType.TIMEOUT.value,
            placements=[],
            words_formed=[],
            score_gained=0,
        )
    )
    return ExpiredGameEvent(
        game_id=game.id,
        timed_out_user_id=timed_out_user_id,
        winner_id=winner_id,
        move_number=game.move_count,
        version=game.version,
        players_payload=build_public_players_payload(game.players),
        notification_targets=tuple(
            (gp.user_id, gp.user.ui_language if gp.user else "tr")
            for gp in game.players
        ),
    )


async def dispatch_timeout_events(
    events: list[ExpiredGameEvent],
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
) -> None:
    """Broadcasts WebSocket and push notification events for expired games."""
    for item in events:
        room_id = str(item.game_id)
        if broadcaster is not None:
            try:
                await broadcaster.publish(
                    room_id,
                    {
                        "event": "turn_expired",
                        "game_id": room_id,
                        "timed_out_user_id": (
                            str(item.timed_out_user_id) if item.timed_out_user_id else None
                        ),
                        "winner_id": str(item.winner_id) if item.winner_id else None,
                        "move_number": item.move_number,
                        "version": item.version,
                    },
                )
                await broadcaster.publish(
                    room_id,
                    {
                        "event": "game_finished",
                        "game_id": room_id,
                        "finish_reason": MoveType.TIMEOUT.value,
                        "winner_id": str(item.winner_id) if item.winner_id else None,
                        "version": item.version,
                        "players": item.players_payload,
                    },
                )
            except Exception:
                logger.exception("Failed to broadcast timeout event for game %s", room_id)

        if notifier is not None:
            for user_id, ui_lang in item.notification_targets:
                try:
                    await notifier.notify_game_finished(
                        user_id=user_id,
                        ui_language=ui_lang,
                        game_id=item.game_id,
                        reason=MoveType.TIMEOUT.value,
                        winner_id=item.winner_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to send timeout notification user_id=%s game_id=%s",
                        user_id,
                        room_id,
                    )


async def process_expired_games(
    db: AsyncSession,
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
    batch_size: int = 50,
) -> list[uuid.UUID]:
    """Finds active games past turn_expires_at, resolves them as TIMEOUT, and notifies."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Game)
        .where(
            Game.status == GameStatus.ACTIVE.value,
            Game.turn_expires_at.is_not(None),
            Game.turn_expires_at <= now,
        )
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
        .order_by(Game.turn_expires_at.asc())
        .limit(batch_size)
        .with_for_update(of=Game, skip_locked=True)
    )
    expired_games = list((await db.scalars(stmt)).all())
    if not expired_games:
        return []

    processed_ids: list[uuid.UUID] = []
    pending_events: list[ExpiredGameEvent] = []

    for game in expired_games:
        pending_events.append(apply_timeout_to_game(db, game, now))
        processed_ids.append(game.id)

    await db.commit()
    await dispatch_timeout_events(pending_events, broadcaster=broadcaster, notifier=notifier)
    return processed_ids


async def purge_expired_refresh_tokens(db: AsyncSession) -> int:
    """Deletes expired refresh token rows to prevent unbounded table growth."""
    now = datetime.now(timezone.utc)
    result = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at <= now))
    await db.commit()
    return int(result.rowcount or 0)


async def run_timeout_worker(
    session_factory: async_sessionmaker[AsyncSession],
    broadcaster: EventBroadcaster,
    notifier: NotificationHook,
    interval_seconds: int,
    batch_size: int = 50,
) -> None:
    """Background loop that periodically checks for expired turn timers and stale tokens."""
    while True:
        try:
            while True:
                async with session_factory() as session:
                    expired = await process_expired_games(
                        db=session,
                        broadcaster=broadcaster,
                        notifier=notifier,
                        batch_size=batch_size,
                    )
                if expired:
                    logger.info("Processed %d expired game(s)", len(expired))
                if len(expired) < batch_size:
                    break

            async with session_factory() as session:
                purged = await purge_expired_refresh_tokens(session)
                if purged:
                    logger.info("Purged %d expired refresh token(s)", purged)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error while running background maintenance worker")

        await asyncio.sleep(interval_seconds)
