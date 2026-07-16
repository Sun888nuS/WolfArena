# frontend/src/app

React 应用入口层，负责挂载应用、加载全局样式，并选择顶层页面。

## 文件分工

- `main.tsx` 创建 React root，把应用挂载到 DOM，并引入全局 CSS。
- `App.tsx` 读取鉴权状态，渲染登录/注册面板或游戏主页面。
- `styles.css` 保存全局布局、鉴权界面、游戏页、弹窗、玩家卡片、行动面板和音频/模型设置等样式。
- `vite-env.d.ts` 提供 Vite 环境类型声明。

## 常见修改入口

- 增加顶层路由、切换页面或调整登录后落点：改 `App.tsx`。
- 调整全局背景、布局、按钮、弹窗或当前游戏页样式：改 `styles.css`。
- 新增 Vite 环境变量类型：改 `vite-env.d.ts`。

## 拆分建议

`styles.css` 当前承担了大量 feature 样式。继续扩展房间、复盘或语音页面时，建议只把全局基础样式留在这里，把功能强相关样式迁移到对应 `features/<feature>/` 目录。
