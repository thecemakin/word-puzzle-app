from typing import Any

from app.models.game_player import GamePlayer


def build_public_players_payload(players: list[GamePlayer]) -> list[dict[str, Any]]:
    """Builds a public player summary list without leaking rack tiles."""
    return [
        {
            "user_id": str(gp.user_id),
            "username": gp.user.username if gp.user else "unknown",
            "seat_order": gp.seat_order,
            "score": gp.score,
            "rack_count": len(gp.rack),
        }
        for gp in sorted(players, key=lambda p: p.seat_order)
    ]
