# backend

后端服务目录，负责游戏规则、流程编排、AI Agent、API 和进程内会话管理。

## 这里负责什么

- 启动 FastAPI 服务，向前端提供 REST API 和 WebSocket 快照推送。
- 使用确定性规则引擎维护游戏真相状态。
- 使用 LangGraph 编排狼人杀流程，并在真人玩家需要行动时暂停等待输入。
- 调用 OpenAI-compatible 大模型服务驱动 AI 玩家。
- 提供后端测试和辅助脚本。

## 常见修改入口

- 修改后端依赖或测试配置：`pyproject.toml`。
- 修改容器构建：`Dockerfile`。
- 修改 API、规则、Agent、会话等业务代码：`app/`。
- 跑完整对局或 LLM 连通性检查：`scripts/`。
- 增加规则、API、Agent 回归测试：`tests/`。

## 边界说明

后端不直接处理页面展示样式；前端展示字段由 `app/sessions/snapshots.py` 统一生成。LLM 也不应直接修改游戏状态，只能输出候选行动，再由规则引擎校验和落库到内存状态。
