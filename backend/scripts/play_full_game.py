"""通过多 Agent 图流程跑完一局确定性测试游戏。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.graph import GraphRuntime
from app.agents.schemas import AgentDecision
from app.core.models import GameState, Phase, Role
from app.core.rules import (
    get_player,
    legal_seer_targets,
    legal_vote_targets,
    legal_werewolf_targets,
    legal_witch_poison_targets,
)
from app.sessions.manager import GameSessionManager
from app.sessions.models import GameSnapshotResponse, SubmitActionRequest


class ScriptedAgent:
    """只用于本地完整局验证的确定性 Agent。"""

    def __init__(self, player_id: str, *, player_index: int) -> None:
        """记录玩家 id 和座位序号，模拟真实 TextAgent 的构造参数。"""
        self.player_id = player_id
        self.player_index = player_index

    async def decide(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """根据当前阶段返回一个合法且可复现的决策。"""
        player = get_player(state, self.player_id)
        if state.phase is Phase.NIGHT and player.role is Role.WEREWOLF:
            target = _first_target(legal_werewolf_targets(state), prefer_power=True, state=state)
            return AgentDecision(
                action_type="werewolf_kill_intent",
                target_id=target,
                memory_note=f"今晚优先处理 {target}",
            )
        if state.phase is Phase.NIGHT and player.role is Role.SEER:
            targets = legal_seer_targets(state, self.player_id)
            return AgentDecision(action_type="seer_check", target_id=targets[0])
        if state.phase is Phase.NIGHT and player.role is Role.WITCH:
            killed = state.night_actions.werewolf_target_id
            poison_targets = legal_witch_poison_targets(
                state,
                self.player_id,
                killed_player_id=killed,
            )
            poison = poison_targets[0] if state.round_no >= 2 and poison_targets else None
            return AgentDecision(
                action_type="witch_action",
                save=False,
                poison_target_id=poison,
            )
        if state.phase is Phase.DAY_SPEECH:
            return AgentDecision(
                action_type="speak",
                speech=f"我是 {self.player_id}，这一轮我会根据死亡和投票继续排狼。",
                memory_note="保持观察公开信息。",
            )
        if state.phase is Phase.DAY_VOTE:
            target = _scripted_vote_target(state, self.player_id)
            scores = {target: 80} if target else {}
            return AgentDecision(
                action_type="vote" if target else "abstain",
                target_id=target,
                public_reason="根据公开发言、死亡信息和历史投票独立选择目标。",
                suspicion_scores=scores,
            )
        return AgentDecision(action_type="abstain")


async def main() -> None:
    """运行完整对局并打印最终胜负结果。"""
    manager = GameSessionManager()
    manager._runtime = GraphRuntime(
        pending_sink=manager._set_pending_action,
        agent_factory=lambda player_id, player_index: ScriptedAgent(
            player_id,
            player_index=player_index,
        ),
    )

    snapshot = await manager.create_game(seed=42, player_name="Tester")
    game_id = snapshot.game_id
    steps = 0
    while snapshot.phase != "game_over":
        steps += 1
        if steps > 240:
            raise RuntimeError("游戏未能在 240 个图节点内结束。")
        pending = snapshot.pending_action
        if pending is None:
            snapshot = await (await manager.get(game_id)).advance()
            continue
        request = _human_request(snapshot)
        snapshot = await (await manager.get(game_id)).submit_action(request)

    print(f"游戏在 {steps} 个图节点后结束。")
    print(f"胜者：{snapshot.winner}")
    print("玩家：")
    for player in sorted(snapshot.players, key=lambda item: item.seat):
        status = "存活" if player.alive else "出局"
        print(f"  {player.seat}. {player.name} ({player.player_id}) {player.role} {status}")
    await manager.close()


def _human_request(snapshot: GameSnapshotResponse) -> SubmitActionRequest:
    """为当前真人 pending prompt 自动生成一个合法行动。"""
    pending = snapshot.pending_action
    if pending is None:
        raise RuntimeError("当前没有等待真人行动。")
    if pending.action_type == "werewolf_kill":
        return SubmitActionRequest(
            action_type="werewolf_kill",
            target_id=pending.legal_targets[0],
        )
    if pending.action_type == "seer_check":
        return SubmitActionRequest(
            action_type="seer_check",
            target_id=pending.legal_targets[0],
        )
    if pending.action_type == "witch_action":
        return SubmitActionRequest(action_type="witch_action", save=False)
    if pending.action_type == "speak":
        return SubmitActionRequest(
            action_type="speak",
            speech="我先基于公开信息发言，重点看投票和死亡情况。",
        )
    if pending.action_type == "vote":
        target = pending.legal_targets[0] if pending.legal_targets else None
        if target is None:
            return SubmitActionRequest(action_type="abstain")
        return SubmitActionRequest(action_type="vote", target_id=target)
    raise RuntimeError(f"不支持的 pending action：{pending.action_type}")


def _first_target(
    targets: list[str],
    *,
    prefer_power: bool,
    state: GameState,
) -> str:
    """返回确定性目标，可优先选择神职作为夜晚袭击对象。"""
    if not targets:
        raise RuntimeError("当前没有合法目标。")
    if prefer_power:
        for role in (Role.SEER, Role.WITCH):
            for player in state.players:
                if player.player_id in targets and player.role is role:
                    return player.player_id
    return targets[0]


def _scripted_vote_target(state: GameState, voter_id: str) -> str | None:
    """生成确定性投票目标，保证脚本能走到胜负结果。"""
    targets = legal_vote_targets(state, voter_id)
    if not targets:
        return None
    wolves = [player.player_id for player in state.players if player.role is Role.WEREWOLF and player.alive]
    villagers = [player.player_id for player in state.players if player.role is not Role.WEREWOLF and player.alive]
    voter = get_player(state, voter_id)
    if voter.role is Role.WEREWOLF:
        return villagers[0] if villagers else targets[0]
    return wolves[0] if wolves else targets[0]


if __name__ == "__main__":
    asyncio.run(main())
