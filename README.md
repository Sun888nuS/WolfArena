# WolfArena AI

WolfArena AI 是一个 6 人局多 Agent 狼人杀系统。每局只有一个真人玩家，身份随机；其余玩家由在线大模型 Agent 控制。游戏流程由 LangGraph 编排，规则结算由确定性规则引擎负责。

LLM 不能直接修改游戏状态。它只能输出候选发言和候选行动，所有行动都必须经过 schema 校验和规则校验后，才会进入规则引擎。

## 当前规则

- 6 名玩家：2 狼人、1 预言家、1 女巫、2 村民。
- 只有 1 名真人玩家，身份随机。
- 狼队使用一份共享记忆。
- 预言家、女巫拥有各自合法的私有记忆。
- 村民没有私有夜间信息，只使用公共记忆。
- 公开发言、投票、死亡、放逐、公开摘要进入公共记忆。
- 游戏只保存在当前后端进程内；关闭后端、退出程序或关机后，本局不会恢复，只能重新开局。
- 生产路径不使用本地假 Agent。如果没有配置 LLM，或模型调用失败，AI 行动会返回服务错误。

## LangGraph 节点

当前已经不是单一 `step` 节点，而是按狼人杀流程拆成多节点：

```text
check_win_before_round
night_start
wolf_team_entry
wolf_collect_proposals
wolf_consensus
wolf_reconcile
wolf_commit_kill
seer_action
seer_commit_result
witch_action
witch_commit_action
resolve_night
dawn_announcement
check_win_after_night
day_speech_start
day_speech_turn
day_speech_summary
day_vote_start
day_vote_turn
resolve_vote
public_vote_summary
check_win_after_vote
start_round
game_over
```

LangGraph 使用内存 checkpointer，支持同一后端进程内的 interrupt/resume；不会把游戏写入 SQLite 或磁盘。

## 记忆边界

```text
public_memory
  所有人可见：公开发言、投票、死亡、放逐、轮次摘要。

wolf_shared_memory
  仅狼人可见：狼队成员、夜间刀人提案、统一目标、狼队策略。

private_memories
  仅非狼人特殊身份使用：预言家的查验结果、女巫的用药记录和策略备注。

agent_profile
  每个 AI 的固定人格和表达风格，不承载局内隐藏信息。
```

狼人白天不会写入新的共享记忆，避免狼队在白天“心灵同步”。白天公开发生的内容只进入公共记忆。

## 项目结构

```text
ours/
  backend/
    app/main.py              FastAPI 入口
    app/api/                 REST 和 WebSocket 接口
    app/sessions/            内存游戏会话和前端快照
    app/agents/              LangGraph 流程、记忆模型、prompt、在线 Agent
    app/core/                确定性狼人杀规则引擎
    app/llm/                 OpenAI-compatible provider 适配器
    scripts/                 LLM 测试和完整对局试玩脚本
    tests/                   规则和 API 测试
  frontend/
    src/app/                 React 应用入口和样式
    src/features/game/       可玩的游戏界面
    src/services/            HTTP 和 WebSocket 客户端
    src/types/               API 类型
```

## 配置模型

复制 `.env.example` 为 `.env`，然后配置 OpenAI-compatible 模型服务：

```text
LLM_BASE_URL=https://your-relay.example.com/v1
LLM_API_KEY=sk-your-relay-key
LLM_MODEL=gpt-4o-mini
```

## 启动后端

```powershell
cd backend
$env:UV_CACHE_DIR=".uv-cache"
uv sync --extra dev
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```text
http://localhost:8000/api/health
```

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:5173
```

## 测试

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

完整对局试玩：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/play_full_game.py
```

这个脚本会注入确定性测试 Agent，并自动处理真人 interrupt，用来验证整局能从开局跑到最终胜负。
