"""Stable player labels for AI prompts and public memory."""

from app.core.models import GameState, PlayerState


def player_label(player: PlayerState) -> str:
    """Return the human-readable label used in speeches and memory."""
    return f"{player.seat}号 {player.name}"


def player_label_by_id(state: GameState, player_id: str | None) -> str:
    """Return a player label by id, preserving unknown ids for debugging."""
    if not player_id:
        return "无"
    for player in state.players:
        if player.player_id == player_id:
            return player_label(player)
    return player_id


def player_labels_by_id(state: GameState) -> dict[str, str]:
    """Build a player_id -> label mapping for prompt and memory rendering."""
    return {player.player_id: player_label(player) for player in state.players}
