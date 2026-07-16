# frontend/src

前端源码根目录，基于 React 和 TypeScript 组织应用入口、业务功能、后端服务客户端和共享类型。

## 目录分工

- `app/` 放应用入口、根组件和全局样式。
- `features/` 放面向用户的业务功能，包括鉴权、游戏主界面、复盘、语音和后续房间能力。
- `services/` 封装后端 HTTP API、WebSocket 地址和音频资源地址。
- `types/` 放前端共享的 TypeScript 类型，主要对应后端 Pydantic 响应。
- `components/` 预留跨 feature 复用的通用组件。

## 常见修改入口

- 改登录、注册、密码重置入口：看 `features/auth/`。
- 改狼人杀桌面、真人行动面板、主持播报、背景音、模型设置和复盘入口：看 `features/game/`。
- 改复盘弹窗、事件文案或分组选项：看 `features/review/`。
- 改固定主持语音播放：看 `features/voice/`。
- 改接口地址、请求函数或错误处理：看 `services/`。
- 改 API 字段类型：看 `types/`，并同步后端 `backend/app/sessions/models.py` 或鉴权 schemas。

## 维护边界

业务页面通过 `services/` 访问后端，通过 `types/` 约束数据结构。前端可以做展示态和表单校验，但不要复制后端狼人杀规则。
