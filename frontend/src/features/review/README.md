# frontend/src/features/review

游戏复盘功能目录，负责把后端事件流整理成玩家可读的复盘弹窗。

## 文件分工

- `GameReviewDialog.tsx` 渲染复盘弹窗，提供完整流程、夜晚行动、发言记录、投票记录和身份总览等标签页。
- `reviewFormat.ts` 把 `GameEvent` 转换成复盘时间线条目，并提供事件、阶段、身份、阵营、胜者和死亡原因文案。
- `review.css` 保存复盘弹窗的布局和视觉样式。

## 数据来源

- 优先使用 `snapshot.review_events`，游戏未结束或没有全量复盘事件时回退到 `snapshot.events`。
- 玩家展示名来自 `playersById`，角色和阵营展示来自快照里的可见字段。
- 强制结束对局通过事件流中的结束事件识别，并在复盘顶部提示。

## 常见修改入口

- 改复盘标签页或弹窗结构：改 `GameReviewDialog.tsx`。
- 改某类事件的描述文案、筛选规则或标签：改 `reviewFormat.ts`。
- 改复盘视觉样式：改 `review.css`。
- 后端新增事件类型或 payload：同步 `reviewFormat.ts`，必要时同步 `frontend/src/features/game/GamePage.tsx` 的事件流文案。

## 维护边界

复盘只解释已经发生的事件，不重新结算规则。若需要跨对局历史列表或持久化复盘，应同步新增后端数据库表和 API。
