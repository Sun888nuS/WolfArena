"""内存会话管理层。

本模块只负责创建和保存当前进程内的游戏会话、处理真人 pending action、
以及向 WebSocket 订阅者发布快照。规则判断在 core，流程推进在 agents.graph，
前端快照组装在 sessions.snapshots。
"""

import asyncio
from random import Random

from fastapi import WebSocket

from app.agents.graph import GraphRuntime, HUMAN_PLAYER_ID
from app.core.engine import WerewolfEngine
from app.core.exceptions import InvalidActionError
from app.core.serialization import deserialize_game_state
from app.sessions.snapshots import build_snapshot_response
from app.sessions.models import (
    GameSnapshotResponse,
    PendingActionResponse,
    SubmitActionRequest,
)


AI_NAME_POOL: tuple[str, ...] = (
    "青岚",
    "南枝",
    "白术",
    "云舒",
    "星河",
    "听雨",
    "墨川",
    "栖梧",
    "阿洛",
    "小满",
    "知夏",
    "清和",
    "若水",
    "长风",
    "明澈",
    "晚舟",
)


WebSocketPayload = dict[str, object]


class GameSession:
    """单局进程内游戏会话，负责串行化推进和发布快照。"""

    def __init__(
        self,
        *,
        game_id: str,
        runtime: GraphRuntime,
        pending_actions: dict[str, PendingActionResponse],
    ) -> None:
        """绑定游戏 id、图运行时和共享 pending action 注册表。"""
        self.game_id = game_id
        self._runtime = runtime
        self._pending_actions = pending_actions
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[WebSocketPayload]] = set()

    async def start(self) -> GameSnapshotResponse:
        """返回开局后的初始快照并通知订阅者。"""
        snapshot = await self.snapshot()
        await self.publish(snapshot)
        return snapshot

    async def advance(self) -> GameSnapshotResponse:
        """推进一个 LangGraph 节点；如果正在等待真人，则只返回当前快照。"""
        async with self._lock:
            if self._pending_actions.get(self.game_id) is None:
                await self._runtime.advance(self.game_id)
            snapshot = await self.snapshot()
        await self.publish(snapshot)
        return snapshot

    async def submit_action(self, request: SubmitActionRequest) -> GameSnapshotResponse:
        """提交真人行动并恢复被 interrupt 暂停的 LangGraph。"""
        async with self._lock:
            pending = self._pending_actions.get(self.game_id)
            if pending is None:
                raise InvalidActionError("No pending human action.")
            if request.action_type != pending.action_type:
                if not (
                    pending.action_type in {"vote", "sheriff_vote", "sheriff_run"}
                    and request.action_type == "abstain"
                ):
                    raise InvalidActionError("Submitted action does not match pending action.")
            self._pending_actions.pop(self.game_id, None)
            try:
                await self._runtime.resume(self.game_id, request)
            except Exception:
                self._pending_actions[self.game_id] = pending
                raise
            snapshot = await self.snapshot()
        await self.publish(snapshot)
        return snapshot

    async def finish(self) -> GameSnapshotResponse:
        """强制结束当前局，并保留已有事件用于复盘。"""
        async with self._lock:
            self._pending_actions.pop(self.game_id, None)
            await self._runtime.force_finish(self.game_id)
            snapshot = await self.snapshot()
        await self.publish(snapshot)
        return snapshot

    async def snapshot(self) -> GameSnapshotResponse:
        """读取图状态并构建真人玩家视角快照。"""
        graph_state = await self._runtime.load(self.game_id)
        if "game" not in graph_state:
            raise InvalidActionError(f"Unknown game id: {self.game_id}")
        state = deserialize_game_state(dict(graph_state["game"]))
        pending_action = self._pending_actions.get(self.game_id)
        last_node = str(graph_state.get("last_node") or "")
        speech_order = list(graph_state.get("speech_order") or [])
        speech_index = int(graph_state.get("speech_index") or 0)
        vote_order = list(graph_state.get("vote_order") or [])
        vote_index = int(graph_state.get("vote_index") or 0)
        if last_node == "sheriff_candidate_collect":
            speech_order = list(graph_state.get("sheriff_candidate_order") or [])
            speech_index = int(graph_state.get("sheriff_candidate_index") or 0)
        elif last_node in {"sheriff_speech_turn", "sheriff_pk_speech"}:
            speech_order = list(graph_state.get("sheriff_speech_order") or [])
            speech_index = int(graph_state.get("sheriff_speech_index") or 0)
        elif last_node in {"sheriff_vote_turn", "sheriff_pk_vote_turn"}:
            vote_order = list(graph_state.get("sheriff_vote_order") or [])
            vote_index = int(graph_state.get("sheriff_vote_index") or 0)
        return build_snapshot_response(
            state,
            game_id=self.game_id,
            human_player_id=HUMAN_PLAYER_ID,
            pending_action=pending_action,
            public_memory=dict(graph_state.get("public_memory") or {}),
            private_memories=dict(graph_state.get("private_memories") or {}),
            wolf_shared_memory=dict(graph_state.get("wolf_shared_memory") or {}),
            speech_order=speech_order,
            speech_index=speech_index,
            vote_order=vote_order,
            vote_index=vote_index,
            last_node=last_node,
        )

    async def subscribe(self, websocket: WebSocket) -> None:
        """把一个 WebSocket 连接注册为本局快照订阅者。"""
        await websocket.accept()
        queue: asyncio.Queue[WebSocketPayload] = asyncio.Queue(maxsize=80)
        self._subscribers.add(queue)
        await websocket.send_json((await self.snapshot()).model_dump(mode="json"))
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        finally:
            self._subscribers.discard(queue)

    async def publish(self, snapshot: GameSnapshotResponse) -> None:
        """向所有仍然可用的 WebSocket 订阅者发布快照。"""
        await self._publish_payload(snapshot.model_dump(mode="json"))

    async def publish_stream(self, payload: WebSocketPayload) -> None:
        """向订阅者发布非持久化的 AI 发言预览。"""
        await self._publish_payload(payload)

    async def _publish_payload(self, payload: WebSocketPayload) -> None:
        """向所有仍然可用的 WebSocket 订阅者发布一条消息。"""
        dead: list[asyncio.Queue[WebSocketPayload]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                if not _replace_oldest_queue_payload(queue, payload):
                    dead.append(queue)
        for queue in dead:
            self._subscribers.discard(queue)


class GameSessionManager:
    """进程内会话注册表；后端重启后不会恢复旧局。"""

    def __init__(self) -> None:
        """创建共享图运行时、会话表和真人 pending action 表。"""
        self._pending_actions: dict[str, PendingActionResponse] = {}
        self._runtime = GraphRuntime(
            pending_sink=self._set_pending_action,
            stream_sink=self._publish_stream_event,
        )
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    async def create_game(self, *, seed: int | None, player_name: str) -> GameSnapshotResponse:
        """创建新游戏、初始化 LangGraph 状态并返回初始快照。"""
        names = [player_name, *_ai_player_names(seed, count=11)]
        engine = WerewolfEngine(names, human_player_id=HUMAN_PLAYER_ID, seed=seed)
        game_id = engine.state.game_id
        async with self._lock:
            await self._runtime.initialize(game_id=game_id, engine=engine)
            session = self._session_for(game_id)
        return await session.start()

    async def get(self, game_id: str) -> GameSession:
        """根据 game_id 返回当前进程内仍然存在的会话。"""
        if game_id not in self._sessions:
            raise InvalidActionError(f"Unknown game id: {game_id}")
        return self._session_for(game_id)

    def list_game_ids(self) -> list[str]:
        """返回当前进程内仍存在的游戏 id，最新创建的排在前面。"""
        return list(reversed(list(self._sessions)))

    async def close(self) -> None:
        """关闭运行时并清空所有进程内会话引用。"""
        await self._runtime.close()
        self._sessions.clear()
        self._pending_actions.clear()

    def _session_for(self, game_id: str) -> GameSession:
        """返回或创建轻量会话包装对象。"""
        if game_id not in self._sessions:
            self._sessions[game_id] = GameSession(
                game_id=game_id,
                runtime=self._runtime,
                pending_actions=self._pending_actions,
            )
        return self._sessions[game_id]

    def _set_pending_action(self, game_id: str, pending: PendingActionResponse | None) -> None:
        """设置或清除某局正在等待的真人行动。"""
        if pending is None:
            self._pending_actions.pop(game_id, None)
        else:
            self._pending_actions[game_id] = pending

    async def _publish_stream_event(self, game_id: str, payload: WebSocketPayload) -> None:
        """把 LangGraph 运行过程中的临时预览消息转发给对应会话。"""
        session = self._sessions.get(game_id)
        if session is None:
            return
        await session.publish_stream(payload)


def _ai_player_names(seed: int | None, *, count: int) -> list[str]:
    """根据 seed 生成不带数字的唯一 AI 昵称。"""
    candidates = list(AI_NAME_POOL)
    Random(seed).shuffle(candidates)
    return candidates[:count]


def _replace_oldest_queue_payload(
    queue: asyncio.Queue[WebSocketPayload],
    payload: WebSocketPayload,
) -> bool:
    """队列满时丢弃最旧消息并保留订阅者，避免流式预览挤掉后续快照。"""
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        return False
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        return False
    return True


manager = GameSessionManager()
