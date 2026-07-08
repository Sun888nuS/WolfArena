# Phase 4 验收说明

Phase 4 的目标是将 Phase 3 的内存流程推进迁移到 LangGraph，并加入 checkpoint 与断线恢复能力。

## 已实现

- `LangGraph` 作为主流程控制器：
  - 夜晚狼人/预言家/女巫行动
  - 夜晚结算
  - 白天发言
  - 白天投票
  - 投票结算与下一轮
- `human-in-the-loop`：
  - 真人行动节点通过 `interrupt()` 暂停。
  - 提交行动后通过 `Command(resume=...)` 恢复同一 graph thread。
- checkpoint：
  - `CHECKPOINT_DB_PATH` 保存 LangGraph graph state。
  - `thread_id` 使用 `game_id`。
- pending action 持久化：
  - `SESSION_DB_PATH` 保存 game registry 和 pending action。
  - 刷新页面后可通过 `GET /api/games/{game_id}` 恢复当前待操作状态。
- 前端恢复：
  - 开局后保存最近 `game_id`。
  - 页面加载时优先恢复本地最近对局。
  - 如本地无记录，则尝试恢复后端最近 checkpointed game。
- 玩家展示名：
  - 真人玩家昵称继续来自开局输入。
  - AI 玩家从无数字昵称池中随机抽取，避免 `AI 2` 这类名字和座位号混淆。
- 保持规则边界：
  - Graph 节点只编排流程。
  - 规则执行仍调用 `WerewolfEngine`。
  - AI 仍只通过 `TextAgent` 产出候选决策。
- AI 行为与狼人一致性：
  - 狼人夜晚不再由单个狼人直接决定刀人目标。
  - 每名存活狼人提交一次结构化刀人意向，全部一致后才记录最终击杀目标。
  - 若狼人意向不一致，`WerewolfEngine` 记录狼队可见事件并清空本轮意向，LangGraph 继续要求重新统一。
  - AI prompt 只接收 `PlayerView`，包含公开发言、投票记录、自己的记忆、合法私有信息和狼队可见意向。
  - fallback 策略基于公开压力、票型、查验结果、队友意向和短记忆，不直接读取对手隐藏身份来决定发言或投票。
  - fallback 投票单独走个人信念推理：每个 AI 只整合自己的合法私有信息、个人记忆、谁公开攻击过自己、自己如何解读发言和已出票型，不再复用全员共享的通用投票公式。
  - 低信息局允许弃票或分散投票；强信息局仍会集中，例如预言家查到狼人、某玩家持续攻击自己或自己的历史记忆明确指向某目标。
  - 首轮第一个发言者不能凭空点名，只能说明观察框架和希望后置位回应的问题。

## 关键文件

- `backend/app/agents/graph.py`
- `backend/app/agents/prompts.py`
- `backend/app/agents/validators.py`
- `backend/app/core/serialization.py`
- `backend/app/core/visibility.py`
- `backend/app/sessions/checkpoint.py`
- `backend/app/sessions/manager.py`
- `backend/app/api/games.py`
- `frontend/src/services/game.ts`
- `frontend/src/features/game/GamePage.tsx`
- `backend/tests/test_core_rules.py`
- `backend/tests/test_game_api.py`

## 验收命令

后端：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：

```text
36 passed, 1 warning
```

前端：

```powershell
npm.cmd run build
```

结果：

```text
✓ built
```

## 不在本阶段实现

- 后台超时默认动作调度器。
- 多真人房间。
- PostgreSQL 持久化。
- AgentScope 语音。

## 后续建议

- Phase 5 接入 AgentScope 时，语音转写结果应继续提交到 LangGraph pending action。
- Phase 6 多真人房间需要把 `human_player_id` 从固定 `p1` 扩展为房间座位映射。
- Phase 7 可把当前 graph `node_trace` 暴露给复盘页面。
