"""前端快照适配层。

本模块只负责把规则引擎真相状态和 LangGraph 运行状态转换成前端可读的
`GameSnapshotResponse`。它不推进游戏、不调用 LLM、不修改规则状态。
"""

from app.config import get_settings
from app.core.models import GameEvent, GameState, Phase, PlayerState, Role, Winner
from app.core.rules import alive_werewolves
from app.core.visibility import build_player_view
from app.sessions.models import (
    EventResponse,
    GameSnapshotResponse,
    GodStepResponse,
    PendingActionResponse,
    PublicPlayerResponse,
)


def build_snapshot_response(
    state: GameState,
    *,
    game_id: str,
    human_player_id: str,
    pending_action: PendingActionResponse | None,
    public_memory: dict[str, object],
    private_memories: dict[str, dict[str, object]],
    wolf_shared_memory: dict[str, object],
    speech_order: list[str],
    speech_index: int,
    vote_order: list[str],
    vote_index: int,
    last_node: str,
) -> GameSnapshotResponse:
    """根据游戏状态和图状态构建真人玩家视角的前端快照。"""
    human_view = build_player_view(
        state,
        human_player_id,
        public_memory=public_memory,
        private_memories=private_memories,
        wolf_shared_memory=wolf_shared_memory,
    )
    reveal_all = state.phase is Phase.GAME_OVER
    players = [
        PublicPlayerResponse(
            player_id=player.player_id,
            name=player.name,
            seat=player.seat,
            alive=player.alive,
            is_human=player.is_human,
            role=player.role.value
            if reveal_all or player.player_id == human_player_id or player.revealed_role
            else None,
            alignment=player.alignment.value if reveal_all or player.player_id == human_player_id else None,
            can_vote=player.can_vote,
            can_speak=player.can_speak,
            revealed_role=player.revealed_role,
            dead_reason=player.dead_reason.value if player.dead_reason else None,
            has_sheriff_badge=player.player_id == state.sheriff_id and not state.sheriff_badge_lost,
        )
        for player in sorted(state.players, key=lambda item: item.seat)
    ]
    return GameSnapshotResponse(
        game_id=game_id,
        human_player_id=human_player_id,
        phase=state.phase.value,
        round_no=state.round_no,
        winner=state.winner.value if state.winner else None,
        players=players,
        events=[serialize_event(event) for event in human_view.events],
        review_events=[serialize_event(event) for event in state.events] if reveal_all else [],
        pending_action=pending_action,
        known_werewolves=list(human_view.known_werewolves),
        seer_results={target: alignment.value for target, alignment in human_view.seer_results.items()},
        llm_status=_llm_status(),
        god_message=_god_message(
            state,
            pending_action=pending_action,
            speech_order=speech_order,
            speech_index=speech_index,
            vote_order=vote_order,
            vote_index=vote_index,
            last_node=last_node,
        ),
        god_steps=_god_steps(state, last_node=last_node),
        current_actor_id=_current_actor_id(
            state,
            pending_action=pending_action,
            speech_order=speech_order,
            speech_index=speech_index,
            vote_order=vote_order,
            vote_index=vote_index,
            last_node=last_node,
        ),
        sheriff_id=state.sheriff_id,
        sheriff_badge_lost=state.sheriff_badge_lost,
        pk_tied_player_ids=list(state.pk_tied_player_ids),
    )


def serialize_event(event: GameEvent) -> EventResponse:
    """把领域事件转换成 API 响应事件。"""
    return EventResponse(
        type=event.event_type.value,
        round_no=event.round_no,
        phase=event.phase.value,
        actor_id=event.actor_id,
        visibility=event.visibility.value,
        payload=event.payload,
    )


def _llm_status() -> str:
    """返回适合前端展示的在线模型状态。"""
    settings = get_settings()
    if not settings.llm_api_key_configured:
        return "online agent not configured"
    return "online multi-agent"


def _god_message(
    state: GameState,
    *,
    pending_action: PendingActionResponse | None,
    speech_order: list[str],
    speech_index: int,
    vote_order: list[str],
    vote_index: int,
    last_node: str,
) -> str:
    """根据当前节点和阶段生成系统主持播报文案。"""
    if state.phase is Phase.GAME_OVER:
        return f"游戏结束，{_winner_label(state.winner)}获胜。"
    if pending_action is not None:
        return _pending_action_message(pending_action)
    if last_node == "dawn_announcement":
        return _dawn_announcement_message(state)
    node_messages = {
        "check_win_before_round": "上帝正在确认新一轮是否继续。",
        "night_start": "天黑请闭眼。",
        "wolf_team_entry": "狼人请睁眼，请确定你今晚要击杀的目标。",
        "wolf_collect_proposals": "狼人请睁眼，请确定你今晚要击杀的目标。",
        "wolf_consensus": "狼人请统一目标。",
        "wolf_reconcile": "狼人请统一目标。",
        "wolf_commit_kill": "狼人请闭眼。",
        "seer_action": "预言家请睁眼，请确认你今晚要查验的目标。",
        "seer_commit_result": "预言家请闭眼。",
        "witch_action": "女巫请睁眼，请选择今晚是否使用药剂。",
        "witch_commit_action": "女巫请闭眼。",
        "hunter_status": "猎人请睁眼，请确认你的技能状态。",
        "hunter_commit_status": "猎人请闭眼。",
        "idiot_confirm": "白痴请睁眼，请确认你的身份。",
        "idiot_commit_confirm": "白痴请闭眼。",
        "resolve_night": "上帝正在结算夜晚结果。",
        "resolve_death_reactions": "上帝正在处理死亡技能和警徽移交。",
        "check_win_after_night": "上帝正在检查夜晚后的胜负。",
        "sheriff_election_start": "进入警长竞选阶段。",
        "sheriff_candidate_collect": "玩家正在决定是否参与警长竞选。",
        "sheriff_speech_turn": "警上玩家正在发言。",
        "sheriff_vote_start": "进入警长投票。",
        "sheriff_vote_turn": "玩家正在投票选择警长。",
        "resolve_sheriff_vote": "上帝正在结算警长投票。",
        "sheriff_pk_speech": "警长竞选平票，进入 PK 发言。",
        "sheriff_pk_vote": "进入警长 PK 投票。",
        "resolve_sheriff_pk_vote": "上帝正在结算警长 PK 投票。",
        "sheriff_assigned": "警长已经产生。",
        "sheriff_badge_lost": "警徽流失，本局没有警长。",
        "day_speech_start": "白天开始，上帝正在安排发言顺序。",
        "day_speech_summary": "本轮公开发言已汇总进公共记忆。",
        "day_vote_start": "所有玩家发言结束，进入投票。",
        "exile_pk_speech": "放逐投票平票，进入 PK 发言。",
        "exile_pk_vote_start": "进入放逐 PK 投票。",
        "exile_pk_vote_turn": "玩家正在进行 PK 投票。",
        "resolve_exile_pk_vote": "上帝正在结算 PK 投票。",
        "resolve_exile_reactions": "上帝正在处理放逐后的技能。",
        "no_exile_today": "今日无人出局。",
        "resolve_vote": "上帝正在结算放逐投票。",
        "public_vote_summary": "投票结果已写入公共记忆。",
        "check_win_after_vote": "上帝正在检查投票后的胜负。",
        "start_round": "本轮结束，准备进入下一轮。",
    }
    if last_node in node_messages:
        return node_messages[last_node]
    if state.phase is Phase.DAY_SPEECH:
        actor = _current_order_player(state, speech_order, speech_index)
        if actor:
            return f"白天发言阶段，{actor.seat} 号 {actor.name} 正在发言。"
    if state.phase is Phase.DAY_VOTE:
        voter = _current_order_player(state, vote_order, vote_index)
        if voter:
            return f"投票阶段，{voter.seat} 号 {voter.name} 正在投票。"
    return "上帝正在推进多 Agent 狼人杀流程。"


def _pending_action_message(pending_action: PendingActionResponse) -> str:
    """把真人待行动提示转换为系统主持播报。"""
    action_messages = {
        "werewolf_kill": "狼人请睁眼，请确定你今晚要击杀的目标。",
        "seer_check": "预言家请睁眼，请确认你今晚要查验的目标。",
        "witch_action": "女巫请睁眼，请选择今晚是否使用药剂。",
        "hunter_shot": "猎人发动技能，请选择是否开枪。",
        "idiot_reveal": "白痴请确认是否翻牌。",
        "sheriff_run": "警长竞选开始，请决定是否上警。",
        "sheriff_vote": "请投票选择警长。",
        "sheriff_order": "警长请选择本轮发言顺序。",
        "sheriff_handoff": "警长请选择是否移交警徽。",
        "speak": "请开始发言。",
        "vote": "请投票选择放逐目标。",
    }
    return action_messages.get(pending_action.action_type, pending_action.prompt)


def _dawn_announcement_message(state: GameState) -> str:
    """根据夜晚结算死亡名单生成天亮播报。"""
    dead_players = [
        player
        for player in sorted(state.players, key=lambda item: item.seat)
        if player.player_id in state.last_dead_player_ids
    ]
    if not dead_players:
        return "天亮了，昨晚平安夜。"
    dead_labels = "、".join(f"{player.seat} 号" for player in dead_players)
    return f"天亮了，昨晚 {dead_labels}玩家死亡。"


def _god_steps(state: GameState, *, last_node: str) -> list[GodStepResponse]:
    """生成当前昼夜循环的流程进度条。"""
    if state.phase is Phase.GAME_OVER:
        return [GodStepResponse(key="game_over", label="公布胜负", status="active")]
    steps = [
        ("wolf_team", "狼队协作"),
        ("witch", "女巫用药"),
        ("seer", "预言家查验"),
        ("hunter", "猎人确认"),
        ("idiot", "白痴确认"),
        ("night_result", "夜晚结算"),
        ("sheriff", "警长竞选"),
        ("speech", "公开发言"),
        ("summary", "公共摘要"),
        ("vote", "投票放逐"),
        ("reaction", "技能结算"),
    ]
    active_key = _active_god_step_key(state, last_node=last_node)
    done_keys = _done_god_step_keys(state, last_node=last_node)
    return [
        GodStepResponse(
            key=key,
            label=label,
            status="active" if key == active_key else "done" if key in done_keys else "pending",
        )
        for key, label in steps
    ]


def _active_god_step_key(state: GameState, *, last_node: str) -> str:
    """根据最近执行节点推导当前高亮的流程步骤。"""
    if last_node in {"wolf_team_entry", "wolf_collect_proposals", "wolf_consensus", "wolf_reconcile", "wolf_commit_kill"}:
        return "wolf_team"
    if last_node in {"witch_action", "witch_commit_action"}:
        return "witch"
    if last_node in {"seer_action", "seer_commit_result"}:
        return "seer"
    if last_node in {"hunter_status", "hunter_commit_status"}:
        return "hunter"
    if last_node in {"idiot_confirm", "idiot_commit_confirm"}:
        return "idiot"
    if last_node in {"resolve_night", "dawn_announcement", "resolve_death_reactions", "check_win_after_night"}:
        return "night_result"
    if last_node.startswith("sheriff_") or state.phase is Phase.SHERIFF_ELECTION:
        return "sheriff"
    if last_node in {"day_speech_start", "day_speech_turn"} or state.phase is Phase.DAY_SPEECH:
        return "speech"
    if last_node == "day_speech_summary":
        return "summary"
    if state.phase in {Phase.DAY_VOTE, Phase.EXILE_PK_SPEECH, Phase.EXILE_PK_VOTE}:
        return "vote"
    if last_node in {"resolve_exile_reactions", "no_exile_today"}:
        return "reaction"
    return "wolf_team"


def _done_god_step_keys(state: GameState, *, last_node: str) -> set[str]:
    """返回当前循环中已经完成的流程步骤 key。"""
    order = ["wolf_team", "witch", "seer", "hunter", "idiot", "night_result", "sheriff", "speech", "summary", "vote", "reaction"]
    active = _active_god_step_key(state, last_node=last_node)
    try:
        index = order.index(active)
    except ValueError:
        return set()
    return set(order[:index])


def _current_actor_id(
    state: GameState,
    *,
    pending_action: PendingActionResponse | None,
    speech_order: list[str],
    speech_index: int,
    vote_order: list[str],
    vote_index: int,
    last_node: str,
) -> str | None:
    """返回前端桌面上需要高亮的当前行动玩家。"""
    if pending_action is not None and pending_action.action_type in {"speak", "vote", "sheriff_vote", "sheriff_run"}:
        return pending_action.player_id
    if state.phase in {Phase.DAY_SPEECH, Phase.EXILE_PK_SPEECH, Phase.SHERIFF_ELECTION}:
        actor = _current_order_player(state, speech_order, speech_index)
        return actor.player_id if actor else None
    if state.phase in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE}:
        voter = _current_order_player(state, vote_order, vote_index)
        return voter.player_id if voter else None
    return None


def _current_order_player(
    state: GameState,
    order: list[str],
    index: int,
) -> PlayerState | None:
    """从发言或投票顺序中取出当前行动玩家。"""
    if not order or index >= len(order):
        return None
    player_id = order[index]
    return next(player for player in state.players if player.player_id == player_id)


def _living_role(state: GameState, role: Role) -> str | None:
    """返回某个角色当前存活玩家的 id。"""
    for player in state.players:
        if player.role is role and player.alive:
            return player.player_id
    return None


def _next_werewolf_actor(state: GameState) -> str | None:
    """返回一个用于前端高亮的存活狼人 id。"""
    wolves = sorted(alive_werewolves(state), key=lambda player: player.seat)
    return wolves[0].player_id if wolves else None


def _winner_label(winner: Winner | None) -> str:
    """把胜利阵营枚举转换成中文标签。"""
    if winner is Winner.WEREWOLVES:
        return "狼人阵营"
    if winner is Winner.VILLAGERS:
        return "好人阵营"
    return "未知阵营"
