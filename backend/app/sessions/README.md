# backend/app/sessions

进程内游戏会话层，负责把 LangGraph 运行时、真人待行动、前端快照和 WebSocket 订阅连接起来。

## 文件分工

- `manager.py` 管理当前后端进程里的游戏会话，创建游戏、串行推进图节点、接收真人行动、强制结束游戏、发布快照和流式消息。
- `models.py` 定义 API 请求、响应、前端快照、玩家公开信息、事件、待行动、主持播报、流程步骤和辅助面板等 Pydantic 模型。
- `snapshots.py` 把 `core` 的真实状态和 `agents` 的图状态转换成真人玩家视角的 `GameSnapshotResponse`。
- `checkpoint.py` 预留或承载会话检查点相关能力。

## 数据流

1. `api/games.py` 调用 `manager` 创建、推进或查询游戏。
2. `manager.py` 使用 `agents/graph.py` 推进 LangGraph。
3. 图运行中产生的状态由 `snapshots.py` 转成前端快照。
4. `manager.py` 将快照和 AI 发言流式消息发布给 WebSocket 订阅者。

## 常见修改入口

- 改前端快照字段：同步 `models.py`、`snapshots.py` 和 `frontend/src/types/game.ts`。
- 改开局真人昵称、AI 玩家名称、游戏列表或会话生命周期：改 `manager.py`。
- 改主持播报、固定语音 key、自动推进停留时间、流程进度、高亮行动者：改 `snapshots.py`。
- 改 WebSocket 发布节奏或消息替换策略：改 `manager.py`，并检查 `api/websocket.py` 和前端订阅逻辑。
- 改复盘可见事件：改 `snapshots.py`，并同步 `frontend/src/features/review/`。

## 维护边界

会话层不负责规则判断，也不负责 AI 推理。它只协调单局状态、图运行、真人输入、快照转换和消息发布。
