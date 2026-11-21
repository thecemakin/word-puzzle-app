from dataclasses import dataclass
from typing import Any, Optional

from app.core.constants import BOARD_SIZE, CENTER_POS
from app.engine.errors import EngineError
from app.engine.locales import LanguagePack


@dataclass(frozen=True)
class BoardCell:
    letter: str
    is_blank: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"letter": self.letter, "is_blank": self.is_blank}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoardCell":
        return cls(letter=str(data["letter"]), is_blank=bool(data.get("is_blank", False)))


@dataclass(frozen=True)
class TilePlacement:
    row: int
    col: int
    letter: str
    is_blank: bool = False


@dataclass(frozen=True)
class ExtractedWord:
    word: str
    direction: str  # "H" or "V"
    cells: tuple[tuple[int, int, BoardCell], ...]


class Board:
    """15x15 word game board handling placement validation and word extraction."""

    def __init__(self, grid: Optional[list[list[Optional[BoardCell]]]] = None) -> None:
        if grid is None:
            self._grid: list[list[Optional[BoardCell]]] = [
                [None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
            ]
        else:
            if len(grid) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in grid):
                raise ValueError(f"Board must be {BOARD_SIZE}x{BOARD_SIZE}")
            self._grid = [list(row) for row in grid]

    @classmethod
    def from_state(cls, state: Optional[list[list[Optional[dict[str, Any]]]]]) -> "Board":
        if not state:
            return cls()
        grid: list[list[Optional[BoardCell]]] = [
            [BoardCell.from_dict(cell) if cell is not None else None for cell in row]
            for row in state
        ]
        return cls(grid)

    def to_state(self) -> list[list[Optional[dict[str, Any]]]]:
        return [
            [cell.to_dict() if cell is not None else None for cell in row]
            for row in self._grid
        ]

    @staticmethod
    def in_bounds(row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def get(self, row: int, col: int) -> Optional[BoardCell]:
        return self._grid[row][col]

    def is_empty(self) -> bool:
        return all(cell is None for row in self._grid for cell in row)

    def copy(self) -> "Board":
        return Board(self._grid)

    def apply_placements(
        self,
        placements: list[TilePlacement],
        language_pack: LanguagePack,
    ) -> "Board":
        new_board = self.copy()
        for p in placements:
            normalized = language_pack.normalize(p.letter)
            new_board._grid[p.row][p.col] = BoardCell(letter=normalized, is_blank=p.is_blank)
        return new_board

    def validate_and_extract_words(
        self,
        placements: list[TilePlacement],
        language_pack: LanguagePack,
    ) -> list[ExtractedWord]:
        if not placements:
            raise EngineError(
                error_code="EMPTY_PLACEMENT",
                message="At least one tile must be placed on the board",
            )

        placed_map: dict[tuple[int, int], BoardCell] = {}
        for p in placements:
            if not self.in_bounds(p.row, p.col):
                raise EngineError(
                    error_code="OUT_OF_BOUNDS",
                    message=f"Coordinate ({p.row}, {p.col}) is outside the board",
                    details={"row": p.row, "col": p.col},
                )
            coord = (p.row, p.col)
            if coord in placed_map:
                raise EngineError(
                    error_code="DUPLICATE_COORDINATE",
                    message=f"Duplicate tile placement at ({p.row}, {p.col})",
                    details={"row": p.row, "col": p.col},
                )
            if self._grid[p.row][p.col] is not None:
                raise EngineError(
                    error_code="CELL_OCCUPIED",
                    message=f"Cell ({p.row}, {p.col}) is already occupied",
                    details={"row": p.row, "col": p.col},
                )
            normalized = language_pack.normalize(p.letter)
            if len(normalized) != 1 or normalized not in language_pack.alphabet:
                raise EngineError(
                    error_code="INVALID_LETTER",
                    message=f"Letter '{p.letter}' is not valid for language '{language_pack.code}'",
                    details={"letter": p.letter, "language": language_pack.code},
                )
            placed_map[coord] = BoardCell(letter=normalized, is_blank=p.is_blank)

        rows = {r for r, _ in placed_map}
        cols = {c for _, c in placed_map}
        same_row = len(rows) == 1
        same_col = len(cols) == 1
        if not (same_row or same_col):
            raise EngineError(
                error_code="NOT_ALIGNED",
                message="Placed tiles must lie on a single row or a single column",
            )

        board_was_empty = self.is_empty()
        if board_was_empty:
            if CENTER_POS not in placed_map:
                raise EngineError(
                    error_code="FIRST_MOVE_MUST_COVER_CENTER",
                    message="The first move must cover the center square (7, 7)",
                )
            if len(placed_map) < 2:
                raise EngineError(
                    error_code="WORD_TOO_SHORT",
                    message="The first word must contain at least 2 letters",
                )

        def cell_at(r: int, c: int) -> Optional[BoardCell]:
            if (r, c) in placed_map:
                return placed_map[(r, c)]
            return self._grid[r][c]

        # Check continuity along the placement axis (no gaps)
        if len(placed_map) > 1:
            if same_row:
                row = next(iter(rows))
                min_c, max_c = min(cols), max(cols)
                for c in range(min_c, max_c + 1):
                    if cell_at(row, c) is None:
                        raise EngineError(
                            error_code="GAP_IN_PLACEMENT",
                            message="Placed tiles cannot contain empty gaps",
                        )
            else:
                col = next(iter(cols))
                min_r, max_r = min(rows), max(rows)
                for r in range(min_r, max_r + 1):
                    if cell_at(r, col) is None:
                        raise EngineError(
                            error_code="GAP_IN_PLACEMENT",
                            message="Placed tiles cannot contain empty gaps",
                        )

        # Check connectivity to existing tiles (for subsequent moves)
        if not board_was_empty:
            if not self._touches_existing_tile(placed_map):
                raise EngineError(
                    error_code="NOT_CONNECTED",
                    message="New tiles must connect to at least one existing tile on the board",
                )

        extracted: list[ExtractedWord] = []

        if len(placed_map) == 1:
            r, c = next(iter(placed_map))
            h_word = self._extract_span(r, c, 0, 1, "H", cell_at)
            v_word = self._extract_span(r, c, 1, 0, "V", cell_at)
            if h_word is not None:
                extracted.append(h_word)
            if v_word is not None:
                extracted.append(v_word)
        elif same_row:
            anchor_r, anchor_c = next(iter(placed_map))
            main_word = self._extract_span(anchor_r, anchor_c, 0, 1, "H", cell_at)
            if main_word is not None:
                extracted.append(main_word)
            for r, c in sorted(placed_map):
                cross = self._extract_span(r, c, 1, 0, "V", cell_at)
                if cross is not None:
                    extracted.append(cross)
        else:
            anchor_r, anchor_c = next(iter(placed_map))
            main_word = self._extract_span(anchor_r, anchor_c, 1, 0, "V", cell_at)
            if main_word is not None:
                extracted.append(main_word)
            for r, c in sorted(placed_map):
                cross = self._extract_span(r, c, 0, 1, "H", cell_at)
                if cross is not None:
                    extracted.append(cross)

        if not extracted:
            raise EngineError(
                error_code="WORD_TOO_SHORT",
                message="Move must form at least one word of length 2 or more",
            )

        return extracted

    def _touches_existing_tile(self, placed_map: dict[tuple[int, int], BoardCell]) -> bool:
        for r, c in placed_map:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc) and self._grid[nr][nc] is not None:
                    return True
        return False

    def _extract_span(
        self,
        row: int,
        col: int,
        dr: int,
        dc: int,
        direction: str,
        cell_at,
    ) -> Optional[ExtractedWord]:
        r, c = row, col
        while self.in_bounds(r - dr, c - dc) and cell_at(r - dr, c - dc) is not None:
            r -= dr
            c -= dc

        cells: list[tuple[int, int, BoardCell]] = []
        while self.in_bounds(r, c):
            cell = cell_at(r, c)
            if cell is None:
                break
            cells.append((r, c, cell))
            r += dr
            c += dc

        if len(cells) < 2:
            return None

        word = "".join(cell.letter for _, _, cell in cells)
        return ExtractedWord(word=word, direction=direction, cells=tuple(cells))
