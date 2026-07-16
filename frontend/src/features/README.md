# frontend/src/features

前端业务功能目录。每个子目录对应一个相对独立的产品能力，优先在 feature 内部维护自己的组件、hooks、工具函数和样式。

## 子目录分工

- `auth/` 登录、注册、密码重置和当前用户状态。
- `game/` 当前可玩的狼人杀主界面，包括桌面、行动面板、主持播报、背景音、模型配置和复盘入口。
- `review/` 游戏结束或手动结束后的复盘弹窗、事件格式化和复盘样式。
- `voice/` 固定主持语音播放 hook。
- `room/` 房间/大厅能力预留目录。

## 常见修改入口

- 改某个页面或业务能力：优先在对应 feature 内修改。
- 某个组件只服务一个 feature：留在该 feature 内。
- 多个 feature 稳定复用的组件：再提升到 `frontend/src/components/`。
- 后端字段变化：同步 `frontend/src/types/`，再改 feature 页面。

## 维护边界

feature 可以做交互状态、展示逻辑和轻量表单校验，但不应复制后端狼人杀规则。需要的数据通过 `services/` 获取，字段结构通过 `types/` 约束。
