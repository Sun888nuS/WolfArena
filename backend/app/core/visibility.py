"""玩家视角构建层。

本模块只负责信息隔离：把规则引擎的完整真相状态裁剪成某个玩家合法可见的
`PlayerView`。它不推进流程、不调用 LLM、不改变规则状态。
"""

from dataclasses import dataclass
from typing import Any

from app.core.models import (
    Alignment,
    EventVisibility,
    GameEvent,
    GameState,
    Phase,
    Role,
)
from app.core.player_labels import player_label
from app.core.rules import (
    get_player,
    legal_seer_targets,
    legal_sheriff_vote_targets,
    legal_vote_targets,
    legal_werewolf_targets,
    legal_witch_poison_targets,
)


@dataclass(frozen=True, slots=True)
class PublicPlayer:
    """所有玩家都可以看到的公开玩家信息。"""

    player_id: str  # 玩家 id
    name: str  # 昵称
    seat: int  # 座位号
    label: str  # AI 和记忆中使用的稳定称呼
    alive: bool  # 是否存活


@dataclass(frozen=True, slots=True)
class PlayerView:
    """单个玩家或阵营 Agent 合法可见的信息集合。"""

    player_id: str  # 当前视角所属玩家 id
    own_role: Role  # 当前玩家自己的真实角色
    phase: Phase  # 当前阶段
    round_no: int  # 当前轮次
    alive: bool  # 当前玩家是否存活
    players: tuple[PublicPlayer, ...]  # 公开玩家列表
    known_werewolves: tuple[str, ...]  # 狼人视角可见的狼队成员
    seer_results: dict[str, Alignment]  # 当前预言家已知查验结果
    public_memory: dict[str, Any]  # 所有人共享的公共记忆
    private_memory: dict[str, Any]  # 非狼人特殊身份的个人私有记忆
    wolf_shared_memory: dict[str, Any]  # 狼人专属共享记忆
    events: tuple[GameEvent, ...]  # 当前玩家可见事件
    legal_actions: tuple[str, ...]  # 当前阶段可执行动作名
    legal_targets: tuple[str, ...]  # 当前动作可选目标
    attacked_player_id: str | None  # 女巫可见的夜晚刀口
    can_save: bool  # 女巫当前是否可以救人
    can_poison: bool  # 女巫当前是否可以毒人


def build_player_view(
    state: GameState,
    player_id: str,
    *,
    public_memory: dict[str, Any] | None = None,
    private_memories: dict[str, dict[str, Any]] | None = None,
    wolf_shared_memory: dict[str, Any] | None = None,
) -> PlayerView:
    """构建某个玩家的合法视角，避免泄露隐藏身份和非法记忆。"""
    player = get_player(state, player_id)
    public_memory = public_memory or {}
    private_memories = private_memories or {}
    wolf_shared_memory = wolf_shared_memory or {}

    known_werewolves: tuple[str, ...] = ()
    private_memory: dict[str, Any] = {}
    visible_wolf_memory: dict[str, Any] = {}
    if player.role is Role.WEREWOLF:
        known_werewolves = tuple(
            sorted(
                other.player_id
                for other in state.players
                if other.role is Role.WEREWOLF
            )
        )  # 狼人视角可见的狼队成员id
        visible_wolf_memory = dict(wolf_shared_memory)
    else:
        private_memory = dict(private_memories.get(player_id, {}))

    legal_actions = _legal_actions_for_phase(state, player_id)
    legal_targets = _legal_targets_for_phase(state, player_id)
    attacked_player_id = (
        state.night_actions.werewolf_target_id
        if player.role is Role.WITCH and state.witch_state.has_antidote
        else None
    )
    can_save = (
        player.role is Role.WITCH
        and bool(attacked_player_id)
        and state.witch_state.has_antidote
    )
    can_poison = player.role is Role.WITCH and state.witch_state.has_poison

    return PlayerView(
        player_id=player.player_id,
        own_role=player.role,
        phase=state.phase,
        round_no=state.round_no,
        alive=player.alive,
        players=tuple(
            PublicPlayer(
                player_id=other.player_id,
                name=other.name,
                seat=other.seat,
                label=player_label(other),
                alive=other.alive,
            )
            for other in sorted(state.players, key=lambda item: item.seat)
        ),
        known_werewolves=known_werewolves,
        seer_results=dict(state.seer_results.get(player_id, {})),
        public_memory=dict(public_memory),
        private_memory=private_memory,
        wolf_shared_memory=visible_wolf_memory,
        events=tuple(_visible_events(state, player_id)),
        legal_actions=legal_actions,
        legal_targets=tuple(legal_targets),
        attacked_player_id=attacked_player_id,
        can_save=can_save,
        can_poison=can_poison,
    )


def _visible_events(state: GameState, player_id: str) -> list[GameEvent]:
    """返回某个玩家可以看到的原始事件。"""
    player = get_player(state, player_id)
    visible: list[GameEvent] = []
    for event in state.events:
        if event.visibility is EventVisibility.PUBLIC:
            visible.append(event)
        elif event.visibility is EventVisibility.PRIVATE and player_id in event.recipients:
            visible.append(event)
        elif (
            event.visibility is EventVisibility.WEREWOLVES
            and player.role is Role.WEREWOLF
        ):
            visible.append(event)
    return visible


def _legal_actions_for_phase(state: GameState, player_id: str) -> tuple[str, ...]:
    """根据当前阶段和身份返回玩家可执行的动作名。"""
    player = get_player(state, player_id)
    if state.phase is Phase.GAME_OVER:
        return ()

    if state.phase is Phase.NIGHT:
        if not player.alive:
            return ()
        actions: list[str] = []
        if player.role is Role.WEREWOLF:
            actions.append("werewolf_kill")
        if player.role is Role.SEER:
            actions.append("seer_check")
        if player.role is Role.WITCH:
            if state.witch_state.has_antidote:
                actions.append("witch_save")
            if state.witch_state.has_poison:
                actions.append("witch_poison")
        return tuple(actions)

    if state.phase is Phase.SHERIFF_ELECTION:
        if not state.sheriff_candidate_ids and player.alive and player.can_vote:
            return ("sheriff_run", "abstain")
        if player.player_id in state.sheriff_candidate_ids and player.can_speak:
            return ("speak",)
        if player.alive and player.can_vote:
            return ("sheriff_vote", "abstain")
        return ()

    if state.phase in {Phase.DAY_SPEECH, Phase.EXILE_PK_SPEECH} and player.can_speak:
        return ("speak",)
    if state.phase in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE} and player.alive and player.can_vote:
        return ("vote", "abstain")
    return ()


def _legal_targets_for_phase(state: GameState, player_id: str) -> list[str]:
    """根据当前阶段和身份返回玩家可选择的目标 id。"""
    player = get_player(state, player_id)
    if state.phase is Phase.GAME_OVER:
        return []
    if not player.alive and state.phase is not Phase.DAY_SPEECH:
        return []
    if state.phase is Phase.NIGHT and player.role is Role.WEREWOLF:
        return legal_werewolf_targets(state)
    if state.phase is Phase.NIGHT and player.role is Role.SEER:
        return legal_seer_targets(state, player_id)
    if state.phase is Phase.NIGHT and player.role is Role.WITCH:
        return legal_witch_poison_targets(
            state,
            player_id,
            killed_player_id=state.night_actions.werewolf_target_id,
        )  #问题点1：werewolf_target_id一定会死亡吗？答案是：不，女巫可以救人
       
    if state.phase is Phase.DAY_VOTE:
        return legal_vote_targets(state, player_id)
    if state.phase is Phase.EXILE_PK_VOTE:
        return legal_vote_targets(state, player_id, candidates=state.pk_tied_player_ids)
    if state.phase is Phase.SHERIFF_ELECTION:
        if not state.sheriff_candidate_ids:
            return []
        return legal_sheriff_vote_targets(state, player_id)
    return []
