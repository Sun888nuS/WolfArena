# backend/app/auth

鉴权模块，负责邮箱验证码、注册、登录、密码重置、访问令牌、刷新令牌和 HttpOnly Cookie。它只处理用户身份，不直接影响游戏规则或 AI 流程。

## 文件分工

- `router.py` 挂载 `/api/auth` 下的路由：发送注册验证码、注册、发送重置验证码、重置密码、登录、刷新、退出和读取当前用户。
- `schemas.py` 定义鉴权请求和响应模型。
- `service.py` 编排鉴权用例，处理验证码校验、用户创建、登录时间、会话刷新、事务提交和 Cookie 写入。
- `repository.py` 封装用户表和会话表的数据库访问。
- `security.py` 负责 Argon2 密码哈希、JWT access token、refresh token 哈希、Cookie 设置和清理。
- `redis_codes.py` 用 Redis 保存邮箱验证码、发送冷却、每日上限和失败次数限制。
- `email_sender.py` 适配阿里云 DirectMail `SingleSendMail`。
- `exceptions.py` 定义鉴权业务异常。

## 外部依赖

- 用户和会话表定义在 `backend/app/db/models.py`，迁移脚本在 `backend/app/db/migrations/`。
- Redis 客户端来自 `backend/app/cache/redis_client.py`。
- 密钥、Cookie、验证码和邮件参数来自 `backend/app/config.py`。

## 常见修改入口

- 调整鉴权接口或状态码：改 `router.py`。
- 调整注册、登录、刷新、退出或密码重置流程：改 `service.py`。
- 调整数据库查询或会话撤销策略：改 `repository.py`。
- 调整密码、JWT、refresh token 或 Cookie 规则：改 `security.py`。
- 调整验证码 TTL、冷却、次数限制：优先改配置；需要改存储结构时再改 `redis_codes.py`。
- 调整邮件供应商或邮件内容：改 `email_sender.py`。

## 维护边界

鉴权结果可以被后续对局记录、排行榜或复盘功能引用，但本模块不创建游戏、不推进游戏、不修改 `GameState`。
