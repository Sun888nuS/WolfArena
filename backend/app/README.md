# backend/app

后端应用源码根目录，承载 FastAPI 服务、狼人杀规则核心、AI 玩家流程、鉴权、持久化和音频资源接口。

## 目录分工

- `main.py` 创建 FastAPI 应用，配置 CORS、生命周期钩子，并挂载健康检查、鉴权、LLM 配置、音频、游戏和 WebSocket 路由。
- `config.py` 通过 `.env` 和环境变量读取运行配置，包括 API 前缀、CORS、LLM、数据库、Redis、鉴权和邮件参数。
- `api/` 放业务 API 入口，主要负责游戏、健康检查、运行时 LLM 配置和 WebSocket 协议层。
- `auth/` 放注册、登录、邮箱验证码、会话 Cookie 和用户认证逻辑。
- `cache/` 放 Redis 客户端，用于验证码、限流等需要短期状态的能力。
- `db/` 放 SQLAlchemy 模型、异步会话和 Alembic 迁移。
- `core/` 放确定性的狼人杀规则、状态模型、事件、胜负结算和玩家视角可见性。
- `agents/` 放 LangGraph 流程编排、AI 玩家、提示词、记忆和模型输出校验。
- `sessions/` 管理进程内单局游戏，把规则状态、图状态和前端快照连接起来。
- `llm/` 封装 OpenAI-compatible 聊天模型 provider。
- `voice/` 提供背景音乐和固定主持语音资源接口。

## 常见修改入口

- 调整服务启动、路由挂载、CORS 或关闭资源：改 `main.py`。
- 调整环境变量、默认模型、数据库、Redis、Cookie 或邮件参数：改 `config.py`。
- 新增 HTTP 接口：优先在 `api/` 或对应业务包里新增 router，再在 `main.py` 挂载。
- 修改狼人杀规则：进入 `core/`，不要在 API 或前端复制规则。
- 修改 AI 玩家流程或提示词：进入 `agents/`，必要时同步 `llm/`。
- 修改前端快照字段：同步 `sessions/models.py`、`sessions/snapshots.py` 和 `frontend/src/types/`。

## 维护边界

`backend/app` 这一层负责装配模块。具体规则、模型调用、鉴权、数据库访问、音频资源和快照转换应留在各自子目录内，避免把跨层逻辑堆进 `main.py`。
