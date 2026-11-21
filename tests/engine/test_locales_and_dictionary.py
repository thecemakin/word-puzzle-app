from pathlib import Path

import pytest

from app.core.constants import BOARD_SIZE, BONUS_BOARD, CENTER_POS, DL, DW, START, TL, TW
from app.engine.dictionary import Dictionary, DictionaryManager
from app.engine.errors import EngineError
from app.engine.locales import (
    EN_PACK,
    TR_PACK,
    LanguagePack,
    TileSpec,
    get_language_pack,
    register_language,
)


def test_bonus_board_dimensions_and_four_way_symmetry() -> None:
    assert len(BONUS_BOARD) == BOARD_SIZE
    assert all(len(row) == BOARD_SIZE for row in BONUS_BOARD)
    assert BONUS_BOARD[CENTER_POS[0]][CENTER_POS[1]] == START

    counts = {TW: 0, DW: 0, TL: 0, DL: 0, START: 0}
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            cell = BONUS_BOARD[r][c]
            # Vertical, horizontal, and rotational symmetry
            assert BONUS_BOARD[r][BOARD_SIZE - 1 - c] == cell
            assert BONUS_BOARD[BOARD_SIZE - 1 - r][c] == cell
            assert BONUS_BOARD[BOARD_SIZE - 1 - r][BOARD_SIZE - 1 - c] == cell
            if cell is not None:
                counts[cell] += 1

    assert counts == {TW: 8, DW: 16, TL: 12, DL: 24, START: 1}


def test_language_pack_tile_totals() -> None:
    assert len(TR_PACK.alphabet) == 29
    assert TR_PACK.total_tile_count == 100
    assert TR_PACK.blank_count == 2

    assert len(EN_PACK.alphabet) == 26
    assert EN_PACK.total_tile_count == 100
    assert EN_PACK.blank_count == 2


def test_turkish_locale_aware_normalization() -> None:
    assert TR_PACK.normalize("istanbul") == "İSTANBUL"
    assert TR_PACK.normalize("ışık") == "IŞIK"
    assert TR_PACK.normalize("çiğdem") == "ÇİĞDEM"
    assert TR_PACK.normalize("şeker") == "ŞEKER"
    assert TR_PACK.normalize("öykü") == "ÖYKÜ"
    assert TR_PACK.normalize("güneş") == "GÜNEŞ"
    # Decomposed NFD dotted i/I and Python's "İ".lower() ("i\u0307") normalize cleanly to NFC İ
    assert TR_PACK.normalize("i\u0307z") == "İZ"
    assert TR_PACK.normalize("I\u0307STANBUL") == "İSTANBUL"
    assert TR_PACK.normalize("İSTANBUL".lower()) == "İSTANBUL"
    assert not TR_PACK.is_valid_letter("Q")
    assert not TR_PACK.is_valid_letter("W")
    assert not TR_PACK.is_valid_letter("X")


def test_english_normalization_and_validation() -> None:
    assert EN_PACK.normalize("  quiz ") == "QUIZ"
    assert EN_PACK.is_valid_letter("Q")
    assert not EN_PACK.is_valid_letter("Ğ")
    assert not EN_PACK.is_valid_letter("İ")


def test_unsupported_language_raises_engine_error() -> None:
    with pytest.raises(EngineError) as exc_info:
        get_language_pack("xx")
    assert exc_info.value.error_code == "UNSUPPORTED_LANGUAGE"


def test_register_custom_language_extensibility() -> None:
    custom = LanguagePack(
        code="testlang",
        name="Test",
        dictionary_filename="testlang.txt",
        blank_count=1,
        tiles=(TileSpec("A", 5, 1), TileSpec("B", 5, 2)),
    )
    register_language(custom)
    assert get_language_pack("testlang") is custom


def test_dictionary_from_words_and_turkish_lookup() -> None:
    tr_dict = Dictionary.from_words("tr", ["# comment", "", "istanbul", "ışık", "A", "invalid123"])
    assert "İSTANBUL" in tr_dict
    assert tr_dict.is_valid("istanbul")
    assert tr_dict.is_valid("IŞIK")
    assert not tr_dict.is_valid("isik")  # İSİK != IŞIK
    assert not tr_dict.is_valid("A")  # single char ignored
    assert len(tr_dict) == 2


def test_dictionary_manager_loads_starter_files() -> None:
    manager = DictionaryManager(Path("data/dictionaries"))
    manager.load_languages(["tr", "en"])
    assert set(manager.loaded_languages) == {"tr", "en"}
    assert manager.is_valid_word("tr", "istanbul")
    assert manager.is_valid_word("tr", "güneş")
    assert manager.is_valid_word("en", "puzzle")
    assert not manager.is_valid_word("en", "zzzzzz")
