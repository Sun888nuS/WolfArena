# 真人参与 AI 狼人杀系统项目规划 v2

更新日期：2026-06-09

## 1. 项目目标

本项目要做一套我们自己的“真人 + AI 混合狼人杀系统”，而不是简单复刻现有开源 demo。

最终系统应具备：

- 真人可以创建房间、加入座位、参与发言、投票和夜晚技能。
- AI 玩家拥有角色目标、人格差异、阵营策略、短期记忆和复盘能力。
- 游戏流程由确定性规则引擎控制，LLM 只负责在合法信息范围内生成发言和决策。
- 支持 Web 实时对局、事件流、断线重连、对局复盘。
- 后期接入 AgentScope 语音能力，让真人语音输入、AI 语音发言成为体验增强点。
- 项目可 Docker 打包，可部署到云服务器。
- 项目架构和技术点能写进 AI 工程岗简历。

核心原则：

> 先做最小可玩的 MVP，再逐步增强 Agent、语音、多真人、评测、部署能力。不要一开始就实现完整系统。

## 2. 现有目录资产

当前目录下有三类可参考资产：

1. `WolfMind-main`
   - 技术栈：AgentScope + FastAPI + Vue3。
   - 已有较完整的狼人杀流程、角色类、结构化输出、日志、经验更新、分析报告。
   - 可借鉴：角色 prompt、角色行为设计、日志格式、AgentScope 使用方式。
   - 不建议直接作为主项目底座，因为它更偏全 AI 对局和展示型控制台，不是面向真人参与的房间制系统。

2. `werewolf_ai_agents-main`
   - 基于 MetaGPT 的狼人杀多 Agent 示例。
   - 可借鉴：多角色动作拆分、Agent 行为组织。
   - 不建议作为产品底座，工程形态偏实验。

3. `ours/AI_WEREWOLF_SYSTEM_BLUEPRINT.md`
   - 已经沉淀了新版系统蓝图。
   - 本文件作为根目录总计划，后续实现以 `ours/` 为主项目目录。

## 3. 最终技术选型

推荐技术栈：

- Agent 编排主框架：`LangGraph`
- 语音与实时多模态增强：`AgentScope`
- 规则引擎：自研确定性状态机
- 后端：`FastAPI + WebSocket`
- 前端：`React + Vite + TypeScript + Tailwind`
- 数据模型：`Pydantic v2`
- 数据库：MVP 用 `SQLite`，生产部署可切 `PostgreSQL`
- LLM 接入：OpenAI-compatible provider 抽象，支持 OpenAI、DeepSeek、Qwen、Claude、Ollama
- 评测：`pytest + 离线模拟局 + Agent 行为评分`
- 部署：`Docker + Docker Compose + Nginx/Caddy 反向代理`

## 4. LangGraph 与 AgentScope 如何协作

两个框架都可以做 Agent，但职责必须分清，避免双框架抢控制权。

推荐分工：

| 模块 | 框架/技术 | 职责 |
| --- | --- | --- |
| 游戏主流程 | LangGraph | 控制夜晚、白天、发言、投票、结算、复盘等状态图 |
| 真人中断与恢复 | LangGraph | pending action、human-in-the-loop、checkpoint、断线恢复 |
| 规则裁判 | 自研 game-core | 角色分配、合法动作、信息隔离、胜负判断 |
| 文本 AI 决策 | LangGraph node + LLM provider | 生成发言、投票、技能目标、策略摘要 |
| 语音输入输出 | AgentScope | 真人语音输入、AI 语音播报、实时语音 agent |
| 房间与通信 | FastAPI + WebSocket | 房间 API、事件推送、前端连接、语音流转发 |
| 前端体验 | React | 座位、事件流、行动面板、语音控制、复盘页 |

一句话：

> LangGraph 管“游戏怎么走”，AgentScope 管“玩家怎么说话和听起来像人”。

关键边界：

- AgentScope 不直接读取完整 `GameState`，只能读取当前玩家的 `PlayerView`。
- AgentScope 不决定游戏阶段，阶段推进只能由 LangGraph 和 game-core 完成。
- AgentScope 输出的文本、语音转写、候选动作都必须经过 action validator。
- LangGraph 是唯一流程控制器，AgentScope 是语音/runtime adapter。

## 5. 为什么不一开始就做完整系统

狼人杀系统的复杂度来自多个维度：

- 规则复杂：夜晚行动、白天发言、投票、遗言、胜负判定。
- 信息隔离复杂：不同角色看到的信息不同。
- LLM 不稳定：可能输出非法 JSON、越权身份、无效目标。
- 真人参与复杂：需要等待输入、超时、断线重连。
- 语音复杂：ASR、TTS、延迟、说话人区分、前端音频权限。
- 部署复杂：多服务、环境变量、模型 key、安全和日志。

如果一开始就同时做完整规则、多真人、语音、长期记忆和部署，很容易变成不可控的大工程。

因此采用分阶段路线：

1. 先做纯文本、单真人、6 人局 MVP。
2. 再做 Web 房间和断线恢复。
3. 再接 LangGraph checkpoint 和 Agent 评测。
4. 再加入 AgentScope 语音体验。
5. 最后做生产部署和完整复盘系统。

## 6. MVP 范围

### 6.1 MVP 目标

第一版 MVP 只追求“完整可玩一局”，不追求完整产品。

MVP 配置：

- 人数：6 人局。
- 真人：1 人。
- AI：5 人。
- 角色：2 狼人、1 预言家、1 女巫、2 村民。
- 模式：文本交互。
- 前端：可以简洁，但必须可操作。
- 后端：规则必须稳定，AI 输出必须校验。

### 6.2 MVP 必须实现

- 创建新局。
- 随机分配身份。
- 真人可以看到自己的身份。
- AI 根据身份和可见信息发言、投票、使用技能。
- 真人可以：
  - 白天发言。
  - 白天投票。
  - 如果是狼人，夜晚刀人。
  - 如果是预言家，夜晚验人。
  - 如果是女巫，夜晚救人或毒人。
- 夜晚阶段：
  - 狼人选择击杀目标。
  - 预言家查验目标。
  - 女巫救/毒。
- 白天阶段：
  - 公布死亡。
  - 所有存活玩家依次发言。
  - 所有存活玩家投票。
  - 最高票出局。
- 胜负判断：
  - 狼人全出局，好人胜。
  - 狼人数大于等于好人数，狼人胜。
- 结算复盘：
  - 展示所有玩家身份。
  - 展示关键夜晚行动。
  - 展示投票记录。

### 6.3 MVP 暂不实现

- 语音输入/输出。
- 多真人实时房间。
- 9/12 人标准完整板子。
- 猎人、守卫、白痴、狼王、骑士等复杂角色。
- 长期跨局记忆。
- 好看的完整 UI 动效。
- AgentScope ChatRoom 多人实时语音。
- 生产级权限系统。

## 7. 系统架构

```text
React Frontend
  - 房间/座位
  - 身份面板
  - 发言输入
  - 技能目标选择
  - 投票面板
  - 事件流
  - 复盘页

FastAPI Gateway
  - REST API
  - WebSocket
  - 房间状态
  - 真人行动提交

LangGraph Orchestrator
  - 游戏阶段状态图
  - AI 决策节点
  - human-in-the-loop
  - checkpoint/resume

Game Core
  - 确定性规则引擎
  - 信息隔离 PlayerView
  - legal action validator
  - 胜负判定

LLM Provider
  - OpenAI-compatible
  - Claude / Qwen / DeepSeek / Ollama
  - JSON schema 输出
  - retry / repair / fallback

AgentScope Voice Layer
  - V1.5 后接入
  - ASR/TTS
  - AI 角色声音
  - 语音 WebSocket

Storage
  - SQLite/PostgreSQL
  - game_events
  - rooms
  - players
  - pending_actions
  - agent_traces
```

## 8. 核心模块设计

### 8.1 game-core

职责：

- 不依赖 LLM。
- 不依赖前端。
- 不依赖具体 Agent 框架。
- 输入合法动作，输出新状态和事件。

核心对象：

```text
GameState
PlayerState
Role
Phase
GameEvent
NightAction
VoteResult
WinResult
PlayerView
LegalAction
```

验收要求：

- 不接 LLM 也能用 FakeAgent 自动跑完 100 局。
- 核心规则有单元测试。
- 任意非法 action 都不能污染真实 game state。

### 8.2 visibility 信息隔离

每次 AI 决策前，不给完整 `GameState`，只给当前玩家 `PlayerView`。

示例：

```text
村民 PlayerView:
  - 公开玩家列表
  - 公开死亡信息
  - 公开发言
  - 历史投票
  - 自己是村民
  - 不包含任何隐藏身份

狼人 PlayerView:
  - 公开信息
  - 自己是狼人
  - 狼队友列表
  - 狼人夜聊记录

预言家 PlayerView:
  - 公开信息
  - 自己是预言家
  - 已查验结果：目标 -> 好人/狼人
```

这是项目最重要的 AI 工程亮点之一。

### 8.3 LangGraph orchestration

核心状态图：

```text
init_game
  -> assign_roles
  -> night_werewolf
  -> night_seer
  -> night_witch
  -> resolve_night
  -> day_announcement
  -> speech_round
  -> vote_round
  -> resolve_vote
  -> check_win
  -> reflection
  -> next_round 或 game_over
```

真人输入节点：

- 真人技能选择。
- 真人发言。
- 真人投票。

这些节点需要：

- 创建 `pending_action`。
- 通过 WebSocket 通知前端。
- 暂停图执行。
- 用户提交后 resume。
- 超时后执行默认策略。

### 8.4 AgentScope voice layer

AgentScope 不在 MVP 阶段接入，建议在 V1.5 或 V2 加入。

接入方式：

1. 真人语音输入
   - 前端录音。
   - WebSocket 上传音频。
   - AgentScope/ASR 转写为文本。
   - 文本提交给 LangGraph pending action。

2. AI 语音播报
   - LangGraph 生成 AI 发言文本。
   - AgentScope/TTS 根据 AI 人格生成语音。
   - 前端播放音频，同时展示文字。

3. AI 角色声音
   - 每个 AI 玩家配置 voice persona。
   - 不同角色使用不同语速、语气、音色。

4. 后期实验
   - 狼人夜聊实时语音。
   - 白天自由辩论。
   - AgentScope ChatRoom 多 agent voice interaction。

不建议第一版做全实时多人语音，因为音频延迟、打断、说话人区分和模型成本都会显著增加复杂度。

## 9. 分阶段实现路线

### Phase 0：项目初始化

目标：建立可持续开发的项目骨架。

实现内容：

- 创建 `ours/backend`。
- 创建 `ours/frontend`。
- 建立基础 README。
- 配置 `.env.example`。
- 配置 Docker 基础文件占位。
- 明确代码目录和模块边界。

验收标准：

- 后端可以启动一个健康检查接口。
- 前端可以访问基础页面。
- README 说明如何启动。

预计时间：0.5-1 天。

### Phase 1：最小规则引擎 MVP

目标：不接 LLM、不做 UI，先跑通狼人杀规则闭环。

实现内容：

- 6 人局角色分配。
- 阶段状态机。
- 夜晚行动结算。
- 白天投票结算。
- 胜负判断。
- FakeAgent 随机或规则化行动。
- CLI 跑完整对局。
- pytest 覆盖核心规则。

验收标准：

- 命令行可自动跑完一局。
- 可连续模拟 100 局不崩。
- 非法行动会被拒绝。
- 测试覆盖核心规则。

预计时间：2-3 天。

### Phase 2：文本 AI MVP

目标：加入 LLM，让 AI 能发言和决策，但仍保持最小产品。

实现内容：

- LLM provider 抽象。
- OpenAI-compatible 接入。
- AI 玩家人格。
- Pydantic 结构化输出。
- JSON 解析、修复、重试、fallback。
- AI 发言、投票、夜晚技能。
- 信息隔离 PlayerView。
- action validator。

验收标准：

- 1 真人 + 5 AI 可以在后端跑完文本局。
- AI 不明显泄露自己不该知道的信息。
- AI 非法目标不会进入规则引擎。
- 每次 LLM 调用有日志。

预计时间：3-5 天。

### Phase 3：Web 可玩 MVP

目标：让普通用户可以通过浏览器玩完整一局。

实现内容：

- React 房间页面。
- 座位区。
- 身份展示。
- 事件流。
- 发言输入框。
- 技能目标选择。
- 投票面板。
- FastAPI REST API。
- WebSocket 实时事件推送。

验收标准：

- 浏览器可以开始新局。
- 用户可以完成身份相关操作。
- 可以完整打完一局并看到复盘。
- 不需要语音，不需要多真人。

预计时间：3-5 天。

### Phase 4：LangGraph checkpoint 与断线恢复

目标：把系统从 demo 提升为工程化 Agent 应用。

实现内容：

- 将阶段流程正式迁移到 LangGraph state graph。
- human-in-the-loop interrupt/resume。
- checkpoint 持久化。
- pending action 数据表。
- 断线重连恢复当前阶段。
- 超时默认动作。

验收标准：

- 用户刷新页面后仍能回到当前局。
- 等待真人输入时后端不会阻塞。
- graph 状态可以恢复。
- 复盘可以追踪每个节点的输入输出。

预计时间：3-5 天。

### Phase 5：AgentScope 语音体验增强

目标：加入语音能力，但不改变主流程控制权。

实现内容：

- 前端录音按钮。
- 语音 WebSocket。
- AgentScope ASR 或 realtime agent 接入。
- 真人语音转文字提交发言。
- AI 发言 TTS 播报。
- AI 玩家 voice persona。
- 可关闭语音，保留纯文本模式。

验收标准：

- 真人可以用语音输入发言。
- AI 发言可以播放语音。
- 语音失败时自动降级到文本。
- LangGraph 仍是唯一流程控制器。

预计时间：3-6 天。

### Phase 6：多真人与房间系统

目标：从单真人陪玩扩展到混合房间。

实现内容：

- 房间创建和加入。
- 2-3 名真人混合局。
- 房主配置板子。
- 玩家准备状态。
- 真人断线重连。
- 真人超时处理。
- 私有消息按玩家推送。

验收标准：

- 多个浏览器可加入同一房间。
- 不同真人只能看到自己的私有信息。
- AI 自动补位。
- 房主可以开局。

预计时间：4-7 天。

### Phase 7：复盘、评测与可观测性

目标：让项目具备 AI 工程岗简历竞争力。

实现内容：

- 对局复盘页。
- 票型时间线。
- 夜晚行动摘要。
- AI 私有策略摘要。
- Agent trace。
- token、cost、latency 统计。
- 离线模拟评测。
- 指标：
  - 合法动作率。
  - 身份泄露率。
  - JSON 修复率。
  - 发言重复率。
  - 平均响应延迟。
  - 不同模型胜率分布。

验收标准：

- 每局生成 review JSON。
- 能跑批量模拟并输出报告。
- README 展示核心指标。

预计时间：3-6 天。

### Phase 8：Docker 打包与服务器部署

目标：项目可以真正部署到服务器。

实现内容：

- 后端 Dockerfile。
- 前端 Dockerfile 或 Vite build + Nginx。
- docker-compose.yml。
- SQLite volume 或 PostgreSQL service。
- `.env.production.example`。
- Nginx/Caddy 反向代理配置。
- WebSocket 代理配置。
- 健康检查接口。
- 日志目录 volume。
- 生产启动文档。

推荐 compose 服务：

```text
services:
  backend:
    FastAPI + LangGraph + game-core + AgentScope adapter

  frontend:
    Nginx static frontend

  db:
    PostgreSQL，可选；MVP 可以 SQLite volume

  reverse-proxy:
    Caddy 或 Nginx，可选
```

验收标准：

- `docker compose up -d` 可启动完整系统。
- 浏览器访问服务器域名可进入房间。
- WebSocket 正常工作。
- 环境变量不写死在代码中。
- 日志和数据库持久化。

预计时间：2-4 天。

## 10. 推荐开发顺序

不要从 UI 和语音开始。

推荐顺序：

1. `game-core` 规则引擎。
2. FakeAgent 自动跑局。
3. LLM 文本 AI。
4. Web 可玩 MVP。
5. LangGraph checkpoint。
6. AgentScope 语音。
7. 多真人房间。
8. 复盘评测。
9. Docker 部署。

这样每一步都有可运行成果，不会陷入“大而全但不可玩”的状态。

## 11. 目录规划

推荐在 `ours/` 下形成主项目：

```text
ours/
  README.md
  docker-compose.yml
  .env.example
  .env.production.example

  backend/
    Dockerfile
    pyproject.toml
    app/
      main.py
      api/
        health.py
        rooms.py
        games.py
        websocket.py
      core/
        engine.py
        rules.py
        phases.py
        visibility.py
        events.py
      agents/
        graph.py
        nodes.py
        personas.py
        prompts.py
        schemas.py
        validators.py
      voice/
        agentscope_adapter.py
        asr.py
        tts.py
      llm/
        base.py
        openai_compatible.py
        anthropic.py
        ollama.py
      db/
        models.py
        session.py
        repositories.py
      tests/

  frontend/
    Dockerfile
    package.json
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

  docs/
    architecture.md
    game-rules.md
    agent-design.md
    voice-design.md
    deployment.md
    evaluation.md
```

## 12. 简历亮点设计

项目名：

> WolfArena AI：基于 LangGraph 与 AgentScope 的真人参与多 Agent 狼人杀系统

可写进简历的技术点：

- 基于 LangGraph 构建可恢复的人机混合狼人杀状态图，支持夜晚、白天、发言、投票、结算和复盘流程。
- 自研确定性规则引擎，将狼人杀规则与 LLM 决策解耦，避免模型直接控制游戏状态。
- 设计 player-scoped visibility layer，确保不同角色只能访问合法信息，降低隐藏身份泄露风险。
- 使用 Pydantic schema 和 legal action validator 约束 AI 输出，实现非法目标拦截、JSON 修复、重试和 fallback。
- 集成 AgentScope 作为语音交互层，实现真人语音输入、AI 角色语音播报和文本降级机制。
- 基于 FastAPI/WebSocket 实现实时房间、事件流、真人 pending action 和断线恢复。
- 构建离线模拟评测体系，统计合法动作率、身份泄露率、发言重复率、响应延迟和模型成本。
- 使用 Docker Compose 打包前后端、数据库和反向代理，实现服务器部署。

## 13. 第一阶段立刻要做什么

下一步不要先写完整 Web 系统，也不要先接 AgentScope。

立刻开始：

1. 在 `ours/backend` 初始化 Python 项目。
2. 实现 `game-core`。
3. 写 FakeAgent。
4. 跑通 6 人局 CLI。
5. 加核心规则测试。

第一阶段完成后，项目就有一个稳定内核。后面的 LLM、Web、语音、Docker 都是在这个内核上逐层加能力。

## 14. 当前版本结论

AgentScope 值得加入，但加入时机应放在文本 MVP 之后。

最终推荐架构是：

```text
LangGraph = 主流程编排和恢复
game-core = 规则裁判和信息隔离
AgentScope = 语音和实时体验增强
FastAPI = 房间网关和 WebSocket 通信
React = 可玩前端
Docker = 部署交付
```

这个路线既能快速做出可玩的 MVP，又能逐步扩展到完整项目，并且技术点足够支撑 AI 工程岗简历和面试讲解。
