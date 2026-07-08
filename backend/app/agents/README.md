# backend/app/agents

AI 玩家和 LangGraph 流程编排目录，负责“谁在什么时候行动”和“AI 如何做决定”。

## 这里负责什么

- `graph.py` 定义狼人杀流程图、节点路由、真人 interrupt/resume 和 AI 行动顺序。
- `text_agent.py` 为单个 AI 玩家构造可见视角，调用在线模型，并返回结构化决策。
- `prompts.py` 构造发给模型的系统提示和任务提示。
- `schemas.py` 定义模型输出的结构化决策格式。
- `validators.py` 校验 AI 决策是否符合当前阶段和合法目标。
- `memory.py` 管理公共记忆、狼人共享记忆和特殊身份私有记忆。
- `personas.py` 定义 AI 玩家的固定人格和表达风格。

## 常见修改入口

- 改游戏流程节点或阶段顺序：`graph.py`。
- 改 AI 提示词、发言风格、推理输入：`prompts.py`、`personas.py`。
- 改 AI 输出字段：`schemas.py`，并同步 `validators.py`。
- 改记忆边界或摘要内容：`memory.py`。
- 改模型调用失败策略：`text_agent.py` 和 `backend/app/llm/`。

## 边界说明

这里不应直接绕过规则引擎改生死、身份、胜负等真相状态。所有真实状态变更都要通过 `backend/app/core/engine.py`。
