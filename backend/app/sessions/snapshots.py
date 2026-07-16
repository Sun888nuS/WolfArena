"""前端快照适配层。

本模块只负责把规则引擎真相状态和 LangGraph 运行状态转换成前端可读的
`GameSnapshotResponse`。它不推进游戏、不调用 LLM、不修改规则状态。
"""

from collections import Counter
from hashlib import sha1

from app.config import get_settings
from app.core.models import EventType, GameEvent, GameState, Phase, PlayerState, Role, Winner
from app.core.rules import alive_werewolves
from app.core.visibility import build_player_view
from app.sessions.models import (
    AssistantPanelItemResponse,
    AssistantPanelResponse,
    EventResponse,
    GameSnapshotResponse,
    GodStepResponse,
    HostCueResponse,
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
    next_node: str,
    graph_state: dict[str, object] | None = None,
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
    host_cue = _host_cue(
        state,
        game_id=game_id,
        pending_action=pending_action,
        speech_order=speech_order,
        speech_index=speech_index,
        vote_order=vote_order,
        vote_index=vote_index,
        last_node=last_node,
        next_node=next_node,
    )
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
        god_message=host_cue.message,
        host_cue=host_cue,
        god_steps=_god_steps(state, last_node=last_node),
        assistant_panel=_assistant_panel(
            state,
            human_player_id=human_player_id,
            graph_state=graph_state or {},
        ),
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


def _host_cue(
    state: GameState,
    *,
    game_id: str,
    pending_action: PendingActionResponse | None,
    speech_order: list[str],
    speech_index: int,
    vote_order: list[str],
    vote_index: int,
    last_node: str,
    next_node: str,
) -> HostCueResponse:
    """根据当前节点和阶段生成玩家可见的中央主持播报。"""
    if state.phase is Phase.GAME_OVER:
        return _cue(
            state,
            game_id,
            last_node,
            f"游戏结束，{_winner_label(state.winner)}获胜。",
            voice_key=_winner_voice_key(state.winner),
            hold_ms=1600,
        )
    if pending_action is not None:
        return _cue(
            state,
            game_id,
            last_node,
            _pending_action_message(pending_action),
            current_actor_id=pending_action.player_id,
            hold_ms=1200,
            blocks_auto_advance=False,
        )
    if last_node == "dawn_announcement":
        return _cue(
            state,
            game_id,
            last_node,
            _dawn_announcement_message(state),
            voice_key="dawn_peaceful_night" if not state.last_dead_player_ids else None,
            hold_ms=1800,
        )
    if last_node == "check_win_before_round":
        return _hidden_cue(state, game_id, last_node)
    if last_node == "night_start":
        return _cue(state, game_id, last_node, "天黑请闭眼。", voice_key="night_close_eyes", hold_ms=1000)
    if last_node == "wolf_team_entry":
        return _cue(
            state,
            game_id,
            last_node,
            "狼人请睁眼，请协商并选择今晚袭击目标。",
            voice_key="wolf_open_choose_target",
            hold_ms=1300,
        )
    if last_node == "wolf_collect_proposals":
        return _hidden_cue(state, game_id, last_node)
    if last_node == "wolf_consensus":
        if next_node == "wolf_reconcile":
            return _cue(state, game_id, last_node, "狼人请统一目标。", voice_key="wolf_unify_target", hold_ms=900)
        return _hidden_cue(state, game_id, last_node)
    if last_node == "wolf_reconcile":
        return _hidden_cue(state, game_id, last_node)
    if last_node == "wolf_commit_kill":
        return _cue(state, game_id, last_node, "狼人请闭眼。", voice_key="wolf_close_eyes", hold_ms=800)
    if last_node == "witch_action":
        follow_up = "女巫请闭眼。" if _living_role(state, Role.WITCH) is None or state.night_actions.witch_actor_id else None
        return _cue(
            state,
            game_id,
            last_node,
            "女巫请睁眼，请选择今晚是否使用药剂。",
            voice_key="witch_open_use_medicine",
            follow_up=follow_up,
            follow_up_voice_key="witch_close_eyes" if follow_up else None,
            voice_pause_ms=1500 if follow_up else 0,
            hold_ms=1500 if follow_up else 1000,
        )
    if last_node == "witch_commit_action":
        return _cue(state, game_id, last_node, "女巫请闭眼。", voice_key="witch_close_eyes", hold_ms=800)
    if last_node == "seer_action":
        follow_up = "预言家请闭眼。" if _living_role(state, Role.SEER) is None or state.night_actions.seer_target_id else None
        return _cue(
            state,
            game_id,
            last_node,
            "预言家请睁眼，请选择今晚要查验的玩家。",
            voice_key="seer_open_check_player",
            follow_up=follow_up,
            follow_up_voice_key="seer_close_eyes" if follow_up else None,
            voice_pause_ms=1500 if follow_up else 0,
            hold_ms=1500 if follow_up else 1000,
        )
    if last_node == "seer_commit_result":
        return _cue(state, game_id, last_node, "预言家请闭眼。", voice_key="seer_close_eyes", hold_ms=800)
    if last_node == "hunter_status":
        if state.round_no != 1:
            return _hidden_cue(state, game_id, last_node)
        return _cue(
            state,
            game_id,
            last_node,
            "猎人请睁眼，请确认你的身份。",
            voice_key="hunter_open_confirm_identity",
            follow_up="猎人请闭眼。",
            follow_up_voice_key="hunter_close_eyes",
            voice_pause_ms=1200,
            hold_ms=1500,
        )
    if last_node == "idiot_confirm":
        if state.round_no != 1:
            return _hidden_cue(state, game_id, last_node)
        return _cue(
            state,
            game_id,
            last_node,
            "白痴请睁眼，请确认你的身份。",
            voice_key="idiot_open_confirm_identity",
            follow_up="白痴请闭眼。",
            follow_up_voice_key="idiot_close_eyes",
            voice_pause_ms=1200,
            hold_ms=1500,
        )
    if last_node in {"resolve_night", "resolve_death_reactions", "check_win_after_night"}:
        return _hidden_cue(state, game_id, last_node)
    if last_node == "sheriff_election_start":
        return _cue(state, game_id, last_node, "警长竞选开始。", voice_key="sheriff_election_start", hold_ms=900)
    if last_node == "sheriff_candidate_collect":
        if next_node == "sheriff_speech_turn":
            return _cue(state, game_id, last_node, "警上玩家开始发言。", voice_key="sheriff_speech_start", hold_ms=900)
        if next_node == "day_speech_start" and state.sheriff_badge_lost:
            return _cue(state, game_id, last_node, "警徽流失，本局没有警长。", voice_key="sheriff_badge_lost", hold_ms=1400)
        return _hidden_cue(state, game_id, last_node)
    if last_node == "sheriff_speech_turn":
        actor = _current_order_player(state, speech_order, speech_index)
        if actor:
            return _cue(
                state,
                game_id,
                last_node,
                f"{_player_label(actor)}正在发言。",
                current_actor_id=actor.player_id,
                hold_ms=700,
            )
        return _hidden_cue(state, game_id, last_node)
    if last_node == "sheriff_vote_start":
        return _cue(state, game_id, last_node, "进入警长投票。", voice_key="sheriff_vote_start", hold_ms=900)
    if last_node == "sheriff_vote_turn":
        voter = _current_order_player(state, vote_order, vote_index)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(voter)}正在投票选择警长。" if voter else "玩家正在投票选择警长。",
            current_actor_id=voter.player_id if voter else None,
            hold_ms=700,
        )
    if last_node == "resolve_sheriff_vote":
        return _sheriff_vote_result_cue(state, game_id=game_id, last_node=last_node)
    if last_node == "sheriff_pk_speech":
        actor = _current_order_player(state, speech_order, speech_index)
        if actor:
            return _cue(
                state,
                game_id,
                last_node,
                f"{_player_label(actor)}正在进行警长 PK 发言。",
                current_actor_id=actor.player_id,
                hold_ms=700,
            )
        return _hidden_cue(state, game_id, last_node)
    if last_node == "sheriff_pk_vote_start":
        return _cue(state, game_id, last_node, "进入警长 PK 投票。", voice_key="sheriff_pk_vote_start", hold_ms=900)
    if last_node == "sheriff_pk_vote_turn":
        voter = _current_order_player(state, vote_order, vote_index)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(voter)}正在进行警长 PK 投票。" if voter else "玩家正在进行警长 PK 投票。",
            current_actor_id=voter.player_id if voter else None,
            hold_ms=700,
        )
    if last_node == "resolve_sheriff_pk_vote":
        return _sheriff_vote_result_cue(state, game_id=game_id, last_node=last_node)
    if last_node == "day_speech_start":
        return _cue(state, game_id, last_node, "白天开始，准备发言。", voice_key="day_speech_start", hold_ms=900)
    if last_node == "day_speech_summary":
        return _hidden_cue(state, game_id, last_node)
    if last_node == "day_vote_start":
        return _cue(state, game_id, last_node, "所有玩家发言结束，进入投票。", voice_key="day_vote_start", hold_ms=900)
    if last_node == "day_vote_turn":
        voter = _current_order_player(state, vote_order, vote_index)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(voter)}正在投票。" if voter else "玩家正在投票。",
            current_actor_id=voter.player_id if voter else None,
            hold_ms=700,
        )
    if last_node == "resolve_vote":
        return _exile_vote_result_cue(state, game_id=game_id, last_node=last_node)
    if last_node == "exile_pk_speech":
        actor = _current_order_player(state, speech_order, speech_index)
        if actor:
            return _cue(
                state,
                game_id,
                last_node,
                f"{_player_label(actor)}正在进行 PK 发言。",
                current_actor_id=actor.player_id,
                hold_ms=700,
            )
        return _hidden_cue(state, game_id, last_node)
    if last_node == "exile_pk_vote_start":
        return _cue(state, game_id, last_node, "进入放逐 PK 投票。", voice_key="exile_pk_vote_start", hold_ms=900)
    if last_node == "exile_pk_vote_turn":
        voter = _current_order_player(state, vote_order, vote_index)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(voter)}正在进行 PK 投票。" if voter else "玩家正在进行 PK 投票。",
            current_actor_id=voter.player_id if voter else None,
            hold_ms=700,
        )
    if last_node == "resolve_exile_pk_vote":
        return _exile_vote_result_cue(state, game_id=game_id, last_node=last_node)
    if last_node in {"resolve_exile_reactions", "public_vote_summary", "check_win_after_vote"}:
        return _hidden_cue(state, game_id, last_node)
    if last_node == "start_round":
        return _hidden_cue(state, game_id, last_node)
    if state.phase is Phase.DAY_SPEECH:
        actor = _current_order_player(state, speech_order, speech_index)
        if actor:
            return _cue(
                state,
                game_id,
                last_node,
                f"{_player_label(actor)}正在发言。",
                current_actor_id=actor.player_id,
                hold_ms=700,
            )
    if state.phase is Phase.DAY_VOTE:
        voter = _current_order_player(state, vote_order, vote_index)
        if voter:
            return _cue(
                state,
                game_id,
                last_node,
                f"{_player_label(voter)}正在投票。",
                current_actor_id=voter.player_id,
                hold_ms=700,
            )
    return _hidden_cue(state, game_id, last_node)


def _cue(
    state: GameState,
    game_id: str,
    last_node: str,
    message: str,
    *,
    voice_key: str | None = None,
    follow_up: str | None = None,
    follow_up_voice_key: str | None = None,
    voice_pause_ms: int = 0,
    hold_ms: int = 650,
    visible: bool = True,
    blocks_auto_advance: bool = True,
    current_actor_id: str | None = None,
) -> HostCueResponse:
    """创建一条中央主持播报。"""
    return HostCueResponse(
        cue_id=_cue_id(
            game_id=game_id,
            round_no=state.round_no,
            phase=state.phase.value,
            last_node=last_node,
            current_actor_id=current_actor_id,
            message=message,
            follow_up=follow_up,
        ),
        message=message,
        follow_up_message=follow_up,
        voice_key=voice_key,
        follow_up_voice_key=follow_up_voice_key,
        voice_pause_ms=voice_pause_ms,
        hold_ms=hold_ms,
        visible=visible,
        blocks_auto_advance=blocks_auto_advance,
    )


def _hidden_cue(state: GameState, game_id: str, last_node: str) -> HostCueResponse:
    """隐藏内部流程节点，让前端保留上一条玩家可见播报。"""
    return _cue(
        state,
        game_id,
        last_node,
        "",
        hold_ms=150,
        visible=False,
        blocks_auto_advance=False,
    )


def _sheriff_vote_result_cue(state: GameState, *, game_id: str, last_node: str) -> HostCueResponse:
    """生成警长投票结算后的玩家可见播报。"""
    if state.sheriff_id and state.sheriff_election_done and not state.sheriff_badge_lost:
        sheriff = _player_by_id_or_none(state, state.sheriff_id)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(sheriff)}当选警长。",
            current_actor_id=sheriff.player_id if sheriff else None,
            hold_ms=1400,
        )
    if state.sheriff_badge_lost:
        return _cue(state, game_id, last_node, "警徽流失，本局没有警长。", voice_key="sheriff_badge_lost", hold_ms=1400)
    if state.sheriff_tied_candidate_ids:
        return _cue(state, game_id, last_node, "警长投票平票，进入 PK 发言。", voice_key="sheriff_vote_tied_pk_speech", hold_ms=1100)
    return _cue(state, game_id, last_node, "警长投票结束。", voice_key="sheriff_vote_finished", hold_ms=900)


def _exile_vote_result_cue(state: GameState, *, game_id: str, last_node: str) -> HostCueResponse:
    """生成放逐投票结算后的玩家可见播报。"""
    latest_vote = state.vote_history[-1] if state.vote_history else None
    if state.last_exiled_player_id:
        exiled = _player_by_id_or_none(state, state.last_exiled_player_id)
        return _cue(
            state,
            game_id,
            last_node,
            f"{_player_label(exiled)}被放逐。",
            current_actor_id=exiled.player_id if exiled else None,
            hold_ms=1400,
        )
    if latest_vote and latest_vote.no_exile:
        return _cue(state, game_id, last_node, "今日无人出局。", voice_key="day_no_exile", hold_ms=1200)
    if latest_vote and latest_vote.tied_player_ids:
        return _cue(state, game_id, last_node, "放逐投票平票，进入 PK 发言。", voice_key="exile_pk_speech_start", hold_ms=1100)
    return _cue(state, game_id, last_node, "今日无人出局。", voice_key="day_no_exile", hold_ms=1200)


def _pending_action_message(pending_action: PendingActionResponse) -> str:
    """把真人待行动提示转换为系统主持播报。"""
    action_messages = {
        "werewolf_kill": "请选择今晚袭击目标。",
        "seer_check": "请选择今晚要查验的玩家。",
        "witch_action": "请选择今晚是否使用药剂。",
        "hunter_shot": "猎人发动技能，请选择是否开枪。",
        "idiot_reveal": "白痴请确认是否翻牌。",
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
        ("hunter", "猎人环节"),
        ("idiot", "白痴环节"),
        ("night_result", "天亮公布"),
        ("sheriff", "警长竞选"),
        ("speech", "公开发言"),
        ("summary", "发言整理"),
        ("vote", "投票放逐"),
        ("reaction", "出局技能"),
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


def _assistant_panel(
    state: GameState,
    *,
    human_player_id: str,
    graph_state: dict[str, object],
) -> AssistantPanelResponse:
    """Build the role-specific helper panel for the human player's legal view."""
    player = _player_by_id_or_none(state, human_player_id)
    if player is None:
        return AssistantPanelResponse(role="", title="游戏辅助", summary="开局后显示你的个人辅助信息。")
    if player.role is Role.WEREWOLF:
        return _werewolf_assistant_panel(state, graph_state)
    if player.role is Role.SEER:
        return _seer_assistant_panel(state, human_player_id)
    if player.role is Role.WITCH:
        return _witch_assistant_panel(state, human_player_id)
    if player.role is Role.HUNTER:
        return _hunter_assistant_panel(state, human_player_id)
    if player.role is Role.IDIOT:
        return _idiot_assistant_panel(player)
    return _villager_assistant_panel(player)


def _werewolf_assistant_panel(state: GameState, graph_state: dict[str, object]) -> AssistantPanelResponse:
    wolves = sorted((player for player in state.players if player.role is Role.WEREWOLF), key=lambda item: item.seat)
    nomination = _str_dict(graph_state.get("wolf_nomination_proposals"))
    current = _str_dict(graph_state.get("pending_wolf_proposals"))
    candidates = _str_list(graph_state.get("wolf_revote_candidates"))
    resolution = dict(graph_state.get("wolf_kill_resolution") or {})
    target_id = str(resolution.get("target_id") or state.night_actions.werewolf_target_id or "")
    items = [_panel_item("狼队成员", "、".join(_player_label(wolf) for wolf in wolves) or "暂无")]
    if nomination:
        items.append(_panel_item("第一轮建议", _format_proposals(state, nomination)))
        items.append(_panel_item("第一轮票型", _format_tally(state, nomination)))
    elif current:
        items.append(_panel_item("当前建议", _format_proposals(state, current)))
        items.append(_panel_item("当前票型", _format_tally(state, current)))
    else:
        items.append(_panel_item("当前建议", "等待狼队提交刀人建议", "muted"))
    if candidates:
        items.append(_panel_item("统一候选", "、".join(_player_name_by_id(state, target_id) for target_id in candidates), "warning"))
    if target_id:
        reason = _wolf_resolution_reason(str(resolution.get("reason") or "selected"))
        items.append(_panel_item("最终刀口", f"{_player_name_by_id(state, target_id)}（{reason}）", "bad"))
    return AssistantPanelResponse(
        role=Role.WEREWOLF.value,
        title="狼队协作",
        summary="只显示狼人阵营可见的夜晚刀人协作信息。",
        items=items,
    )


def _seer_assistant_panel(state: GameState, human_player_id: str) -> AssistantPanelResponse:
    items: list[AssistantPanelItemResponse] = []
    for event in state.events:
        if event.event_type is EventType.SEER_CHECKED and event.actor_id == human_player_id:
            target_id = str(event.payload.get("target_id") or "")
            alignment = str(event.payload.get("alignment") or "")
            value = f"{_player_name_by_id(state, target_id)}：{_alignment_label(alignment)}"
            items.append(_panel_item(f"第 {event.round_no} 夜", value, "bad" if alignment == "werewolves" else "good"))
    if not items:
        items.append(_panel_item("查验档案", "尚未留下查验结果", "muted"))
    return AssistantPanelResponse(role=Role.SEER.value, title="查验档案", summary="按夜晚整理你的查验对象和结果。", items=items)


def _witch_assistant_panel(state: GameState, human_player_id: str) -> AssistantPanelResponse:
    save_events = []
    poison_events = []
    for event in state.events:
        if event.event_type is EventType.WITCH_ACTED and event.actor_id == human_player_id:
            if event.payload.get("save"):
                save_events.append(event)
            if event.payload.get("poison_target_id"):
                poison_events.append(event)
    items = [
        _panel_item(
            "解药",
            _format_witch_save(state, save_events[-1]) if save_events else ("可用" if state.witch_state.has_antidote else "已使用"),
            "good" if state.witch_state.has_antidote else "muted",
        ),
        _panel_item(
            "毒药",
            _format_witch_poison(state, poison_events[-1]) if poison_events else ("可用" if state.witch_state.has_poison else "已使用"),
            "warning" if state.witch_state.has_poison else "muted",
        ),
    ]
    if state.phase is Phase.NIGHT and state.night_actions.werewolf_target_id and state.witch_state.has_antidote:
        items.append(_panel_item("今晚刀口", _player_name_by_id(state, state.night_actions.werewolf_target_id), "bad"))
    return AssistantPanelResponse(role=Role.WITCH.value, title="药剂记录", summary="只记录你的解药、毒药使用情况。", items=items)


def _hunter_assistant_panel(state: GameState, human_player_id: str) -> AssistantPanelResponse:
    player = _player_by_id_or_none(state, human_player_id)
    shot_event = next(
        (event for event in reversed(state.events) if event.event_type is EventType.HUNTER_SHOT and event.actor_id == human_player_id),
        None,
    )
    if shot_event:
        value = f"已开枪，带走 {_player_name_by_id(state, str(shot_event.payload.get('target_id') or ''))}"
        tone = "bad"
    elif state.hunter_shot_used:
        value = "已结算，未开枪"
        tone = "muted"
    elif player and not player.alive:
        value = f"已出局，死因：{_death_reason_label(player.dead_reason.value if player.dead_reason else '')}"
        tone = "muted"
    else:
        value = "技能未使用"
        tone = "good"
    return AssistantPanelResponse(
        role=Role.HUNTER.value,
        title="猎人技能",
        summary="记录你的猎枪是否已触发或使用。",
        items=[_panel_item("猎枪状态", value, tone)],
    )


def _idiot_assistant_panel(player: PlayerState) -> AssistantPanelResponse:
    items = [
        _panel_item("存活状态", "存活" if player.alive else "出局", "good" if player.alive else "bad"),
        _panel_item("翻牌状态", "已翻牌" if player.revealed_role else "未翻牌", "warning" if player.revealed_role else "muted"),
        _panel_item("投票权", "仍可投票" if player.can_vote else "已失去投票权", "good" if player.can_vote else "warning"),
    ]
    return AssistantPanelResponse(role=Role.IDIOT.value, title="白痴状态", summary="整理你的翻牌与投票权状态。", items=items)


def _villager_assistant_panel(player: PlayerState) -> AssistantPanelResponse:
    items = [
        _panel_item("存活状态", "存活" if player.alive else "出局", "good" if player.alive else "bad"),
        _panel_item("投票权", "仍可投票" if player.can_vote else "不可投票", "good" if player.can_vote else "warning"),
        _panel_item("发言状态", "可发言" if player.can_speak else "不可发言", "default" if player.can_speak else "muted"),
    ]
    return AssistantPanelResponse(role=Role.VILLAGER.value, title="村民状态", summary="你没有夜间技能，重点关注发言与投票。", items=items)


def _panel_item(label: str, value: str, tone: str = "default") -> AssistantPanelItemResponse:
    return AssistantPanelItemResponse(label=label, value=value) if tone == "default" else AssistantPanelItemResponse(label=label, value=value, tone=tone)  # type: ignore[arg-type]


def _str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if isinstance(key, str) and item}


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _format_proposals(state: GameState, proposals: dict[str, str]) -> str:
    actor_items = [
        f"{_player_name_by_id(state, actor_id)} → {_player_name_by_id(state, target_id)}"
        for actor_id, target_id in proposals.items()
        if not actor_id.startswith("_")
    ]
    return "；".join(actor_items) if actor_items else "暂无"


def _format_tally(state: GameState, proposals: dict[str, str]) -> str:
    counts = Counter(target_id for actor_id, target_id in proposals.items() if not actor_id.startswith("_"))
    if not counts:
        return "暂无票型"
    return "；".join(
        f"{_player_name_by_id(state, target_id)} {count} 票"
        for target_id, count in sorted(counts.items(), key=lambda item: (-item[1], _player_seat_by_id(state, item[0])))
    )


def _format_witch_save(state: GameState, event: GameEvent) -> str:
    target_id = str(event.payload.get("saved_player_id") or event.payload.get("attacked_player_id") or "")
    return f"第 {event.round_no} 夜救了 {_player_name_by_id(state, target_id)}"


def _format_witch_poison(state: GameState, event: GameEvent) -> str:
    target_id = str(event.payload.get("poison_target_id") or "")
    return f"第 {event.round_no} 夜毒了 {_player_name_by_id(state, target_id)}"


def _wolf_resolution_reason(reason: str) -> str:
    if reason == "consensus":
        return "全员一致"
    if reason == "majority":
        return "二轮多数票"
    if reason == "lead_wolf_tiebreak":
        return "二轮平票，按主刀狼人选择"
    if reason == "seat_tiebreak":
        return "二轮平票，按座位兜底"
    return "已确定"


def _alignment_label(alignment: str) -> str:
    if alignment == "werewolves":
        return "狼人阵营"
    if alignment == "villagers":
        return "好人阵营"
    return "未知"


def _death_reason_label(reason: str) -> str:
    if reason == "werewolf_kill":
        return "狼人袭击"
    if reason == "witch_poison":
        return "女巫毒杀"
    if reason == "exile":
        return "白天放逐"
    if reason == "hunter_shot":
        return "猎人开枪"
    if reason == "self_explode":
        return "狼人自爆"
    return "未知"


def _player_name_by_id(state: GameState, player_id: str | None) -> str:
    player = _player_by_id_or_none(state, player_id)
    return _player_label(player) if player else "未知玩家"


def _player_seat_by_id(state: GameState, player_id: str) -> int:
    player = _player_by_id_or_none(state, player_id)
    return player.seat if player else 999


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
    if last_node in {"sheriff_vote_start", "sheriff_vote_turn", "sheriff_pk_vote_start", "sheriff_pk_vote_turn"}:
        voter = _current_order_player(state, vote_order, vote_index)
        return voter.player_id if voter else None
    if last_node in {"day_vote_start", "day_vote_turn", "exile_pk_vote_start", "exile_pk_vote_turn"}:
        voter = _current_order_player(state, vote_order, vote_index)
        return voter.player_id if voter else None
    if last_node in {"sheriff_candidate_collect", "sheriff_speech_turn", "sheriff_pk_speech"}:
        actor = _current_order_player(state, speech_order, speech_index)
        return actor.player_id if actor else None
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


def _player_by_id_or_none(state: GameState, player_id: str | None) -> PlayerState | None:
    """根据 id 返回玩家；不存在时返回 None。"""
    if not player_id:
        return None
    return next((player for player in state.players if player.player_id == player_id), None)


def _player_label(player: PlayerState | None) -> str:
    """返回适合主持播报的座位称呼。"""
    if player is None:
        return "该玩家"
    return f"{player.seat} 号 {player.name}"


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


def _winner_voice_key(winner: Winner | None) -> str | None:
    """返回胜利阵营对应的固定语音 key。"""
    if winner is Winner.WEREWOLVES:
        return "werewolves_win"
    if winner is Winner.VILLAGERS:
        return "villagers_win"
    return None


def _cue_id(
    *,
    game_id: str,
    round_no: int,
    phase: str,
    last_node: str,
    current_actor_id: str | None,
    message: str,
    follow_up: str | None,
) -> str:
    """生成前端用于同步显示、语音和自动推进的稳定播报 id。"""
    text_hash = sha1(f"{message}|{follow_up or ''}".encode("utf-8")).hexdigest()[:8]
    actor = current_actor_id or "none"
    return f"{game_id}:{round_no}:{phase}:{last_node}:{actor}:{text_hash}"
