# WolfArena AI

WolfArena AI 是一款单人参与、由多智能体共同完成的 12 人标准狼人杀 Web 游戏。玩家以随机身份加入对局，其余 11 名玩家由接入 OpenAI-compatible 模型的 AI 扮演。系统使用 LangGraph 编排夜晚、警长竞选、白天发言、投票与结算流程，并由确定性规则引擎负责所有身份、行动合法性、死亡与胜负判断。

项目的重点不是让模型直接“主持”游戏，而是在明确的信息边界和规则约束下，让 AI 像一名独立玩家一样发言、推理和行动。

## 功能介绍

- **12 人标准局**：1 名真人玩家与 11 名 AI 玩家同桌，座位和身份在每局开始时随机分配。
- **多智能体对局**：AI 具有固定人格与表达风格；狼人共享狼队记忆，预言家和女巫拥有各自的私有夜晚信息。
- **可靠的规则执行**：模型只输出候选发言和行动，输出会经过结构化解析、Schema 校验和规则校验，不能直接修改游戏真相状态。
- **完整对局流程**：支持夜间行动、死亡反应、首日警长竞选、白天发言、投票放逐、平票 PK、下一轮推进和胜负结算。
- **实时游戏界面**：前端通过 REST API 提交真人行动，并使用 WebSocket 接收状态快照与 AI 发言流式预览。
- **沉浸式反馈**：根据夜晚、讨论与投票阶段切换背景音；固定主持语音会按照流程播报。
- **账号与复盘**：支持邮箱验证码注册、登录、刷新登录态和重置密码；对局结束或手动结束后可查看流程、夜晚行动、发言、投票和身份总览。

## 游戏规则

### 角色配置

| 阵营 | 角色 | 数量 | 能力 |
| --- | --- | ---: | --- |
| 狼人 | 狼人 | 4 | 夜晚共同确定一名非狼玩家为袭击目标；白天可发言、投票和伪装身份。 |
| 好人 | 村民 | 4 | 没有夜间技能，根据公开发言、票型和死亡信息找出狼人。 |
| 好人 | 预言家 | 1 | 每晚查验一名存活玩家，获得其“好人阵营”或“狼人阵营”结果。 |
| 好人 | 女巫 | 1 | 持有一瓶解药和一瓶毒药；每晚可救被袭击者或毒杀一名玩家，不能在同一晚同时使用两种药。 |
| 好人 | 猎人 | 1 | 被狼人袭击或被白天放逐时，可开枪带走一名存活玩家；被女巫毒死时不能开枪。 |
| 好人 | 白痴 | 1 | 被白天放逐时可翻牌，之后仍可发言，但永久失去投票权。 |

### 对局流程

1. **夜晚行动**：存活狼人分别提交刀人意向，系统在狼队意见统一后确认袭击目标；预言家查验，女巫决定是否用药。
2. **天亮与死亡反应**：主持人公布夜晚死亡情况，并依次处理猎人开枪、白痴翻牌和警徽移交等效果。
3. **警长竞选**：首个白天会进行警长竞选。候选玩家发言后，由警下玩家投票；竞选平票会进入候选人 PK，连续两次平票则警徽流失。首轮竞选期间若狼人自爆，竞选会暂停并在下一个白天继续；连续两次因此自爆，警徽同样流失。
4. **白天发言**：玩家按座位顺序发言；有存活警长时，由警长选择顺时针或逆时针起始方向，并最后发言。
5. **投票放逐**：所有存活且有投票权的玩家投票或弃票。首轮平票的玩家进入 PK 发言，其他玩家在 PK 中重新投票；PK 再次平票时，当日无人出局。
6. **进入下一轮**：放逐及其死亡反应结算后，若未分出胜负，游戏进入下一晚。

### 警长与胜负

- 警长的白天投票权重为 **1.5 票**。
- 警长出局时可以把警徽移交给一名存活玩家，或撕毁警徽。
- 所有狼人出局时，好人阵营获胜。
- 所有普通村民出局，或所有神职玩家出局时，狼人阵营获胜。

### 信息边界

- 所有玩家可见公开发言、投票、死亡、放逐和回合摘要。
- 狼人仅在夜间共享狼队成员、刀人意向和策略记忆；白天公开内容不会写入狼队私有记忆。
- 预言家的查验结果、女巫的用药信息等仅对对应身份可见。
- 游戏规则、状态转换和胜负判断只由后端规则引擎执行。

## 技术组成

```text
backend/app/
  core/       确定性规则、状态、可见性与结算
  agents/     LangGraph 流程、AI 人格、提示词、记忆与输出校验
  sessions/   进程内对局、快照和 WebSocket 推送
  auth/       邮箱验证码、账号、JWT 与 Cookie 会话
  llm/        OpenAI-compatible 模型适配
  voice/      背景音乐与主持语音接口

frontend/src/
  features/   登录、对局、复盘与音频交互
  services/   REST/WebSocket 客户端
  types/      前后端共享的接口类型
```

## 启动方式

### 前置条件

- Docker Desktop（推荐使用 Docker Compose 启动完整服务），或 Python 3.11+、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 与 npm。
- 一个 OpenAI-compatible 模型服务的地址、API Key 和模型名。未配置模型时，AI 无法行动，游戏会返回服务错误。
- 用于注册与找回密码的阿里云 DirectMail 配置。当前前端需要先登录才能开始对局，因此首次注册前必须设置邮件服务凭据。

### 1. 配置环境变量

在项目根目录复制示例文件：

```powershell
Copy-Item .env.example .env
```

至少修改 `.env` 中以下项目：

```dotenv
# OpenAI-compatible LLM
LLM_BASE_URL=https://your-provider.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name

# 本地 HTTP 开发请使用一个随机长密钥，并关闭 Secure Cookie
AUTH_SECRET_KEY=replace-with-a-random-long-secret
AUTH_COOKIE_SECURE=false

# 阿里云 DirectMail：用于发送注册和密码重置验证码
ALIYUN_MAIL_ACCESS_KEY_ID=your-access-key-id
ALIYUN_MAIL_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_MAIL_ACCOUNT_NAME=your-sender-address
ALIYUN_MAIL_FROM_ALIAS=WolfArena AI
```

不要将真实 API Key、邮件密钥或 `.env` 提交到版本库。运行中的模型配置也可在登录后的“模型设置”中修改；该修改仅保留在当前后端进程中。

### 2. 使用 Docker Compose 启动（推荐）

在项目根目录执行：

```powershell
docker compose up --build
```

Compose 会启动 PostgreSQL、Redis、FastAPI 后端和 Nginx 承载的前端。服务就绪后打开：

- 游戏界面：<http://localhost:5173>
- 健康检查：<http://localhost:8000/api/health>

首次使用时，在游戏界面注册账号、登录，确认模型设置后创建新对局。

停止服务：

```powershell
docker compose down
```

如需同时清除 PostgreSQL 与 Redis 的本地数据卷：

```powershell
docker compose down -v
```

### 3. 本地开发启动

先启动本地依赖：

```powershell
docker compose up postgres redis
```

在另一个终端启动后端：

```powershell
cd backend
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --extra dev
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

再在第三个终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

开发服务器默认访问 <http://localhost:5173>，并默认请求 `http://localhost:8000`。如后端地址不同，可在 `frontend/.env.local` 中设置：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

## 运行说明

- 账号、会话和邮箱验证码依赖 PostgreSQL 与 Redis；后端启动时会自动创建尚不存在的数据库表。
- 游戏对局由后端内存中的 LangGraph checkpointer 和会话管理器保存。**重启后端、停止容器或断电后，正在进行的对局无法恢复**；账号数据仍保留在数据库中。
- 浏览器可能阻止自动播放音频。进入对局后在页面内点击一次即可解锁背景音和主持语音。

## 验证

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

前端生产构建检查：

```powershell
cd frontend
npm run build
```
