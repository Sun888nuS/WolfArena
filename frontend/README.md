# frontend

前端 React + Vite 应用目录，负责狼人杀桌面、真人操作面板、事件流和与后端的通信。

## 这里负责什么

- `src/` 保存前端源码。
- `package.json` 定义开发、构建和预览脚本。
- `index.html` 是 Vite 页面入口。
- `Dockerfile`、`nginx.conf` 用于生产构建和静态资源部署。

## 常见修改入口

- 改页面展示、交互、样式：`src/app/`、`src/features/`。
- 改请求后端的方式：`src/services/`。
- 改前后端数据字段类型：`src/types/`，并同步后端 `backend/app/sessions/models.py`。
- 改前端构建命令或依赖：`package.json`。

## 当前独立性判断

目录已经按 app、features、services、types 分层，适合继续按功能扩展。当前 `src/features/game/GamePage.tsx` 和 `src/app/styles.css` 承载了较多 UI 子组件和样式；如果后续 UI 功能继续增加，建议把 game 内的组件、hooks、labels、样式按子功能拆开。
