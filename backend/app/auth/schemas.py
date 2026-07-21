"""Pydantic schemas for auth API requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# 发送注册验证码
class SendRegisterCodeRequest(BaseModel):
    """Request body for sending a registration code."""

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)

# 发送密码重置验证码
class SendPasswordResetCodeRequest(BaseModel):
    """Request body for sending a password reset code."""

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)

# 注册请求
class RegisterRequest(BaseModel):
    """Request body for creating a user account."""

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    code: str = Field(min_length=4, max_length=12)
    display_name: str | None = Field(default=None, max_length=80)

# 登录请求
class LoginRequest(BaseModel):
    """Request body for password login."""

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    password: str = Field(min_length=1, max_length=128)

# 密码重置
class PasswordResetRequest(BaseModel):
    """Request body for resetting a password by email code."""

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=128)

# 用户响应
class UserResponse(BaseModel):
    """Safe current-user payload."""

    id: UUID
    email: str
    display_name: str | None
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None

# 认证响应
class AuthResponse(BaseModel):
    """Response payload after register/login/refresh."""

    user: UserResponse

# 消息响应
class MessageResponse(BaseModel):
    """Simple success message payload."""

    message: str
