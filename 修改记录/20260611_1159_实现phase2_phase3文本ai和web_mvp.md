# 修改记录：实现 Phase 2/3 文本 AI 和 Web MVP

## 修改时间

2026-06-11 11:59

## 修改范围

- `ours/backend/app/llm/base.py`
- `ours/backend/app/llm/openai_compatible.py`
- `ours/backend/app/agents/personas.py`
- `ours/backend/app/agents/prompts.py`
- `ours/backend/app/agents/schemas.py`
- `ours/backend/app/agents/text_agent.py`
- `ours/backend/app/agents/validators.py`
- `ours/backend/app/sessions/models.py`
- `ours/backend/app/sessions/manager.py`
- `ours/backend/app/api/games.py`
- `ours/backend/app/api/websocket.py`
- `ours/backend/app/main.py`
- `ours/backend/app/config.py`
- `ours/backend/app/core/rules.py`
- `ours/backend/pyproject.toml`
- `ours/backend/uv.lock`
- `ours/backend/tests/conftest.py`
- `ours/backend/tests/test_game_api.py`
- `ours/frontend/src/app/App.tsx`
- `ours/frontend/src/app/styles.css`
- `ours/frontend/src/features/game/GamePage.tsx`
- `ours/frontend/src/services/game.ts`
- `ours/frontend/src/types/game.ts`
- `ours/.env.example`
- `ours/README.md`
- `ours/docs/phase-2-3.md`
- `ours/修改记录/20260611_1159_实现phase2_phase3文本ai和web_mvp.md`

## 修改内容

- 实现 OpenAI-compatible 第三方中转站 provider，支持 `/chat/completions`。
- 新增文本 AI Agent，基于 `PlayerView` 构建 prompt，避免注入完整 `GameState`。
- 新增 `AgentDecision` 结构化输出和 validator，LLM 输出必须校验后才能进入 game-core。
- 新增 `LLM_FORCE_FALLBACK`，测试和离线环境可以强制使用本地 fallback，不调用外部 API。
- 新增内存 `GameSession` 和 `GameSessionManager`，支持单真人 `p1` + 5 AI 自动补位。
- 新增 REST API：创建游戏、查询游戏快照、提交真人行动。
- 新增 WebSocket API：推送最新游戏快照。
- 新增前端可玩页面，包含开始游戏、玩家座位、身份信息、事件流和行动面板。
- 调整狼人合法刀人目标为非狼人，避免狼人刀队友，同时让本地 fallback 更适合作为可玩 MVP。
- 修复 `.env.example`，移除真实形态 API Key，恢复为占位配置，符合安全规范。
- 新增 Phase 2/3 验收文档，并更新 README 当前状态。

## 验证方式

- 运行 `.\.venv\Scripts\python.exe -m pytest`，结果：`19 passed, 1 warning`。
- 运行 `npm.cmd run build`，前端 TypeScript 和 Vite 生产构建通过。
- 运行 FastAPI TestClient 创建游戏：`POST /api/games` 返回 `200`，并返回可用快照。
- 运行 `uv lock` 更新后端依赖锁文件。

## 风险与后续

- 当前会话存储在内存中，服务重启会丢失对局。
- 当前只支持单真人 `p1`，不是多真人房间。
- 当前 WebSocket 只推送 snapshot，尚未做细粒度事件增量和断线恢复。
- 当前 LangGraph 尚未接入，流程仍由内存 `GameSession` 推进。
- 下一步应进入 Phase 4：将会话推进迁移到 LangGraph state graph，并加入 checkpoint/resume。
