"""AI prompt and memory label rendering tests."""

import json

from app.agents.memory import (
    initial_public_memory,
    summarize_current_speech_round,
    sync_new_public_events,
)
from app.agents.prompts import build_decision_prompt
from app.core.engine import WerewolfEngine
from app.core.models import Phase, Role
from app.core.rules import get_player
from app.core.visibility import build_player_view


def test_prompt_exposes_ids_for_actions_and_labels_for_speech() -> None:
    """AI prompt should keep ids for structured actions while exposing stable labels."""
    engine = _engine(seed=7)
    actor_id = _player_with_role(engine, Role.VILLAGER)
    view = build_player_view(engine.state, actor_id)

    messages = build_decision_prompt(view, "测试人格", "进行白天公开发言")
    user_payload = json.loads(messages[1]["content"])
    visible_state = user_payload["visible_state"]
    actor = get_player(engine.state, actor_id)

    assert visible_state["self_id"] == actor_id
    assert visible_state["self_label"] == f"{actor.seat}号 {actor.name}"
    assert all("id" in player and "label" in player for player in visible_state["players"])
    assert all("id" in option and "label" in option for option in visible_state["legal_target_options"])
    assert "不要写 p1、p2" in messages[0]["content"]


def test_public_memory_summary_uses_player_labels_instead_of_raw_ids() -> None:
    """Speech summaries fed back to AI should not start with pX actor ids."""
    engine = _engine(seed=7)
    engine.state.phase = Phase.DAY_SPEECH
    actor_id = _player_with_role(engine, Role.VILLAGER)
    actor = get_player(engine.state, actor_id)
    memory = initial_public_memory(engine.state)
    cursor = len(engine.state.events)

    engine.record_speech(actor_id, "我先观察发言顺序。")
    memory, _ = sync_new_public_events(engine.state, memory, cursor)
    memory = summarize_current_speech_round(engine.state, memory)

    assert memory["speech_log"][-1]["actor"] == actor_id
    assert memory["speech_log"][-1]["actor_label"] == f"{actor.seat}号 {actor.name}"
    assert memory["round_summaries"][-1].startswith(
        f"第 {engine.state.round_no} 轮发言摘要：{actor.seat}号 {actor.name}:"
    )
    assert f"{actor_id}:" not in memory["round_summaries"][-1]


def test_public_memory_filters_private_and_werewolf_events() -> None:
    """公共记忆不应沉淀狼人、预言家和女巫的夜间真实目标。"""
    engine = _engine(seed=8)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    seer_id = _player_with_role(engine, Role.SEER)
    witch_id = _player_with_role(engine, Role.WITCH)
    kill_target = _first_alive_not_in(engine, {wolf_id, witch_id})
    seer_target = _first_alive_not_in(engine, {seer_id, kill_target})
    poison_target = _first_alive_not_in(engine, {wolf_id, witch_id, kill_target, seer_target})
    memory = initial_public_memory(engine.state)
    cursor = len(engine.state.events)

    engine.select_werewolf_kill(wolf_id, kill_target)
    engine.seer_check(seer_id, seer_target)
    engine.witch_action(witch_id, poison_target_id=poison_target)
    memory, _ = sync_new_public_events(engine.state, memory, cursor)

    event_types = {event["type"] for event in memory["event_log"]}
    assert "night.werewolf_kill_selected" not in event_types
    assert "night.werewolf_kill_intent_recorded" not in event_types
    assert "night.werewolf_consensus_required" not in event_types
    assert "night.seer_checked" not in event_types
    assert "night.witch_acted" not in event_types


def test_public_memory_night_resolved_hides_death_reasons() -> None:
    """天亮公开记忆只保留死亡名单，不泄露狼刀或女巫毒药原因。"""
    engine = _engine(seed=9)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    witch_id = _player_with_role(engine, Role.WITCH)
    kill_target = _first_alive_not_in(engine, {wolf_id, witch_id})
    poison_target = _first_alive_not_in(engine, {wolf_id, witch_id, kill_target})
    memory = initial_public_memory(engine.state)
    cursor = len(engine.state.events)

    engine.select_werewolf_kill(wolf_id, kill_target)
    engine.witch_action(witch_id, poison_target_id=poison_target)
    engine.resolve_night()
    memory, _ = sync_new_public_events(engine.state, memory, cursor)

    resolved = next(event for event in memory["event_log"] if event["type"] == "night.resolved")
    assert sorted(resolved["payload"]["dead_player_ids"]) == sorted([kill_target, poison_target])
    assert "death_reasons" not in resolved["payload"]
    assert memory["death_log"][-1]["dead_player_ids"] == resolved["payload"]["dead_player_ids"]
    assert "death_reasons" not in memory["death_log"][-1]


def _engine(*, seed: int) -> WerewolfEngine:
    """Create a deterministic 12-player game."""
    return WerewolfEngine(
        ["Tester", "青岚", "南枝", "白术", "云舒", "星河", "听雨", "墨川", "栖梧", "阿洛", "小满", "知夏"],
        human_player_id="p1",
        seed=seed,
    )


def _player_with_role(engine: WerewolfEngine, role: Role) -> str:
    """Return the first player id with a role."""
    for player in engine.state.players:
        if player.role is role:
            return player.player_id
    raise AssertionError(f"Missing role: {role}")


def _first_alive_not_in(engine: WerewolfEngine, excluded: set[str]) -> str:
    """Return the first living player outside the excluded ids."""
    for player in engine.state.players:
        if player.alive and player.player_id not in excluded:
            return player.player_id
    raise AssertionError("Missing candidate")
