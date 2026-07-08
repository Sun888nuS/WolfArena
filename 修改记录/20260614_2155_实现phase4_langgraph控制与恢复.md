# 修改记录：实现 Phase 4 LangGraph 控制与恢复

## 修改时间

2026-06-14 21:55

## 修改范围

- `backend/app/agents/graph.py`
- `backend/app/core/serialization.py`
- `backend/app/sessions/checkpoint.py`
- `backend/app/sessions/manager.py`
- `backend/app/api/games.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/tests/test_game_api.py`
- `frontend/src/services/game.ts`
- `frontend/src/features/game/GamePage.tsx`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `.env.example`
- `.env.production.example`
- `README.md`
- `docs/deployment.md`
- `docs/phase-2-3.md`
- `docs/phase-4.md`

## 修改内容

- 新增 LangGraph 依赖，并将游戏流程推进迁移到 `StateGraph` 节点控制。
- 使用 `interrupt()` 与 `Command(resume=...)` 实现真人 pending action 的暂停与恢复。
- 新增 `GameState` JSON 序列化/反序列化，保证 checkpoint 数据不依赖完整 Python 对象 pickle 语义。
- 新增 SQLite 持久化：
  - `CHECKPOINT_DB_PATH` 存放 LangGraph checkpoint。
  - `SESSION_DB_PATH` 存放 game registry 和 pending action。
- 改造 `GameSessionManager`，支持从 checkpointed `game_id` 恢复快照。
- 新增 `GET /api/games`，用于前端发现最近可恢复对局。
- 前端开局后保存最近 `game_id`，页面刷新后自动恢复当前对局。
- 补充 Phase 4 文档、部署持久化说明和 README 状态。

## 验证方式

- 运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：`25 passed, 1 warning`

- 运行前端构建：

```powershell
npm.cmd run build
```

结果：构建成功，Vite 输出 `✓ built`

- 人工检查：
  - 手工创建游戏并推进到真人 pending action。
  - 通过 `GET /api/games/{game_id}` 验证 pending action 可恢复。
  - 验证提交真人行动后 graph resume 能继续推进。

## 风险与后续

- 当前 graph 采用“一次请求推进一个上帝步骤”的节奏，前端仍通过自动 `/advance` 连续推进。
- 后台超时默认动作调度器尚未实现，本阶段只保留 pending action 持久化与手动 resume。
- 多真人房间仍未实现，当前 human player 仍固定为 `p1`。
- 后续 Phase 7 可将 graph `node_trace` 暴露给复盘页面，展示每个节点输入输出摘要。
