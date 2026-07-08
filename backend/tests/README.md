# backend/tests

后端自动化测试目录，覆盖规则引擎、API、Agent 流程和标签显示等回归场景。

## 这里负责什么

- `test_core_rules.py` 测规则引擎和核心规则。
- `test_game_api.py` 测开局、推进、提交行动等 API 行为。
- `test_agents_graph.py` 测 LangGraph 流程编排。
- `test_agent_labels.py` 测 AI/玩家标签相关行为。
- `test_health.py` 测健康检查。
- `conftest.py` 放测试共享 fixture。

## 常见修改入口

- 改 `backend/app/core/` 后，优先补规则测试。
- 改 `backend/app/api/` 或 `backend/app/sessions/models.py` 后，优先补 API 测试。
- 改 `backend/app/agents/graph.py` 后，优先补流程测试。

## 边界说明

测试里可以使用确定性 seed 或测试 Agent 来避免在线模型不稳定。不要让核心测试依赖真实 LLM 网络调用。
