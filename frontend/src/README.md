# frontend/src

前端源码根目录，按应用入口、业务功能、接口服务和类型定义分层。

## 这里负责什么

- `app/` 放 React 应用入口、根组件和全局样式。
- `features/` 放面向用户的业务功能页面或功能域。
- `services/` 放访问后端 API 和 WebSocket 的客户端函数。
- `types/` 放前端使用的 TypeScript 数据类型。
- `components/` 是通用组件预留目录，目前尚未接入实际组件。

## 常见修改入口

- 改狼人杀主界面：`features/game/`。
- 改全局样式或应用挂载：`app/`。
- 改接口地址、请求函数、错误处理：`services/`。
- 改数据结构声明：`types/`。

## 边界说明

业务页面应通过 `services/` 访问后端，通过 `types/` 共享数据结构，避免在组件中散落硬编码 API 路径和重复类型。
