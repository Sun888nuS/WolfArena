"""pytest 共享配置。"""

from collections.abc import Iterator

import pytest

from app.agents.schemas import AgentDecision
from app.config import get_settings
from app.core.models import GameState, Phase, Role
from app.core.rules import (
    alive_players,
    get_player,
    legal_seer_targets,
    legal_sheriff_vote_targets,
    legal_vote_targets,
    legal_werewolf_targets,
    legal_witch_poison_targets,
)
from app.sessions.manager import manager


class StubOnlineAgent:
    """在线 Agent 接口的测试替身。"""

    def __init__(self, player_id: str, *, player_index: int) -> None:
        """记录玩家 id 和座位序号，保持与真实 Agent 构造参数一致。"""
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
        """不调用外部模型，直接返回合法测试决策。"""
        player = get_player(state, self.player_id)
        if state.phase is Phase.NIGHT and player.role is Role.WEREWOLF:
            return AgentDecision(
                action_type="werewolf_kill_intent",
                target_id=legal_werewolf_targets(state)[0],
                thought_summary=task,
            )
        if state.phase is Phase.NIGHT and player.role is Role.SEER:
            return AgentDecision(
                action_type="seer_check",
                target_id=legal_seer_targets(state, self.player_id)[0],
                thought_summary=task,
            )
        if state.phase is Phase.NIGHT and player.role is Role.WITCH:
            return AgentDecision(
                action_type="witch_action",
                save=False,
                poison_target_id=None,
                thought_summary=task,
            )
        if state.phase is Phase.SHERIFF_ELECTION:
            targets = legal_sheriff_vote_targets(state, self.player_id)
            if not state.sheriff_candidate_ids:
                wants_run = self.player_index % 3 != 0
                return AgentDecision(
                    action_type="sheriff_run" if wants_run else "abstain",
                    thought_summary=task,
                )
            if self.player_id in state.sheriff_candidate_ids:
                return AgentDecision(
                    action_type="speak",
                    speech="测试替身参与警长竞选发言。",
                    thought_summary=task,
                )
            return AgentDecision(
                action_type="sheriff_vote" if targets else "abstain",
                target_id=targets[0] if targets else None,
                public_reason="测试替身根据警上发言选择更可信的候选人。",
                suspicion_scores={targets[0]: 70} if targets else {},
                thought_summary=task,
            )
        if state.phase is Phase.DAY_SPEECH:
            return AgentDecision(
                action_type="speak",
                speech="测试替身玩家发言。",
                thought_summary=task,
            )
        if state.phase is Phase.DAY_VOTE:
            targets = legal_vote_targets(state, self.player_id)
            return AgentDecision(
                action_type="vote" if targets else "abstain",
                target_id=targets[0] if targets else None,
                public_reason="测试替身根据公开发言和历史事件独立选择目标。",
                suspicion_scores={targets[0]: 70} if targets else {},
                thought_summary=task,
            )
        return AgentDecision(action_type="abstain", thought_summary=task)

    async def decide_sheriff_order(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """测试替身警长固定选择逆时针发言。"""
        return AgentDecision(
            action_type="sheriff_order",
            direction="counterclockwise",
            thought_summary=task,
        )

    async def decide_sheriff_handoff(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """测试替身警长选择一个非首位存活玩家，避免固定第一个目标。"""
        targets = [
            player.player_id
            for player in sorted(alive_players(state), key=lambda item: item.seat)
            if player.player_id != self.player_id
        ]
        target_id = targets[-1] if targets else None
        return AgentDecision(
            action_type="sheriff_handoff" if target_id else "abstain",
            target_id=target_id,
            thought_summary=task,
        )


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch) -> Iterator[None]:
    """隔离测试配置，并注入确定性的 AI Agent。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")
    monkeypatch.setattr(manager, "_sessions", {})
    monkeypatch.setattr(manager, "_pending_actions", {})
    monkeypatch.setattr(
        manager,
        "_runtime",
        manager._runtime.__class__(
            pending_sink=manager._set_pending_action,
            agent_factory=lambda player_id, player_index: StubOnlineAgent(
                player_id,
                player_index=player_index,
            ),
        ),
    )
    yield
    get_settings.cache_clear()
