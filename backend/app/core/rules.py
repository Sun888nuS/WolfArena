"""确定性狼人杀规则纯函数。

本模块不调用 LLM、不处理 Web 会话、不维护 LangGraph 状态，只负责合法性判断、
候选目标计算、投票结算和胜负判断。
"""

from collections import Counter
from random import Random

from app.core.exceptions import InvalidActionError
from app.core.models import (
    Alignment,
    GameState,
    Phase,
    PlayerState,
    Role,
    VoteResult,
    Winner,
)

STANDARD_12_ROLE_DECK: tuple[Role, ...] = (
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.WEREWOLF,
    Role.SEER,
    Role.WITCH,
    Role.HUNTER,
    Role.IDIOT,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.VILLAGER,
)

# Backward-compatible name used by older tests and scripts.
MIN_ROLE_DECK = STANDARD_12_ROLE_DECK


def create_standard_12_player_game_players(
    names: list[str],
    *,
    human_player_id: str | None = None,
    seed: int | None = None,
) -> list[PlayerState]:
    """创建 12 人标准局玩家，并根据 seed 洗牌身份和座位。"""
    return _create_players(
        names,
        role_deck=STANDARD_12_ROLE_DECK,
        human_player_id=human_player_id,
        seed=seed,
        expected_label="12 人标准局",
    )


def create_six_player_game_players(
    names: list[str],
    *,
    human_player_id: str | None = None,
    seed: int | None = None,
) -> list[PlayerState]:
    """兼容旧入口：现在创建 12 人标准局玩家。"""
    return create_standard_12_player_game_players(
        names,
        human_player_id=human_player_id,
        seed=seed,
    )


def get_player(state: GameState, player_id: str) -> PlayerState:
    """根据玩家 id 返回玩家状态，不存在时抛出规则异常。"""
    for player in state.players:
        if player.player_id == player_id:
            return player
    raise InvalidActionError(f"未知玩家：{player_id}")


def alive_players(state: GameState) -> list[PlayerState]:
    """返回所有仍然存活的玩家。"""
    return [player for player in state.players if player.alive]


def speaking_players(state: GameState) -> list[PlayerState]:
    """返回白天可发言的玩家，包含已翻牌白痴。"""
    return [player for player in state.players if player.can_speak]


def voting_players(state: GameState) -> list[PlayerState]:
    """返回当前有投票权的玩家。"""
    return [player for player in state.players if player.alive and player.can_vote]


def alive_player_ids(state: GameState) -> set[str]:
    """返回所有存活玩家 id。"""
    return {player.player_id for player in alive_players(state)}


def alive_werewolves(state: GameState) -> list[PlayerState]:
    """返回所有存活狼人。"""
    return [
        player
        for player in alive_players(state)
        if player.alignment is Alignment.WEREWOLVES
    ]


def alive_villagers(state: GameState) -> list[PlayerState]:
    """返回所有存活好人阵营玩家。"""
    return [
        player
        for player in alive_players(state)
        if player.alignment is Alignment.VILLAGERS
    ]


def alive_common_villagers(state: GameState) -> list[PlayerState]:
    """返回所有存活普通村民。"""
    return [
        player
        for player in alive_players(state)
        if player.role is Role.VILLAGER
    ]


def alive_power_villagers(state: GameState) -> list[PlayerState]:
    """返回所有存活神民。"""
    return [
        player
        for player in alive_players(state)
        if player.role.is_power_role
    ]


def find_role_player(state: GameState, role: Role) -> PlayerState | None:
    """返回指定角色的玩家；标准局中神职唯一。"""
    for player in state.players:
        if player.role is role:
            return player
    return None


def require_alive_player(state: GameState, player_id: str) -> PlayerState:
    """要求玩家存活，并返回该玩家状态。"""
    player = get_player(state, player_id)
    if not player.alive:
        raise InvalidActionError(f"玩家已出局：{player_id}")
    return player


def require_phase(state: GameState, phase: Phase) -> None:
    """要求游戏处于指定阶段。"""
    if state.phase is not phase:
        raise InvalidActionError(
            f"行动需要处于 {phase.value} 阶段，当前阶段是 {state.phase.value}。"
        )


def legal_werewolf_targets(state: GameState) -> list[str]:
    """返回狼人夜晚可以袭击的合法目标。"""
    return [
        player.player_id
        for player in alive_players(state)
        if player.role is not Role.WEREWOLF
    ]


def legal_seer_targets(state: GameState, seer_id: str) -> list[str]:
    """返回预言家可以查验的合法目标。"""
    require_alive_player(state, seer_id)
    return [
        player.player_id
        for player in alive_players(state)
        if player.player_id != seer_id
    ]


def legal_witch_poison_targets(
    state: GameState,
    witch_id: str,
    *,
    killed_player_id: str | None,
) -> list[str]:
    """返回女巫可以毒杀的合法目标。"""
    require_alive_player(state, witch_id)
    if not state.witch_state.has_poison:
        return []
    return [
        player.player_id
        for player in alive_players(state)
        if player.player_id != witch_id
    ]


def legal_vote_targets(
    state: GameState,
    voter_id: str,
    *,
    candidates: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """返回某个玩家白天可以投票的合法目标。"""
    voter = require_alive_player(state, voter_id)
    if not voter.can_vote:
        raise InvalidActionError(f"玩家没有投票权：{voter_id}")
    candidate_ids = set(candidates or [player.player_id for player in alive_players(state)])
    return [
        player.player_id
        for player in alive_players(state)
        if player.player_id != voter_id and player.player_id in candidate_ids
    ]


def legal_hunter_shot_targets(state: GameState, hunter_id: str) -> list[str]:
    """返回猎人可以开枪带走的目标。"""
    hunter = get_player(state, hunter_id)
    if hunter.role is not Role.HUNTER or state.hunter_shot_used:
        return []
    return [
        player.player_id
        for player in alive_players(state)
        if player.player_id != hunter_id
    ]


def legal_sheriff_candidates(state: GameState) -> list[str]:
    """返回可竞选警长的玩家。"""
    return [player.player_id for player in alive_players(state) if player.can_vote]


def legal_sheriff_vote_targets(state: GameState, voter_id: str) -> list[str]:
    """返回警长竞选投票可选目标。"""
    voter = require_alive_player(state, voter_id)
    if not voter.can_vote:
        return []
    return [
        candidate_id
        for candidate_id in state.sheriff_candidate_ids
        if candidate_id != voter_id and get_player(state, candidate_id).alive
    ]


def validate_werewolf_kill(
    state: GameState,
    *,
    actor_id: str,
    target_id: str,
) -> None:
    """校验狼人刀人行动是否合法。"""
    actor = require_alive_player(state, actor_id)
    if actor.role is not Role.WEREWOLF:
        raise InvalidActionError("只有存活狼人可以选择袭击目标。")
    if target_id not in legal_werewolf_targets(state):
        raise InvalidActionError(f"非法狼人袭击目标：{target_id}")


def validate_seer_check(
    state: GameState,
    *,
    actor_id: str,
    target_id: str,
) -> None:
    """校验预言家查验行动是否合法。"""
    actor = require_alive_player(state, actor_id)
    if actor.role is not Role.SEER:
        raise InvalidActionError("只有存活预言家可以查验玩家。")
    if target_id not in legal_seer_targets(state, actor_id):
        raise InvalidActionError(f"非法预言家查验目标：{target_id}")


def validate_witch_action(
    state: GameState,
    *,
    actor_id: str,
    save: bool,
    poison_target_id: str | None,
) -> None:
    """校验女巫救人和毒人行动是否合法。"""
    actor = require_alive_player(state, actor_id)
    if actor.role is not Role.WITCH:
        raise InvalidActionError("只有存活女巫可以用药。")

    killed_player_id = state.night_actions.werewolf_target_id
    if save and poison_target_id is not None:
        raise InvalidActionError("女巫同一晚不能同时使用解药和毒药。")
    if save and not state.witch_state.has_antidote:
        raise InvalidActionError("女巫解药已经用完。")
    if save and not killed_player_id:
        raise InvalidActionError("无人被袭击时女巫不能救人。")

    if poison_target_id is not None:
        legal_targets = legal_witch_poison_targets(
            state,
            actor_id,
            killed_player_id=killed_player_id,
        )
        if poison_target_id not in legal_targets:
            raise InvalidActionError(f"非法女巫毒药目标：{poison_target_id}")


def validate_vote(
    state: GameState,
    *,
    voter_id: str,
    target_id: str | None,
    candidates: tuple[str, ...] | list[str] | None = None,
) -> None:
    """校验白天投票是否合法。"""
    require_alive_player(state, voter_id)
    if not get_player(state, voter_id).can_vote:
        raise InvalidActionError("该玩家没有投票权。")
    if target_id is None:
        return
    if target_id not in legal_vote_targets(state, voter_id, candidates=candidates):
        raise InvalidActionError(f"非法投票目标：{target_id}")


def resolve_vote_records(
    votes: dict[str, str | None],
    *,
    weights: dict[str, float] | None = None,
    no_exile_on_tie: bool = False,
) -> VoteResult:
    """根据投票记录结算结果；默认平票只返回平票玩家。"""
    weights = weights or {}
    tally: dict[str, float] = {}
    for voter_id, target_id in votes.items():
        if target_id is None:
            continue
        tally[target_id] = tally.get(target_id, 0.0) + float(weights.get(voter_id, 1.0))
    if not tally:
        return VoteResult(tally={}, exiled_player_id=None, no_exile=True)

    highest = max(tally.values())
    tied = tuple(sorted(player_id for player_id, count in tally.items() if count == highest))
    if len(tied) > 1:
        return VoteResult(
            tally=tally,
            exiled_player_id=None,
            tied_player_ids=tied,
            no_exile=no_exile_on_tie,
        )
    return VoteResult(tally=tally, exiled_player_id=tied[0])


def check_winner(state: GameState) -> Winner | None:
    """检查标准 12 人局胜负条件，未满足时返回 None。"""
    if len(alive_werewolves(state)) == 0:
        return Winner.VILLAGERS
    if len(alive_common_villagers(state)) == 0:
        return Winner.WEREWOLVES
    if len(alive_power_villagers(state)) == 0:
        return Winner.WEREWOLVES
    return None


def _create_players(
    names: list[str],
    *,
    role_deck: tuple[Role, ...],
    human_player_id: str | None,
    seed: int | None,
    expected_label: str,
) -> list[PlayerState]:
    """创建玩家并把身份随机分配给随机座位。"""
    if len(names) != len(role_deck):
        raise InvalidActionError(f"{expected_label}需要恰好 {len(role_deck)} 个玩家昵称。")

    random = Random(seed)
    seats = list(range(1, len(role_deck) + 1))
    random.shuffle(seats)
    roles_by_seat: dict[int, Role] = {}
    role_pool = list(role_deck)
    for seat in sorted(seats):
        role_index = random.randrange(len(role_pool))
        roles_by_seat[seat] = role_pool.pop(role_index)

    players: list[PlayerState] = []
    for index, (name, seat) in enumerate(zip(names, seats, strict=True), start=1):
        player_id = f"p{index}"
        players.append(
            PlayerState(
                player_id=player_id,
                name=name,
                role=roles_by_seat[seat],
                seat=seat,
                is_human=player_id == human_player_id,
            ),
        )
    return players
