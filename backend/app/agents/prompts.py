"""多 Agent 狼人杀的 prompt 构建器。

本模块只把 `PlayerView` 和任务说明转换成大模型 messages，不调用模型、
不做规则校验、不写记忆。
"""

import json
from typing import Any

from app.core.models import Phase, Role
from app.core.visibility import PlayerView


def build_decision_prompt(view: PlayerView, persona: str, task: str) -> list[dict[str, str]]:
    """根据玩家视角、人格和任务构建结构化决策 prompt。"""
    system = (
        "你是正在参与 12 人标准局狼人杀的 AI 玩家。规则引擎负责真实结算，你只输出候选行动。"
        "你必须只基于 visible_state 中提供的信息推理，不能声称知道未提供的隐藏身份。"
        "公开发言不得暴露非法私有信息；狼人白天不能把新的白天想法同步给队友。"
        "玩家对外称呼必须使用 visible_state 中的 label，例如“4号 青岚”。"
        "player_id 只用于 target_id 等结构化字段，speech、public_reason、thought_summary、memory_note 中不要写 p1、p2 这类内部 id。"
        "只输出 JSON，不要 Markdown。不要输出完整思维链，只写简短 thought_summary 和 memory_note。"
    )
    user = {
        "persona": persona,
        "task": task,
        "role_objective": _role_objective(view.own_role),
        "phase_rules": _phase_rules(view),
        "visible_state": _visible_state(view),
        "output_schema": _output_schema(),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def build_speech_prompt(view: PlayerView, persona: str, task: str) -> list[dict[str, str]]:
    """根据玩家视角构建只输出公开发言正文的流式 prompt。"""
    system = (
        "你是正在参与 12 人标准局狼人杀的 AI 玩家。现在轮到你公开发言。"
        "只输出你要对其他玩家说的发言正文，不要输出 JSON、Markdown、标题、引号或解释。"
        "发言最多 240 字，要像真人玩家，称呼玩家必须使用 visible_state 中的 label。"
        "只能基于 visible_state 中的公开信息和你合法可见的私有信息发言，不得编造未提供的信息。"
    )
    user = {
        "persona": persona,
        "task": task,
        "role_objective": _role_objective(view.own_role),
        "phase_rules": _phase_rules(view),
        "visible_state": _visible_state(view),
        "output": "只输出公开发言正文，最多 240 字。",
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _visible_state(view: PlayerView) -> dict[str, Any]:
    """把玩家视角转换成 JSON 安全的 visible_state。"""
    labels_by_id = {player.player_id: player.label for player in view.players}
    return {
        "self_id": view.player_id,
        "self_label": labels_by_id.get(view.player_id, view.player_id),
        "own_role": view.own_role.value,
        "phase": view.phase.value,
        "round_no": view.round_no,
        "alive": view.alive,
        "players": [
            {
                "id": player.player_id,
                "name": player.name,
                "seat": player.seat,
                "label": player.label,
                "alive": player.alive,
            }
            for player in view.players
        ],
        "known_werewolves": [
            {
                "id": player_id,
                "label": labels_by_id.get(player_id, player_id),
            }
            for player_id in view.known_werewolves
        ],
        "seer_results": {
            target: {
                "label": labels_by_id.get(target, target),
                "alignment": alignment.value,
            }
            for target, alignment in view.seer_results.items()
        },
        "public_memory": {
            "round_summaries": list(view.public_memory.get("round_summaries", []))[-8:],
            "speech_log": list(view.public_memory.get("speech_log", []))[-12:],
            "vote_log": list(view.public_memory.get("vote_log", []))[-12:],
            "death_log": list(view.public_memory.get("death_log", []))[-8:],
            "event_log": list(view.public_memory.get("event_log", []))[-12:],
        },
        "private_memory": view.private_memory,
        "wolf_shared_memory": view.wolf_shared_memory,
        "legal_actions": list(view.legal_actions),
        "legal_targets": list(view.legal_targets),
        "legal_target_options": [
            {
                "id": target_id,
                "label": labels_by_id.get(target_id, target_id),
            }
            for target_id in view.legal_targets
        ],
        "attacked_player_id": view.attacked_player_id,
        "attacked_player_label": labels_by_id.get(view.attacked_player_id, view.attacked_player_id),
        "can_save": view.can_save,
        "can_poison": view.can_poison,
    }


def _output_schema() -> dict[str, str]:
    """返回模型必须遵守的结构化输出说明。"""
    return {
        "action_type": "werewolf_kill_intent|seer_check|witch_action|hunter_shot|idiot_reveal|sheriff_vote|sheriff_run|sheriff_order|sheriff_handoff|werewolf_self_explode|speak|vote|abstain",
        "target_id": "目标玩家 id；弃权无目标时为 null",
        "speech": "白天公开发言，最多 240 字；夜晚为空",
        "public_reason": "公开理由，最多 240 字；不能暴露非法私有信息；称呼玩家时使用 label，不要写内部 id",
        "thought_summary": "私有策略摘要，最多 240 字；称呼玩家时使用 label，不要写内部 id",
        "memory_note": "本次行动后要保留的短记忆，最多 240 字；称呼玩家时使用 label，不要写内部 id",
        "suspicion_scores": "对合法目标的怀疑分，0-100，key 为玩家 id",
        "confidence": "本次判断置信度，0-100",
        "save": "女巫是否救人",
        "poison_target_id": "女巫毒药目标 id 或 null",
        "direction": "警长选择发言顺序时使用：clockwise 或 counterclockwise；其他行动为 null",
    }


def _role_objective(role: Role) -> str:
    """返回不同角色的阵营目标和行为约束。"""
    if role is Role.WEREWOLF:
        return (
            "你属于狼人阵营。夜晚与狼队共享信息并统一刀人；白天伪装成好人，"
            "只能基于公开信息发言，不得暴露狼队共享记忆。"
        )
    if role is Role.SEER:
        return (
            "你是预言家。夜晚查验关键玩家；白天根据局势决定是否公开查验结果，"
            "不能编造未查验信息。"
        )
    if role is Role.WITCH:
        return (
            "你是女巫。夜晚根据刀口和药剂状态决定是否救人或毒人；白天谨慎隐藏身份。"
        )
    if role is Role.HUNTER:
        return "你是猎人。被狼人刀死或被公投出局时可以开枪带走一名玩家；被女巫毒死不能发动技能。"
    if role is Role.IDIOT:
        return "你是白痴。被白天公投出局时可以翻牌自证，之后继续发言但失去投票权。"
    return "你是村民。没有夜间信息，只能通过公开发言、投票、死亡和摘要找狼。"


def _phase_rules(view: PlayerView) -> str:
    """返回当前阶段下的行动规则说明。"""
    if view.phase is Phase.NIGHT and view.own_role is Role.WEREWOLF:
        return (
            "狼人夜晚输出结构化刀人意向。优先参考 wolf_shared_memory 中的共同策略，"
            "若已有队友提案，尽量统一到最有利目标。"
        )
    if view.phase is Phase.NIGHT and view.own_role is Role.SEER:
        return "预言家选择一名仍存活且合法的目标查验阵营。"
    if view.phase is Phase.NIGHT and view.own_role is Role.WITCH:
        return "女巫基于 attacked_player_id、can_save、can_poison 和合法毒药目标选择行动；女巫被狼人刀中时可以自救，同一晚不能同时救毒。"
    if view.phase is Phase.SHERIFF_ELECTION:
        return (
            "警长竞选阶段分三步：还没有候选名单时，每名玩家独立选择是否上警，想上警输出 sheriff_run，不上警输出 abstain；"
            "候选名单产生后，警上玩家发言，警下玩家投票；警长白天投票算 1.5 票。"
            "警长指定白天发言顺序时，输出 sheriff_order 和 direction，让自己最后总结。"
        )
    if view.phase in {Phase.DAY_SPEECH, Phase.EXILE_PK_SPEECH}:
        return (
            "白天发言围绕 public_memory 和自己的合法私有信息。发言要像真人玩家，"
            "不要机械复述摘要，不要输出行动 JSON 之外的内容。"
        )
    if view.phase in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE}:
        return (
            "投票必须基于公开发言、公开事件、自己的合法私有信息和个人记忆，输出 vote 或 abstain。"
            "不要因为已有票型或其他玩家刚投了谁就跟风；public_reason 要给出你自己的可公开理由。"
        )
    return "游戏已经结束或当前没有可执行行动。"
