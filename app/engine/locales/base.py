import unicodedata
from dataclasses import dataclass, field

from app.core.constants import BLANK_TILE


@dataclass(frozen=True)
class TileSpec:
    letter: str
    count: int
    points: int


@dataclass(frozen=True)
class LanguagePack:
    code: str
    name: str
    tiles: tuple[TileSpec, ...]
    blank_count: int
    dictionary_filename: str
    upper_map: dict[str, str] = field(default_factory=dict)
    pre_replace: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        alphabet = frozenset(spec.letter for spec in self.tiles)
        points_map = {spec.letter: spec.points for spec in self.tiles}
        points_map[BLANK_TILE] = 0
        object.__setattr__(self, "_alphabet", alphabet)
        object.__setattr__(self, "_points_map", points_map)

    @property
    def alphabet(self) -> frozenset[str]:
        return self._alphabet  # type: ignore[attr-defined]

    @property
    def total_tile_count(self) -> int:
        return sum(spec.count for spec in self.tiles) + self.blank_count

    def normalize(self, text: str) -> str:
        """Locale-aware uppercase normalization (handles Turkish i->İ, ı->I and NFD/NFC)."""
        nfc = unicodedata.normalize("NFC", text.strip())
        for old, new in self.pre_replace:
            nfc = nfc.replace(old, new)
        if self.upper_map:
            mapped = "".join(self.upper_map.get(ch, ch) for ch in nfc)
        else:
            mapped = nfc
        return unicodedata.normalize("NFC", mapped.upper())

    def is_valid_letter(self, letter: str) -> bool:
        return self.normalize(letter) in self.alphabet

    def letter_points(self, letter: str) -> int:
        if letter == BLANK_TILE:
            return 0
        normalized = self.normalize(letter)
        points_map: dict[str, int] = self._points_map  # type: ignore[attr-defined]
        if normalized not in points_map:
            raise ValueError(f"Unsupported letter '{letter}' for language '{self.code}'")
        return points_map[normalized]
