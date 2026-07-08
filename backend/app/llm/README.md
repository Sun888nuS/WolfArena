# backend/app/llm

大模型 provider 适配层，负责把内部聊天请求转成 OpenAI-compatible API 调用。

## 这里负责什么

- `base.py` 定义通用的聊天消息、请求、响应和 provider 异常。
- `openai_compatible.py` 通过 HTTP 调用兼容 OpenAI `/chat/completions` 的模型服务。

## 常见修改入口

- 改模型服务地址、模型名、超时：优先改根目录 `.env` 或 `backend/app/config.py`。
- 接入新的模型供应商：新增 provider 文件，并在 Agent 或配置里选择它。
- 改调用参数，如 temperature、返回格式：通常从 `backend/app/agents/text_agent.py` 发起请求处调整。

## 边界说明

这里不理解狼人杀规则，也不校验玩家行动是否合法。模型响应必须回到 `backend/app/agents/validators.py` 和 `backend/app/core/engine.py` 才能影响游戏。
