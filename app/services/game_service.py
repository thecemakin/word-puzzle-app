import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.constants import RACK_SIZE
from app.core.exceptions import AppError
from app.engine.bag import TileBag
from app.engine.board import Board, TilePlacement
from app.engine.dictionary import DictionaryManager
from app.engine.locales import get_language_pack, list_language_packs
from app.engine.rules import check_game_over, evaluate_play_move, evaluate_swap_move
from app.models.game import Game, GameStatus
from app.models.game_player import GamePlayer
from app.models.move import Move, MoveType
from app.models.user import User
from app.realtime.broadcaster import EventBroadcaster
from app.realtime.events import build_public_players_payload
from app.schemas.game import (
    CreateGameRequest,
    GameDetailResponse,
    GameOptionsResponse,
    GamePlayerResponse,
    GameSummaryResponse,
    LanguageOption,
    MatchmakingRequest,
    MatchmakingResponse,
    SubmitMoveRequest,
)
from app.services.notification_service import NotificationHook
from app.services.timeout_service import apply_timeout_to_game, dispatch_timeout_events

logger = logging.getLogger(__name__)


def get_game_options() -> GameOptionsResponse:
    settings = get_settings()
    allowed_codes = set(settings.game_languages)
    languages = [
        LanguageOption(code=pack.code, name=pack.name)
        for pack in list_language_packs()
        if pack.code in allowed_codes
    ]
    return GameOptionsResponse(
        languages=languages,
        turn_duration_hours=settings.turn_duration_hours_options,
    )


def _validate_game_settings(language: str, turn_duration_hours: int) -> str:
    settings = get_settings()
    pack = get_language_pack(language)
    if pack.code not in settings.game_languages:
        raise AppError(
            error_code="UNSUPPORTED_LANGUAGE",
            message=f"Game language '{language}' is not enabled",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"supported": settings.game_languages},
        )
    if turn_duration_hours not in settings.turn_duration_hours_options:
        raise AppError(
            error_code="INVALID_TURN_DURATION",
            message=f"Turn duration '{turn_duration_hours}' hours is not allowed",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"allowed": settings.turn_duration_hours_options},
        )
    return pack.code


def _build_player_responses(
    players: list[GamePlayer],
    viewer_id: uuid.UUID,
) -> list[GamePlayerResponse]:
    sorted_players = sorted(players, key=lambda p: p.seat_order)
    result: list[GamePlayerResponse] = []
    for gp in sorted_players:
        is_me = gp.user_id == viewer_id
        result.append(
            GamePlayerResponse(
                user_id=gp.user_id,
                username=gp.user.username if gp.user else "unknown",
                seat_order=gp.seat_order,
                score=gp.score,
                rack_count=len(gp.rack),
                is_me=is_me,
                # Anti-cheat: only reveal rack tiles to the owning player
                rack=list(gp.rack) if is_me else None,
            )
        )
    return result


def _to_game_summary(game: Game, viewer_id: uuid.UUID) -> GameSummaryResponse:
    return GameSummaryResponse(
        id=game.id,
        language=game.language,
        turn_duration_hours=game.turn_duration_hours,
        status=game.status,
        current_turn_user_id=game.current_turn_user_id,
        invited_user_id=game.invited_user_id,
        turn_expires_at=game.turn_expires_at,
        move_count=game.move_count,
        version=game.version,
        winner_id=game.winner_id,
        finish_reason=game.finish_reason,
        created_at=game.created_at,
        finished_at=game.finished_at,
        players=_build_player_responses(game.players, viewer_id),
    )


def _to_game_detail(game: Game, viewer_id: uuid.UUID) -> GameDetailResponse:
    summary = _to_game_summary(game, viewer_id)
    return GameDetailResponse(
        **summary.model_dump(),
        board_state=game.board_state,
        bag_remaining=len(game.tile_bag),
        consecutive_passes=game.consecutive_passes,
    )


async def _load_game_with_players(
    db: AsyncSession,
    game_id: uuid.UUID,
    for_update: bool = False,
) -> Game:
    stmt = (
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update(of=Game)
    game = await db.scalar(stmt)
    if game is None:
        raise AppError(
            error_code="GAME_NOT_FOUND",
            message="Game not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return game


def _assert_participant_or_invited(game: Game, user_id: uuid.UUID) -> None:
    is_player = any(p.user_id == user_id for p in game.players)
    if not is_player and game.invited_user_id != user_id:
        raise AppError(
            error_code="NOT_A_GAME_PARTICIPANT",
            message="You are not a participant of this game",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _determine_winner(players: list[GamePlayer]) -> Optional[uuid.UUID]:
    if not players:
        return None
    highest = max(p.score for p in players)
    top_players = [p for p in players if p.score == highest]
    if len(top_players) == 1:
        return top_players[0].user_id
    return None


async def create_game(
    db: AsyncSession,
    creator: User,
    payload: CreateGameRequest,
) -> GameDetailResponse:
    language_code = _validate_game_settings(payload.language, payload.turn_duration_hours)

    invited_user_id: Optional[uuid.UUID] = None
    if payload.opponent_username is not None:
        opponent = await db.scalar(
            select(User).where(
                func.lower(User.username) == payload.opponent_username.strip().lower()
            )
        )
        if opponent is None or not opponent.is_active:
            raise AppError(
                error_code="OPPONENT_NOT_FOUND",
                message=f"User '{payload.opponent_username}' not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if opponent.id == creator.id:
            raise AppError(
                error_code="CANNOT_PLAY_SELF",
                message="You cannot invite yourself to a game",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        invited_user_id = opponent.id

    game = Game(
        language=language_code,
        turn_duration_hours=payload.turn_duration_hours,
        status=GameStatus.WAITING.value,
        board_state=Board().to_state(),
        tile_bag=[],
        invited_user_id=invited_user_id,
    )
    db.add(game)
    await db.flush()

    creator_player = GamePlayer(
        game_id=game.id,
        user_id=creator.id,
        seat_order=1,
        rack=[],
        score=0,
    )
    db.add(creator_player)
    await db.commit()

    loaded = await _load_game_with_players(db, game.id)
    return _to_game_detail(loaded, creator.id)


async def _activate_game_with_player(
    db: AsyncSession,
    game: Game,
    joining_user: User,
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
) -> GameDetailResponse:
    bag = TileBag.create(game.language)
    first_player = game.players[0]
    first_player.rack = bag.draw(RACK_SIZE)

    second_player = GamePlayer(
        game_id=game.id,
        user_id=joining_user.id,
        seat_order=2,
        rack=bag.draw(RACK_SIZE),
        score=0,
    )
    db.add(second_player)

    now = datetime.now(timezone.utc)
    game.tile_bag = bag.to_list()
    game.status = GameStatus.ACTIVE.value
    game.current_turn_user_id = first_player.user_id
    game.turn_expires_at = now + timedelta(hours=game.turn_duration_hours)
    game.version += 1

    await db.commit()
    loaded = await _load_game_with_players(db, game.id)

    if broadcaster is not None:
        try:
            await broadcaster.publish(
                str(loaded.id),
                {
                    "event": "game_started",
                    "game_id": str(loaded.id),
                    "language": loaded.language,
                    "current_turn_user_id": str(loaded.current_turn_user_id),
                    "turn_expires_at": (
                        loaded.turn_expires_at.isoformat() if loaded.turn_expires_at else None
                    ),
                    "bag_remaining": len(loaded.tile_bag),
                    "version": loaded.version,
                    "players": build_public_players_payload(loaded.players),
                },
            )
        except Exception:
            logger.exception("Failed to broadcast game_started for game %s", loaded.id)
    if notifier is not None and loaded.current_turn_user_id is not None:
        turn_player = next(
            (p for p in loaded.players if p.user_id == loaded.current_turn_user_id),
            None,
        )
        if turn_player is not None and turn_player.user is not None:
            try:
                await notifier.notify_turn_started(
                    user_id=turn_player.user_id,
                    ui_language=turn_player.user.ui_language,
                    game_id=loaded.id,
                )
            except Exception:
                logger.exception("Failed to notify turn_started for game %s", loaded.id)

    return _to_game_detail(loaded, joining_user.id)


async def join_game(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
) -> GameDetailResponse:
    game = await _load_game_with_players(db, game_id, for_update=True)

    if game.status != GameStatus.WAITING.value:
        raise AppError(
            error_code="GAME_NOT_JOINABLE",
            message="Game is no longer waiting for players",
            status_code=status.HTTP_409_CONFLICT,
        )
    if any(p.user_id == user.id for p in game.players):
        raise AppError(
            error_code="ALREADY_IN_GAME",
            message="You have already joined this game",
            status_code=status.HTTP_409_CONFLICT,
        )
    if game.invited_user_id is not None and game.invited_user_id != user.id:
        raise AppError(
            error_code="GAME_INVITE_ONLY",
            message="This game is reserved for an invited player",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if len(game.players) >= 2:
        raise AppError(
            error_code="GAME_FULL",
            message="Game already has two players",
            status_code=status.HTTP_409_CONFLICT,
        )

    return await _activate_game_with_player(
        db=db,
        game=game,
        joining_user=user,
        broadcaster=broadcaster,
        notifier=notifier,
    )


async def matchmake_game(
    db: AsyncSession,
    user: User,
    payload: MatchmakingRequest,
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
) -> MatchmakingResponse:
    language_code = _validate_game_settings(payload.language, payload.turn_duration_hours)

    # Serialize concurrent matchmaking requests from the same user to avoid duplicate queues
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())

    # 1. Look for an open waiting game created by someone else with matching language & duration
    candidate_stmt = (
        select(Game)
        .join(GamePlayer, GamePlayer.game_id == Game.id)
        .where(
            Game.status == GameStatus.WAITING.value,
            Game.invited_user_id.is_(None),
            Game.language == language_code,
            Game.turn_duration_hours == payload.turn_duration_hours,
            GamePlayer.user_id != user.id,
        )
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
        .order_by(Game.created_at.asc())
        .limit(1)
        .with_for_update(of=Game, skip_locked=True)
    )
    candidate = await db.scalar(candidate_stmt)
    if candidate is not None and len(candidate.players) == 1:
        detail = await _activate_game_with_player(
            db=db,
            game=candidate,
            joining_user=user,
            broadcaster=broadcaster,
            notifier=notifier,
        )
        return MatchmakingResponse(matched=True, game=detail)

    # 2. Avoid duplicate open queues: return user's existing open game for the same criteria if any
    existing_own_stmt = (
        select(Game)
        .join(GamePlayer, GamePlayer.game_id == Game.id)
        .where(
            Game.status == GameStatus.WAITING.value,
            Game.invited_user_id.is_(None),
            Game.language == language_code,
            Game.turn_duration_hours == payload.turn_duration_hours,
            GamePlayer.user_id == user.id,
        )
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
        .order_by(Game.created_at.asc())
        .limit(1)
    )
    existing_own = await db.scalar(existing_own_stmt)
    if existing_own is not None:
        return MatchmakingResponse(
            matched=False,
            game=_to_game_detail(existing_own, user.id),
        )

    # 3. Create a new open waiting game
    detail = await create_game(
        db=db,
        creator=user,
        payload=CreateGameRequest(
            language=language_code,
            turn_duration_hours=payload.turn_duration_hours,
        ),
    )
    return MatchmakingResponse(matched=False, game=detail)


async def list_user_games(
    db: AsyncSession,
    user: User,
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[GameSummaryResponse]:
    stmt = (
        select(Game)
        .outerjoin(GamePlayer, GamePlayer.game_id == Game.id)
        .where(
            or_(
                GamePlayer.user_id == user.id,
                Game.invited_user_id == user.id,
            )
        )
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
        .distinct()
        .order_by(Game.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(Game.status == status_filter.strip().lower())

    games = (await db.scalars(stmt)).all()
    return [_to_game_summary(game, user.id) for game in games]


async def get_game_detail(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
) -> GameDetailResponse:
    game = await _load_game_with_players(db, game_id)
    _assert_participant_or_invited(game, user.id)
    return _to_game_detail(game, user.id)


async def get_game_moves(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
    since_move_number: int = 0,
    limit: int = 100,
) -> list[Move]:
    game = await _load_game_with_players(db, game_id)
    _assert_participant_or_invited(game, user.id)

    stmt = (
        select(Move)
        .where(Move.game_id == game_id, Move.move_number > since_move_number)
        .order_by(Move.move_number.asc())
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def submit_move(
    db: AsyncSession,
    user: User,
    game_id: uuid.UUID,
    payload: SubmitMoveRequest,
    dictionary_manager: DictionaryManager,
    broadcaster: Optional[EventBroadcaster] = None,
    notifier: Optional[NotificationHook] = None,
) -> GameDetailResponse:
    game = await _load_game_with_players(db, game_id, for_update=True)

    player = next((p for p in game.players if p.user_id == user.id), None)
    if player is None:
        raise AppError(
            error_code="NOT_A_GAME_PARTICIPANT",
            message="You are not a participant of this game",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if game.status != GameStatus.ACTIVE.value:
        raise AppError(
            error_code="GAME_NOT_ACTIVE",
            message="Moves can only be submitted on active games",
            status_code=status.HTTP_409_CONFLICT,
            details={"status": game.status},
        )

    if payload.expected_version is not None and game.version != payload.expected_version:
        raise AppError(
            error_code="VERSION_CONFLICT",
            message="Game state has changed; please refresh before submitting a move",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_version": game.version},
        )

    now = datetime.now(timezone.utc)
    if game.turn_expires_at is not None and game.turn_expires_at <= now:
        timeout_event = apply_timeout_to_game(db, game, now)
        await db.commit()
        await dispatch_timeout_events(
            [timeout_event],
            broadcaster=broadcaster,
            notifier=notifier,
        )
        raise AppError(
            error_code="GAME_EXPIRED",
            message="Turn timer has expired for this game",
            status_code=status.HTTP_409_CONFLICT,
        )

    opponent = next((p for p in game.players if p.user_id != user.id), None)
    if opponent is None:
        raise AppError(
            error_code="OPPONENT_MISSING",
            message="Game does not have two players",
            status_code=status.HTTP_409_CONFLICT,
        )

    if payload.move_type != MoveType.RESIGN.value and game.current_turn_user_id != user.id:
        raise AppError(
            error_code="NOT_YOUR_TURN",
            message="It is not your turn",
            status_code=status.HTTP_409_CONFLICT,
        )

    placements_json: list[dict[str, Any]] = []
    words_formed_json: list[dict[str, Any]] = []
    score_gained = 0
    finished_by_resign = False

    if payload.move_type == MoveType.PLAY.value:
        board = Board.from_state(game.board_state)
        dictionary = dictionary_manager.get(game.language)
        tile_placements = [
            TilePlacement(
                row=p.row,
                col=p.col,
                letter=p.letter,
                is_blank=p.is_blank,
            )
            for p in payload.placements
        ]
        eval_res = evaluate_play_move(
            board=board,
            rack=list(player.rack),
            placements=tile_placements,
            language_code=game.language,
            dictionary=dictionary,
        )

        bag = TileBag.from_list(list(game.tile_bag))
        needed = max(0, RACK_SIZE - len(eval_res.remaining_rack))
        drawn = bag.draw(needed)

        player.rack = eval_res.remaining_rack + drawn
        player.score += eval_res.score_result.total_score
        game.board_state = eval_res.board.to_state()
        game.tile_bag = bag.to_list()
        game.consecutive_passes = 0

        score_gained = eval_res.score_result.total_score
        placements_json = [
            {
                "row": p.row,
                "col": p.col,
                "letter": p.letter,
                "is_blank": p.is_blank,
            }
            for p in eval_res.normalized_placements
        ]
        words_formed_json = [
            {"word": ws.word, "score": ws.score}
            for ws in eval_res.score_result.word_scores
        ]

    elif payload.move_type == MoveType.SWAP.value:
        bag = TileBag.from_list(list(game.tile_bag))
        swap_res = evaluate_swap_move(
            rack=list(player.rack),
            tiles_to_swap=payload.tiles_to_swap,
            bag=bag,
            language_code=game.language,
        )
        player.rack = swap_res.new_rack
        game.tile_bag = swap_res.bag.to_list()
        game.consecutive_passes += 1

    elif payload.move_type == MoveType.PASS.value:
        game.consecutive_passes += 1

    elif payload.move_type == MoveType.RESIGN.value:
        finished_by_resign = True
        game.status = GameStatus.FINISHED.value
        game.winner_id = opponent.user_id
        game.finish_reason = MoveType.RESIGN.value
        game.current_turn_user_id = None
        game.turn_expires_at = None
        game.finished_at = now

    game.move_count += 1
    game.version += 1

    move = Move(
        game_id=game.id,
        user_id=user.id,
        move_number=game.move_count,
        move_type=payload.move_type,
        placements=placements_json,
        words_formed=words_formed_json,
        score_gained=score_gained,
    )
    db.add(move)

    if not finished_by_resign:
        racks_by_player = {str(p.user_id): list(p.rack) for p in game.players}
        over_res = check_game_over(
            player_racks=racks_by_player,
            bag_remaining=len(game.tile_bag),
            consecutive_passes=game.consecutive_passes,
            language_code=game.language,
        )
        if over_res.is_game_over:
            if over_res.score_adjustments:
                for gp in game.players:
                    gp.score += over_res.score_adjustments.get(str(gp.user_id), 0)
            game.status = GameStatus.FINISHED.value
            game.winner_id = _determine_winner(game.players)
            game.finish_reason = over_res.reason
            game.current_turn_user_id = None
            game.turn_expires_at = None
            game.finished_at = now
        else:
            game.current_turn_user_id = opponent.user_id
            game.turn_expires_at = now + timedelta(hours=game.turn_duration_hours)

    await db.commit()
    loaded = await _load_game_with_players(db, game.id)

    room_id = str(loaded.id)
    players_payload = build_public_players_payload(loaded.players)

    if broadcaster is not None:
        try:
            await broadcaster.publish(
                room_id,
                {
                    "event": "move_made",
                    "game_id": room_id,
                    "move_number": move.move_number,
                    "move_type": move.move_type,
                    "user_id": str(user.id),
                    "placements": placements_json,
                    "words_formed": words_formed_json,
                    "score_gained": score_gained,
                    "current_turn_user_id": (
                        str(loaded.current_turn_user_id) if loaded.current_turn_user_id else None
                    ),
                    "turn_expires_at": (
                        loaded.turn_expires_at.isoformat() if loaded.turn_expires_at else None
                    ),
                    "bag_remaining": len(loaded.tile_bag),
                    "status": loaded.status,
                    "version": loaded.version,
                    "players": players_payload,
                },
            )
            if loaded.status == GameStatus.FINISHED.value:
                await broadcaster.publish(
                    room_id,
                    {
                        "event": "game_finished",
                        "game_id": room_id,
                        "finish_reason": loaded.finish_reason,
                        "winner_id": str(loaded.winner_id) if loaded.winner_id else None,
                        "version": loaded.version,
                        "players": players_payload,
                    },
                )
        except Exception:
            logger.exception("Failed to broadcast move event for game %s", room_id)

    if notifier is not None:
        if loaded.status == GameStatus.FINISHED.value:
            for gp in loaded.players:
                ui_lang = gp.user.ui_language if gp.user else "tr"
                try:
                    await notifier.notify_game_finished(
                        user_id=gp.user_id,
                        ui_language=ui_lang,
                        game_id=loaded.id,
                        reason=loaded.finish_reason or "FINISHED",
                        winner_id=loaded.winner_id,
                    )
                except Exception:
                    logger.exception("Failed to notify game_finished for game %s", room_id)
        elif loaded.current_turn_user_id is not None:
            next_player = next(
                (p for p in loaded.players if p.user_id == loaded.current_turn_user_id),
                None,
            )
            if next_player is not None and next_player.user is not None:
                try:
                    await notifier.notify_turn_started(
                        user_id=next_player.user_id,
                        ui_language=next_player.user.ui_language,
                        game_id=loaded.id,
                    )
                except Exception:
                    logger.exception("Failed to notify turn_started for game %s", room_id)

    return _to_game_detail(loaded, user.id)
