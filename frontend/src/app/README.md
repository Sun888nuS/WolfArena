# frontend/src/app

React 应用入口层，负责挂载根组件和加载全局样式。

## 这里负责什么

- `main.tsx` 把 React 应用挂载到 DOM。
- `App.tsx` 选择当前展示的顶层页面，目前直接渲染狼人杀游戏页。
- `styles.css` 保存当前全局样式和游戏页样式。
- `vite-env.d.ts` 提供 Vite 环境类型声明。

## 常见修改入口

- 改应用入口或增加路由：`App.tsx`。
- 改全局 CSS 变量、布局基础样式、当前游戏页面样式：`styles.css`。
- 改 Vite 环境变量类型：`vite-env.d.ts`。

## 后续拆分建议

现在大量游戏页样式集中在 `styles.css`。如果继续添加房间、复盘、语音等页面，建议把通用样式留在这里，把功能样式迁移到对应 `features/<feature>/` 目录。
