"""Domain exceptions for authentication flows."""


class AuthError(Exception):
    """Base authentication error carrying an HTTP status and safe detail."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class InvalidCredentialsError(AuthError):
    """Raised when email or password is invalid."""

    def __init__(self) -> None:
        super().__init__("邮箱或密码不正确", status_code=401)


class InactiveUserError(AuthError):
    """Raised when a user is disabled."""

    def __init__(self) -> None:
        super().__init__("账号已停用", status_code=403)


class DuplicateEmailError(AuthError):
    """Raised when registering an email that already exists."""

    def __init__(self) -> None:
        super().__init__("邮箱已注册", status_code=409)


class EmailCodeError(AuthError):
    """Raised for email-code validation and rate-limit failures."""
