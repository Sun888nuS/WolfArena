# backend/app/core

确定性的狼人杀规则核心，是整局游戏真相状态的唯一来源。这里不依赖 FastAPI、React 或具体模型服务。

## 文件分工

- `models.py` 定义阵营、身份、阶段、事件类型、玩家状态、夜晚行动缓存、投票记录和 `GameState`。
- `rules.py` 提供纯规则函数：创建玩家板子、查找存活玩家、合法目标、阶段校验、投票结算和胜负判断。
- `engine.py` 是修改 `GameState` 的主要入口，负责狼人刀人、预言家查验、女巫用药、发言、投票、警长、死亡技能和胜负结算等状态变更。
- `events.py` 统一追加领域事件，保证事件字段和可见性一致。
- `visibility.py` 根据真人或 AI 玩家视角生成可见玩家、可见事件、合法行动和私有信息。
- `serialization.py` 在 dataclass 状态和 LangGraph 可持久化字典之间转换。
- `exceptions.py` 定义规则层异常。
- `player_labels.py` 生成稳定的座位号和玩家展示标签。

## 常见修改入口

- 改角色、阶段、状态字段：先改 `models.py`。
- 改 12 人或 6 人板子、合法目标、胜负条件、投票结算：改 `rules.py`。
- 改某个行动如何改变游戏真相：改 `engine.py`。
- 改事件类型或 payload：同步 `models.py`、`events.py`、`sessions/snapshots.py` 和前端复盘展示。
- 改某个身份能看到什么：改 `visibility.py`。
- 改图状态保存格式：改 `serialization.py`，并确认 `agents/graph.py` 的读写字段。

## 维护边界

前端、API 和 Agent 都可以调用这里的规则入口，但不应复制一套规则判断。所有生死、身份、胜负、投票和技能结果都应以 `core` 为准。
