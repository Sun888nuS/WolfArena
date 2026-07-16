# backend/app/db/migrations

数据库迁移目录，使用 Alembic 管理后端持久化表结构。目前迁移主要覆盖鉴权相关的用户表和刷新会话表。

## 文件分工

- `env.py` 配置 Alembic 运行环境，连接项目的 SQLAlchemy metadata。
- `script.py.mako` 是生成新迁移文件时使用的模板。
- `versions/20260629_0001_create_auth_tables.py` 创建 `users` 和 `user_sessions` 表，以及邮箱、refresh token 等索引约束。

## 运行关系

本地首次启动时，应用会尝试通过 `backend/app/db/session.py` 创建缺失表，方便开发环境快速运行。生产或共享环境仍应显式运行 Alembic 迁移，避免表结构变化不可追踪。

## 常见修改入口

- 新增持久化模型：先改 `backend/app/db/models.py`，再生成迁移。
- 修改鉴权表结构：同步 `auth/repository.py`、`auth/service.py` 和对应迁移。
- 新增对局历史、复盘或排行榜表：在 `db/models.py` 建模，并在 `versions/` 新增迁移文件。

## 维护边界

迁移文件只描述数据库结构变化，不放业务规则、不调用外部服务，也不承担数据快照生成逻辑。
