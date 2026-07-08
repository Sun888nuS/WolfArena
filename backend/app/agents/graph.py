"""多 Agent 狼人杀 LangGraph 编排层。

本模块只负责“下一步走哪个节点”和“何时 interrupt 等待真人”。规则真相
由 `core.engine` 修改，记忆写入由 `agents.memory` 完成，Web 快照由
`sessions.snapshots` 生成。
"""

from collections import Counter
from collections.abc import Awaitable, Callable
from inspect import Parameter, isawaitable, signature
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.memory import (
    add_private_note,
    add_wolf_strategy_note,
    commit_wolf_kill,
    initial_private_memories,
    initial_public_memory,
    initial_wolf_shared_memory,
    set_wolf_proposals,
    summarize_current_speech_round,
    sync_new_public_events,
)
from app.agents.schemas import AgentDecision
from app.agents.text_agent import TextAgent
from app.agents.validators import (
    validate_agent_decision,
    validate_sheriff_handoff_decision,
    validate_sheriff_order_decision,
)
from app.core.events import append_event
from app.core.engine import WerewolfEngine
from app.core.exceptions import InvalidActionError
from app.core.models import EventType, EventVisibility, GameState, Phase, PlayerState, Role
from app.core.player_labels import player_label_by_id, player_labels_by_id
from app.core.rules import (
    alive_players,
    alive_werewolves,
    legal_hunter_shot_targets,
    legal_seer_targets,
    legal_sheriff_candidates,
    legal_sheriff_vote_targets,
    legal_vote_targets,
    legal_werewolf_targets,
    legal_witch_poison_targets,
    speaking_players,
    voting_players,
)
from app.core.serialization import deserialize_game_state, serialize_game_state
from app.sessions.models import PendingActionResponse, SubmitActionRequest

HUMAN_PLAYER_ID = "p1"

GraphNode = Literal[
    "check_win_before_round",
    "night_start",
    "wolf_team_entry",
    "wolf_collect_proposals",
    "wolf_consensus",
    "wolf_reconcile",
    "wolf_commit_kill",
    "witch_action",
    "witch_commit_action",
    "seer_action",
    "seer_commit_result",
    "hunter_status",
    "idiot_confirm",
    "resolve_night",
    "dawn_announcement",
    "resolve_death_reactions",
    "check_win_after_night",
    "sheriff_election_start",
    "sheriff_candidate_collect",
    "sheriff_speech_turn",
    "sheriff_vote_start",
    "sheriff_vote_turn",
    "resolve_sheriff_vote",
    "sheriff_pk_speech",
    "sheriff_pk_vote_start",
    "sheriff_pk_vote_turn",
    "resolve_sheriff_pk_vote",
    "day_speech_start",
    "day_speech_turn",
    "day_speech_summary",
    "day_vote_start",
    "day_vote_turn",
    "resolve_vote",
    "exile_pk_speech",
    "exile_pk_vote_start",
    "exile_pk_vote_turn",
    "resolve_exile_pk_vote",
    "resolve_exile_reactions",
    "public_vote_summary",
    "check_win_after_vote",
    "start_round",
    "game_over",
]


class GameGraphState(TypedDict, total=False):
    """LangGraph 持有的图状态。"""

    game: dict[str, object]  # 序列化后的规则引擎真相状态
    public_memory: dict[str, object]  # 公共记忆
    private_memories: dict[str, dict[str, object]]  # 非狼人玩家私有记忆
    wolf_shared_memory: dict[str, object]  # 狼队共享记忆
    speech_order: list[str]  # 当前白天发言顺序
    speech_index: int  # 当前发言顺序索引
    vote_order: list[str]  # 当前白天投票顺序
    vote_index: int  # 当前投票顺序索引
    event_cursor: int  # 已同步到公共记忆的事件游标
    wolf_consensus_attempts: int  # 狼队统一目标尝试次数
    pending_wolf_proposals: dict[str, str]  # 当前夜晚狼队提案
    pending_seer_decision: dict[str, object]  # 待提交的预言家决策
    pending_witch_decision: dict[str, object]  # 待提交的女巫决策
    reaction_queue: list[str]  # 等待处理死亡反应的玩家
    reaction_index: int  # 当前死亡反应索引
    speech_direction: Literal["clockwise", "counterclockwise"] | None  # 当前白天发言方向
    sheriff_candidate_order: list[str]  # 警长竞选选择顺序
    sheriff_candidate_index: int  # 警长竞选选择索引
    pending_sheriff_candidates: list[str]  # 已选择上警的玩家
    sheriff_speech_order: list[str]  # 警长竞选发言顺序
    sheriff_speech_index: int  # 警长竞选发言索引
    sheriff_vote_order: list[str]  # 警长投票顺序
    sheriff_vote_index: int  # 警长投票索引
    pk_speech_order: list[str]  # 放逐 PK 发言顺序
    pk_speech_index: int  # 放逐 PK 发言索引
    completed_speech_stream_ids: list[str]  # 已完成的公开发言流 id，用于防止重复落盘
    last_node: str  # 最近执行节点名
    next_node: str  # 下一个节点名
    node_trace: list[dict[str, object]]  # 精简节点轨迹


AgentFactory = Callable[[str, int], TextAgent]
PendingSink = Callable[[str, PendingActionResponse | None], None]
StreamSink = Callable[[str, dict[str, object]], Awaitable[None] | None]


class WerewolfGraphController:
    """单个内存运行时中的 LangGraph 控制器。"""

    def __init__(
        self,
        *,
        checkpointer: Any,
        pending_sink: PendingSink,
        agent_factory: AgentFactory | None = None,
        stream_sink: StreamSink | None = None,
    ) -> None:
        """注入 checkpointer、真人 pending 回调和 AI Agent 工厂。"""
        self._pending_sink = pending_sink
        self._agent_factory = agent_factory or _default_agent_factory
        self._stream_sink = stream_sink
        self._agents_by_game: dict[str, dict[str, TextAgent]] = {}
        self.graph = self._build_graph().compile(checkpointer=checkpointer)

    def config_for(self, game_id: str) -> dict[str, dict[str, str]]:
        """返回某局游戏对应的 LangGraph thread 配置。"""
        return {"configurable": {"thread_id": game_id}}

    async def initialize(self, *, game_id: str, engine: WerewolfEngine) -> None:
        """为新游戏写入初始图状态。"""
        await self.graph.aupdate_state(
            self.config_for(game_id),
            _state_from_engine(engine),
            as_node=START,
        )

    async def advance(self, game_id: str) -> GameGraphState:
        """推进一个图节点；如果节点触发真人 interrupt，则暂停。"""
        result = await self.graph.ainvoke(
            None,
            self.config_for(game_id),
            interrupt_after=_ALL_NODE_NAMES,
        )
        return _strip_interrupt(result)

    async def resume(self, game_id: str, request: SubmitActionRequest) -> GameGraphState:
        """用真人提交的行动恢复被 interrupt 暂停的图。"""
        result = await self.graph.ainvoke(
            Command(resume=request.model_dump()),
            self.config_for(game_id),
            interrupt_after=_ALL_NODE_NAMES,
        )
        return _strip_interrupt(result)

    async def load(self, game_id: str) -> GameGraphState:
        """读取某局游戏最新图状态。"""
        snapshot = await self.graph.aget_state(self.config_for(game_id))
        return dict(snapshot.values)

    def _build_graph(self) -> StateGraph:
        """构建多节点狼人杀流程图。"""
        graph = StateGraph(GameGraphState) # 声明：这个图的所有节点，输入/输出都必须是 GameGraphState 类型
        nodes: dict[str, Callable[[GameGraphState], Any]] = {
            "check_win_before_round": self._check_win_before_round,
            "night_start": self._night_start,
            "wolf_team_entry": self._wolf_team_entry,
            "wolf_collect_proposals": self._wolf_collect_proposals,
            "wolf_consensus": self._wolf_consensus,
            "wolf_reconcile": self._wolf_reconcile,
            "wolf_commit_kill": self._wolf_commit_kill,
            "witch_action": self._witch_action,
            "witch_commit_action": self._witch_commit_action,
            "seer_action": self._seer_action,
            "seer_commit_result": self._seer_commit_result,
            "hunter_status": self._hunter_status,
            "idiot_confirm": self._idiot_confirm,
            "resolve_night": self._resolve_night,
            "dawn_announcement": self._dawn_announcement,
            "resolve_death_reactions": self._resolve_death_reactions,
            "check_win_after_night": self._check_win_after_night,
            "sheriff_election_start": self._sheriff_election_start,
            "sheriff_candidate_collect": self._sheriff_candidate_collect,
            "sheriff_speech_turn": self._sheriff_speech_turn,
            "sheriff_vote_start": self._sheriff_vote_start,
            "sheriff_vote_turn": self._sheriff_vote_turn,
            "resolve_sheriff_vote": self._resolve_sheriff_vote,
            "sheriff_pk_speech": self._sheriff_pk_speech,
            "sheriff_pk_vote_start": self._sheriff_pk_vote_start,
            "sheriff_pk_vote_turn": self._sheriff_pk_vote_turn,
            "resolve_sheriff_pk_vote": self._resolve_sheriff_pk_vote,
            "day_speech_start": self._day_speech_start,
            "day_speech_turn": self._day_speech_turn,
            "day_speech_summary": self._day_speech_summary,
            "day_vote_start": self._day_vote_start,
            "day_vote_turn": self._day_vote_turn,
            "resolve_vote": self._resolve_vote,
            "exile_pk_speech": self._exile_pk_speech,
            "exile_pk_vote_start": self._exile_pk_vote_start,
            "exile_pk_vote_turn": self._exile_pk_vote_turn,
            "resolve_exile_pk_vote": self._resolve_exile_pk_vote,
            "resolve_exile_reactions": self._resolve_exile_reactions,
            "public_vote_summary": self._public_vote_summary,
            "check_win_after_vote": self._check_win_after_vote,
            "start_round": self._start_round,
            "game_over": self._game_over,
        }
        for name, node in nodes.items():
            graph.add_node(name, node)

        graph.add_edge(START, "check_win_before_round")
        for name in nodes:
            graph.add_conditional_edges(name, _route_next_node, _ROUTE_MAP)
        return graph

    def _agent_for(self, engine: WerewolfEngine, player_id: str) -> TextAgent:
        """返回某局中某个 AI 玩家对应的缓存 TextAgent。"""
        game_agents = self._agents_by_game.setdefault(engine.state.game_id, {})
        if player_id not in game_agents:
            player = _player_by_id(engine.state, player_id)
            game_agents[player_id] = self._agent_factory(player_id, player.seat)
        return game_agents[player_id]

    async def _decide_streamed_speech(
        self,
        engine: WerewolfEngine,
        state: GameGraphState,
        actor_id: str,
        *,
        task: str,
        node_name: str,
        stream_id: str,
    ) -> AgentDecision:
        """为公开发言节点调用 AI，并把 speech 字段实时推给订阅者。"""
        await self._publish_agent_reply(
            engine,
            actor_id,
            "agent_reply_started",
            node_name=node_name,
            stream_id=stream_id,
        )
        agent = self._agent_for(engine, actor_id)
        decide_kwargs: dict[str, object] = {
            "public_memory": dict(state.get("public_memory") or {}),
            "private_memories": dict(state.get("private_memories") or {}),
            "wolf_shared_memory": dict(state.get("wolf_shared_memory") or {}),
        }
        try:
            stream_decider = getattr(agent, "decide_streamed_speech")
        except AttributeError:
            stream_decider = None
        if stream_decider is not None:
            try:
                decision = await stream_decider(
                    engine.state,
                    task,
                    **decide_kwargs,
                    on_speech_delta=lambda player_id, text: self._publish_agent_reply(
                        engine,
                        player_id,
                        "agent_reply_delta",
                        node_name=node_name,
                        stream_id=stream_id,
                        text=text,
                    ),
                )
            except Exception:
                await self._publish_agent_reply(
                    engine,
                    actor_id,
                    "agent_reply_failed",
                    node_name=node_name,
                    stream_id=stream_id,
                )
                raise
            return validate_agent_decision(engine.state, actor_id, decision)

        if _agent_decide_accepts_stream(agent):
            decide_kwargs.update(
                {
                    "stream_speech": True,
                    "on_speech_delta": lambda player_id, text: self._publish_agent_reply(
                        engine,
                        player_id,
                        "agent_reply_delta",
                        node_name=node_name,
                        stream_id=stream_id,
                        text=text,
                    ),
                }
            )
        try:
            decision = await agent.decide(engine.state, task, **decide_kwargs)
        except Exception:
            await self._publish_agent_reply(
                engine,
                actor_id,
                "agent_reply_failed",
                node_name=node_name,
                stream_id=stream_id,
            )
            raise
        return decision

    async def _publish_agent_reply(
        self,
        engine: WerewolfEngine,
        player_id: str,
        event_type: str,
        *,
        node_name: str,
        stream_id: str,
        text: str = "",
    ) -> None:
        """通过会话层向前端推送公开 AI 发言的临时预览。"""
        if self._stream_sink is None:
            return
        result = self._stream_sink(
            engine.state.game_id,
            {
                "type": event_type,
                "game_id": engine.state.game_id,
                "player_id": player_id,
                "stream_id": stream_id,
                "text": text[:240],
                "node": node_name,
                "round_no": engine.state.round_no,
                "phase": engine.state.phase.value,
            },
        )
        if isawaitable(result):
            await result

    async def _check_win_before_round(self, state: GameGraphState) -> GameGraphState:
        """轮次开始前检查胜负，决定进入夜晚还是结束。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        engine._check_and_set_winner()
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        next_node = "game_over" if engine.state.is_over else "night_start"
        return _with_trace(
            state,
            engine,
            "check_win_before_round",
            before,
            next_node=next_node,
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _night_start(self, state: GameGraphState) -> GameGraphState:
        """初始化本轮夜晚的临时图状态。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        if engine.state.phase is not Phase.NIGHT:
            next_node = "game_over" if engine.state.is_over else "day_speech_start"
            return _with_trace(state, engine, "night_start", before, next_node=next_node)
        return _with_trace(
            {
                **state,
                "speech_order": [],
                "speech_index": 0,
                "vote_order": [],
                "vote_index": 0,
                "pending_wolf_proposals": {},
                "wolf_consensus_attempts": 0,
            },
            engine,
            "night_start",
            before,
            next_node="wolf_team_entry",
        )

    async def _wolf_team_entry(self, state: GameGraphState) -> GameGraphState:
        """进入狼人团队节点，判断是否还有存活狼人需要行动。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        wolves = sorted(alive_werewolves(engine.state), key=lambda player: player.seat)
        next_node = "wolf_collect_proposals" if wolves else "witch_action"
        return _with_trace(state, engine, "wolf_team_entry", before, next_node=next_node)

    async def _wolf_collect_proposals(self, state: GameGraphState) -> GameGraphState:
        """逐个收集存活狼人的刀人提案，真人狼人会触发 interrupt。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        proposals = dict(state.get("pending_wolf_proposals") or {})
        public_memory = dict(state.get("public_memory") or {})
        private_memories = dict(state.get("private_memories") or {})
        wolf_shared_memory = dict(state.get("wolf_shared_memory") or {})

        for wolf in sorted(alive_werewolves(engine.state), key=lambda player: player.seat):
            if wolf.player_id in proposals:
                continue
            if wolf.player_id == HUMAN_PLAYER_ID:
                request = PendingActionResponse(
                    action_type="werewolf_kill",
                    player_id=HUMAN_PLAYER_ID,
                    prompt="你是狼人，请提交今晚的刀人建议。狼队共享夜间信息，稍后会统一目标。",
                    legal_targets=legal_werewolf_targets(engine.state),
                )
                payload = _interrupt_for_human(engine, request, self._pending_sink)
                submit = SubmitActionRequest.model_validate(payload)
                if submit.target_id is None:
                    raise InvalidActionError("狼人行动需要选择目标。")
                proposals[wolf.player_id] = submit.target_id
                break

            decision = await self._agent_for(engine, wolf.player_id).decide(
                engine.state,
                "作为狼人提出今晚刀人建议",
                public_memory=public_memory,
                private_memories=private_memories,
                wolf_shared_memory=wolf_shared_memory,
            )
            proposals[wolf.player_id] = _target_or_first(
                decision,
                legal_werewolf_targets(engine.state),
            )
            if decision.memory_note:
                wolf_shared_memory = add_wolf_strategy_note(
                    wolf_shared_memory,
                    f"{player_label_by_id(engine.state, wolf.player_id)}: {decision.memory_note}",
                )

        wolf_shared_memory = set_wolf_proposals(
            wolf_shared_memory,
            proposals,
            player_labels_by_id(engine.state),
        )
        next_node = (
            "wolf_consensus"
            if _all_living_wolves_proposed(engine.state, proposals)
            else "wolf_collect_proposals"
        )
        return _with_trace(
            state,
            engine,
            "wolf_collect_proposals",
            before,
            next_node=next_node,
            pending_wolf_proposals=proposals,
            wolf_shared_memory=wolf_shared_memory,
        )

    async def _wolf_consensus(self, state: GameGraphState) -> GameGraphState:
        """汇总狼队提案，判断是否达成统一刀人目标。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        proposals = dict(state.get("pending_wolf_proposals") or {})
        attempts = int(state.get("wolf_consensus_attempts", 0)) + 1
        targets = list(proposals.values())
        selected = _consensus_target(targets)
        if selected is not None or attempts >= 2:
            selected = selected or _most_common_or_first(targets, legal_werewolf_targets(engine.state))
            return _with_trace(
                state,
                engine,
                "wolf_consensus",
                before,
                next_node="wolf_commit_kill",
                wolf_consensus_attempts=attempts,
                pending_wolf_proposals={**proposals, "_consensus": selected},
            )
        return _with_trace(
            state,
            engine,
            "wolf_consensus",
            before,
            next_node="wolf_reconcile",
            wolf_consensus_attempts=attempts,
        )

    async def _wolf_reconcile(self, state: GameGraphState) -> GameGraphState:
        """在狼队意见不一致时执行一次确定性二次协调。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        proposals = dict(state.get("pending_wolf_proposals") or {})
        target = _most_common_or_first(list(proposals.values()), legal_werewolf_targets(engine.state))
        wolves = sorted(player.player_id for player in alive_werewolves(engine.state))
        proposals = {wolf_id: target for wolf_id in wolves}
        wolf_shared_memory = set_wolf_proposals(
            dict(state.get("wolf_shared_memory") or {}),
            proposals,
            player_labels_by_id(engine.state),
        )
        wolf_shared_memory = add_wolf_strategy_note(
            wolf_shared_memory,
            f"第 {engine.state.round_no} 夜二次协调后统一目标 {player_label_by_id(engine.state, target)}。",
        )
        return _with_trace(
            state,
            engine,
            "wolf_reconcile",
            before,
            next_node="wolf_consensus",
            pending_wolf_proposals=proposals,
            wolf_shared_memory=wolf_shared_memory,
        )

    async def _wolf_commit_kill(self, state: GameGraphState) -> GameGraphState:
        """把狼队最终目标提交给规则引擎，并写入狼队共享记忆。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        proposals = dict(state.get("pending_wolf_proposals") or {})
        target = str(proposals.get("_consensus") or _most_common_or_first(
            [target for actor, target in proposals.items() if not actor.startswith("_")],
            legal_werewolf_targets(engine.state),
        ))
        actor_id = _first_living_wolf_id(engine.state)
        if actor_id is None:
            raise InvalidActionError("没有存活狼人可以行动。")
        engine.select_werewolf_kill(actor_id, target)
        wolf_shared_memory = commit_wolf_kill(
            dict(state.get("wolf_shared_memory") or {}),
            round_no=engine.state.round_no,
            target_id=target,
            target_label=player_label_by_id(engine.state, target),
        )
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "wolf_commit_kill",
            before,
            next_node="witch_action",
            public_memory=public_memory,
            event_cursor=cursor,
            wolf_shared_memory=wolf_shared_memory,
            pending_wolf_proposals={},
        )

    async def _seer_action(self, state: GameGraphState) -> GameGraphState:
        """让预言家选择查验目标，真人预言家会触发 interrupt。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        seer_id = engine.living_role(Role.SEER)
        if not seer_id or engine.state.night_actions.seer_target_id is not None:
            return _with_trace(state, engine, "seer_action", before, next_node="hunter_status")

        if seer_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="seer_check",
                player_id=HUMAN_PLAYER_ID,
                prompt="你是预言家，请选择一名玩家查验阵营。",
                legal_targets=legal_seer_targets(engine.state, seer_id),
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            if submit.target_id is None:
                raise InvalidActionError("预言家查验需要选择目标。")
            decision = AgentDecision(action_type="seer_check", target_id=submit.target_id)
        else:
            decision = await self._agent_for(engine, seer_id).decide(
                engine.state,
                "选择预言家查验目标",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
        return _with_trace(
            state,
            engine,
            "seer_action",
            before,
            next_node="seer_commit_result",
            pending_seer_decision=decision.model_dump(mode="json"),
        )

    async def _seer_commit_result(self, state: GameGraphState) -> GameGraphState:
        """把预言家查验决策提交给规则引擎并写入私有记忆。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        seer_id = engine.living_role(Role.SEER)
        decision_data = dict(state.get("pending_seer_decision") or {})
        if seer_id and decision_data:
            decision = AgentDecision.model_validate(decision_data)
            target = _target_or_first(decision, legal_seer_targets(engine.state, seer_id))
            result = engine.seer_check(seer_id, target)
            private_memories = add_private_note(
                dict(state.get("private_memories") or {}),
                seer_id,
                f"第 {engine.state.round_no} 夜查验 {player_label_by_id(engine.state, target)}: {result.value}。",
                decision.suspicion_scores,
            )
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "seer_commit_result",
                before,
                next_node="hunter_status",
                private_memories=private_memories,
                public_memory=public_memory,
                event_cursor=cursor,
                pending_seer_decision={},
            )
        return _with_trace(state, engine, "seer_commit_result", before, next_node="hunter_status")

    async def _witch_action(self, state: GameGraphState) -> GameGraphState:
        """让女巫选择是否救人或毒人，真人女巫会触发 interrupt。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        witch_id = engine.living_role(Role.WITCH)
        if not witch_id or engine.state.night_actions.witch_actor_id is not None:
            return _with_trace(state, engine, "witch_action", before, next_node="seer_action")

        killed = engine.state.night_actions.werewolf_target_id
        if witch_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="witch_action",
                player_id=HUMAN_PLAYER_ID,
                prompt="你是女巫，请选择是否使用解药或毒药。",
                legal_targets=legal_witch_poison_targets(
                    engine.state,
                    witch_id,
                    killed_player_id=killed,
                ),
                can_save=bool(killed and engine.state.witch_state.has_antidote),
                can_poison=engine.state.witch_state.has_poison,
                attacked_player_id=killed if engine.state.witch_state.has_antidote else None,
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            decision = AgentDecision(
                action_type="witch_action",
                save=submit.save,
                poison_target_id=submit.poison_target_id,
            )
        else:
            decision = await self._agent_for(engine, witch_id).decide(
                engine.state,
                "选择女巫夜晚行动",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
        return _with_trace(
            state,
            engine,
            "witch_action",
            before,
            next_node="witch_commit_action",
            pending_witch_decision=decision.model_dump(mode="json"),
        )

    async def _witch_commit_action(self, state: GameGraphState) -> GameGraphState:
        """把女巫用药决策提交给规则引擎并写入私有记忆。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        witch_id = engine.living_role(Role.WITCH)
        decision_data = dict(state.get("pending_witch_decision") or {})
        if witch_id and decision_data:
            decision = AgentDecision.model_validate(decision_data)
            engine.witch_action(
                witch_id,
                save=decision.save,
                poison_target_id=decision.poison_target_id,
            )
            note = _witch_memory_note(engine.state, decision)
            private_memories = add_private_note(
                dict(state.get("private_memories") or {}),
                witch_id,
                note,
                decision.suspicion_scores,
            )
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "witch_commit_action",
                before,
                next_node="seer_action",
                private_memories=private_memories,
                public_memory=public_memory,
                event_cursor=cursor,
                pending_witch_decision={},
            )
        return _with_trace(state, engine, "witch_commit_action", before, next_node="seer_action")

    async def _hunter_status(self, state: GameGraphState) -> GameGraphState:
        """猎人夜晚确认技能状态。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        hunter_id = engine.living_role(Role.HUNTER)
        if hunter_id and engine.state.night_actions.hunter_actor_id is None:
            engine.confirm_hunter_status(hunter_id)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "hunter_status",
            before,
            next_node="idiot_confirm",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _idiot_confirm(self, state: GameGraphState) -> GameGraphState:
        """白痴夜晚确认身份。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        idiot_id = engine.living_role(Role.IDIOT)
        if idiot_id and engine.state.night_actions.idiot_actor_id is None:
            engine.confirm_idiot(idiot_id)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "idiot_confirm",
            before,
            next_node="resolve_night",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _resolve_night(self, state: GameGraphState) -> GameGraphState:
        """调用规则引擎结算夜晚，并同步公开事件。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        if engine.state.phase is Phase.NIGHT:
            engine.resolve_night()
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_night",
            before,
            next_node="dawn_announcement",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _dawn_announcement(self, state: GameGraphState) -> GameGraphState:
        """夜晚后天亮播报节点，保留为独立 trace 节点。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        return _with_trace(
            state,
            engine,
            "dawn_announcement",
            before,
            next_node="resolve_death_reactions",
        )

    async def _resolve_death_reactions(self, state: GameGraphState) -> GameGraphState:
        """处理夜晚死亡后的猎人开枪、白痴翻牌和警徽移交。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        hunter_target = _reaction_hunter_target(engine, self._pending_sink)
        idiot_reveal = _reaction_idiot_reveal(engine, self._pending_sink)
        sheriff_handoff = await self._reaction_sheriff_handoff(engine, state)
        engine.resolve_death_reactions(
            hunter_shot_target_id=hunter_target,
            idiot_reveal=idiot_reveal,
            sheriff_handoff_target_id=sheriff_handoff,
        )
        if hunter_target and engine.state.sheriff_id == hunter_target:
            followup_handoff = await self._reaction_sheriff_handoff(engine, state)
            engine.resolve_death_reactions(sheriff_handoff_target_id=followup_handoff)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_death_reactions",
            before,
            next_node="check_win_after_night",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _check_win_after_night(self, state: GameGraphState) -> GameGraphState:
        """夜晚结算后检查胜负，决定进入白天或结束。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        next_node = (
            "game_over"
            if engine.state.is_over
            else "sheriff_election_start"
            if _should_start_sheriff_election(engine.state)
            else "day_speech_start"
        )
        return _with_trace(state, engine, "check_win_after_night", before, next_node=next_node)

    async def _sheriff_election_start(self, state: GameGraphState) -> GameGraphState:
        """首日进入警长竞选。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        engine.start_sheriff_election()
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "sheriff_election_start",
            before,
            next_node="sheriff_candidate_collect",
            public_memory=public_memory,
            event_cursor=cursor,
            sheriff_candidate_order=legal_sheriff_candidates(engine.state),
            sheriff_candidate_index=0,
            pending_sheriff_candidates=[],
        )

    async def _sheriff_candidate_collect(self, state: GameGraphState) -> GameGraphState:
        """逐个收集玩家是否参与警长竞选。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("sheriff_candidate_order") or legal_sheriff_candidates(engine.state))
        index = int(state.get("sheriff_candidate_index") or 0)
        candidates = list(state.get("pending_sheriff_candidates") or [])

        if index < len(order):
            actor_id = order[index]
            if actor_id == HUMAN_PLAYER_ID:
                request = PendingActionResponse(
                    action_type="sheriff_run",
                    player_id=HUMAN_PLAYER_ID,
                    prompt="警长竞选开始，请选择是否上警。选择上警后你会进行警上发言，未上警则参与警长投票。",
                    legal_targets=[],
                    can_skip=True,
                )
                payload = _interrupt_for_human(engine, request, self._pending_sink)
                submit = SubmitActionRequest.model_validate(payload)
                wants_run = submit.action_type == "sheriff_run"
            else:
                decision = await self._agent_for(engine, actor_id).decide(
                    engine.state,
                    "警长竞选报名。请基于你的身份、夜晚信息、座位和个人策略，独立决定是否上警；想上警输出 sheriff_run，不上警输出 abstain。",
                    public_memory=dict(state.get("public_memory") or {}),
                    private_memories=dict(state.get("private_memories") or {}),
                    wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
                )
                wants_run = decision.action_type == "sheriff_run"
            if wants_run and actor_id not in candidates:
                candidates.append(actor_id)
            return _with_trace(
                state,
                engine,
                "sheriff_candidate_collect",
                before,
                next_node="sheriff_candidate_collect",
                sheriff_candidate_order=order,
                sheriff_candidate_index=index + 1,
                pending_sheriff_candidates=candidates,
            )

        engine.set_sheriff_candidates(tuple(candidates))
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        if not candidates:
            engine.state.sheriff_badge_lost = True
            engine.state.sheriff_election_done = True
            engine.state.phase = Phase.DAY_SPEECH
            append_event(
                engine.state,
                EventType.SHERIFF_BADGE_LOST,
                visibility=EventVisibility.PUBLIC,
                payload={"reason": "no_candidate"},
            )
            next_node = "day_speech_start"
        else:
            next_node = "sheriff_speech_turn"
        return _with_trace(
            state,
            engine,
            "sheriff_candidate_collect",
            before,
            next_node=next_node,
            public_memory=public_memory,
            event_cursor=cursor,
            sheriff_speech_order=list(candidates),
            sheriff_speech_index=0,
            sheriff_candidate_order=[],
            sheriff_candidate_index=0,
            pending_sheriff_candidates=[],
        )

    async def _sheriff_speech_turn(self, state: GameGraphState) -> GameGraphState:
        """推进警上发言。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("sheriff_speech_order") or [])
        index = int(state.get("sheriff_speech_index") or 0)
        if index >= len(order):
            return _with_trace(
                state,
                engine,
                "sheriff_speech_turn",
                before,
                next_node="sheriff_vote_start",
            )

        actor_id = order[index]
        stream_id = _speech_stream_id("sheriff_speech_turn", engine.state.round_no, actor_id, index)
        if _speech_stream_completed(state, engine.state, stream_id):
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "sheriff_speech_turn",
                before,
                next_node="sheriff_speech_turn",
                sheriff_speech_index=index + 1,
                public_memory=public_memory,
                event_cursor=cursor,
            )
        if actor_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="speak",
                player_id=HUMAN_PLAYER_ID,
                prompt="你正在参与警长竞选，请发表警上发言。",
                legal_targets=[],
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.record_speech(HUMAN_PLAYER_ID, submit.speech, turn_key=stream_id)
        else:
            decision = await self._decide_streamed_speech(
                engine,
                state,
                actor_id,
                task="进行警上竞选发言",
                node_name="sheriff_speech_turn",
                stream_id=stream_id,
            )
            speech = decision.speech or "我参与竞选警长，会根据夜晚信息组织发言。"
            engine.record_speech(actor_id, speech, turn_key=stream_id)
            await self._publish_agent_reply(
                engine,
                actor_id,
                "agent_reply_completed",
                node_name="sheriff_speech_turn",
                stream_id=stream_id,
                text=speech,
            )

        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "sheriff_speech_turn",
            before,
            next_node="sheriff_speech_turn",
            sheriff_speech_index=index + 1,
            public_memory=public_memory,
            event_cursor=cursor,
            completed_speech_stream_ids=_mark_speech_stream_completed(state, stream_id),
        )

    async def _sheriff_vote_start(self, state: GameGraphState) -> GameGraphState:
        """生成警下投票顺序。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        candidates = set(engine.state.sheriff_candidate_ids)
        vote_order = [
            player.player_id
            for player in sorted(voting_players(engine.state), key=lambda item: item.seat)
            if player.player_id not in candidates
        ]
        return _with_trace(
            state,
            engine,
            "sheriff_vote_start",
            before,
            next_node="sheriff_vote_turn" if vote_order else "resolve_sheriff_vote",
            sheriff_vote_order=vote_order,
            sheriff_vote_index=0,
        )

    async def _sheriff_vote_turn(self, state: GameGraphState) -> GameGraphState:
        """推进警长竞选投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("sheriff_vote_order") or [])
        index = int(state.get("sheriff_vote_index") or 0)
        if index >= len(order):
            return _with_trace(state, engine, "sheriff_vote_turn", before, next_node="resolve_sheriff_vote")

        voter_id = order[index]
        legal_targets = legal_sheriff_vote_targets(engine.state, voter_id)
        if voter_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="sheriff_vote",
                player_id=HUMAN_PLAYER_ID,
                prompt="请选择你支持的警长候选人，也可以弃票。",
                legal_targets=legal_targets,
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.cast_sheriff_vote(voter_id, submit.target_id)
        else:
            decision = await self._agent_for(engine, voter_id).decide(
                engine.state,
                "进行警长竞选投票。请基于警上发言、公开事件和你的合法私有信息选择支持的候选人，也可以弃票。",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
            decision = validate_agent_decision(engine.state, voter_id, decision)
            engine.cast_sheriff_vote(
                voter_id,
                None if decision.action_type == "abstain" else decision.target_id,
                public_reason=decision.public_reason,
                reasoning_score=_decision_score_for_target(decision),
            )

        return _with_trace(
            state,
            engine,
            "sheriff_vote_turn",
            before,
            next_node="sheriff_vote_turn",
            sheriff_vote_index=index + 1,
        )

    async def _resolve_sheriff_vote(self, state: GameGraphState) -> GameGraphState:
        """结算首轮警长投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        result = engine.resolve_sheriff_vote(final_round=False)
        if result.exiled_player_id is not None:
            next_node = "day_speech_start"
        elif result.tied_player_ids:
            next_node = "sheriff_pk_speech"
            engine.set_sheriff_candidates(result.tied_player_ids)
        else:
            engine.state.sheriff_badge_lost = True
            engine.state.sheriff_election_done = True
            engine.state.phase = Phase.DAY_SPEECH
            append_event(
                engine.state,
                EventType.SHERIFF_BADGE_LOST,
                visibility=EventVisibility.PUBLIC,
                payload={"reason": "no_vote"},
            )
            next_node = "day_speech_start"
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_sheriff_vote",
            before,
            next_node=next_node,
            public_memory=public_memory,
            event_cursor=cursor,
            sheriff_speech_order=list(result.tied_player_ids),
            sheriff_speech_index=0,
        )

    async def _sheriff_pk_speech(self, state: GameGraphState) -> GameGraphState:
        """警长竞选 PK 发言。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("sheriff_speech_order") or [])
        index = int(state.get("sheriff_speech_index") or 0)
        if index >= len(order):
            return _with_trace(
                state,
                engine,
                "sheriff_pk_speech",
                before,
                next_node="sheriff_pk_vote_start",
            )

        actor_id = order[index]
        stream_id = _speech_stream_id("sheriff_pk_speech", engine.state.round_no, actor_id, index)
        if _speech_stream_completed(state, engine.state, stream_id):
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "sheriff_pk_speech",
                before,
                next_node="sheriff_pk_speech",
                sheriff_speech_index=index + 1,
                public_memory=public_memory,
                event_cursor=cursor,
            )
        if actor_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="speak",
                player_id=HUMAN_PLAYER_ID,
                prompt="你进入警长 PK，请再次说明竞选理由。",
                legal_targets=[],
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.record_speech(HUMAN_PLAYER_ID, submit.speech, turn_key=stream_id)
        else:
            decision = await self._decide_streamed_speech(
                engine,
                state,
                actor_id,
                task="进行警长竞选 PK 发言",
                node_name="sheriff_pk_speech",
                stream_id=stream_id,
            )
            speech = decision.speech or "我进入警长 PK，会继续说明自己的警徽流和判断。"
            engine.record_speech(actor_id, speech, turn_key=stream_id)
            await self._publish_agent_reply(
                engine,
                actor_id,
                "agent_reply_completed",
                node_name="sheriff_pk_speech",
                stream_id=stream_id,
                text=speech,
            )

        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "sheriff_pk_speech",
            before,
            next_node="sheriff_pk_speech",
            sheriff_speech_index=index + 1,
            public_memory=public_memory,
            event_cursor=cursor,
            completed_speech_stream_ids=_mark_speech_stream_completed(state, stream_id),
        )

    async def _sheriff_pk_vote_start(self, state: GameGraphState) -> GameGraphState:
        """生成警长 PK 投票顺序。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        pk_candidates = set(engine.state.sheriff_candidate_ids)
        vote_order = [
            player.player_id
            for player in sorted(voting_players(engine.state), key=lambda item: item.seat)
            if player.player_id not in pk_candidates
        ]
        return _with_trace(
            state,
            engine,
            "sheriff_pk_vote_start",
            before,
            next_node="sheriff_pk_vote_turn" if vote_order else "resolve_sheriff_pk_vote",
            sheriff_vote_order=vote_order,
            sheriff_vote_index=0,
        )

    async def _sheriff_pk_vote_turn(self, state: GameGraphState) -> GameGraphState:
        """推进警长 PK 投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("sheriff_vote_order") or [])
        index = int(state.get("sheriff_vote_index") or 0)
        if index >= len(order):
            return _with_trace(state, engine, "sheriff_pk_vote_turn", before, next_node="resolve_sheriff_pk_vote")

        voter_id = order[index]
        legal_targets = legal_sheriff_vote_targets(engine.state, voter_id)
        if voter_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="sheriff_vote",
                player_id=HUMAN_PLAYER_ID,
                prompt="警长 PK 投票，请选择一名 PK 候选人，也可以弃票。",
                legal_targets=legal_targets,
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.cast_sheriff_vote(voter_id, submit.target_id)
        else:
            decision = await self._agent_for(engine, voter_id).decide(
                engine.state,
                "进行警长 PK 投票。请在 PK 候选人中选择更可信的警长，也可以弃票。",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
            decision = validate_agent_decision(engine.state, voter_id, decision)
            engine.cast_sheriff_vote(
                voter_id,
                None if decision.action_type == "abstain" else decision.target_id,
                public_reason=decision.public_reason,
                reasoning_score=_decision_score_for_target(decision),
            )

        return _with_trace(
            state,
            engine,
            "sheriff_pk_vote_turn",
            before,
            next_node="sheriff_pk_vote_turn",
            sheriff_vote_index=index + 1,
        )

    async def _resolve_sheriff_pk_vote(self, state: GameGraphState) -> GameGraphState:
        """结算警长 PK 投票，再平票则警徽流失。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        result = engine.resolve_sheriff_vote(final_round=True)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_sheriff_pk_vote",
            before,
            next_node="day_speech_start",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _day_speech_start(self, state: GameGraphState) -> GameGraphState:
        """生成本轮白天发言顺序。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        direction = await self._sheriff_speech_direction(state, engine)
        speech_order = _day_speech_order(engine.state, direction=direction)
        return _with_trace(
            state,
            engine,
            "day_speech_start",
            before,
            next_node="day_speech_turn",
            speech_order=speech_order,
            speech_index=0,
            speech_direction=direction,
        )

    async def _sheriff_speech_direction(
        self,
        state: GameGraphState,
        engine: WerewolfEngine,
    ) -> Literal["clockwise", "counterclockwise"] | None:
        """让存活警长选择白天发言方向；无警长时返回 None。"""
        sheriff_id = _living_sheriff_id(engine.state)
        if sheriff_id is None:
            return None
        if sheriff_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="sheriff_order",
                player_id=HUMAN_PLAYER_ID,
                prompt="你是警长，请选择本轮发言顺序：从左边逆时针开始，或从右边顺时针开始。你会最后发言总结。",
                legal_targets=[],
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            if submit.direction in {"clockwise", "counterclockwise"}:
                return submit.direction
            raise InvalidActionError("警长发言顺序需要 direction。")
        agent = self._agent_for(engine, sheriff_id)
        if not hasattr(agent, "decide_sheriff_order"):
            return "counterclockwise"
        decision = await agent.decide_sheriff_order(
            engine.state,
            "你是警长，请选择本轮白天发言顺序。direction=counterclockwise 表示从你左边逆时针开始；direction=clockwise 表示从你右边顺时针开始；你必须让自己最后发言总结。",
            public_memory=dict(state.get("public_memory") or {}),
            private_memories=dict(state.get("private_memories") or {}),
            wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
        )
        decision = validate_sheriff_order_decision(decision)
        return decision.direction

    async def _day_speech_turn(self, state: GameGraphState) -> GameGraphState:
        """推进一个白天发言玩家，真人发言会触发 interrupt。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        speech_order = list(state.get("speech_order") or [])
        speech_index = int(state.get("speech_index") or 0)
        if speech_index >= len(speech_order):
            return _with_trace(
                state,
                engine,
                "day_speech_turn",
                before,
                next_node="day_speech_summary",
            )

        actor_id = speech_order[speech_index]
        stream_id = _speech_stream_id(
            "day_speech_turn",
            engine.state.round_no,
            actor_id,
            speech_index,
        )
        if _speech_stream_completed(state, engine.state, stream_id):
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "day_speech_turn",
                before,
                next_node="day_speech_turn",
                speech_index=speech_index + 1,
                public_memory=public_memory,
                event_cursor=cursor,
            )
        if actor_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="speak",
                player_id=HUMAN_PLAYER_ID,
                prompt="轮到你白天发言。",
                legal_targets=[],
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.record_speech(HUMAN_PLAYER_ID, submit.speech, turn_key=stream_id)
        else:
            decision = await self._decide_streamed_speech(
                engine,
                state,
                actor_id,
                task="进行白天公开发言",
                node_name="day_speech_turn",
                stream_id=stream_id,
            )
            speech = decision.speech
            engine.record_speech(actor_id, speech, turn_key=stream_id)
            await self._publish_agent_reply(
                engine,
                actor_id,
                "agent_reply_completed",
                node_name="day_speech_turn",
                stream_id=stream_id,
                text=speech,
            )

        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "day_speech_turn",
            before,
            next_node="day_speech_turn",
            speech_index=speech_index + 1,
            public_memory=public_memory,
            event_cursor=cursor,
            completed_speech_stream_ids=_mark_speech_stream_completed(state, stream_id),
        )

    async def _day_speech_summary(self, state: GameGraphState) -> GameGraphState:
        """把本轮公开发言压缩成公共摘要。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        public_memory = summarize_current_speech_round(
            engine.state,
            dict(state.get("public_memory") or {}),
        )
        return _with_trace(
            state,
            engine,
            "day_speech_summary",
            before,
            next_node="day_vote_start",
            public_memory=public_memory,
        )

    async def _day_vote_start(self, state: GameGraphState) -> GameGraphState:
        """调用规则引擎进入投票阶段，并生成投票顺序。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        if engine.state.phase is Phase.DAY_SPEECH:
            engine.start_vote()
        vote_order = [
            player.player_id
            for player in sorted(voting_players(engine.state), key=lambda item: item.seat)
        ]
        return _with_trace(
            state,
            engine,
            "day_vote_start",
            before,
            next_node="day_vote_turn",
            vote_order=vote_order,
            vote_index=0,
        )

    async def _day_vote_turn(self, state: GameGraphState) -> GameGraphState:
        """推进一个白天投票玩家，真人投票会触发 interrupt。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        vote_order = list(state.get("vote_order") or [])
        vote_index = int(state.get("vote_index") or 0)
        if vote_index >= len(vote_order):
            return _with_trace(state, engine, "day_vote_turn", before, next_node="resolve_vote")

        voter_id = vote_order[vote_index]
        if voter_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="vote",
                player_id=HUMAN_PLAYER_ID,
                prompt="请选择你要投票放逐的目标，也可以弃票。",
                legal_targets=legal_vote_targets(engine.state, HUMAN_PLAYER_ID),
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            _apply_human_action(engine, submit)
        else:
            decision = await self._agent_for(engine, voter_id).decide(
                engine.state,
                "进行白天投票",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
            decision = validate_agent_decision(engine.state, voter_id, decision)
            if decision.action_type == "abstain":
                engine.cast_vote(voter_id, None)
            else:
                engine.cast_vote(
                    voter_id,
                    decision.target_id,
                    public_reason=decision.public_reason,
                    reasoning_score=_decision_score_for_target(decision),
                )

        return _with_trace(
            state,
            engine,
            "day_vote_turn",
            before,
            next_node="day_vote_turn",
            vote_index=vote_index + 1,
        )

    async def _resolve_vote(self, state: GameGraphState) -> GameGraphState:
        """调用规则引擎结算投票，并同步公开事件。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        if engine.state.phase is Phase.DAY_VOTE:
            result = engine.resolve_vote(is_pk=False)
            if result.exiled_player_id is not None:
                next_node = "resolve_exile_reactions"
            elif result.tied_player_ids:
                next_node = "exile_pk_speech"
            else:
                next_node = "public_vote_summary"
        else:
            next_node = "public_vote_summary"
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_vote",
            before,
            next_node=next_node,
            public_memory=public_memory,
            event_cursor=cursor,
            pk_speech_order=list(engine.state.vote_history[-1].tied_player_ids if engine.state.vote_history else []),
            pk_speech_index=0,
        )

    async def _exile_pk_speech(self, state: GameGraphState) -> GameGraphState:
        """放逐平票后的 PK 发言。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        order = list(state.get("pk_speech_order") or [])
        index = int(state.get("pk_speech_index") or 0)
        if index >= len(order):
            return _with_trace(
                state,
                engine,
                "exile_pk_speech",
                before,
                next_node="exile_pk_vote_start",
            )
        actor_id = order[index]
        stream_id = _speech_stream_id("exile_pk_speech", engine.state.round_no, actor_id, index)
        if _speech_stream_completed(state, engine.state, stream_id):
            public_memory, cursor = sync_new_public_events(
                engine.state,
                dict(state.get("public_memory") or {}),
                int(state.get("event_cursor", 0)),
            )
            return _with_trace(
                state,
                engine,
                "exile_pk_speech",
                before,
                next_node="exile_pk_speech",
                pk_speech_index=index + 1,
                public_memory=public_memory,
                event_cursor=cursor,
            )
        if actor_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="speak",
                player_id=HUMAN_PLAYER_ID,
                prompt="你进入放逐 PK，请发表 PK 发言。",
                legal_targets=[],
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            engine.record_speech(HUMAN_PLAYER_ID, submit.speech, turn_key=stream_id)
        else:
            decision = await self._decide_streamed_speech(
                engine,
                state,
                actor_id,
                task="进行放逐 PK 发言",
                node_name="exile_pk_speech",
                stream_id=stream_id,
            )
            speech = decision.speech or "我进入 PK，会继续说明自己的票型和判断。"
            engine.record_speech(actor_id, speech, turn_key=stream_id)
            await self._publish_agent_reply(
                engine,
                actor_id,
                "agent_reply_completed",
                node_name="exile_pk_speech",
                stream_id=stream_id,
                text=speech,
            )
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "exile_pk_speech",
            before,
            next_node="exile_pk_speech",
            pk_speech_index=index + 1,
            public_memory=public_memory,
            event_cursor=cursor,
            completed_speech_stream_ids=_mark_speech_stream_completed(state, stream_id),
        )

    async def _exile_pk_vote_start(self, state: GameGraphState) -> GameGraphState:
        """进入放逐 PK 投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        tied = tuple(state.get("pk_speech_order") or engine.state.pk_tied_player_ids)
        engine.start_pk_vote(tied)
        vote_order = [
            player.player_id
            for player in sorted(voting_players(engine.state), key=lambda item: item.seat)
            if player.player_id not in set(tied)
        ]
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "exile_pk_vote_start",
            before,
            next_node="exile_pk_vote_turn" if vote_order else "resolve_exile_pk_vote",
            vote_order=vote_order,
            vote_index=0,
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _exile_pk_vote_turn(self, state: GameGraphState) -> GameGraphState:
        """推进放逐 PK 投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        vote_order = list(state.get("vote_order") or [])
        vote_index = int(state.get("vote_index") or 0)
        if vote_index >= len(vote_order):
            return _with_trace(state, engine, "exile_pk_vote_turn", before, next_node="resolve_exile_pk_vote")

        voter_id = vote_order[vote_index]
        legal_targets = legal_vote_targets(engine.state, voter_id, candidates=engine.state.pk_tied_player_ids)
        if voter_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="vote",
                player_id=HUMAN_PLAYER_ID,
                prompt="请在 PK 玩家中投票，也可以弃票。",
                legal_targets=legal_targets,
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            if submit.action_type == "abstain":
                engine.cast_vote(voter_id, None)
            else:
                engine.cast_vote(voter_id, submit.target_id)
        else:
            decision = await self._agent_for(engine, voter_id).decide(
                engine.state,
                "进行放逐 PK 投票",
                public_memory=dict(state.get("public_memory") or {}),
                private_memories=dict(state.get("private_memories") or {}),
                wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
            )
            decision = validate_agent_decision(engine.state, voter_id, decision)
            engine.cast_vote(
                voter_id,
                None if decision.action_type == "abstain" else decision.target_id,
                public_reason=decision.public_reason,
                reasoning_score=_decision_score_for_target(decision),
            )

        return _with_trace(
            state,
            engine,
            "exile_pk_vote_turn",
            before,
            next_node="exile_pk_vote_turn",
            vote_index=vote_index + 1,
        )

    async def _resolve_exile_pk_vote(self, state: GameGraphState) -> GameGraphState:
        """结算放逐 PK 投票。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        result = engine.resolve_vote(is_pk=True)
        next_node = "resolve_exile_reactions" if result.exiled_player_id else "public_vote_summary"
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_exile_pk_vote",
            before,
            next_node=next_node,
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _resolve_exile_reactions(self, state: GameGraphState) -> GameGraphState:
        """处理白天放逐后的猎人、白痴和警徽移交。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        hunter_target = _reaction_hunter_target(engine, self._pending_sink)
        idiot_reveal = _reaction_idiot_reveal(engine, self._pending_sink)
        sheriff_handoff = await self._reaction_sheriff_handoff(engine, state)
        engine.resolve_death_reactions(
            hunter_shot_target_id=hunter_target,
            idiot_reveal=idiot_reveal,
            sheriff_handoff_target_id=sheriff_handoff,
        )
        if hunter_target and engine.state.sheriff_id == hunter_target:
            followup_handoff = await self._reaction_sheriff_handoff(engine, state)
            engine.resolve_death_reactions(sheriff_handoff_target_id=followup_handoff)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "resolve_exile_reactions",
            before,
            next_node="public_vote_summary",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _public_vote_summary(self, state: GameGraphState) -> GameGraphState:
        """投票后公共摘要节点，保留为独立 trace 节点。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        return _with_trace(
            state,
            engine,
            "public_vote_summary",
            before,
            next_node="check_win_after_vote",
        )

    async def _check_win_after_vote(self, state: GameGraphState) -> GameGraphState:
        """投票后检查胜负，决定结束或进入下一轮。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        next_node = "game_over" if engine.state.is_over else "start_round"
        return _with_trace(state, engine, "check_win_after_vote", before, next_node=next_node)

    async def _start_round(self, state: GameGraphState) -> GameGraphState:
        """调用规则引擎开启下一轮夜晚，并清理图内临时顺序。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        if not engine.state.is_over:
            engine.start_next_round()
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "start_round",
            before,
            next_node="check_win_before_round",
            public_memory=public_memory,
            event_cursor=cursor,
            speech_order=[],
            vote_order=[],
            speech_index=0,
            vote_index=0,
            speech_direction=None,
            completed_speech_stream_ids=[],
            pending_wolf_proposals={},
            wolf_consensus_attempts=0,
        )

    async def _game_over(self, state: GameGraphState) -> GameGraphState:
        """游戏结束节点，负责最后一次同步公开事件并终止图。"""
        engine = _engine_from_state(state)
        before = _trace_summary(engine.state)
        public_memory, cursor = sync_new_public_events(
            engine.state,
            dict(state.get("public_memory") or {}),
            int(state.get("event_cursor", 0)),
        )
        return _with_trace(
            state,
            engine,
            "game_over",
            before,
            next_node="__end__",
            public_memory=public_memory,
            event_cursor=cursor,
        )

    async def _reaction_sheriff_handoff(
        self,
        engine: WerewolfEngine,
        state: GameGraphState,
    ) -> str | None:
        """返回死亡反应中警徽移交目标，AI 警长由模型判断信任对象。"""
        dead_ids = set(engine.state.last_dead_player_ids)
        if engine.state.last_exiled_player_id:
            dead_ids.add(engine.state.last_exiled_player_id)
        if engine.state.sheriff_id not in dead_ids:
            return None
        targets = [
            player.player_id
            for player in sorted(alive_players(engine.state), key=lambda item: item.seat)
            if player.player_id != engine.state.sheriff_id
        ]
        if not targets:
            return None
        if engine.state.sheriff_id == HUMAN_PLAYER_ID:
            request = PendingActionResponse(
                action_type="sheriff_handoff",
                player_id=HUMAN_PLAYER_ID,
                prompt="你是出局警长，请选择警徽移交对象，也可以不移交。",
                legal_targets=targets,
                can_skip=True,
            )
            payload = _interrupt_for_human(engine, request, self._pending_sink)
            submit = SubmitActionRequest.model_validate(payload)
            return submit.target_id
        target_options = "、".join(player_label_by_id(engine.state, target_id) for target_id in targets)
        decision = await self._agent_for(engine, str(engine.state.sheriff_id)).decide_sheriff_handoff(
            engine.state,
            f"你是刚出局的警长，请基于公开信息、发言和你的合法私有信息选择最信任的存活玩家移交警徽。"
            f"只能从这些候选中选择 target_id：{target_options}；若确实无人可信，输出 abstain 撕毁警徽。",
            public_memory=dict(state.get("public_memory") or {}),
            private_memories=dict(state.get("private_memories") or {}),
            wolf_shared_memory=dict(state.get("wolf_shared_memory") or {}),
        )
        decision = validate_sheriff_handoff_decision(decision, targets)
        return decision.target_id


class GraphRuntime:
    """进程内 LangGraph 运行时；进程退出后故意丢弃所有游戏。"""

    def __init__(
        self,
        *,
        pending_sink: PendingSink,
        agent_factory: AgentFactory | None = None,
        stream_sink: StreamSink | None = None,
    ) -> None:
        """创建内存 checkpointer 和图控制器。"""
        self._pending_sink = pending_sink
        self._agent_factory = agent_factory
        self._checkpointer = MemorySaver()
        self._controller = WerewolfGraphController(
            checkpointer=self._checkpointer,
            pending_sink=self._pending_sink,
            agent_factory=self._agent_factory,
            stream_sink=stream_sink,
        )

    async def initialize(self, *, game_id: str, engine: WerewolfEngine) -> None:
        """为某局游戏写入初始图状态。"""
        await self._controller.initialize(game_id=game_id, engine=engine)

    async def advance(self, game_id: str) -> GameGraphState:
        """推进某局游戏的一个图节点。"""
        return await self._controller.advance(game_id)

    async def resume(self, game_id: str, request: SubmitActionRequest) -> GameGraphState:
        """用真人输入恢复某局被暂停的图。"""
        return await self._controller.resume(game_id, request)

    async def load(self, game_id: str) -> GameGraphState:
        """读取某局游戏最新图状态。"""
        return await self._controller.load(game_id)

    async def close(self) -> None:
        """关闭运行时资源；当前内存实现无需额外清理。"""
        return None


def _default_agent_factory(player_id: str, player_index: int) -> TextAgent:
    """创建默认在线文本 Agent。"""
    return TextAgent(player_id, player_index=player_index)


def _speech_stream_id(node_name: str, round_no: int, actor_id: str, index: int) -> str:
    """Return a stable id for one transient public speech stream."""
    return f"{node_name}:{round_no}:{index}:{actor_id}"


def _speech_stream_completed(
    graph_state: GameGraphState,
    game_state: GameState,
    stream_id: str,
) -> bool:
    """Return whether the speech stream was already committed."""
    if stream_id in set(graph_state.get("completed_speech_stream_ids") or []):
        return True
    return any(
        event.event_type is EventType.SPEECH_RECORDED
        and event.payload.get("turn_key") == stream_id
        for event in game_state.events
    )


def _mark_speech_stream_completed(state: GameGraphState, stream_id: str) -> list[str]:
    """Return completed speech stream ids with the current stream recorded once."""
    completed = list(state.get("completed_speech_stream_ids") or [])
    if stream_id not in completed:
        completed.append(stream_id)
    return completed[-120:]


def _agent_decide_accepts_stream(agent: object) -> bool:
    """判断 Agent 的 decide 方法是否接受流式发言参数。"""
    try:
        parameters = signature(agent.decide).parameters  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return False
    return "stream_speech" in parameters or any(
        parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _state_from_engine(engine: WerewolfEngine) -> GameGraphState:
    """根据规则引擎状态构建初始图状态。"""
    return {
        "game": serialize_game_state(engine.state),
        "public_memory": initial_public_memory(engine.state),
        "private_memories": initial_private_memories(engine.state),
        "wolf_shared_memory": initial_wolf_shared_memory(engine.state),
        "speech_order": [],
        "speech_index": 0,
        "vote_order": [],
        "vote_index": 0,
        "event_cursor": len(engine.state.events),
        "wolf_consensus_attempts": 0,
        "pending_wolf_proposals": {},
        "pending_seer_decision": {},
        "pending_witch_decision": {},
        "reaction_queue": [],
        "reaction_index": 0,
        "speech_direction": None,
        "sheriff_candidate_order": [],
        "sheriff_candidate_index": 0,
        "pending_sheriff_candidates": [],
        "sheriff_speech_order": [],
        "sheriff_speech_index": 0,
        "sheriff_vote_order": [],
        "sheriff_vote_index": 0,
        "pk_speech_order": [],
        "pk_speech_index": 0,
        "completed_speech_stream_ids": [],
        "last_node": "bootstrap_game",
        "next_node": "check_win_before_round",
        "node_trace": [],
    }


def _engine_from_state(state: GameGraphState) -> WerewolfEngine:
    """从图状态恢复一个规则引擎包装对象。"""
    engine = WerewolfEngine.__new__(WerewolfEngine)
    engine.state = deserialize_game_state(dict(state["game"]))
    return engine


def _interrupt_for_human(
    engine: WerewolfEngine,
    request: PendingActionResponse,
    pending_sink: PendingSink,
) -> dict[str, object]:
    """登记真人待行动信息，然后通过 LangGraph interrupt 暂停。"""
    pending_sink(engine.state.game_id, request)
    resume_value = interrupt(request.model_dump(mode="json"))
    pending_sink(engine.state.game_id, None)
    return dict(resume_value)


def _with_trace(
    state: GameGraphState,
    engine: WerewolfEngine,
    node_name: str,
    before: dict[str, object],
    *,
    next_node: str,
    **updates: object,
) -> GameGraphState:
    """返回带有更新字段和精简节点轨迹的新图状态。"""
    after = _trace_summary(engine.state)
    trace = list(state.get("node_trace") or [])
    trace.append(
        {
            "node": node_name,
            "input": before,
            "output": after,
            "next": next_node,
        }
    )
    return {
        **state,
        **updates,
        "game": serialize_game_state(engine.state),
        "last_node": node_name,
        "next_node": next_node,
        "node_trace": trace[-180:],
    }


def _trace_summary(state: GameState) -> dict[str, object]:
    """生成节点 trace 中使用的精简状态摘要。"""
    return {
        "round_no": state.round_no,
        "phase": state.phase.value,
        "winner": state.winner.value if state.winner else None,
        "event_count": len(state.events),
        "alive": [player.player_id for player in alive_players(state)],
    }


def _strip_interrupt(result: dict[str, Any]) -> GameGraphState:
    """从 LangGraph 返回值中移除内部 interrupt 元数据。"""
    clean = dict(result)
    clean.pop("__interrupt__", None)
    return clean


def _route_next_node(state: GameGraphState) -> str:
    """读取当前节点写入的 next_node，并交给条件边路由。"""
    return str(state.get("next_node") or "__end__")


def _apply_human_action(engine: WerewolfEngine, request: SubmitActionRequest) -> None:
    """把已通过 API schema 的真人行动提交给规则引擎。"""
    if request.action_type == "werewolf_kill":
        if request.target_id is None:
            raise InvalidActionError("狼人袭击需要 target_id。")
        engine.select_werewolf_kill(HUMAN_PLAYER_ID, request.target_id)
    elif request.action_type == "seer_check":
        if request.target_id is None:
            raise InvalidActionError("预言家查验需要 target_id。")
        engine.seer_check(HUMAN_PLAYER_ID, request.target_id)
    elif request.action_type == "witch_action":
        engine.witch_action(
            HUMAN_PLAYER_ID,
            save=request.save,
            poison_target_id=request.poison_target_id,
        )
    elif request.action_type == "hunter_shot":
        engine.resolve_death_reactions(hunter_shot_target_id=request.target_id)
    elif request.action_type == "idiot_reveal":
        engine.resolve_death_reactions(idiot_reveal=request.reveal)
    elif request.action_type == "sheriff_vote":
        engine.cast_sheriff_vote(HUMAN_PLAYER_ID, request.target_id)
    elif request.action_type == "sheriff_order":
        return
    elif request.action_type == "sheriff_handoff":
        engine.handoff_sheriff(request.target_id)
    elif request.action_type == "werewolf_self_explode":
        engine.werewolf_self_explode(HUMAN_PLAYER_ID)
    elif request.action_type == "speak":
        engine.record_speech(HUMAN_PLAYER_ID, request.speech)
    elif request.action_type == "vote":
        engine.cast_vote(HUMAN_PLAYER_ID, request.target_id)
    elif request.action_type == "abstain":
        engine.cast_vote(HUMAN_PLAYER_ID, None)
    else:
        raise InvalidActionError("不支持的真人行动。")


def _should_start_sheriff_election(state: GameState) -> bool:
    """判断是否应进入首日警长竞选。"""
    return (
        not state.sheriff_election_done
        and not state.sheriff_badge_lost
        and state.phase is not Phase.GAME_OVER
    )


def _living_sheriff_id(state: GameState) -> str | None:
    """返回当前仍存活的警长 id；无警长或警徽流失时返回 None。"""
    if state.sheriff_badge_lost or state.sheriff_id is None:
        return None
    sheriff = _player_by_id(state, state.sheriff_id)
    return sheriff.player_id if sheriff.alive else None


def _day_speech_order(
    state: GameState,
    *,
    direction: Literal["clockwise", "counterclockwise"] | None,
) -> list[str]:
    """生成白天公开发言顺序；有警长时确保警长最后发言。"""
    speakers = sorted(speaking_players(state), key=lambda item: item.seat)
    sheriff_id = _living_sheriff_id(state)
    if sheriff_id is None or direction is None:
        return [player.player_id for player in speakers]

    sheriff = _player_by_id(state, sheriff_id)
    by_seat = {player.seat: player for player in speakers}
    seat_count = len(state.players)
    step = 1 if direction == "clockwise" else -1
    order: list[str] = []
    seat = _wrap_seat(sheriff.seat + step, seat_count)
    while seat != sheriff.seat:
        player = by_seat.get(seat)
        if player is not None:
            order.append(player.player_id)
        seat = _wrap_seat(seat + step, seat_count)
    if sheriff.can_speak:
        order.append(sheriff.player_id)
    return order


def _wrap_seat(seat: int, seat_count: int) -> int:
    """把座位号折回 1..seat_count。"""
    return ((seat - 1) % seat_count) + 1


def _reaction_hunter_target(engine: WerewolfEngine, pending_sink: PendingSink) -> str | None:
    """返回死亡反应中猎人开枪目标。"""
    hunter = _triggered_role_player(engine.state, Role.HUNTER)
    if hunter is None:
        return None
    targets = legal_hunter_shot_targets(engine.state, hunter.player_id)
    if not targets:
        return None
    if hunter.player_id == HUMAN_PLAYER_ID:
        request = PendingActionResponse(
            action_type="hunter_shot",
            player_id=HUMAN_PLAYER_ID,
            prompt="你触发猎人技能，可以选择开枪带走一名玩家，也可以不开枪。",
            legal_targets=targets,
            can_skip=True,
        )
        payload = _interrupt_for_human(engine, request, pending_sink)
        submit = SubmitActionRequest.model_validate(payload)
        return submit.target_id
    return None


def _reaction_idiot_reveal(engine: WerewolfEngine, pending_sink: PendingSink) -> bool:
    """返回死亡反应中白痴是否翻牌。"""
    idiot = _triggered_role_player(engine.state, Role.IDIOT)
    if idiot is None:
        return True
    if idiot.player_id == HUMAN_PLAYER_ID:
        request = PendingActionResponse(
            action_type="idiot_reveal",
            player_id=HUMAN_PLAYER_ID,
            prompt="你被公投出局，可以翻牌成为白痴，继续发言但失去投票权。",
            legal_targets=[],
            can_skip=True,
        )
        payload = _interrupt_for_human(engine, request, pending_sink)
        submit = SubmitActionRequest.model_validate(payload)
        return submit.reveal
    return True


def _triggered_role_player(state: GameState, role: Role) -> PlayerState | None:
    """返回当前死亡反应中触发指定角色技能的玩家。"""
    trigger_ids = [
        player_id
        for player_id in (*state.last_dead_player_ids, state.last_exiled_player_id)
        if player_id
    ]
    for player_id in trigger_ids:
        player = _player_by_id(state, player_id)
        if player.role is role:
            return player
    return None


def _target_or_first(decision: AgentDecision, legal_targets: list[str]) -> str:
    """返回决策中的合法目标；缺失时使用第一个合法目标兜底。"""
    if decision.target_id in legal_targets:
        return str(decision.target_id)
    if not legal_targets:
        raise InvalidActionError("当前没有合法目标。")
    return legal_targets[0]


def _decision_score_for_target(decision: AgentDecision) -> int | None:
    """Return the suspicion score attached to the selected target."""
    if decision.target_id is None:
        return None
    score = decision.suspicion_scores.get(decision.target_id)
    return int(score) if score is not None else None


def _all_living_wolves_proposed(state: GameState, proposals: dict[str, str]) -> bool:
    """判断所有存活狼人是否都已经提交刀人提案。"""
    wolves = {player.player_id for player in alive_werewolves(state)}
    return bool(wolves) and wolves.issubset(set(proposals))


def _consensus_target(targets: list[str]) -> str | None:
    """如果所有狼队提案一致，则返回统一目标。"""
    cleaned = [target for target in targets if target]
    if not cleaned:
        return None
    first = cleaned[0]
    return first if all(target == first for target in cleaned) else None


def _most_common_or_first(targets: list[str], fallback_targets: list[str]) -> str:
    """返回出现次数最多的目标；没有提案时使用合法目标兜底。"""
    cleaned = [target for target in targets if target]
    if cleaned:
        counts = Counter(cleaned)
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    if not fallback_targets:
        raise InvalidActionError("当前没有合法目标。")
    return fallback_targets[0]


def _first_living_wolf_id(state: GameState) -> str | None:
    """按座位顺序返回一个确定性的存活狼人 id。"""
    wolves = sorted(alive_werewolves(state), key=lambda player: player.seat)
    return wolves[0].player_id if wolves else None


def _witch_memory_note(state: GameState, decision: AgentDecision) -> str:
    """根据女巫决策生成一条紧凑私有记忆。"""
    killed = state.night_actions.werewolf_target_id
    killed_label = player_label_by_id(state, killed)
    poison_label = player_label_by_id(state, decision.poison_target_id)
    if decision.save and decision.poison_target_id:
        return f"第 {state.round_no} 夜刀口 {killed_label}，使用解药并毒 {poison_label}。"
    if decision.save:
        return f"第 {state.round_no} 夜刀口 {killed_label}，使用解药。"
    if decision.poison_target_id:
        return f"第 {state.round_no} 夜刀口 {killed_label}，毒 {poison_label}。"
    return f"第 {state.round_no} 夜刀口 {killed_label}，未用药。"


def _player_by_id(state: GameState, player_id: str) -> PlayerState:
    """根据 id 返回玩家；调用方保证玩家存在。"""
    return next(player for player in state.players if player.player_id == player_id)


_ALL_NODE_NAMES = [
    "check_win_before_round",
    "night_start",
    "wolf_team_entry",
    "wolf_collect_proposals",
    "wolf_consensus",
    "wolf_reconcile",
    "wolf_commit_kill",
    "witch_action",
    "witch_commit_action",
    "seer_action",
    "seer_commit_result",
    "hunter_status",
    "idiot_confirm",
    "resolve_night",
    "dawn_announcement",
    "resolve_death_reactions",
    "check_win_after_night",
    "sheriff_election_start",
    "sheriff_candidate_collect",
    "sheriff_speech_turn",
    "sheriff_vote_start",
    "sheriff_vote_turn",
    "resolve_sheriff_vote",
    "sheriff_pk_speech",
    "sheriff_pk_vote_start",
    "sheriff_pk_vote_turn",
    "resolve_sheriff_pk_vote",
    "day_speech_start",
    "day_speech_turn",
    "day_speech_summary",
    "day_vote_start",
    "day_vote_turn",
    "resolve_vote",
    "exile_pk_speech",
    "exile_pk_vote_start",
    "exile_pk_vote_turn",
    "resolve_exile_pk_vote",
    "resolve_exile_reactions",
    "public_vote_summary",
    "check_win_after_vote",
    "start_round",
    "game_over",
]
_ROUTE_MAP = {name: name for name in _ALL_NODE_NAMES}
_ROUTE_MAP["__end__"] = END
