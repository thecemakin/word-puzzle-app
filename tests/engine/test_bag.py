import random

import pytest

from app.core.constants import BLANK_TILE
from app.engine.bag import TileBag
from app.engine.errors import EngineError


def test_tile_bag_creation_and_deterministic_draw() -> None:
    bag1 = TileBag.create("tr", rng=random.Random(42))
    bag2 = TileBag.create("tr", rng=random.Random(42))
    assert bag1.remaining == 100
    assert bag1.to_list() == bag2.to_list()
    assert bag1.to_list().count(BLANK_TILE) == 2

    drawn = bag1.draw(7)
    assert len(drawn) == 7
    assert bag1.remaining == 93


def test_tile_bag_draw_more_than_remaining() -> None:
    bag = TileBag.from_list(["A", "B", "C"])
    drawn = bag.draw(7)
    assert drawn == ["A", "B", "C"]
    assert bag.remaining == 0
    assert bag.is_empty


def test_tile_bag_swap_draws_before_returning() -> None:
    bag = TileBag.from_list(["D", "E", "F", "G", "H", "I", "J"], rng=random.Random(7))
    drawn = bag.swap(["A", "B"])
    assert len(drawn) == 2
    assert set(drawn).isdisjoint({"A", "B"})
    assert bag.remaining == 7
    assert "A" in bag.to_list() and "B" in bag.to_list()


def test_tile_bag_swap_fails_when_too_few_tiles() -> None:
    bag = TileBag.from_list(["A", "B", "C", "D", "E", "F"])
    with pytest.raises(EngineError) as exc_info:
        bag.swap(["Z"])
    assert exc_info.value.error_code == "INSUFFICIENT_BAG_TILES"
    assert bag.remaining == 6  # unchanged


def test_tile_bag_swap_fails_on_empty_request() -> None:
    bag = TileBag.create("en", rng=random.Random(1))
    with pytest.raises(EngineError) as exc_info:
        bag.swap([])
    assert exc_info.value.error_code == "INVALID_SWAP"
