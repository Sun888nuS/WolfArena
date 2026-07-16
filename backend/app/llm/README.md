# backend/app/llm

大模型 provider 适配层，负责把项目内部的聊天请求转换成具体模型服务调用。目前实现面向 OpenAI-compatible `/chat/completions` 接口。

## 文件分工

- `base.py` 定义 provider 协议、聊天消息、请求、响应、流式响应和统一异常。
- `openai_compatible.py` 使用 `httpx` 调用兼容 OpenAI 的聊天补全接口，支持普通响应和流式响应解析。

## 调用关系

- `agents/text_agent.py` 构造 `ChatCompletionRequest`，并调用这里的 provider。
- `api/llm_config.py` 可在运行时更新后续调用使用的 `base_url`、`model` 和 API key。
- 默认地址、模型名、超时和密钥来自 `backend/app/config.py`。

## 常见修改入口

- 改模型服务地址、模型名、超时或默认密钥：优先改 `.env` 或 `backend/app/config.py`。
- 改前端可编辑的 LLM 配置字段：同步 `api/llm_config.py` 和 `frontend/src/types/health.ts`。
- 接入新的模型供应商：新增 provider 文件，并在 Agent 构造处或配置分发处选择。
- 调整 temperature、JSON 输出要求、流式发布节奏：通常改 `agents/text_agent.py`。

## 维护边界

`llm` 只负责调用模型和返回文本，不理解狼人杀规则，也不决定行动是否合法。模型输出必须经过 `agents/validators.py` 和 `core/engine.py` 才能影响游戏。
