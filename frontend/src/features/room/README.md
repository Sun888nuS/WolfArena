# frontend/src/features/room

房间/大厅功能预留目录。

## 这里负责什么

当前目录没有实际源码。后续可用于开局前的房间列表、创建房间、座位选择、邀请、游戏配置等能力。

## 后续适合放什么

- 房间列表和创建房间页面。
- 游戏人数、角色板子、AI 难度、模型配置等开局前配置 UI。
- 只服务房间功能的 hooks、组件和样式。

## 边界说明

房间配置最终需要映射到后端开局请求。后端侧通常会同步修改 `backend/app/sessions/models.py`、`backend/app/sessions/manager.py` 和 `backend/app/core/rules.py`。
