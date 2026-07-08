# 部署说明

本文档记录 WolfArena AI 的服务器部署约定。Phase 0 只提供基础 Docker 部署，后续接入数据库、WebSocket 房间和语音服务时继续扩展。

## 1. 环境要求

- Docker 24+
- Docker Compose v2
- 可访问第三方 OpenAI-compatible 中转站 API

## 2. 生产环境变量

复制模板：

```bash
cp .env.production.example .env
```

配置：

```text
APP_ENV=production
CORS_ORIGINS=https://your-domain.example.com
LLM_BASE_URL=https://your-relay.example.com/v1
LLM_API_KEY=replace-with-server-side-secret
LLM_MODEL=gpt-4o-mini
CHECKPOINT_DB_PATH=data/wolfarena_checkpoints.sqlite3
SESSION_DB_PATH=data/wolfarena_sessions.sqlite3
VITE_API_BASE_URL=https://your-domain.example.com
```

注意：

- 不要把真实 `.env` 提交到 git。
- `LLM_API_KEY` 只放在服务器环境变量中。
- 日志中只能展示脱敏 key。

## 3. Docker 启动

```bash
docker compose up -d --build
```

检查：

```text
http://your-server:8000/api/health
http://your-server:5173
```

## 4. 反向代理建议

后续生产推荐使用 Caddy 或 Nginx：

```text
https://your-domain.example.com      -> frontend:80
https://your-domain.example.com/api  -> backend:8000/api
https://your-domain.example.com/ws   -> backend:8000/ws
```

WebSocket 代理需要保留 Upgrade header。Phase 0 尚未启用游戏 WebSocket，Phase 3 后补充完整配置。

## 5. 持久化数据

Phase 4 起后端会写入两个 SQLite 文件：

- `CHECKPOINT_DB_PATH`：LangGraph checkpoint。
- `SESSION_DB_PATH`：game registry、pending action、节点 trace 元数据表。

生产环境需要把 `data/` 挂载为持久化 volume，否则容器重建后无法恢复正在进行的对局。

## 6. 后续部署扩展

- Phase 6：增加 PostgreSQL 服务。
- Phase 7：增加 trace/log volume。
- Phase 5：如 AgentScope 语音服务需要独立进程，再拆分 `voice` service。
