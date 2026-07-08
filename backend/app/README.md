# backend/app

后端应用源码目录，是 FastAPI 服务和狼人杀业务逻辑的主体。

## 这里负责什么

- `main.py` 创建 FastAPI 应用、注册中间件和路由。
- `config.py` 读取 `.env` 和环境变量配置。
- `api/` 暴露 REST 与 WebSocket 接口。
- `core/` 保存确定性规则、状态模型、事件和可见性逻辑。
- `agents/` 保存 LangGraph 编排、AI Agent、prompt、记忆和校验逻辑。
- `sessions/` 管理进程内游戏会话，并把后端状态转换为前端快照。
- `llm/` 适配 OpenAI-compatible 模型服务。
- `db/`、`voice/` 当前是预留模块。

## 常见修改入口

- 改后端启动、CORS、路由挂载：`main.py`。
- 改环境变量、默认模型、API 前缀：`config.py`。
- 改业务能力时优先进入对应子目录，不建议把跨层逻辑直接堆到 `main.py`。

## 边界说明

这一层允许做模块装配，但具体规则、流程、模型调用和前端快照应留在各自子模块内，保持后续按功能独立开发。
