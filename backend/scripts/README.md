# backend/scripts

后端辅助脚本目录，用于本地验证、调试和试玩。

## 这里负责什么

- `test_llm_api.py` 检查 OpenAI-compatible 模型配置是否可用。
- `play_full_game.py` 注入确定性测试 Agent，自动跑完整对局，用来验证流程能从开局推进到胜负。

## 常见修改入口

- 想快速验证模型服务：改或运行 `test_llm_api.py`。
- 想复现整局流程问题：改或运行 `play_full_game.py`。
- 想加一次性迁移或诊断脚本：可以新增脚本，但稳定能力应沉回 `backend/app/`。

## 边界说明

脚本可以组合调用应用层能力，但不要让线上路径依赖脚本文件。
