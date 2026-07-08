# Phase 0 验收说明

Phase 0 的目标是建立项目骨架，不实现完整狼人杀系统。

## 已实现

- `backend/app/main.py` FastAPI 入口。
- `backend/app/api/health.py` 健康检查接口。
- `backend/app/config.py` 环境变量配置。
- `backend/app/llm/openai_compatible.py` 第三方中转站 provider 占位。
- `frontend/src/app/App.tsx` 基础状态页。
- Dockerfile 和 `docker-compose.yml`。
- `.env.example` 与 `.env.production.example`。

## 验收标准

- 后端可以启动健康检查接口。
- 前端可以访问基础页面。
- 页面能显示后端状态和中转站 API 配置状态。
- Docker 文件已提供，后续可构建运行。

## 不在本阶段实现

- 游戏规则。
- LangGraph 状态图。
- LLM 实际调用。
- AgentScope 语音。
- 多真人房间。

