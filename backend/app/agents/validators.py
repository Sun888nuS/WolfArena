"""AI 决策校验器。

本模块只负责把模型输出归一化为合法候选行动，不写记忆、不推进阶段、
不修改规则引擎状态。
"""

from app.agents.schemas import AgentDecision
from app.core.models import GameState, Phase, Role
from app.core.rules import (
    legal_seer_targets,
    legal_sheriff_vote_targets,
    legal_vote_targets,
    legal_werewolf_targets,
    legal_witch_poison_targets,
)


def validate_agent_decision(
    state: GameState,
    player_id: str,
    decision: AgentDecision,
) -> AgentDecision:
    """在执行前校验并归一化在线 Agent 的候选决策。"""
    if state.phase is Phase.NIGHT:
        validated = _validate_night_decision(state, player_id, decision)
    elif state.phase is Phase.SHERIFF_ELECTION:
        validated = _validate_sheriff_decision(state, player_id, decision)
    elif state.phase in {Phase.DAY_SPEECH, Phase.EXILE_PK_SPEECH}:
        validated = _validate_speech_decision(state, player_id, decision)
    elif state.phase in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE}:
        validated = _validate_vote_decision(state, player_id, decision)
    else:
        raise ValueError("Agent cannot act after the game is over.")

    return validated


def validate_sheriff_order_decision(
    decision: AgentDecision,
) -> AgentDecision:
    """校验警长选择白天发言方向的 AI 决策。"""
    if decision.action_type != "sheriff_order":
        raise ValueError("Sheriff must return a sheriff_order action.")
    if decision.direction not in {"clockwise", "counterclockwise"}:
        raise ValueError("Sheriff order must include clockwise or counterclockwise direction.")
    return AgentDecision(
        action_type="sheriff_order",
        direction=decision.direction,
        public_reason=decision.public_reason,
        thought_summary=decision.thought_summary,
        memory_note=decision.memory_note,
        confidence=decision.confidence,
    )


def validate_sheriff_handoff_decision(
    decision: AgentDecision,
    legal_targets: list[str],
) -> AgentDecision:
    """校验警长死亡后移交或撕毁警徽的 AI 决策。"""
    if decision.action_type == "abstain":
        return AgentDecision(
            action_type="sheriff_handoff",
            target_id=None,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(legal_targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )
    if decision.action_type != "sheriff_handoff":
        raise ValueError("Sheriff handoff must return a sheriff_handoff or abstain action.")
    if decision.target_id not in legal_targets:
        raise ValueError("Sheriff handoff returned an illegal target.")
    return AgentDecision(
        action_type="sheriff_handoff",
        target_id=decision.target_id,
        public_reason=decision.public_reason,
        thought_summary=decision.thought_summary,
        memory_note=decision.memory_note,
        suspicion_scores=_legal_scores(legal_targets, decision.suspicion_scores),
        confidence=decision.confidence,
    )


def validate_hunter_reaction_decision(
    decision: AgentDecision,
    legal_targets: list[str],
) -> AgentDecision:
    """Validate a hunter death-reaction decision."""
    if decision.action_type == "abstain":
        return AgentDecision(
            action_type="hunter_shot",
            target_id=None,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(legal_targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )
    if decision.action_type != "hunter_shot":
        raise ValueError("Hunter reaction must return hunter_shot or abstain.")
    if decision.target_id is None:
        return AgentDecision(
            action_type="hunter_shot",
            target_id=None,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(legal_targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )
    if decision.target_id not in legal_targets:
        raise ValueError("Hunter reaction returned an illegal target.")
    return AgentDecision(
        action_type="hunter_shot",
        target_id=decision.target_id,
        public_reason=decision.public_reason,
        thought_summary=decision.thought_summary,
        memory_note=decision.memory_note,
        suspicion_scores=_legal_scores(legal_targets, decision.suspicion_scores),
        confidence=decision.confidence,
    )


def _validate_night_decision(
    state: GameState,
    player_id: str,
    decision: AgentDecision,
) -> AgentDecision:
    """根据行动者夜间身份校验夜晚决策。"""
    player = _player_role(state, player_id)
    if player is Role.WEREWOLF:
        targets = legal_werewolf_targets(state)
        if decision.action_type not in {"werewolf_kill", "werewolf_kill_intent"}:
            raise ValueError("Werewolf agent must return a kill intent.")
        if decision.target_id not in targets:
            raise ValueError("Werewolf agent returned an illegal target.")
        return AgentDecision(
            action_type="werewolf_kill_intent",
            target_id=decision.target_id,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )

    if player is Role.SEER:
        targets = legal_seer_targets(state, player_id)
        if decision.action_type != "seer_check":
            raise ValueError("Seer agent must return a seer_check action.")
        if decision.target_id not in targets:
            raise ValueError("Seer agent returned an illegal target.")
        return AgentDecision(
            action_type="seer_check",
            target_id=decision.target_id,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )

    if player is Role.WITCH:
        if decision.action_type != "witch_action":
            raise ValueError("Witch agent must return a witch_action action.")
        killed = state.night_actions.werewolf_target_id
        poison_targets = legal_witch_poison_targets(
            state,
            player_id,
            killed_player_id=killed,
        )
        if decision.save and (not killed or not state.witch_state.has_antidote):
            raise ValueError("Witch agent returned an illegal save action.")
        if decision.save and decision.poison_target_id is not None:
            raise ValueError("Witch agent cannot save and poison in the same night.")
        if decision.poison_target_id is not None and decision.poison_target_id not in poison_targets:
            raise ValueError("Witch agent returned an illegal poison target.")
        return AgentDecision(
            action_type="witch_action",
            save=decision.save,
            poison_target_id=decision.poison_target_id,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(poison_targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )

    raise ValueError("Villager agent has no night action.")


def _validate_speech_decision(
    state: GameState,
    player_id: str,
    decision: AgentDecision,
) -> AgentDecision:
    """校验白天发言决策。"""
    if decision.action_type != "speak":
        raise ValueError("Agent must return a speak action during day speech.")
    speech = decision.speech.strip()[:240]
    if not speech:
        raise ValueError("Agent speech cannot be empty.")
    targets = legal_vote_targets(state, player_id)
    return AgentDecision(
        action_type="speak",
        speech=speech,
        public_reason=decision.public_reason,
        thought_summary=decision.thought_summary,
        memory_note=decision.memory_note,
        suspicion_scores=_legal_scores(targets, decision.suspicion_scores),
        confidence=decision.confidence,
    )


def _validate_sheriff_decision(
    state: GameState,
    player_id: str,
    decision: AgentDecision,
) -> AgentDecision:
    """校验警长竞选阶段的发言或投票决策。"""
    targets = legal_sheriff_vote_targets(state, player_id)
    if decision.action_type == "sheriff_run":
        if state.sheriff_candidate_ids:
            raise ValueError("Agent cannot join sheriff race after candidates are set.")
        return AgentDecision(
            action_type="sheriff_run",
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores={},
            confidence=decision.confidence,
        )
    if not state.sheriff_candidate_ids:
        if decision.action_type == "abstain":
            return AgentDecision(
                action_type="abstain",
                target_id=None,
                public_reason=decision.public_reason,
                thought_summary=decision.thought_summary,
                memory_note=decision.memory_note,
                suspicion_scores={},
                confidence=decision.confidence,
            )
        raise ValueError("Agent must return sheriff_run or abstain while sheriff candidates are being collected.")
    if decision.action_type == "sheriff_vote":
        if decision.target_id not in targets:
            raise ValueError("Agent returned an illegal sheriff vote target.")
        _require_independent_vote_reason(decision, decision.target_id)
        return AgentDecision(
            action_type="sheriff_vote",
            target_id=decision.target_id,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )
    if decision.action_type == "abstain":
        return AgentDecision(
            action_type="abstain",
            target_id=None,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=_legal_scores(targets, decision.suspicion_scores),
            confidence=decision.confidence,
        )
    return _validate_speech_decision(state, player_id, decision)


def _validate_vote_decision(
    state: GameState,
    player_id: str,
    decision: AgentDecision,
) -> AgentDecision:
    """校验白天投票或弃票决策。"""
    candidates = state.pk_tied_player_ids if state.phase is Phase.EXILE_PK_VOTE else None
    targets = legal_vote_targets(state, player_id, candidates=candidates)
    scores = _legal_scores(targets, decision.suspicion_scores)
    if decision.action_type == "abstain":
        return AgentDecision(
            action_type="abstain",
            target_id=None,
            public_reason=decision.public_reason,
            thought_summary=decision.thought_summary,
            memory_note=decision.memory_note,
            suspicion_scores=scores,
            confidence=decision.confidence,
        )
    if decision.action_type != "vote":
        raise ValueError("Agent must return vote or abstain during day vote.")
    if decision.target_id not in targets:
        raise ValueError("Agent returned an illegal vote target.")
    _require_independent_vote_reason(decision, decision.target_id)
    return AgentDecision(
        action_type="vote",
        target_id=decision.target_id,
        public_reason=decision.public_reason,
        thought_summary=decision.thought_summary,
        memory_note=decision.memory_note,
        suspicion_scores=scores,
        confidence=decision.confidence,
    )


def _legal_scores(legal_targets: list[str], scores: dict[str, int]) -> dict[str, int]:
    """只保留合法目标的 0-100 怀疑分。"""
    legal = set(legal_targets)
    return {
        target_id: max(0, min(100, int(score)))
        for target_id, score in scores.items()
        if target_id in legal
    }


def _require_independent_vote_reason(
    decision: AgentDecision,
    target_id: str | None,
) -> None:
    """Require AI votes to carry their own explainable basis."""
    if target_id is None:
        return
    if not decision.public_reason.strip():
        raise ValueError("Agent vote must include its own public_reason.")
    if target_id not in decision.suspicion_scores:
        raise ValueError("Agent vote must score the selected target.")


def _player_role(state: GameState, player_id: str) -> Role:
    """返回指定玩家的真实角色。"""
    for player in state.players:
        if player.player_id == player_id:
            return player.role
    raise ValueError(f"Unknown player: {player_id}")
