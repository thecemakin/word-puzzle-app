import pytest

from app.core.constants import BINGO_BONUS
from app.engine.board import Board, TilePlacement
from app.engine.errors import EngineError
from app.engine.locales import EN_PACK, TR_PACK
from app.engine.scorer import calculate_move_score


def test_first_move_requires_center_and_min_two_letters() -> None:
    board = Board()

    with pytest.raises(EngineError) as exc:
        board.validate_and_extract_words(
            [TilePlacement(0, 0, "E"), TilePlacement(0, 1, "V")],
            TR_PACK,
        )
    assert exc.value.error_code == "FIRST_MOVE_MUST_COVER_CENTER"

    with pytest.raises(EngineError) as exc2:
        board.validate_and_extract_words([TilePlacement(7, 7, "E")], TR_PACK)
    assert exc2.value.error_code == "WORD_TOO_SHORT"


def test_invalid_placement_edge_cases() -> None:
    board = Board()

    with pytest.raises(EngineError) as exc_empty:
        board.validate_and_extract_words([], EN_PACK)
    assert exc_empty.value.error_code == "EMPTY_PLACEMENT"

    with pytest.raises(EngineError) as exc_oob:
        board.validate_and_extract_words([TilePlacement(15, 7, "A")], EN_PACK)
    assert exc_oob.value.error_code == "OUT_OF_BOUNDS"

    with pytest.raises(EngineError) as exc_dup:
        board.validate_and_extract_words(
            [TilePlacement(7, 7, "A"), TilePlacement(7, 7, "T")],
            EN_PACK,
        )
    assert exc_dup.value.error_code == "DUPLICATE_COORDINATE"

    with pytest.raises(EngineError) as exc_align:
        board.validate_and_extract_words(
            [TilePlacement(7, 7, "A"), TilePlacement(8, 8, "T")],
            EN_PACK,
        )
    assert exc_align.value.error_code == "NOT_ALIGNED"

    with pytest.raises(EngineError) as exc_gap:
        board.validate_and_extract_words(
            [TilePlacement(7, 7, "A"), TilePlacement(7, 9, "T")],
            EN_PACK,
        )
    assert exc_gap.value.error_code == "GAP_IN_PLACEMENT"


def test_first_move_start_double_word_and_no_bonus_reuse() -> None:
    # EN: C(3) + A(1) + T(1) = 5, START at (7,7) gives DW => 10
    board = Board()
    move1 = [
        TilePlacement(7, 6, "C"),
        TilePlacement(7, 7, "A"),
        TilePlacement(7, 8, "T"),
    ]
    words1 = board.validate_and_extract_words(move1, EN_PACK)
    assert [w.word for w in words1] == ["CAT"]
    score1 = calculate_move_score(words1, {(p.row, p.col) for p in move1}, EN_PACK)
    assert score1.total_score == 10
    assert score1.bingo_bonus == 0

    board = board.apply_placements(move1, EN_PACK)

    # Next move vertically through existing A at (7,7): B(3) at (6,7), A(1) at (7,7), T(1) at (8,7)
    # Neither (6,7) nor (8,7) is a bonus, and START at (7,7) must NOT be reused => 5
    move2 = [TilePlacement(6, 7, "B"), TilePlacement(8, 7, "T")]
    words2 = board.validate_and_extract_words(move2, EN_PACK)
    assert [w.word for w in words2] == ["BAT"]
    score2 = calculate_move_score(words2, {(p.row, p.col) for p in move2}, EN_PACK)
    assert score2.total_score == 5


def test_cross_words_single_tile_and_shared_bonus() -> None:
    # Place "AT" at (7,7)-(7,8)
    board = Board().apply_placements(
        [TilePlacement(7, 7, "A"), TilePlacement(7, 8, "T")],
        EN_PACK,
    )
    # Place "DO" vertically at (6,6)-(7,6) touching A at (7,7)? Wait: (6,6) is DL!
    # Put "O" at (6,7) and "N" at (6,8) -> horizontal "ON", vertical "OA" and "NT"
    # Let's use valid words: "TO" at (6,7)-(6,8) -> H: TO, V: TA (6,7)-(7,7), OT (6,8)-(7,8)
    # (6,8) is DL! O(1)*2 = 2 in BOTH "TO" and "OT"!
    move = [TilePlacement(6, 7, "T"), TilePlacement(6, 8, "O")]
    words = board.validate_and_extract_words(move, EN_PACK)
    assert {w.word for w in words} == {"TO", "TA", "OT"}

    score = calculate_move_score(words, {(6, 7), (6, 8)}, EN_PACK)
    # TO: T(1) + O(1*2 DL) = 3
    # TA: T(1) + A(1) = 2
    # OT: O(1*2 DL) + T(1) = 3
    assert score.total_score == 8

    # Now place a single tile at (8,7) to form vertical "TAT" (6,7)-(7,7)-(8,7)
    board = board.apply_placements(move, EN_PACK)
    single = [TilePlacement(8, 7, "T")]
    single_words = board.validate_and_extract_words(single, EN_PACK)
    assert [w.word for w in single_words] == ["TAT"]


def test_blank_tile_scores_zero_but_activates_word_multiplier() -> None:
    # Place blank 'Q' on (7,7) START (DW) + 'I' at (7,8):
    # Blank = 0, I = 1 -> (0 + 1) * 2 = 2
    board = Board()
    move = [
        TilePlacement(7, 7, "Q", is_blank=True),
        TilePlacement(7, 8, "I", is_blank=False),
    ]
    words = board.validate_and_extract_words(move, EN_PACK)
    score = calculate_move_score(words, {(7, 7), (7, 8)}, EN_PACK)
    assert score.total_score == 2


def test_seven_tile_bingo_bonus_and_dl_square() -> None:
    # 7 tiles across row 7 (cols 4..10): hits (7,7) START (DW); DL squares are at (7,3) & (7,11)
    # EN: P(3) L(1) A(1) Y(4) I(1) N(1) G(2) = 13; DW => 26; + 50 bingo => 76
    board = Board()
    word = "PLAYING"
    move = [TilePlacement(7, 4 + i, ch) for i, ch in enumerate(word)]
    words = board.validate_and_extract_words(move, EN_PACK)
    assert [w.word for w in words] == ["PLAYING"]
    score = calculate_move_score(words, {(p.row, p.col) for p in move}, EN_PACK)
    assert score.bingo_bonus == BINGO_BONUS
    assert score.total_score == 26 + BINGO_BONUS


def test_not_connected_and_occupied_errors() -> None:
    board = Board().apply_placements(
        [TilePlacement(7, 7, "E"), TilePlacement(7, 8, "V")],
        TR_PACK,
    )

    with pytest.raises(EngineError) as exc_conn:
        board.validate_and_extract_words(
            [TilePlacement(0, 0, "A"), TilePlacement(0, 1, "T")],
            TR_PACK,
        )
    assert exc_conn.value.error_code == "NOT_CONNECTED"

    with pytest.raises(EngineError) as exc_occ:
        board.validate_and_extract_words([TilePlacement(7, 7, "A")], TR_PACK)
    assert exc_occ.value.error_code == "CELL_OCCUPIED"


def test_board_state_serialization_roundtrip() -> None:
    board = Board().apply_placements(
        [
            TilePlacement(7, 7, "İ", is_blank=False),
            TilePlacement(7, 8, "Ş", is_blank=True),
        ],
        TR_PACK,
    )
    restored = Board.from_state(board.to_state())
    assert restored.get(7, 7) == board.get(7, 7)
    assert restored.get(7, 8) == board.get(7, 8)
    assert restored.get(0, 0) is None
