# backend/app/api

后端协议入口目录，负责把 HTTP 和 WebSocket 请求转换成对会话层、配置层或健康检查的调用。

## 文件分工

- `health.py` 提供健康检查响应，并返回脱敏后的 LLM 配置状态。
- `games.py` 提供游戏 REST API：创建游戏、列出进程内游戏、读取快照、提交真人行动、推进流程、强制结束和读取真人玩家上下文。
- `llm_config.py` 提供运行时 LLM 配置读取与更新接口，前端可在不重启后端的情况下修改后续 Agent 调用使用的 `base_url`、`model` 和 API key。
- `websocket.py` 提供 `/ws/games/{game_id}`，向前端推送游戏快照和 AI 发言流式消息。

## 调用关系

- 游戏接口通过 `backend/app/sessions/manager.py` 取得或推进单局会话。
- 请求和响应模型主要来自 `backend/app/sessions/models.py`。
- 游戏规则异常会映射为 400 或 404，LLM provider 异常会映射为 503。
- WebSocket 本身不计算快照，只订阅会话层发布的消息。

## 常见修改入口

- 新增前端要调用的游戏接口：改 `games.py`，并同步 `frontend/src/services/game.ts`。
- 修改快照字段或提交行动字段：先改 `sessions/models.py`，再同步 API 使用和前端类型。
- 修改模型配置接口：改 `llm_config.py`，注意不要把原始 API key 回传给前端。
- 修改 WebSocket 消息格式：同步 `sessions/manager.py` 和 `frontend/src/types/game.ts`。

## 维护边界

API 层只做协议转换、错误码映射和调用编排。它不保存游戏状态，不直接写狼人杀规则，也不直接构造 AI 决策。
