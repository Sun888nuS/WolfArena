"""多 Agent 狼人杀的记忆数据结构和归约函数。

本模块只负责记忆读写和压缩，不负责规则结算、流程推进或 LLM 调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.models import EventType, EventVisibility, GameEvent, GameState, Role
from app.core.player_labels import player_labels_by_id
from app.core.rules import alive_players


MAX_PUBLIC_EVENTS = 36
MAX_ROUND_SUMMARIES = 12
MAX_PRIVATE_NOTES = 8
MAX_WOLF_NOTES = 12
PUBLIC_MEMORY_EVENT_TYPES = {
    EventType.GAME_CREATED,
    EventType.NIGHT_STARTED,
    EventType.NIGHT_RESOLVED,
    EventType.DEATH_REACTION_RESOLVED,
    EventType.HUNTER_SHOT,
    EventType.IDIOT_REVEALED,
    EventType.SHERIFF_ELECTION_STARTED,
    EventType.SHERIFF_CANDIDATES_SET,
    EventType.SHERIFF_VOTE_RECORDED,
    EventType.SHERIFF_VOTE_RESOLVED,
    EventType.SHERIFF_ASSIGNED,
    EventType.SHERIFF_BADGE_LOST,
    EventType.SHERIFF_HANDED_OFF,
    EventType.WEREWOLF_SELF_EXPLODED,
    EventType.SPEECH_RECORDED,
    EventType.VOTE_RECORDED,
    EventType.VOTE_RESOLVED,
    EventType.PK_STARTED,
    EventType.NO_EXILE,
    EventType.WIN_CHECKED,
    EventType.NEXT_ROUND_STARTED,
    EventType.GAME_FORCED_FINISH,
}


@dataclass(slots=True)
class PublicMemory:
    """所有玩家都可以合法使用的公共记忆。"""

    event_log: list[dict[str, Any]] = field(default_factory=list)  # 公开事件摘要
    speech_log: list[dict[str, Any]] = field(default_factory=list)  # 公开发言记录
    vote_log: list[dict[str, Any]] = field(default_factory=list)  # 公开投票记录
    round_summaries: list[str] = field(default_factory=list)  # 轮次公共摘要
    death_log: list[dict[str, Any]] = field(default_factory=list)  # 死亡信息记录


@dataclass(slots=True)
class PrivateMemory:
    """非狼人特殊身份的个人私有记忆。"""

    notes: list[str] = field(default_factory=list)  # 私有备注
    suspicion_scores: dict[str, int] = field(default_factory=dict)  # 个人怀疑分


@dataclass(slots=True)
class WolfSharedMemory:
    """狼人阵营共享私有记忆。"""

    wolf_ids: list[str] = field(default_factory=list)  # 狼队成员 id
    kill_history: list[dict[str, Any]] = field(default_factory=list)  # 历史刀人目标
    current_proposals: dict[str, str] = field(default_factory=dict)  # 当前夜晚刀人提案
    current_proposal_labels: dict[str, str] = field(default_factory=dict)  # 当前夜晚刀人提案称呼
    strategy_notes: list[str] = field(default_factory=list)  # 狼队共享策略备注
    suspected_power_roles: dict[str, str] = field(default_factory=dict)  # 疑似神职判断


def initial_public_memory(state: GameState) -> dict[str, Any]:
    """根据开局事件创建 JSON 安全的公共记忆。"""
    memory = PublicMemory()
    for event in state.events:
        record_public_event_with_labels(memory, event, state)
    return public_memory_to_dict(memory)


def initial_private_memories(state: GameState) -> dict[str, dict[str, Any]]:
    """为非狼人玩家创建 JSON 安全的私有记忆容器。"""
    memories: dict[str, dict[str, Any]] = {}
    for player in state.players:
        if player.role is not Role.WEREWOLF:
            memories[player.player_id] = private_memory_to_dict(PrivateMemory())
    return memories


def initial_wolf_shared_memory(state: GameState) -> dict[str, Any]:
    """为狼队创建 JSON 安全的共享记忆容器。"""
    wolf_ids = sorted(player.player_id for player in state.players if player.role is Role.WEREWOLF)
    return wolf_memory_to_dict(WolfSharedMemory(wolf_ids=wolf_ids))


def public_memory_from_dict(data: dict[str, Any] | None) -> PublicMemory:
    """从 LangGraph 字典状态恢复公共记忆对象。"""
    data = data or {}
    return PublicMemory(
        event_log=[dict(item) for item in data.get("event_log", [])],
        speech_log=[dict(item) for item in data.get("speech_log", [])],
        vote_log=[dict(item) for item in data.get("vote_log", [])],
        round_summaries=[str(item) for item in data.get("round_summaries", [])],
        death_log=[dict(item) for item in data.get("death_log", [])],
    )


def public_memory_to_dict(memory: PublicMemory) -> dict[str, Any]:
    """把公共记忆对象转换为 JSON 安全的图状态。"""
    return {
        "event_log": memory.event_log[-MAX_PUBLIC_EVENTS:],
        "speech_log": memory.speech_log[-MAX_PUBLIC_EVENTS:],
        "vote_log": memory.vote_log[-MAX_PUBLIC_EVENTS:],
        "round_summaries": memory.round_summaries[-MAX_ROUND_SUMMARIES:],
        "death_log": memory.death_log[-MAX_PUBLIC_EVENTS:],
    }


def private_memory_from_dict(data: dict[str, Any] | None) -> PrivateMemory:
    """从 LangGraph 字典状态恢复单个私有记忆对象。"""
    data = data or {}
    return PrivateMemory(
        notes=[str(item) for item in data.get("notes", [])],
        suspicion_scores={
            str(player_id): max(0, min(100, int(score)))
            for player_id, score in dict(data.get("suspicion_scores", {})).items()
        },
    )


def private_memory_to_dict(memory: PrivateMemory) -> dict[str, Any]:
    """把单个私有记忆对象转换为 JSON 安全的图状态。"""
    return {
        "notes": memory.notes[-MAX_PRIVATE_NOTES:],
        "suspicion_scores": dict(sorted(memory.suspicion_scores.items())),
    }


def wolf_memory_from_dict(data: dict[str, Any] | None) -> WolfSharedMemory:
    """从 LangGraph 字典状态恢复狼队共享记忆对象。"""
    data = data or {}
    return WolfSharedMemory(
        wolf_ids=[str(item) for item in data.get("wolf_ids", [])],
        kill_history=[dict(item) for item in data.get("kill_history", [])],
        current_proposals={
            str(actor_id): str(target_id)
            for actor_id, target_id in dict(data.get("current_proposals", {})).items()
        },
        current_proposal_labels={
            str(actor_label): str(target_label)
            for actor_label, target_label in dict(data.get("current_proposal_labels", {})).items()
        },
        strategy_notes=[str(item) for item in data.get("strategy_notes", [])],
        suspected_power_roles={
            str(player_id): str(role_name)
            for player_id, role_name in dict(data.get("suspected_power_roles", {})).items()
        },
    )


def wolf_memory_to_dict(memory: WolfSharedMemory) -> dict[str, Any]:
    """把狼队共享记忆对象转换为 JSON 安全的图状态。"""
    return {
        "wolf_ids": list(memory.wolf_ids),
        "kill_history": memory.kill_history[-MAX_WOLF_NOTES:],
        "current_proposals": dict(sorted(memory.current_proposals.items())),
        "current_proposal_labels": dict(sorted(memory.current_proposal_labels.items())),
        "strategy_notes": memory.strategy_notes[-MAX_WOLF_NOTES:],
        "suspected_power_roles": dict(sorted(memory.suspected_power_roles.items())),
    }


def sync_new_public_events(state: GameState, public_memory: dict[str, Any], cursor: int) -> tuple[dict[str, Any], int]:
    """把规则引擎中新产生的事件同步进公共记忆。"""
    memory = public_memory_from_dict(public_memory)
    for event in state.events[cursor:]:
        record_public_event_with_labels(memory, event, state)
    return public_memory_to_dict(memory), len(state.events)


def record_public_event_with_labels(memory: PublicMemory, event: GameEvent, state: GameState) -> None:
    """把可公开沉淀的事件写入公共记忆，并补充玩家可读称呼。"""
    if event.visibility is not EventVisibility.PUBLIC:
        return
    if event.event_type not in PUBLIC_MEMORY_EVENT_TYPES:
        return
    labels_by_id = player_labels_by_id(state)
    payload = _public_event_payload(event)
    target_id = _event_target_id(payload)
    record = {
        "type": event.event_type.value,
        "round": event.round_no,
        "phase": event.phase.value,
        "actor": event.actor_id,
        "actor_label": labels_by_id.get(event.actor_id or "", event.actor_id),
        "payload": payload,
    }
    if target_id:
        record["target_label"] = labels_by_id.get(target_id, target_id)
    memory.event_log.append(record)
    if event.event_type is EventType.SPEECH_RECORDED:
        memory.speech_log.append(
            {
                "round": event.round_no,
                "actor": event.actor_id,
                "actor_label": labels_by_id.get(event.actor_id or "", event.actor_id),
                "speech": str(payload.get("speech", "")),
            }
        )
    elif event.event_type is EventType.VOTE_RECORDED:
        target_id = _optional_payload_str(payload, "target_id")
        memory.vote_log.append(
            {
                "round": event.round_no,
                "actor": event.actor_id,
                "actor_label": labels_by_id.get(event.actor_id or "", event.actor_id),
                "target": target_id,
                "target_label": labels_by_id.get(target_id or "", target_id),
                "public_reason": str(payload.get("public_reason", "")),
                "reasoning_score": payload.get("reasoning_score"),
            }
        )
    elif event.event_type is EventType.NIGHT_RESOLVED:
        dead_player_ids = [str(player_id) for player_id in payload.get("dead_player_ids", [])]
        memory.death_log.append(
            {
                "round": event.round_no,
                "dead_player_ids": dead_player_ids,
                "dead_player_labels": [
                    labels_by_id.get(player_id, player_id) for player_id in dead_player_ids
                ],
            }
        )


def summarize_current_speech_round(state: GameState, public_memory: dict[str, Any]) -> dict[str, Any]:
    """为当前白天发言生成确定性公共摘要。"""
    memory = public_memory_from_dict(public_memory)
    speeches = [
        item
        for item in memory.speech_log
        if int(item.get("round", 0)) == state.round_no
    ]
    if not speeches:
        return public_memory_to_dict(memory)

    alive_ids = {player.player_id for player in alive_players(state)}
    lines = []
    for item in speeches[-len(alive_ids):]:
        speech = str(item.get("speech", "")).strip()
        actor = str(item.get("actor_label") or item.get("actor", ""))
        if not speech:
            continue
        lines.append(f"{actor}: {speech[:80]}")
    summary = f"第 {state.round_no} 轮发言摘要：" + " | ".join(lines)
    if summary not in memory.round_summaries:
        memory.round_summaries.append(summary)
    return public_memory_to_dict(memory)


def add_private_note(
    memories: dict[str, dict[str, Any]],
    player_id: str,
    note: str,
    scores: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    """更新某个非狼人玩家的私有备注和怀疑分。"""
    if not note and not scores:
        return memories
    updated = {key: dict(value) for key, value in memories.items()}
    memory = private_memory_from_dict(updated.get(player_id))
    if note:
        memory.notes.append(note[:240])
    if scores:
        memory.suspicion_scores.update(
            {
                str(target_id): max(0, min(100, int(score)))
                for target_id, score in scores.items()
            }
        )
    updated[player_id] = private_memory_to_dict(memory)
    return updated


def add_wolf_strategy_note(wolf_memory: dict[str, Any], note: str) -> dict[str, Any]:
    """向狼队共享记忆追加一条策略备注。"""
    if not note:
        return wolf_memory
    memory = wolf_memory_from_dict(wolf_memory)
    memory.strategy_notes.append(note[:240])
    return wolf_memory_to_dict(memory)


def set_wolf_proposals(
    wolf_memory: dict[str, Any],
    proposals: dict[str, str],
    labels_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """替换狼队当前夜晚的刀人提案。"""
    memory = wolf_memory_from_dict(wolf_memory)
    memory.current_proposals = dict(sorted(proposals.items()))
    labels_by_id = labels_by_id or {}
    memory.current_proposal_labels = {
        labels_by_id.get(actor_id, actor_id): labels_by_id.get(target_id, target_id)
        for actor_id, target_id in sorted(proposals.items())
    }
    return wolf_memory_to_dict(memory)


def commit_wolf_kill(
    wolf_memory: dict[str, Any],
    *,
    round_no: int,
    target_id: str,
    target_label: str | None = None,
) -> dict[str, Any]:
    """把狼队最终刀人目标写入共享记忆历史。"""
    memory = wolf_memory_from_dict(wolf_memory)
    memory.kill_history.append(
        {
            "round": round_no,
            "target_id": target_id,
            "target_label": target_label or target_id,
        }
    )
    memory.current_proposals.clear()
    memory.current_proposal_labels.clear()
    return wolf_memory_to_dict(memory)


def _event_target_id(payload: dict[str, object]) -> str | None:
    """Return the most common target id field from a public event payload."""
    for key in ("target_id", "poison_target_id", "exiled_player_id"):
        value = _optional_payload_str(payload, key)
        if value:
            return value
    return None


def _public_event_payload(event: GameEvent) -> dict[str, object]:
    """Return the payload fields that may be shared through public memory."""
    if event.event_type is EventType.NIGHT_RESOLVED:
        return {"dead_player_ids": list(event.payload.get("dead_player_ids", []))}
    return dict(event.payload)


def _optional_payload_str(payload: dict[str, object], key: str) -> str | None:
    """Read an optional string from an event payload."""
    value = payload.get(key)
    return str(value) if value is not None else None
