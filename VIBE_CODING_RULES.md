# Vibe Coding 行为规范

本规范适用于 `D:\Codes\wolf_game\ours` 下所有代码生成、修改、重构、测试和文档变更。

目标：

- 保持代码风格、目录结构、命名、日志、测试和提交习惯一致。
- 防止每次生成代码都换一种写法，导致后续难以维护。
- 确保每次修改都有清晰记录，方便复盘、排查。

## 1. 总原则

1. 先读上下文，再写代码。
   - 修改前必须先查看相关文件、目录结构和已有模式。
   - 不允许在不了解现有实现的情况下凭空新增一套风格。

2. 小步修改，保持可运行。
   - 每次改动聚焦一个目标。
   - 不做无关重构。
   - 不把多个阶段功能混在一次修改中。

3. 规则引擎优先确定性。
   - 狼人杀规则、阶段推进、胜负判断必须由确定性代码控制。
   - LLM/Agent 只能提供发言、候选决策和策略摘要。
   - 任何 AI 输出都必须经过 schema 校验和合法动作校验。

4. 代码可读性优先。
   - 命名清晰。
   - 函数短小。
   - 模块边界明确。
   - 少用魔法数字，必要时抽成常量。

5. 不为未来过度设计。
   - 先满足当前 Phase 的验收标准。
   - 抽象只有在重复出现或边界明确时再引入。

## 2. 每次修改必须写修改记录

每次修改代码或项目文档后，必须在以下目录新增一个修改记录文件：

```text
D:\Codes\wolf_game\ours\修改记录
```

记录文件命名格式：

```text
YYYYMMDD_HHMM_简短主题.md
```

示例：

```text
20260609_1515_新增vibe_coding规范.md
20260610_0930_实现game_core基础状态机.md
20260610_1645_修复投票平票结算.md
```

记录文件必须包含：

```markdown
# 修改记录：简短主题

## 修改时间

YYYY-MM-DD HH:MM

## 修改范围

- 文件或模块 1
- 文件或模块 2

## 修改内容

- 做了什么
- 为什么这么做

## 验证方式

- 运行了哪些命令
- 做了哪些人工检查
- 如果未验证，说明原因

## 风险与后续

- 当前风险
- 后续建议
```

要求：

- 修改记录必须真实反映本次改动。
- 如果只改文档，也要写记录。
- 如果运行测试失败，也要记录失败原因。
- 不允许事后编造未执行的验证命令。

## 3. 目录与模块约定

主项目目录：

```text
ours/
  backend/
  frontend/
  docs/
  修改记录/
  PROJECT_PLAN.md
  VIBE_CODING_RULES.md
```

后端建议结构：

```text
backend/
  app/
    main.py
    api/
    core/
    agents/
    llm/
    voice/
    db/
  tests/
```

模块职责：

- `core/`：规则引擎、阶段、角色、事件、信息隔离。不得依赖具体 LLM 框架。
- `agents/`：LangGraph 节点、Agent 人格、prompt、schema、validator。
- `llm/`：模型 provider 抽象和具体供应商实现。
- `voice/`：AgentScope 语音适配、ASR、TTS。
- `api/`：FastAPI 路由、WebSocket、请求响应模型。
- `db/`：数据库模型、session、repository。
- `tests/`：单元测试和集成测试。

前端建议结构：

```text
frontend/
  src/
    app/
    components/
    features/
      room/
      game/
      review/
      voice/
    services/
    types/
```

## 4. Python 代码规范

1. Python 版本目标：`3.11+`。

2. 类型标注：
   - 新增函数必须写参数和返回类型。
   - 复杂 dict 优先使用 Pydantic model、dataclass 或 TypedDict。

3. 数据模型：
   - 外部输入输出用 Pydantic。
   - 规则引擎内部状态优先使用明确模型，不使用随意嵌套 dict。

4. 函数设计：
   - 一个函数只做一件事。
   - 规则计算函数尽量保持纯函数。
   - 有副作用的函数要在命名或文档中体现。

5. 异常处理：
   - 不要裸 `except` 后静默吞掉错误。
   - 可恢复错误要返回明确结果或抛出项目自定义异常。
   - LLM 调用失败必须有 fallback 或明确错误事件。

6. 日志：
   - 后端使用统一 logger。
   - 不在核心库中随意 `print`。
   - 日志不能泄露 API Key。

7. 注释：
   - 只在复杂逻辑前写必要注释。
   - 不写“给变量赋值”这类无意义注释。

## 5. TypeScript/前端规范

1. 使用 TypeScript，不新增纯 JavaScript 业务文件。

2. 组件规范：
   - 页面级组件放 `features/*`。
   - 通用 UI 放 `components/`。
   - API/WebSocket 逻辑放 `services/`。
   - 类型定义放 `types/` 或模块内 `types.ts`。

3. 状态管理：
   - MVP 阶段优先 React 内置 state/context。
   - 不提前引入复杂状态库。

4. UI 约定：
   - 第一屏直接是可玩界面，不做营销 landing page。
   - 操作按钮、投票、技能选择必须清晰。
   - 私有信息和公开信息必须视觉区分。
   - 移动端可用，但 MVP 优先桌面浏览器。

5. WebSocket：
   - 所有事件必须有明确 `type`。
   - 前端不根据自由文本解析游戏状态。
   - 私有事件必须按玩家作用域处理。

## 6. Agent 与 LLM 规范

1. Agent 不直接修改游戏状态。
   - Agent 输出候选动作。
   - `game-core` 校验后才执行。

2. Agent 不读取完整 `GameState`。
   - 只能读取 `PlayerView`。
   - 不同角色的可见信息必须由 `visibility` 模块生成。

3. LLM 输出必须结构化。
   - 使用 Pydantic schema。
   - 禁止依赖纯自然语言解析关键动作。

4. 必须处理非法输出。
   - schema 解析失败：重试或修复。
   - target 不合法：拒绝并 fallback。
   - 多次失败：使用默认安全动作。

5. 不存完整 chain-of-thought。
   - 只存 `thought_summary` 或策略摘要。
   - 对用户展示时区分公开发言和私有摘要。

6. prompt 管理：
   - prompt 放在专门模块。
   - 不在业务逻辑中散落长 prompt。
   - 修改 prompt 也要写修改记录。

## 7. LangGraph 与 AgentScope 边界

1. LangGraph 是唯一主流程控制器。
   - 阶段推进、human-in-the-loop、checkpoint、resume 都由 LangGraph 管。

2. AgentScope 是语音和实时体验适配层。
   - 负责 ASR、TTS、RealtimeAgent、voice persona。
   - 不负责胜负判断。
   - 不负责阶段跳转。

3. AgentScope 输出必须进入统一校验链路。
   - 语音转写文本可以作为真人发言。
   - AI 语音播报来自已经校验后的文本。
   - 候选动作仍需 action validator。

## 8. 测试规范

1. `core/` 规则引擎必须优先写测试。

2. 每个关键规则至少覆盖：
   - 正常路径。
   - 非法动作。
   - 边界条件。

3. MVP 必须具备：
   - 角色分配测试。
   - 夜晚结算测试。
   - 投票结算测试。
   - 胜负判断测试。
   - 信息隔离测试。

4. 测试命令要写入修改记录。

5. 如果因为依赖未安装无法测试，要记录原因和替代检查。

## 9. 配置与安全

1. API Key 只能来自环境变量。

2. 必须提供 `.env.example`。

3. 不提交真实密钥、真实 token、真实数据库密码。

4. Docker 部署配置中使用变量占位。

5. 日志中必须脱敏：
   - API Key
   - Authorization header
   - Cookie
   - 用户隐私数据

## 10. Docker 与部署规范

1. 后端、前端分别提供 Dockerfile。

2. 根目录提供 `docker-compose.yml`。

3. WebSocket 代理配置必须单独说明。

4. 数据库和日志目录使用 volume 持久化。

5. 提供健康检查接口：

```text
GET /api/health
```

6. 生产部署文档放在：

```text
ours/docs/deployment.md
```

## 11. 文档规范

1. 重要架构决策写入 docs 或根计划文档。

2. README 必须包含：
   - 项目介绍。
   - 本地启动。
   - 环境变量。
   - 测试命令。
   - Docker 启动。
   - 当前已实现/未实现功能。

3. 阶段性完成后更新计划状态。

4. 文档变更同样需要修改记录。

## 12. 禁止行为

禁止：

- 未读现有代码就大规模改写。
- 把规则判断交给 LLM。
- AI 直接写入游戏状态。
- 在 prompt 中泄露完整身份表。
- 使用自然语言字符串解析关键动作。
- 随意引入新框架或状态库。
- 提交真实 API Key。
- 没有修改记录就改代码。
- 为了“看起来完整”一次性堆大量不可验证功能。
- 删除或覆盖用户已有改动，除非用户明确要求。

## 13. 每次编码前检查清单

开始修改前：

- [ ] 我知道本次目标属于哪个 Phase。
- [ ] 我已经读过相关文件。
- [ ] 我知道要改哪些模块。
- [ ] 我不会做无关重构。

提交修改前：

- [ ] 代码符合现有目录结构。
- [ ] 规则逻辑不依赖 LLM。
- [ ] AI 输出有 schema 和 validator。
- [ ] 能运行的测试已经运行。
- [ ] 无法运行的测试已说明原因。
- [ ] 已在 `ours/修改记录` 新增修改记录。

## 14. 当前优先级

当前项目优先级：

1. Phase 1：实现 `game-core` 最小规则引擎。
2. FakeAgent 跑通 6 人局。
3. 核心规则测试。
4. 再接文本 LLM。
5. 再做 Web。
6. 再接 AgentScope 语音。
7. 最后做 Docker 生产部署。

任何偏离此顺序的大功能，都需要先更新项目计划并写明原因。
