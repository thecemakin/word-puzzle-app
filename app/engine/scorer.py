from dataclasses import dataclass
from typing import Optional

from app.core.constants import BINGO_BONUS, BONUS_BOARD, DL, DW, RACK_SIZE, START, TL, TW
from app.engine.board import ExtractedWord
from app.engine.locales import LanguagePack


@dataclass(frozen=True)
class WordScore:
    word: str
    score: int


@dataclass(frozen=True)
class MoveScoreResult:
    total_score: int
    word_scores: tuple[WordScore, ...]
    bingo_bonus: int


def calculate_move_score(
    extracted_words: list[ExtractedWord],
    new_positions: set[tuple[int, int]],
    language_pack: LanguagePack,
) -> MoveScoreResult:
    """Calculates move score applying board bonuses only to newly placed tiles."""
    word_scores: list[WordScore] = []
    total = 0

    for extracted in extracted_words:
        word_multiplier = 1
        word_sum = 0

        for row, col, cell in extracted.cells:
            letter_score = 0 if cell.is_blank else language_pack.letter_points(cell.letter)

            if (row, col) in new_positions:
                bonus = BONUS_BOARD[row][col]
                if bonus == DL:
                    letter_score *= 2
                elif bonus == TL:
                    letter_score *= 3
                elif bonus in (DW, START):
                    word_multiplier *= 2
                elif bonus == TW:
                    word_multiplier *= 3

            word_sum += letter_score

        final_word_score = word_sum * word_multiplier
        word_scores.append(WordScore(word=extracted.word, score=final_word_score))
        total += final_word_score

    bingo_bonus = BINGO_BONUS if len(new_positions) == RACK_SIZE else 0
    total += bingo_bonus

    return MoveScoreResult(
        total_score=total,
        word_scores=tuple(word_scores),
        bingo_bonus=bingo_bonus,
    )


def calculate_rack_value(rack: list[str], language_pack: LanguagePack) -> int:
    return sum(language_pack.letter_points(tile) for tile in rack)


def calculate_endgame_adjustments(
    player_racks: dict[str, list[str]],
    language_pack: LanguagePack,
    went_out_player: Optional[str] = None,
) -> dict[str, int]:
    """Computes endgame score deltas based on remaining rack tiles.

    - Every player with remaining tiles loses the sum of their unplayed tiles.
    - If a player emptied their rack (went_out_player), they gain the sum of all
      opponents' remaining tiles.
    """
    adjustments: dict[str, int] = {}
    opponents_remaining_total = 0

    for player_id, rack in player_racks.items():
        rack_val = calculate_rack_value(rack, language_pack)
        if player_id == went_out_player:
            adjustments[player_id] = 0
        else:
            adjustments[player_id] = -rack_val
            opponents_remaining_total += rack_val

    if went_out_player is not None and went_out_player in adjustments:
        adjustments[went_out_player] += opponents_remaining_total

    return adjustments
