"""确定性核心规则测试。"""

import pytest

from app.core.engine import WerewolfEngine
from app.core.exceptions import InvalidActionError
from app.core.models import Alignment, DeathReason, EventType, EventVisibility, Phase, Role, Winner
from app.core.rules import (
    MIN_ROLE_DECK,
    check_winner,
    create_standard_12_player_game_players,
    create_six_player_game_players,
    get_player,
    resolve_vote_records,
)
from app.core.visibility import build_player_view
from app.agents.graph import _day_speech_order


def test_standard_12_role_assignment_has_expected_deck() -> None:
    """12 人标准局应严格分配配置中的 12 张身份牌。"""
    players = create_standard_12_player_game_players(
        _names(),
        human_player_id="p1",
        seed=7,
    )

    assert len(players) == 12
    assert sorted(player.role.value for player in players) == sorted(
        role.value for role in MIN_ROLE_DECK
    )
    assert players[0].is_human is True


def test_standard_12_seats_are_shuffled_with_seed() -> None:
    """座位号应由后端洗牌生成，而不是固定等于玩家 id 顺序。"""
    players = create_six_player_game_players(
        _names(),
        human_player_id="p1",
        seed=7,
    )

    assert sorted(player.seat for player in players) == list(range(1, 13))
    assert [player.seat for player in players] != list(range(1, 13))


def test_role_assignment_is_dealt_by_randomized_seat() -> None:
    """身份应先随机分配给座位，再写回对应玩家。"""
    players = create_six_player_game_players(
        _names(),
        human_player_id="p1",
        seed=7,
    )

    roles_by_seat = {
        player.seat: player.role
        for player in players
    }

    assert sorted(roles_by_seat) == list(range(1, 13))
    assert sorted(role.value for role in roles_by_seat.values()) == sorted(
        role.value for role in MIN_ROLE_DECK
    )


def test_werewolf_kill_without_witch_save_kills_target() -> None:
    """女巫未救人时，狼人袭击目标应死亡。"""
    engine = _engine(seed=1)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    target_id = _first_non_role(engine, Role.WEREWOLF)

    engine.select_werewolf_kill(wolf_id, target_id)
    dead = engine.resolve_night()

    assert dead == (target_id,)
    assert get_player(engine.state, target_id).alive is False
    assert engine.state.phase in {Phase.DAY_SPEECH, Phase.GAME_OVER}


def test_witch_save_prevents_werewolf_kill() -> None:
    """女巫使用解药时应阻止狼人击杀。"""
    engine = _engine(seed=2)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    witch_id = _player_with_role(engine, Role.WITCH)
    target_id = _first_alive_not_in(engine, {wolf_id, witch_id})

    engine.select_werewolf_kill(wolf_id, target_id)
    engine.witch_action(witch_id, save=True)
    dead = engine.resolve_night()

    assert dead == ()
    assert get_player(engine.state, target_id).alive is True
    assert engine.state.witch_state.has_antidote is False


def test_witch_cannot_save_and_poison_same_night() -> None:
    """女巫同一晚不能同时使用解药和毒药。"""
    engine = _engine(seed=3)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    witch_id = _player_with_role(engine, Role.WITCH)
    kill_target = _first_alive_not_in(engine, {wolf_id, witch_id})
    poison_target = _first_alive_not_in(engine, {wolf_id, witch_id, kill_target})

    engine.select_werewolf_kill(wolf_id, kill_target)

    with pytest.raises(InvalidActionError):
        engine.witch_action(witch_id, save=True, poison_target_id=poison_target)


def test_witch_poison_kills_target() -> None:
    """女巫使用毒药时应毒死目标。"""
    engine = _engine(seed=3)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    witch_id = _player_with_role(engine, Role.WITCH)
    kill_target = _first_alive_not_in(engine, {wolf_id, witch_id})
    poison_target = _first_alive_not_in(engine, {wolf_id, witch_id, kill_target})

    engine.select_werewolf_kill(wolf_id, kill_target)
    engine.witch_action(witch_id, poison_target_id=poison_target)
    dead = engine.resolve_night()

    assert set(dead) == {kill_target, poison_target}
    assert get_player(engine.state, poison_target).alive is False
    assert engine.state.witch_state.has_poison is False


def test_witch_can_save_self_when_attacked() -> None:
    """女巫夜晚被狼人袭击时可以自救。"""
    engine = _engine(seed=13)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    witch_id = _player_with_role(engine, Role.WITCH)

    engine.select_werewolf_kill(wolf_id, witch_id)
    engine.witch_action(witch_id, save=True)
    dead = engine.resolve_night()

    assert dead == ()
    assert get_player(engine.state, witch_id).alive is True


def test_seer_gets_alignment_without_exact_role_leak() -> None:
    """预言家查验只应记录阵营，不泄露精确隐藏身份。"""
    engine = _engine(seed=4)
    seer_id = _player_with_role(engine, Role.SEER)
    target_id = _first_alive_not_in(engine, {seer_id})

    result = engine.seer_check(seer_id, target_id)

    assert result in {Alignment.VILLAGERS, Alignment.WEREWOLVES}
    assert engine.state.seer_results[seer_id][target_id] == result


def test_vote_tie_exiles_nobody() -> None:
    """平票时不应放逐任何玩家。"""
    result = resolve_vote_records({"p1": "p3", "p2": "p4", "p5": "p3", "p6": "p4"})

    assert result.exiled_player_id is None
    assert result.tied_player_ids == ("p3", "p4")


def test_single_top_vote_exiles_player() -> None:
    """唯一最高票目标应被放逐。"""
    engine = _engine(seed=5)
    engine.state.phase = Phase.DAY_VOTE
    alive_ids = [player.player_id for player in engine.state.players]
    target_id = alive_ids[0]
    voters = alive_ids[1:4]

    for voter_id in voters:
        engine.cast_vote(voter_id, target_id)
    result = engine.resolve_vote()

    assert result.exiled_player_id == target_id
    assert get_player(engine.state, target_id).alive is False


def test_winner_when_all_werewolves_dead() -> None:
    """所有狼人出局时好人阵营获胜。"""
    engine = _engine(seed=6)
    for player in engine.state.players:
        if player.role is Role.WEREWOLF:
            player.alive = False

    assert check_winner(engine.state) is Winner.VILLAGERS


def test_winner_when_common_villagers_are_all_dead() -> None:
    """所有普通村民出局时狼人阵营屠边获胜。"""
    engine = _engine(seed=8)
    for player in engine.state.players:
        if player.role is Role.VILLAGER:
            player.alive = False

    assert check_winner(engine.state) is Winner.WEREWOLVES


def test_winner_when_power_roles_are_all_dead() -> None:
    """所有神民出局时狼人阵营屠边获胜。"""
    engine = _engine(seed=14)
    for player in engine.state.players:
        if player.role.is_power_role:
            player.alive = False

    assert check_winner(engine.state) is Winner.WEREWOLVES


def test_invalid_werewolf_actor_is_rejected_without_state_mutation() -> None:
    """非狼人不能提交狼人击杀，且失败后不应污染夜晚状态。"""
    engine = _engine(seed=9)
    actor_id = _first_non_role(engine, Role.WEREWOLF)
    target_id = _player_with_role(engine, Role.WEREWOLF)

    with pytest.raises(InvalidActionError):
        engine.select_werewolf_kill(actor_id, target_id)

    assert engine.state.night_actions.werewolf_target_id is None


def test_werewolf_intents_select_kill_only_after_consensus() -> None:
    """所有存活狼人提交一致意向后才能确定击杀目标。"""
    engine = _engine(seed=1)
    wolves = _players_with_role(engine, Role.WEREWOLF)
    target_id = _first_non_role(engine, Role.WEREWOLF)

    first_result = engine.record_werewolf_kill_intent(wolves[0], target_id)
    second_result = engine.record_werewolf_kill_intent(wolves[1], target_id)
    third_result = engine.record_werewolf_kill_intent(wolves[2], target_id)
    fourth_result = engine.record_werewolf_kill_intent(wolves[3], target_id)

    assert first_result is None
    assert second_result is None
    assert third_result is None
    assert fourth_result == target_id
    assert engine.state.night_actions.werewolf_target_id == target_id
    assert engine.state.night_actions.werewolf_intents == {
        wolves[0]: target_id,
        wolves[1]: target_id,
        wolves[2]: target_id,
        wolves[3]: target_id,
    }
    assert engine.state.events[-1].event_type is EventType.WEREWOLF_KILL_SELECTED


def test_werewolf_intent_disagreement_requires_new_round() -> None:
    """狼人意向不一致时应清空本轮意向，并要求重新统一。"""
    engine = _engine(seed=2)
    wolves = _players_with_role(engine, Role.WEREWOLF)
    targets = _non_role_players(engine, Role.WEREWOLF)

    engine.record_werewolf_kill_intent(wolves[0], targets[0])
    engine.record_werewolf_kill_intent(wolves[1], targets[1])
    engine.record_werewolf_kill_intent(wolves[2], targets[0])
    result = engine.record_werewolf_kill_intent(wolves[3], targets[1])

    assert result is None
    assert engine.state.night_actions.werewolf_target_id is None
    assert engine.state.night_actions.werewolf_intents == {}
    assert engine.state.night_actions.werewolf_intent_round == 2
    assert engine.state.events[-1].event_type is EventType.WEREWOLF_CONSENSUS_REQUIRED


def test_player_view_does_not_leak_hidden_roles_to_villager() -> None:
    """村民视角不应暴露其他玩家隐藏身份。"""
    engine = _engine(seed=10)
    villager_id = _player_with_role(engine, Role.VILLAGER)

    view = build_player_view(engine.state, villager_id)

    assert view.own_role is Role.VILLAGER
    assert view.known_werewolves == ()
    assert all(not hasattr(player, "role") for player in view.players)
    assert all(player.label == f"{player.seat}号 {player.name}" for player in view.players)


def test_player_view_hides_wolf_intents_from_villager() -> None:
    """村民视角不应看到狼队共享记忆或狼人专属事件。"""
    engine = _engine(seed=3)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)
    villager_id = _player_with_role(engine, Role.VILLAGER)
    target_id = _first_non_role(engine, Role.WEREWOLF)

    engine.record_werewolf_kill_intent(wolf_id, target_id)
    view = build_player_view(
        engine.state,
        villager_id,
        wolf_shared_memory={"current_proposals": {wolf_id: target_id}},
    )

    assert view.wolf_shared_memory == {}
    assert all(
        event.event_type is not EventType.WEREWOLF_KILL_INTENT_RECORDED
        for event in view.events
    )


def test_werewolf_view_knows_wolf_team() -> None:
    """狼人视角应能看到狼队队友 id。"""
    engine = _engine(seed=11)
    wolf_id = _player_with_role(engine, Role.WEREWOLF)

    view = build_player_view(engine.state, wolf_id)

    assert len(view.known_werewolves) == 4
    assert wolf_id in view.known_werewolves


def test_hunter_shoots_after_exile_but_not_after_poison() -> None:
    """猎人被公投出局可开枪，被毒死不能开枪。"""
    engine = _engine(seed=15)
    hunter_id = _player_with_role(engine, Role.HUNTER)
    target_id = _first_alive_not_in(engine, {hunter_id})

    engine.state.phase = Phase.DAY_VOTE
    for voter in [player.player_id for player in engine.state.players if player.player_id != hunter_id][:5]:
        engine.cast_vote(voter, hunter_id)
    engine.resolve_vote()
    extra = engine.resolve_death_reactions(hunter_shot_target_id=target_id)

    assert extra == (target_id,)
    assert get_player(engine.state, target_id).alive is False

    poisoned = _engine(seed=16)
    wolf_id = _player_with_role(poisoned, Role.WEREWOLF)
    witch_id = _player_with_role(poisoned, Role.WITCH)
    hunter_id = _player_with_role(poisoned, Role.HUNTER)
    kill_target = _first_alive_not_in(poisoned, {wolf_id, witch_id, hunter_id})
    poisoned.select_werewolf_kill(wolf_id, kill_target)
    poisoned.witch_action(witch_id, poison_target_id=hunter_id)
    poisoned.resolve_night()
    assert poisoned.resolve_death_reactions(hunter_shot_target_id=None) == ()


def test_idiot_reveal_keeps_speech_without_vote() -> None:
    """白痴被公投后翻牌，继续发言但失去投票权。"""
    engine = _engine(seed=17)
    idiot_id = _player_with_role(engine, Role.IDIOT)
    engine.state.phase = Phase.DAY_VOTE
    for voter in [player.player_id for player in engine.state.players if player.player_id != idiot_id][:5]:
        engine.cast_vote(voter, idiot_id)
    engine.resolve_vote()
    engine.resolve_death_reactions(idiot_reveal=True)
    idiot = get_player(engine.state, idiot_id)

    assert idiot.alive is False
    assert idiot.can_speak is True
    assert idiot.can_vote is False
    assert idiot.revealed_role is True


def test_sheriff_vote_weight_is_one_and_half() -> None:
    """警长在放逐投票中拥有 1.5 票权。"""
    engine = _engine(seed=18)
    voters = [player.player_id for player in engine.state.players]
    sheriff_id = voters[0]
    target_a = voters[1]
    target_b = voters[2]
    engine.state.sheriff_id = sheriff_id
    engine.state.phase = Phase.DAY_VOTE

    engine.cast_vote(sheriff_id, target_a)
    engine.cast_vote(voters[3], target_b)
    result = engine.resolve_vote()

    assert result.tally[target_a] == 1.5
    assert result.exiled_player_id == target_a


def test_sheriff_assignment_returns_to_day_speech_and_blocks_new_election() -> None:
    """警长首日产生后，本局后续白天不应再次竞选。"""
    engine = _engine(seed=18)
    candidates = tuple(player.player_id for player in engine.state.players[:2])
    voter = engine.state.players[2].player_id

    engine.start_sheriff_election()
    engine.set_sheriff_candidates(candidates)
    engine.cast_sheriff_vote(voter, candidates[0])
    result = engine.resolve_sheriff_vote()
    engine.start_next_round()
    engine.resolve_night()
    engine.start_sheriff_election()

    assert result.exiled_player_id == candidates[0]
    assert engine.state.sheriff_id == candidates[0]
    assert engine.state.sheriff_election_done is True
    assert engine.state.phase is Phase.DAY_SPEECH


def test_sheriff_handoff_keeps_badge_after_sheriff_death() -> None:
    """警长出局后可以把警徽移交给一名存活玩家。"""
    engine = _engine(seed=19)
    sheriff_id = engine.state.players[0].player_id
    target_id = _first_alive_not_in(engine, {sheriff_id})
    engine.state.sheriff_id = sheriff_id

    engine._kill_player(sheriff_id, DeathReason.EXILE)
    engine.state.last_exiled_player_id = sheriff_id
    engine.resolve_death_reactions(sheriff_handoff_target_id=target_id)

    assert engine.state.sheriff_id == target_id
    assert engine.state.sheriff_badge_lost is False


def test_sheriff_election_self_explode_loses_badge_after_second_time() -> None:
    """警长竞选连续两次狼人自爆后，警徽应流失且本局不再竞选。"""
    engine = _engine(seed=20)
    wolves = _players_with_role(engine, Role.WEREWOLF)

    engine.start_sheriff_election()
    engine.werewolf_self_explode(wolves[0])

    assert engine.state.round_no == 2
    assert engine.state.phase is Phase.NIGHT
    assert engine.state.sheriff_election_done is False
    assert engine.state.sheriff_badge_lost is False
    assert engine.state.sheriff_election_self_explode_count == 1

    engine.resolve_night()
    engine.start_sheriff_election()

    assert engine.state.phase is Phase.SHERIFF_ELECTION
    assert engine.state.sheriff_election_done is False

    engine.start_sheriff_election()
    engine.werewolf_self_explode(wolves[1])

    assert engine.state.sheriff_election_done is True
    assert engine.state.sheriff_badge_lost is True
    assert engine.state.sheriff_id is None


def test_sheriff_speech_order_keeps_sheriff_last() -> None:
    """警长指定左右发言方向时，自己都应最后发言。"""
    engine = _engine(seed=21)
    sheriff = next(player for player in engine.state.players if player.seat == 6)
    engine.state.sheriff_id = sheriff.player_id

    clockwise = _day_speech_order(engine.state, direction="clockwise")
    counterclockwise = _day_speech_order(engine.state, direction="counterclockwise")

    assert clockwise[-1] == sheriff.player_id
    assert counterclockwise[-1] == sheriff.player_id
    assert clockwise != counterclockwise


def test_werewolf_view_sees_teammate_intents() -> None:
    """狼人视角应能读取共享狼队记忆用于协作。"""
    engine = _engine(seed=4)
    wolves = _players_with_role(engine, Role.WEREWOLF)
    target_id = _first_non_role(engine, Role.WEREWOLF)

    engine.record_werewolf_kill_intent(wolves[0], target_id)
    view = build_player_view(
        engine.state,
        wolves[1],
        wolf_shared_memory={"current_proposals": {wolves[0]: target_id}},
    )

    assert view.wolf_shared_memory["current_proposals"] == {wolves[0]: target_id}
    assert any(
        event.event_type is EventType.WEREWOLF_KILL_INTENT_RECORDED
        for event in view.events
    )


def test_private_events_are_visible_only_to_recipient() -> None:
    """私有身份事件只应对对应接收者可见。"""
    engine = _engine(seed=12)
    seer_id = _player_with_role(engine, Role.SEER)
    villager_id = _player_with_role(engine, Role.VILLAGER)

    seer_view = build_player_view(engine.state, seer_id)
    villager_view = build_player_view(engine.state, villager_id)
    seer_private = [
        event
        for event in seer_view.events
        if event.visibility is EventVisibility.PRIVATE
    ]
    villager_private = [
        event
        for event in villager_view.events
        if event.visibility is EventVisibility.PRIVATE
    ]

    assert all(seer_id in event.recipients for event in seer_private)
    assert all(villager_id in event.recipients for event in villager_private)


def _engine(*, seed: int) -> WerewolfEngine:
    """创建贴近产品形态的 12 人规则引擎。"""
    return WerewolfEngine(
        _names(),
        human_player_id="p1",
        seed=seed,
    )


def _names() -> list[str]:
    """返回 12 人标准局测试昵称。"""
    return [
        "Tester",
        "AI A",
        "AI B",
        "AI C",
        "AI D",
        "AI E",
        "AI F",
        "AI G",
        "AI H",
        "AI I",
        "AI J",
        "AI K",
    ]


def _player_with_role(engine: WerewolfEngine, role: Role) -> str:
    """返回第一个拥有指定身份的玩家 id。"""
    for player in engine.state.players:
        if player.role is role:
            return player.player_id
    raise AssertionError(f"Missing role: {role}")


def _players_with_role(engine: WerewolfEngine, role: Role) -> list[str]:
    """返回所有拥有指定身份的玩家 id。"""
    players = [
        player.player_id
        for player in engine.state.players
        if player.role is role
    ]
    if not players:
        raise AssertionError(f"Missing role: {role}")
    return players


def _non_role_players(engine: WerewolfEngine, role: Role) -> list[str]:
    """返回所有不是指定身份的玩家 id。"""
    players = [
        player.player_id
        for player in engine.state.players
        if player.role is not role
    ]
    if not players:
        raise AssertionError(f"Missing non-role: {role}")
    return players


def _first_non_role(engine: WerewolfEngine, role: Role) -> str:
    """返回第一个不是指定身份的玩家 id。"""
    for player in engine.state.players:
        if player.role is not role:
            return player.player_id
    raise AssertionError(f"Missing non-role: {role}")


def _first_alive_not_in(engine: WerewolfEngine, excluded: set[str]) -> str:
    """返回第一个存活且不在排除集合中的玩家 id。"""
    for player in engine.state.players:
        if player.alive and player.player_id not in excluded:
            return player.player_id
    raise AssertionError("Missing candidate")
