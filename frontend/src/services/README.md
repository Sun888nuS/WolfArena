# frontend/src/services

前端服务客户端目录，统一封装后端 HTTP API、WebSocket 地址和音频资源地址。

## 文件分工

- `game.ts` 封装游戏相关接口：创建游戏、列出游戏、读取快照、推进流程、强制结束、提交真人行动、读取/更新 LLM 配置、生成 WebSocket 地址、生成背景音乐和固定主持语音地址。
- `auth.ts` 封装鉴权接口：发送验证码、注册、登录、密码重置、读取当前用户、刷新登录状态和退出登录。
- `health.ts` 封装健康检查接口。

## 配置

后端基础地址来自 `VITE_API_BASE_URL`，未配置时默认使用 `http://localhost:8000`。WebSocket 地址会基于同一个基础地址自动把 `http/https` 转换成 `ws/wss`。

## 常见修改入口

- 新增后端接口调用：先在对应 service 文件里加函数，再由 feature 调用。
- 修改请求或响应类型：同步 `frontend/src/types/` 和后端 Pydantic 模型。
- 修改错误提示解析：改对应函数的 `response.ok` 分支。
- 新增需要携带 Cookie 的接口：记得设置 `credentials: "include"`。

## 维护边界

service 不保存 React 状态，也不渲染 UI。它只负责网络请求、地址拼接、错误转换和响应类型收敛。
