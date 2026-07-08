# Phase 1 验收说明

Phase 1 的目标是实现不依赖 LLM、不依赖 UI 的最小狼人杀规则闭环。

## 已实现

- 6 人 MVP 角色配置：
  - 2 狼人
  - 1 预言家
  - 1 女巫
  - 2 村民
- 确定性规则模型：
  - `GameState`
  - `PlayerState`
  - `Role`
  - `Phase`
  - `GameEvent`
  - `NightActionBuffer`
  - `VoteResult`
  - `PlayerView`
- 夜晚行动：
  - 狼人刀人
  - 预言家验人
  - 女巫救人/毒人
- 白天行动：
  - 公开发言事件
  - 投票
  - 平票无人出局
  - 单最高票出局
- 胜负判断：
  - 狼人全出局，好人胜
  - 狼人数大于等于好人数，狼人胜
- 信息隔离：
  - 村民视图不暴露隐藏身份
  - 狼人视图知道狼队友
  - 预言家只获得目标阵营，不获得具体身份
- FakeAgent 离线模拟。
- CLI 自动跑局。
- 核心 pytest 测试。

## 关键文件

- `backend/app/core/models.py`
- `backend/app/core/rules.py`
- `backend/app/core/engine.py`
- `backend/app/core/visibility.py`
- `backend/app/core/fake_agent.py`
- `backend/app/core/simulation.py`
- `backend/app/core/cli.py`
- `backend/tests/test_core_rules.py`

## 验收命令

后端目录下执行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：

```text
16 passed, 1 warning
```

运行 CLI 模拟：

```powershell
.\.venv\Scripts\python.exe -m app.core.cli --games 3 --seed 42
```

示例输出：

```text
Simulated games: 3
Villagers wins: 0
Werewolves wins: 3
Last winner: werewolves
```

## 不在本阶段实现

- LLM 文本 Agent。
- LangGraph 状态图。
- AgentScope 语音。
- Web 房间对局。
- 多真人输入。
- 复杂角色。

## 下一步

Phase 2 将在 `game-core` 稳定基础上接入文本 LLM Agent：

- LLM provider 实际 HTTP 调用。
- AI 玩家人格。
- Pydantic 结构化输出。
- JSON 修复、重试、fallback。
- action validator 与 game-core 串联。
