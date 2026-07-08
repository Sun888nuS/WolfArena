# backend/app/api

HTTP 和 WebSocket 接口层，负责把外部请求转交给会话管理层。

## 这里负责什么

- `health.py` 提供健康检查接口。
- `games.py` 提供开局、读取快照、提交真人行动、推进流程等 REST API。
- `websocket.py` 提供单局游戏快照订阅。

## 常见修改入口

- 新增或调整前端调用的接口：在这里新增 router 或修改对应文件。
- 改请求/响应字段：优先先修改 `backend/app/sessions/models.py`，再调整 API 使用。
- 改游戏推进规则：不要在这里写规则逻辑，去 `backend/app/core/` 或 `backend/app/agents/`。

## 边界说明

API 层只做协议转换、错误码映射和调用编排，不保存游戏状态，不直接调用 LLM，也不直接修改 `GameState`。
