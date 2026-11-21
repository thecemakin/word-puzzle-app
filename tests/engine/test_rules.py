import random

import pytest

from app.core.constants import BLANK_TILE
from app.engine.bag import TileBag
from app.engine.board import Board, TilePlacement
from app.engine.dictionary import Dictionary
from app.engine.errors import EngineError
from app.engine.rules import check_game_over, evaluate_play_move, evaluate_swap_move


def test_evaluate_play_move_turkish_with_blank_and_lowercase() -> None:
    tr_dict = Dictionary.from_words("tr", ["İSTANBUL", "IŞIK", "İŞ", "İP"])
    board = Board()
    # Player has lowercase/blank tiles and plays "ışık" with blank for Ş
    rack = ["I", "*", "I", "K", "A", "E", "R"]
    placements = [
        TilePlacement(7, 6, "ı"),
        TilePlacement(7, 7, "ş", is_blank=True),
        TilePlacement(7, 8, "ı"),
        TilePlacement(7, 9, "k"),
    ]

    result = evaluate_play_move(board, rack, placements, "tr", tr_dict)

    assert [w.word for w in result.extracted_words] == ["IŞIK"]
    # TR points: I(2) + blank Ş(0) + I(2) + K(1) = 5; START at (7,7) is DW => 10
    assert result.score_result.total_score == 10
    assert result.remaining_rack == ["A", "E", "R"]
    assert result.board.get(7, 7) is not None
    assert result.board.get(7, 7).letter == "Ş"
    assert result.board.get(7, 7).is_blank is True


def test_evaluate_play_move_rejects_missing_rack_tiles() -> None:
    en_dict = Dictionary.from_words("en", ["QUIZ"])
    board = Board()
    rack = ["Q", "U", "I", "A", "E", "T", "R"]  # missing Z
    placements = [
        TilePlacement(7, 7, "Q"),
        TilePlacement(7, 8, "U"),
        TilePlacement(7, 9, "I"),
        TilePlacement(7, 10, "Z"),
    ]

    with pytest.raises(EngineError) as exc:
        evaluate_play_move(board, rack, placements, "en", en_dict)
    assert exc.value.error_code == "TILES_NOT_IN_RACK"
    assert exc.value.details["missing_tiles"] == ["Z"]


def test_evaluate_play_move_reports_all_invalid_words() -> None:
    en_dict = Dictionary.from_words("en", ["AT"])
    board = Board().apply_placements(
        [TilePlacement(7, 7, "A"), TilePlacement(7, 8, "T")],
        en_dict._language_pack,
    )
    # Place Z at (6,7) and X at (6,8) -> ZX, ZA, XT all invalid
    rack = ["Z", "X", "A", "E", "I", "O", "U"]
    placements = [TilePlacement(6, 7, "Z"), TilePlacement(6, 8, "X")]

    with pytest.raises(EngineError) as exc:
        evaluate_play_move(board, rack, placements, "en", en_dict)
    assert exc.value.error_code == "INVALID_WORD"
    assert set(exc.value.details["invalid_words"]) == {"ZX", "ZA", "XT"}


def test_evaluate_swap_move_and_immutability_on_error() -> None:
    bag = TileBag.create("tr", rng=random.Random(10))
    initial_bag_snapshot = bag.to_list()
    rack = ["A", "B", "C", "D", "E", "F", "G"]

    # Invalid swap (player doesn't hold Z) must not mutate bag
    with pytest.raises(EngineError) as exc:
        evaluate_swap_move(rack, ["Z"], bag, "tr")
    assert exc.value.error_code == "TILES_NOT_IN_RACK"
    assert bag.to_list() == initial_bag_snapshot

    # Valid swap
    swap_res = evaluate_swap_move(rack, ["A", "B"], bag, "tr")
    assert len(swap_res.new_rack) == 7
    assert len(swap_res.drawn_tiles) == 2
    assert swap_res.bag.remaining == 100
    assert bag.to_list() == initial_bag_snapshot  # original bag still untouched


def test_check_game_over_rack_emptied() -> None:
    # EN: p1 emptied rack; p2 has Q(10) + Z(10) + blank(0) = 20
    result = check_game_over(
        player_racks={"p1": [], "p2": ["Q", "Z", BLANK_TILE]},
        bag_remaining=0,
        consecutive_passes=0,
        language_code="en",
    )
    assert result.is_game_over is True
    assert result.reason == "RACK_EMPTIED"
    assert result.went_out_player == "p1"
    assert result.score_adjustments == {"p1": 20, "p2": -20}


def test_check_game_over_consecutive_passes() -> None:
    # TR: p1 has Ğ(8) + A(1) = 9, p2 has J(10) + blank(0) = 10
    result = check_game_over(
        player_racks={"p1": ["Ğ", "A"], "p2": ["J", BLANK_TILE]},
        bag_remaining=15,
        consecutive_passes=6,
        language_code="tr",
    )
    assert result.is_game_over is True
    assert result.reason == "CONSECUTIVE_PASSES"
    assert result.went_out_player is None
    assert result.score_adjustments == {"p1": -9, "p2": -10}


def test_check_game_over_not_finished_yet() -> None:
    result = check_game_over(
        player_racks={"p1": ["A"], "p2": ["B"]},
        bag_remaining=0,
        consecutive_passes=2,
        language_code="tr",
    )
    assert result.is_game_over is False
