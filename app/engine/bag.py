import random
from typing import Optional

from app.core.constants import BLANK_TILE, RACK_SIZE
from app.engine.errors import EngineError
from app.engine.locales import get_language_pack


class TileBag:
    """Manages drawing, shuffling, and swapping tiles for a single game."""

    def __init__(self, tiles: list[str], rng: Optional[random.Random] = None) -> None:
        self._tiles = list(tiles)
        self._rng = rng or random.Random()

    @classmethod
    def create(cls, language_code: str, rng: Optional[random.Random] = None) -> "TileBag":
        pack = get_language_pack(language_code)
        tiles: list[str] = []
        for spec in pack.tiles:
            tiles.extend([spec.letter] * spec.count)
        tiles.extend([BLANK_TILE] * pack.blank_count)

        generator = rng or random.Random()
        generator.shuffle(tiles)
        return cls(tiles=tiles, rng=generator)

    @classmethod
    def from_list(cls, tiles: list[str], rng: Optional[random.Random] = None) -> "TileBag":
        return cls(tiles=tiles, rng=rng)

    @property
    def remaining(self) -> int:
        return len(self._tiles)

    @property
    def is_empty(self) -> bool:
        return len(self._tiles) == 0

    def to_list(self) -> list[str]:
        return list(self._tiles)

    def draw(self, count: int) -> list[str]:
        if count < 0:
            raise ValueError("count must be non-negative")
        draw_count = min(count, len(self._tiles))
        drawn = self._tiles[:draw_count]
        del self._tiles[:draw_count]
        return drawn

    def swap(
        self,
        tiles_to_return: list[str],
        min_bag_size: int = RACK_SIZE,
    ) -> list[str]:
        if not tiles_to_return:
            raise EngineError(
                error_code="INVALID_SWAP",
                message="At least one tile must be selected to swap",
            )
        if len(self._tiles) < min_bag_size or len(tiles_to_return) > len(self._tiles):
            raise EngineError(
                error_code="INSUFFICIENT_BAG_TILES",
                message="Not enough tiles remaining in the bag to swap",
                details={
                    "requested": len(tiles_to_return),
                    "remaining": len(self._tiles),
                    "minimum_required": min_bag_size,
                },
            )

        # Draw replacement tiles before returning old tiles so the player doesn't draw the same ones
        drawn = self.draw(len(tiles_to_return))
        self._tiles.extend(tiles_to_return)
        self._rng.shuffle(self._tiles)
        return drawn
