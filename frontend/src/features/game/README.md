# frontend/src/features/game

狼人杀主游戏界面目录，负责当前可玩的桌面、真人行动面板、上帝播报、规则弹窗和事件流。

## 这里负责什么

- `GamePage.tsx` 连接后端快照、订阅 WebSocket、自动推进流程，并渲染所有游戏 UI。
- 页面内包含玩家座位、行动表单、身份信息、规则说明、事件描述、阶段/角色/阵营标签转换等逻辑。

## 常见修改入口

- 改游戏桌面、玩家卡片、行动面板、事件流展示：`GamePage.tsx`。
- 改游戏页样式：目前在 `frontend/src/app/styles.css`。
- 改前端提交给后端的行动 payload：`GamePage.tsx` 的 `buildPayload`，并同步 `frontend/src/types/game.ts`。
- 改后端快照字段的读取：先同步 `frontend/src/types/game.ts`。

## 后续拆分建议

这个目录已经是独立 feature，但 `GamePage.tsx` 目前偏大。后续建议拆成：

- `components/`：`PlayerTable`、`PlayerCard`、`ActionPanel`、`EventFeed`、`RulesDialog`。
- `hooks/`：恢复游戏、WebSocket 订阅、自动推进。
- `labels.ts`：阶段、身份、阵营、事件类型文案。
- `payload.ts`：真人行动表单到后端请求体的转换。

这样以后改“规则弹窗”“事件流”“女巫操作”等子功能时，可以进入对应文件独立修改。
