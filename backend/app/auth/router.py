"""FastAPI router for authentication endpoints."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email_sender import AliyunMailSender
from app.auth.exceptions import AuthError
from app.auth.redis_codes import RedisEmailCodeStore
from app.auth.repository import AuthRepository
from app.auth.schemas import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    RegisterRequest,
    SendPasswordResetCodeRequest,
    SendRegisterCodeRequest,
    UserResponse,
)
from app.auth.security import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    decode_access_token,
)
from app.auth.service import AuthService, user_to_response
from app.cache.redis_client import get_redis_client
from app.config import Settings, get_settings
from app.db.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


def build_auth_service(db_session: AsyncSession, settings: Settings) -> AuthService:
    """Build an auth service around the current request session."""
    return AuthService(
        repository=AuthRepository(db_session),
        code_store=RedisEmailCodeStore(get_redis_client(), settings),
        mail_sender=AliyunMailSender(settings),
        settings=settings,
    )

# 发送注册验证码
@router.post("/register/send-code", response_model=MessageResponse)
async def send_register_code(
    payload: SendRegisterCodeRequest,
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Send a verification code for registration."""
    service = build_auth_service(db_session, settings)
    try:
        await service.send_register_code(payload.email)
        await db_session.commit()
    except AuthError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return MessageResponse(message="验证码已发送")

# 验证验证码，创建账号并自动登录
@router.post("/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Create a new account and log the browser in."""
    service = build_auth_service(db_session, settings)
    try:
        result = await service.register(
            email=payload.email,
            password=payload.password,
            code=payload.code,
            display_name=payload.display_name,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        await db_session.commit()
        return result
    except AuthError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

#发送重置密码验证码
@router.post("/password-reset/send-code", response_model=MessageResponse)
async def send_password_reset_code(
    payload: SendPasswordResetCodeRequest,
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Send a verification code for password reset."""
    service = build_auth_service(db_session, settings)
    try:
        await service.send_password_reset_code(payload.email)
        await db_session.commit()
    except AuthError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return MessageResponse(message="验证码已发送")

# 验证验证码，重置密码
@router.post("/password-reset", response_model=MessageResponse)
async def reset_password(
    payload: PasswordResetRequest,
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Reset password using email code."""
    service = build_auth_service(db_session, settings)
    try:
        await service.reset_password(
            email=payload.email,
            code=payload.code,
            new_password=payload.new_password,
        )
        await db_session.commit()
    except AuthError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return MessageResponse(message="密码已重置")

# 邮箱和密码登录
@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Log in with email and password."""
    service = build_auth_service(db_session, settings)
    try:
        result = await service.login(
            email=payload.email,
            password=payload.password,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        await db_session.commit()
        return result
    except AuthError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

# 使用刷新令牌换取新的登录凭据。
@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Rotate refresh token and issue a new access token."""
    service = build_auth_service(db_session, settings)
    try:
        result = await service.refresh(
            refresh_token=refresh_token,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        await db_session.commit()
        return result
    except AuthError as exc:
        await db_session.rollback()
        clear_auth_cookies(response, settings)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

# 撤销当前浏览器会话并清理 Cookie
@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Log out the current browser session."""
    service = build_auth_service(db_session, settings)
    await service.logout(refresh_token)
    await db_session.commit()
    clear_auth_cookies(response, settings)
    return MessageResponse(message="已退出登录")

# 根据访问令牌返回当前用户资料
@router.get("/me", response_model=UserResponse)
async def me(
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE_NAME),
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    """Return the current user based on the access-token cookie."""
    if not access_token:
        raise HTTPException(status_code=401, detail="未登录")
    user_id = decode_access_token(access_token, settings)
    if user_id is None:
        raise HTTPException(status_code=401, detail="登录状态已过期")
    user = await AuthRepository(db_session).get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="登录状态无效")
    return user_to_response(user)
