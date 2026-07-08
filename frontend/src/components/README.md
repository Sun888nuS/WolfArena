# frontend/src/components

通用前端组件预留目录。

## 这里负责什么

当前目录没有实际组件。后续适合放跨多个 feature 复用的基础组件，例如通用按钮、弹窗、状态徽章、加载态、错误提示等。

## 放入规则

- 只放不绑定某个具体业务页面的组件。
- 业务强相关组件优先放在对应 `frontend/src/features/<feature>/`。
- 组件需要的通用类型可以放在 `frontend/src/types/`，业务类型仍跟随后端快照类型维护。
