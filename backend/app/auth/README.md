# backend/app/auth

Authentication is isolated here. This package owns registration, login,
verification codes, user sessions, token/cookie handling, and outbound auth
emails.

It intentionally does not change werewolf rules, agents, or game flow. The
first integration stage keeps game creation optional for anonymous users; later
features can attach `user_id` to match history, reviews, and rankings.

Main files:

- `router.py`: FastAPI routes under `/api/auth`.
- `schemas.py`: request and response models.
- `service.py`: auth use cases and transaction-facing orchestration.
- `repository.py`: PostgreSQL access for users and sessions.
- `security.py`: Argon2, JWT, opaque refresh tokens, and HttpOnly cookies.
- `redis_codes.py`: verification-code storage, cooldowns, daily limits, and
  failure throttling.
- `email_sender.py`: Aliyun DirectMail SingleSendMail adapter.
