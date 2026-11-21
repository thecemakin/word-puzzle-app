from dataclasses import dataclass
from typing import Optional

from app.core.constants import BLANK_TILE, MAX_CONSECUTIVE_PASSES, RACK_SIZE
from app.engine.bag import TileBag
from app.engine.board import Board, ExtractedWord, TilePlacement
from app.engine.dictionary import Dictionary
from app.engine.errors import EngineError
from app.engine.locales import LanguagePack, get_language_pack
from app.engine.scorer import (
    MoveScoreResult,
    calculate_endgame_adjustments,
    calculate_move_score,
)


@dataclass(frozen=True)
class PlayMoveEvaluation:
    board: Board
    remaining_rack: list[str]
    extracted_words: tuple[ExtractedWord, ...]
    score_result: MoveScoreResult
    normalized_placements: tuple[TilePlacement, ...]


@dataclass(frozen=True)
class SwapMoveEvaluation:
    new_rack: list[str]
    drawn_tiles: list[str]
    bag: TileBag


@dataclass(frozen=True)
class GameOverResult:
    is_game_over: bool
    reason: Optional[str] = None  # "RACK_EMPTIED" or "CONSECUTIVE_PASSES"
    went_out_player: Optional[str] = None
    score_adjustments: Optional[dict[str, int]] = None


def _consume_tiles_from_rack(
    rack: list[str],
    required_tiles: list[str],
    language_pack: LanguagePack,
) -> list[str]:
    available = [
        BLANK_TILE if tile == BLANK_TILE else language_pack.normalize(tile)
        for tile in rack
    ]
    missing: list[str] = []

    for needed in required_tiles:
        normalized = BLANK_TILE if needed == BLANK_TILE else language_pack.normalize(needed)
        if normalized in available:
            available.remove(normalized)
        else:
            missing.append(normalized)

    if missing:
        raise EngineError(
            error_code="TILES_NOT_IN_RACK",
            message="Player does not hold all tiles required for this move",
            details={"missing_tiles": missing},
        )
    return available


def evaluate_play_move(
    board: Board,
    rack: list[str],
    placements: list[TilePlacement],
    language_code: str,
    dictionary: Dictionary,
) -> PlayMoveEvaluation:
    """Validates a PLAY move end-to-end and returns the resulting board, rack, and score."""
    pack = get_language_pack(language_code)
    if dictionary.language_code != pack.code:
        raise EngineError(
            error_code="DICTIONARY_LANGUAGE_MISMATCH",
            message=(
                f"Dictionary language '{dictionary.language_code}' "
                f"does not match game language '{pack.code}'"
            ),
        )

    if not placements:
        raise EngineError(
            error_code="EMPTY_PLACEMENT",
            message="At least one tile must be placed on the board",
        )

    normalized_placements: list[TilePlacement] = []
    required_rack_tiles: list[str] = []

    for p in placements:
        normalized_letter = pack.normalize(p.letter)
        if len(normalized_letter) != 1 or normalized_letter not in pack.alphabet:
            raise EngineError(
                error_code="INVALID_LETTER",
                message=f"Letter '{p.letter}' is not valid for language '{pack.code}'",
                details={"letter": p.letter, "language": pack.code},
            )
        normalized_placements.append(
            TilePlacement(
                row=p.row,
                col=p.col,
                letter=normalized_letter,
                is_blank=p.is_blank,
            )
        )
        required_rack_tiles.append(BLANK_TILE if p.is_blank else normalized_letter)

    remaining_rack = _consume_tiles_from_rack(rack, required_rack_tiles, pack)

    extracted_words = board.validate_and_extract_words(normalized_placements, pack)

    invalid_words = [w.word for w in extracted_words if not dictionary.is_valid(w.word)]
    if invalid_words:
        raise EngineError(
            error_code="INVALID_WORD",
            message=f"Invalid word(s): {', '.join(invalid_words)}",
            details={"invalid_words": invalid_words},
        )

    new_positions = {(p.row, p.col) for p in normalized_placements}
    score_result = calculate_move_score(extracted_words, new_positions, pack)
    updated_board = board.apply_placements(normalized_placements, pack)

    return PlayMoveEvaluation(
        board=updated_board,
        remaining_rack=remaining_rack,
        extracted_words=tuple(extracted_words),
        score_result=score_result,
        normalized_placements=tuple(normalized_placements),
    )


def evaluate_swap_move(
    rack: list[str],
    tiles_to_swap: list[str],
    bag: TileBag,
    language_code: str,
    min_bag_size: int = RACK_SIZE,
) -> SwapMoveEvaluation:
    """Validates and performs a SWAP move, returning updated rack and bag."""
    pack = get_language_pack(language_code)
    if not tiles_to_swap:
        raise EngineError(
            error_code="INVALID_SWAP",
            message="At least one tile must be selected to swap",
        )

    normalized_swap = [
        BLANK_TILE if t == BLANK_TILE else pack.normalize(t) for t in tiles_to_swap
    ]
    remaining_rack = _consume_tiles_from_rack(rack, normalized_swap, pack)

    # Operate on a copy of the bag so errors leave the caller's bag untouched
    bag_copy = TileBag.from_list(bag.to_list(), rng=bag._rng)
    drawn = bag_copy.swap(normalized_swap, min_bag_size=min_bag_size)

    return SwapMoveEvaluation(
        new_rack=remaining_rack + drawn,
        drawn_tiles=drawn,
        bag=bag_copy,
    )


def check_game_over(
    player_racks: dict[str, list[str]],
    bag_remaining: int,
    consecutive_passes: int,
    language_code: str,
    max_consecutive_passes: int = MAX_CONSECUTIVE_PASSES,
) -> GameOverResult:
    """Checks standard end-of-game conditions and computes endgame score adjustments."""
    pack = get_language_pack(language_code)

    if bag_remaining == 0:
        for player_id, rack in player_racks.items():
            if len(rack) == 0:
                adjustments = calculate_endgame_adjustments(
                    player_racks=player_racks,
                    language_pack=pack,
                    went_out_player=player_id,
                )
                return GameOverResult(
                    is_game_over=True,
                    reason="RACK_EMPTIED",
                    went_out_player=player_id,
                    score_adjustments=adjustments,
                )

    if consecutive_passes >= max_consecutive_passes:
        adjustments = calculate_endgame_adjustments(
            player_racks=player_racks,
            language_pack=pack,
            went_out_player=None,
        )
        return GameOverResult(
            is_game_over=True,
            reason="CONSECUTIVE_PASSES",
            went_out_player=None,
            score_adjustments=adjustments,
        )

    return GameOverResult(is_game_over=False)
