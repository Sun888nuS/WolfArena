"""Email verification code storage and rate limits in Redis."""

from datetime import UTC, datetime
import hashlib
import hmac
import secrets

from redis.asyncio import Redis

from app.auth.exceptions import EmailCodeError
from app.config import Settings


class RedisEmailCodeStore:
    """Manage registration email codes in Redis."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    async def create_register_code(self, email: str) -> str:
        """Create, store, and return a six-digit registration code."""
        return await self._create_code(email, purpose="register")

    async def create_password_reset_code(self, email: str) -> str:
        """Create, store, and return a six-digit password reset code."""
        return await self._create_code(email, purpose="password_reset")

    async def verify_register_code(self, email: str, code: str) -> None:
        """Verify a registration code and delete it after success."""
        await self._verify_code(email, code, purpose="register")

    async def verify_password_reset_code(self, email: str, code: str) -> None:
        """Verify a password reset code and delete it after success."""
        await self._verify_code(email, code, purpose="password_reset")

    async def delete_register_code(self, email: str) -> None:
        """Delete a registration code and its failure counter."""
        await self._delete_code(email, purpose="register")

    async def delete_password_reset_code(self, email: str) -> None:
        """Delete a password reset code and its failure counter."""
        await self._delete_code(email, purpose="password_reset")

    async def _create_code(self, email: str, *, purpose: str) -> str:
        await self._ensure_send_allowed(email, purpose=purpose)
        code = f"{secrets.randbelow(1_000_000):06d}"
        await self.redis.set(
            self._code_key(email, purpose=purpose),
            self._code_digest(email, code),
            ex=self.settings.email_code_ttl_seconds,
        )
        await self.redis.set(
            self._cooldown_key(email, purpose=purpose),
            "1",
            ex=self.settings.email_code_cooldown_seconds,
        )
        daily_key = self._daily_key(email, purpose=purpose)
        count = await self.redis.incr(daily_key)
        if count == 1:
            await self.redis.expire(daily_key, 24 * 60 * 60)
        return code

    async def _verify_code(self, email: str, code: str, *, purpose: str) -> None:
        fail_key = self._fail_key(email, purpose=purpose)
        failures = await self.redis.get(fail_key)
        if failures is not None and int(failures) >= self.settings.email_code_fail_limit:
            raise EmailCodeError("验证码错误次数过多，请稍后再试", status_code=429)

        stored_digest = await self.redis.get(self._code_key(email, purpose=purpose))
        if not stored_digest:
            raise EmailCodeError("验证码已过期，请重新获取")

        expected = self._code_digest(email, code.strip())
        if not hmac.compare_digest(stored_digest, expected):
            count = await self.redis.incr(fail_key)
            if count == 1:
                await self.redis.expire(fail_key, self.settings.email_code_fail_ttl_seconds)
            raise EmailCodeError("验证码不正确")

        await self._delete_code(email, purpose=purpose)

    async def _delete_code(self, email: str, *, purpose: str) -> None:
        await self.redis.delete(
            self._code_key(email, purpose=purpose),
            self._fail_key(email, purpose=purpose),
        )

    async def _ensure_send_allowed(self, email: str, *, purpose: str) -> None:
        if await self.redis.exists(self._cooldown_key(email, purpose=purpose)):
            raise EmailCodeError("验证码发送太频繁，请稍后再试", status_code=429)

        daily_count = await self.redis.get(self._daily_key(email, purpose=purpose))
        if daily_count is not None and int(daily_count) >= self.settings.email_code_daily_limit:
            raise EmailCodeError("今日验证码发送次数已达上限", status_code=429)

    def _code_digest(self, email: str, code: str) -> str:
        payload = f"{email}:{code}".encode("utf-8")
        return hmac.new(
            self.settings.auth_secret_key.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _code_key(email: str, *, purpose: str) -> str:
        return f"auth:email_code:{purpose}:{email}"

    @staticmethod
    def _cooldown_key(email: str, *, purpose: str) -> str:
        return f"auth:email_code:cooldown:{purpose}:{email}"

    @staticmethod
    def _fail_key(email: str, *, purpose: str) -> str:
        return f"auth:email_code:fail:{purpose}:{email}"

    @staticmethod
    def _daily_key(email: str, *, purpose: str) -> str:
        day = datetime.now(UTC).strftime("%Y%m%d")
        return f"auth:email_code:daily:{purpose}:{email}:{day}"
