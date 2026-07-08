# backend/app/sessions

进程内游戏会话层，负责把 LangGraph 运行时、真人 pending action、WebSocket 订阅和前端快照串起来。

## 这里负责什么

- `manager.py` 创建和保存当前进程内的游戏会话，串行推进单局游戏，发布快照。
- `models.py` 定义 API 请求、响应、前端快照、待行动等 Pydantic 模型。
- `snapshots.py` 把规则状态和图状态转换成真人玩家视角的 `GameSnapshotResponse`。

## 常见修改入口

- 改前端需要的快照字段：`models.py` 和 `snapshots.py`。
- 改开局玩家昵称、真人玩家位置、会话生命周期：`manager.py`。
- 改上帝播报、流程进度条、当前行动者高亮：`snapshots.py`。
- 改 WebSocket 推送行为：`manager.py`，同时检查 `backend/app/api/websocket.py`。

## 边界说明

这里不负责规则判断，也不负责 AI 推理。会话层只协调当前进程内的单局状态、快照和订阅关系。
