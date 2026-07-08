# frontend/src/services

前端服务客户端目录，负责封装对后端 API 和 WebSocket 的访问。

## 这里负责什么

- `game.ts` 封装开局、读取游戏、推进流程、提交行动和游戏 WebSocket 地址。
- `health.ts` 封装健康检查。

## 常见修改入口

- 改后端基础地址：通过 `VITE_API_BASE_URL` 环境变量，默认是 `http://localhost:8000`。
- 新增后端接口调用：在这里增加函数，再由 feature 页面调用。
- 改错误提示解析：修改对应 service 函数里的 `response.ok` 分支。

## 边界说明

这里不放 React 状态，也不渲染 UI。service 只负责网络请求和响应转换。
