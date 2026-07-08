# Phase 2/3 验收说明

Phase 2/3 的目标是实现文本 AI MVP 和 Web 可玩 MVP。

## 已实现

### Phase 2：文本 AI MVP

- OpenAI-compatible 第三方中转站 provider：
  - `LLM_BASE_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL`
  - `LLM_TIMEOUT_SECONDS`
- `LLM_FORCE_FALLBACK` 离线开关，测试和本地无 key 时可使用确定性 fallback。
- AI 决策 schema：`AgentDecision`。
- Prompt 构建：
  - 只注入 `PlayerView`
  - 不注入完整 `GameState`
  - 不要求完整 chain-of-thought
- 决策校验：
  - 夜晚技能目标
  - 白天发言
  - 白天投票
  - 女巫救/毒
- LLM 调用失败、JSON 解析失败或 schema 失败时，自动 fallback。

### Phase 3：Web 可玩 MVP

- 内存 `GameSession`：
  - 单真人 `p1`
  - 5 个 AI 自动补位
  - 自动推进 AI 行动
  - 遇到真人行动时暂停为 `pending_action`
- REST API：
  - `POST /api/games`
  - `GET /api/games/{game_id}`
  - `POST /api/games/{game_id}/actions`
- WebSocket：
  - `WS /ws/games/{game_id}`
  - 推送最新游戏快照
- React 前端：
  - 开始游戏
  - 玩家座位
  - 身份展示
  - 事件流
  - 技能/发言/投票行动面板
  - 游戏结束后身份揭示

## 关键文件

- `backend/app/llm/openai_compatible.py`
- `backend/app/agents/text_agent.py`
- `backend/app/agents/schemas.py`
- `backend/app/agents/prompts.py`
- `backend/app/agents/validators.py`
- `backend/app/sessions/manager.py`
- `backend/app/sessions/models.py`
- `backend/app/api/games.py`
- `backend/app/api/websocket.py`
- `frontend/src/features/game/GamePage.tsx`
- `frontend/src/services/game.ts`
- `frontend/src/types/game.ts`
- `backend/tests/test_game_api.py`

## 验收命令

后端：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：

```text
19 passed, 1 warning
```

前端：

```powershell
npm.cmd run build
```

结果：

```text
✓ built
```

## 本地试玩

后端：

```powershell
cd backend
$env:UV_CACHE_DIR=".uv-cache"
uv sync --extra dev
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```powershell
cd frontend
npm.cmd install --cache .\.npm-cache
npm.cmd run dev
```

访问：

```text
http://localhost:5173
```

## 安全说明

- `.env.example` 只能放占位值，不能写真实 API Key。
- 真实第三方中转站 API Key 只能放本地 `.env` 或服务器环境变量。
- 测试通过 `LLM_FORCE_FALLBACK=true` 强制离线，不调用外部 API。

## 不在本阶段实现

- LangGraph checkpoint。
- 持久化数据库。
- 多真人房间。
- AgentScope 语音。
- 复杂角色。

## 下一步

Phase 4：

- 已完成，详见 `docs/phase-4.md`。
