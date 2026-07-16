# backend/app/agents

AI 玩家和 LangGraph 编排目录，负责决定“流程走到哪个节点”“当前由谁行动”“AI 如何基于可见信息输出行动或发言”。

## 文件分工

- `graph.py` 定义整局狼人杀流程图，包含夜晚行动、警长竞选、白天发言、投票、PK、死亡技能、真人 interrupt/resume 和 AI 行动顺序。
- `text_agent.py` 为单个 AI 玩家构造玩家视角，调用在线模型，解析结构化 JSON 决策，并支持公开发言的流式预览。
- `prompts.py` 构造系统提示、行动提示和发言提示。
- `schemas.py` 定义模型必须返回的结构化决策格式。
- `validators.py` 校验 AI 决策是否匹配当前阶段、身份和合法目标，防止模型输出越权行动。
- `memory.py` 管理公共记忆、狼人共享记忆、特殊身份私有记忆和发言轮摘要。
- `personas.py` 为 AI 玩家分配稳定的人格与表达风格。

## 数据流

1. `sessions/manager.py` 调用 `GraphRuntime` 推进图。
2. `graph.py` 根据当前节点决定调用规则引擎、等待真人输入，或让 AI 行动。
3. AI 节点通过 `text_agent.py` 调用 `llm/` provider。
4. 模型输出先经过 `schemas.py` 解析，再经过 `validators.py` 校验。
5. 真实状态变更交给 `core/engine.py`，图状态再序列化回会话层。

## 常见修改入口

- 改流程节点、阶段顺序或 interrupt 行为：改 `graph.py`。
- 改 AI 思考输入、提示词或发言风格：改 `prompts.py` 和 `personas.py`。
- 改 AI 输出字段：改 `schemas.py`，并同步 `validators.py` 和 `text_agent.py`。
- 改记忆内容、狼人共享信息或私有信息边界：改 `memory.py`。
- 改模型调用参数、失败兜底或流式发言发布：改 `text_agent.py`，必要时同步 `backend/app/llm/`。

## 维护边界

Agent 可以提出行动，但不能绕过规则引擎改生死、身份、胜负等真相状态。所有真实状态变更都应通过 `backend/app/core/engine.py` 完成。
