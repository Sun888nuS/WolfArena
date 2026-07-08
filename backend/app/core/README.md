# backend/app/core

确定性狼人杀规则核心目录，负责游戏真相状态和所有规则结算。

## 这里负责什么

- `models.py` 定义玩家、阶段、身份、事件、投票、夜晚行动缓存等领域模型。
- `engine.py` 是修改 `GameState` 的主要入口，负责夜晚行动、投票、死亡、胜负等状态变更。
- `rules.py` 提供合法目标、胜负检查、投票结算、阶段校验等纯规则函数。
- `events.py` 统一追加领域事件。
- `visibility.py` 根据玩家视角过滤可见事件和私有信息。
- `serialization.py` 负责 `GameState` 和 LangGraph 状态之间的序列化。
- `exceptions.py` 定义规则层异常。
- `player_labels.py` 提供稳定的玩家中文标签。

## 常见修改入口

- 改角色配置、胜负条件、合法行动：优先看 `rules.py` 和 `models.py`。
- 改行动如何影响状态：`engine.py`。
- 改玩家能看到什么：`visibility.py`。
- 改事件记录字段：`events.py` 和 `models.py`。
- 改图状态持久化格式：`serialization.py`。

## 边界说明

这个目录是规则真相源。前端、API、Agent 可以读取或调用规则入口，但不应复制一套规则判断，否则很容易出现“显示能点、后端不认”或“AI 认为合法、规则拒绝”的问题。
