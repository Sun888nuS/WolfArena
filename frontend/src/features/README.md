# frontend/src/features

前端业务功能目录，每个子目录对应一个相对独立的产品功能域。

## 这里负责什么

- `game/` 当前可玩的狼人杀主界面。
- `room/` 房间/大厅能力预留目录。
- `review/` 复盘/历史记录能力预留目录。
- `voice/` 语音能力预留目录。

## 常见修改入口

- 添加或修改某个具体页面功能时，优先在对应 feature 目录中开发。
- 某个组件只服务一个 feature，就留在这个 feature 内。
- 多个 feature 复用的组件，再提升到 `frontend/src/components/`。

## 边界说明

feature 目录不应直接复制后端规则。需要的数据通过 `services/` 获取，字段结构通过 `types/` 约束。
