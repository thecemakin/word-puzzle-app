from typing import Optional

BOARD_SIZE = 15
CENTER_POS = (7, 7)
RACK_SIZE = 7
BINGO_BONUS = 50
BLANK_TILE = "*"

ALLOWED_TURN_DURATION_HOURS = (12, 24, 48, 72)
MAX_CONSECUTIVE_PASSES = 6

# Bonus cell codes
TW = "TW"  # Triple Word
DW = "DW"  # Double Word
TL = "TL"  # Triple Letter
DL = "DL"  # Double Letter
START = "START"  # Center square (also acts as Double Word on first move)


def _build_bonus_board() -> tuple[tuple[Optional[str], ...], ...]:
    grid: list[list[Optional[str]]] = [
        [None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
    ]

    triple_word = (
        (0, 0), (0, 7), (0, 14),
        (7, 0), (7, 14),
        (14, 0), (14, 7), (14, 14),
    )
    double_word = (
        (1, 1), (2, 2), (3, 3), (4, 4),
        (1, 13), (2, 12), (3, 11), (4, 10),
        (13, 1), (12, 2), (11, 3), (10, 4),
        (13, 13), (12, 12), (11, 11), (10, 10),
    )
    triple_letter = (
        (1, 5), (1, 9),
        (5, 1), (5, 5), (5, 9), (5, 13),
        (9, 1), (9, 5), (9, 9), (9, 13),
        (13, 5), (13, 9),
    )
    double_letter = (
        (0, 3), (0, 11),
        (2, 6), (2, 8),
        (3, 0), (3, 7), (3, 14),
        (6, 2), (6, 6), (6, 8), (6, 12),
        (7, 3), (7, 11),
        (8, 2), (8, 6), (8, 8), (8, 12),
        (11, 0), (11, 7), (11, 14),
        (12, 6), (12, 8),
        (14, 3), (14, 11),
    )

    for r, c in triple_word:
        grid[r][c] = TW
    for r, c in double_word:
        grid[r][c] = DW
    for r, c in triple_letter:
        grid[r][c] = TL
    for r, c in double_letter:
        grid[r][c] = DL

    center_r, center_c = CENTER_POS
    grid[center_r][center_c] = START

    return tuple(tuple(row) for row in grid)


BONUS_BOARD: tuple[tuple[Optional[str], ...], ...] = _build_bonus_board()
