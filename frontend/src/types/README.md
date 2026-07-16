# frontend/src/types

前端共享 TypeScript 类型目录，用来约束 API 响应、请求体和跨 feature 使用的数据结构。

## 文件分工

- `game.ts` 定义游戏快照、公开玩家、事件、待行动、主持播报、流程步骤、辅助面板、AI 发言流式消息和提交行动 payload。
- `auth.ts` 定义鉴权用户、登录、注册、密码重置和鉴权响应类型。
- `health.ts` 定义健康检查、LLM 配置状态和运行时 LLM 配置更新 payload。

## 对应后端

- `game.ts` 主要对应 `backend/app/sessions/models.py`。
- `auth.ts` 主要对应 `backend/app/auth/schemas.py`。
- `health.ts` 对应 `backend/app/api/health.py` 和 `backend/app/api/llm_config.py`。

## 常见修改入口

- 后端快照字段增删：同步 `game.ts`。
- 提交真人行动字段变化：同步 `SubmitActionPayload` 和后端 `SubmitActionRequest`。
- 鉴权接口字段变化：同步 `auth.ts` 和 `frontend/src/services/auth.ts`。
- LLM 配置或健康检查字段变化：同步 `health.ts` 和 `frontend/src/services/game.ts` 或 `health.ts`。

## 维护边界

类型文件不放运行时逻辑。字段含义以后端 Pydantic 模型为准，前端类型负责尽早暴露调用和展示代码中的字段不匹配。
