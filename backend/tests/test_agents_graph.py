"""LangGraph 编排层的规则衔接测试。"""

import asyncio
from typing import Any

import app.agents.graph as graph_module
from app.agents.graph import WerewolfGraphController, _state_from_engine
from app.agents.schemas import AgentDecision
from app.agents.validators import validate_agent_decision
from app.core.engine import WerewolfEngine
from app.core.models import DeathReason
from app.core.rules import alive_players, legal_sheriff_candidates, speaking_players


class HandoffAgent:
    """只用于验证警徽移交的测试 Agent。"""

    def __init__(self, target_id: str) -> None:
        self.target_id = target_id

    async def decide_sheriff_handoff(
        self,
        state: Any,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """返回指定目标，证明编排层使用了 Agent 决策。"""
        return AgentDecision(
            action_type="sheriff_handoff",
            target_id=self.target_id,
            thought_summary=task,
        )


class SheriffRunAgent:
    """只用于验证上警报名会使用每个 AI 的独立决策。"""

    def __init__(self, player_id: str, run_ids: set[str]) -> None:
        self.player_id = player_id
        self.run_ids = run_ids
        self.calls: list[str] | None = None

    def with_calls(self, calls: list[str]) -> "SheriffRunAgent":
        self.calls = calls
        return self

    async def decide(
        self,
        state: Any,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        if self.calls is not None:
            self.calls.append(self.player_id)
        return AgentDecision(
            action_type="sheriff_run" if self.player_id in self.run_ids else "abstain",
            thought_summary=task,
        )


class VoteAgent:
    """记录投票时可见的公共记忆，验证 AI 不吃本轮即时票型。"""

    def __init__(self, player_id: str, seen_vote_counts: list[int]) -> None:
        self.player_id = player_id
        self.seen_vote_counts = seen_vote_counts

    async def decide(
        self,
        state: Any,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        self.seen_vote_counts.append(len(list((public_memory or {}).get("vote_log", []))))
        target = next(
            player.player_id
            for player in sorted(state.players, key=lambda item: item.seat)
            if player.alive and player.can_vote and player.player_id != self.player_id
        )
        return AgentDecision(
            action_type="vote",
            target_id=target,
            public_reason="我根据公开发言和历史信息独立选择这个目标。",
            suspicion_scores={target: 70},
            thought_summary=task,
        )


class StreamingSpeechAgent:
    """用于验证公开发言流和发言索引推进的测试 Agent。"""

    def __init__(self, player_id: str, seat: int, calls: list[str]) -> None:
        self.player_id = player_id
        self.seat = seat
        self.calls = calls

    async def decide_streamed_speech(
        self,
        state: Any,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
        on_speech_delta: Any = None,
    ) -> AgentDecision:
        self.calls.append(self.player_id)
        speech = f"{self.seat}号测试发言，按座位顺序推进。"
        if on_speech_delta is not None:
            await on_speech_delta(self.player_id, speech[:8])
            await on_speech_delta(self.player_id, speech)
        return AgentDecision(action_type="speak", speech=speech, thought_summary=task)


def test_sheriff_candidate_collect_uses_each_player_choice(monkeypatch: Any) -> None:
    """警长报名应逐个玩家决策，而不是自动挑固定候选名单。"""

    async def scenario() -> None:
        monkeypatch.setattr(graph_module, "HUMAN_PLAYER_ID", "__no_human__")
        engine = WerewolfEngine(_names(), human_player_id=None, seed=24)
        engine.start_sheriff_election()
        sorted_players = sorted(engine.state.players, key=lambda item: item.seat)
        run_ids = {sorted_players[1].player_id, sorted_players[4].player_id}
        asked_ids: list[str] = []
        controller = _controller_with_agent_factory(
            lambda player_id, *_: SheriffRunAgent(player_id, run_ids).with_calls(asked_ids)
        )
        state = _state_from_engine(engine)
        state["sheriff_candidate_order"] = legal_sheriff_candidates(engine.state)
        state["sheriff_candidate_index"] = 0
        state["pending_sheriff_candidates"] = []

        current = state
        for _ in range(len(legal_sheriff_candidates(engine.state)) + 1):
            current = await controller._sheriff_candidate_collect(current)

        assert current["next_node"] == "sheriff_speech_turn"
        assert set(current["sheriff_speech_order"]) == run_ids
        assert asked_ids == legal_sheriff_candidates(engine.state)

    asyncio.run(scenario())


def test_day_speech_streams_and_advances_to_next_speaker() -> None:
    """白天发言应按座位顺序流式输出，并在每名玩家结束后推进索引。"""

    async def scenario() -> None:
        stream_events: list[dict[str, object]] = []
        calls: list[str] = []
        engine = WerewolfEngine(_names(), human_player_id=None, seed=28)
        engine.resolve_night()
        order = [player.player_id for player in sorted(speaking_players(engine.state), key=lambda item: item.seat)][:3]
        controller = _controller_with_agent_factory(
            lambda player_id, seat: StreamingSpeechAgent(player_id, seat, calls),
            stream_sink=lambda _game_id, payload: stream_events.append(payload),
        )
        state = _state_from_engine(engine)
        state["speech_order"] = order
        state["speech_index"] = 0
        state["event_cursor"] = len(engine.state.events)

        current = state
        for expected_index in range(1, len(order) + 1):
            current = await controller._day_speech_turn(current)
            assert current["speech_index"] == expected_index
            assert current["next_node"] == "day_speech_turn"

        assert calls == order
        assert [event["player_id"] for event in stream_events if event["type"] == "agent_reply_started"] == order
        assert [event["player_id"] for event in stream_events if event["type"] == "agent_reply_completed"] == order
        assert [event["player_id"] for event in stream_events if event["type"] == "agent_reply_delta"] == [
            player_id for player_id in order for _ in range(2)
        ]
        assert len({event["stream_id"] for event in stream_events}) == len(order)

        duplicate_state = {**current, "speech_index": 0}
        before_event_count = len(stream_events)
        before_call_count = len(calls)
        skipped = await controller._day_speech_turn(duplicate_state)

        assert skipped["speech_index"] == 1
        assert len(stream_events) == before_event_count
        assert len(calls) == before_call_count

    asyncio.run(scenario())


def test_sheriff_pk_speech_routes_to_pk_vote_after_all_candidates_spoke() -> None:
    """警长 PK 发言结束后应进入 PK 投票，而不是回到首轮投票。"""

    async def scenario() -> None:
        engine = WerewolfEngine(_names(), human_player_id="p1", seed=22)
        controller = _controller_with_agent_factory()
        engine.start_sheriff_election()
        candidates = tuple(player.player_id for player in engine.state.players[:2])
        engine.set_sheriff_candidates(candidates)
        state = _state_from_engine(engine)
        state["sheriff_speech_order"] = list(candidates)
        state["sheriff_speech_index"] = len(candidates)

        result = await controller._sheriff_pk_speech(state)

        assert result["last_node"] == "sheriff_pk_speech"
        assert result["next_node"] == "sheriff_pk_vote_start"

    asyncio.run(scenario())


def test_sheriff_vote_start_uses_only_off_sheriff_voters() -> None:
    """警上玩家发言后，应由所有未上警且有票权玩家投警长票。"""

    async def scenario() -> None:
        engine = WerewolfEngine(_names(), human_player_id=None, seed=27)
        controller = _controller_with_agent_factory()
        engine.start_sheriff_election()
        sorted_voters = [player.player_id for player in sorted(alive_players(engine.state), key=lambda item: item.seat)]
        candidates = tuple(sorted_voters[1:4])
        engine.set_sheriff_candidates(candidates)

        result = await controller._sheriff_vote_start(_state_from_engine(engine))

        assert result["sheriff_vote_order"] == [
            player_id for player_id in sorted_voters if player_id not in candidates
        ]

    asyncio.run(scenario())


def test_day_vote_turn_keeps_current_round_votes_out_of_ai_public_memory() -> None:
    """同轮投票不应把前手即时票型喂给后手 AI，避免机械跟风。"""

    async def scenario() -> None:
        seen_vote_counts: list[int] = []
        engine = WerewolfEngine(_names(), human_player_id=None, seed=25)
        engine.resolve_night()
        engine.start_vote()
        voters = [
            player.player_id
            for player in sorted(alive_players(engine.state), key=lambda item: item.seat)
            if not player.is_human
        ][:3]
        controller = _controller_with_agent_factory(lambda player_id, *_: VoteAgent(player_id, seen_vote_counts))
        state = _state_from_engine(engine)
        state["vote_order"] = voters
        state["vote_index"] = 0
        state["public_memory"] = {"vote_log": [{"round": 0, "actor": "old", "target": "old"}]}
        state["event_cursor"] = len(engine.state.events)

        current = state
        for _ in voters:
            current = await controller._day_vote_turn(current)

        assert seen_vote_counts == [1, 1, 1]
        assert current["event_cursor"] == state["event_cursor"]

    asyncio.run(scenario())


def test_vote_decision_requires_own_reason_and_target_score() -> None:
    """AI 投票必须带自己的公开理由和被投目标评分，避免固定跟风投票。"""
    engine = WerewolfEngine(_names(), human_player_id=None, seed=26)
    engine.resolve_night()
    engine.start_vote()
    voter = next(player for player in sorted(alive_players(engine.state), key=lambda item: item.seat))
    target = next(
        player.player_id
        for player in sorted(alive_players(engine.state), key=lambda item: item.seat)
        if player.player_id != voter.player_id
    )

    try:
        validate_agent_decision(
            engine.state,
            voter.player_id,
            AgentDecision(action_type="vote", target_id=target, suspicion_scores={target: 80}),
        )
    except ValueError as exc:
        assert "public_reason" in str(exc)
    else:
        raise AssertionError("Vote without public_reason should fail")

    try:
        validate_agent_decision(
            engine.state,
            voter.player_id,
            AgentDecision(action_type="vote", target_id=target, public_reason="基于发言独立判断。"),
        )
    except ValueError as exc:
        assert "score" in str(exc)
    else:
        raise AssertionError("Vote without target score should fail")

    validated = validate_agent_decision(
        engine.state,
        voter.player_id,
        AgentDecision(
            action_type="vote",
            target_id=target,
            public_reason="基于发言独立判断。",
            suspicion_scores={target: 80},
        ),
    )
    assert validated.target_id == target


def test_ai_sheriff_handoff_uses_agent_decision_instead_of_first_alive() -> None:
    """AI 警长出局后应按模型决策移交警徽，而不是固定交给第一个存活玩家。"""

    async def scenario() -> None:
        engine = WerewolfEngine(_names(), human_player_id="p1", seed=23)
        sheriff = next(player for player in sorted(engine.state.players, key=lambda item: item.seat) if not player.is_human)
        engine.state.sheriff_id = sheriff.player_id
        engine._kill_player(sheriff.player_id, DeathReason.EXILE)
        engine.state.last_exiled_player_id = sheriff.player_id
        targets = [
            player.player_id
            for player in sorted(alive_players(engine.state), key=lambda item: item.seat)
            if player.player_id != sheriff.player_id
        ]
        first_alive = targets[0]
        agent_target = targets[-1]
        controller = _controller_with_agent_factory(lambda *_: HandoffAgent(agent_target))

        target = await controller._reaction_sheriff_handoff(engine, _state_from_engine(engine))

        assert agent_target != first_alive
        assert target == agent_target

    asyncio.run(scenario())


def _controller_with_agent_factory(
    factory: Any | None = None,
    stream_sink: Any | None = None,
) -> WerewolfGraphController:
    """构造不编译整张图的控制器实例，用于直接测试节点方法。"""
    controller = WerewolfGraphController.__new__(WerewolfGraphController)
    controller._pending_sink = lambda _game_id, _pending: None
    controller._agent_factory = factory or (lambda *_: HandoffAgent("p1"))
    controller._stream_sink = stream_sink
    controller._agents_by_game = {}
    return controller


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
