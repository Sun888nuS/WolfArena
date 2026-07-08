"""规则引擎事件写入工具。"""

from app.core.models import EventType, EventVisibility, GameEvent, GameState


def append_event(
    state: GameState,
    event_type: EventType,
    *,
    visibility: EventVisibility,
    payload: dict[str, object],
    actor_id: str | None = None,
    recipients: tuple[str, ...] = (),
) -> GameEvent:
    """向游戏事件流追加一条事件并返回该事件。"""
    event = GameEvent(
        event_type=event_type,
        round_no=state.round_no,
        phase=state.phase,
        visibility=visibility,
        payload=payload,
        actor_id=actor_id,
        recipients=recipients,
    )
    state.events.append(event)
    return event
