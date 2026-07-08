# frontend/src/types

前端 TypeScript 类型目录，负责约束 API 响应、请求体和页面使用的数据结构。

## 这里负责什么

- `game.ts` 定义游戏快照、玩家、事件、待行动、提交行动 payload 等类型。
- `health.ts` 定义健康检查响应类型。

## 常见修改入口

- 后端 `backend/app/sessions/models.py` 增删字段后，要同步这里。
- 前端页面读取新字段前，先在这里补类型。
- 提交行动 payload 新增字段时，同步 `SubmitActionPayload` 和后端请求模型。

## 边界说明

类型文件不放运行时逻辑。字段含义以后端 Pydantic 模型为准，前端类型负责尽量提前暴露不匹配问题。
