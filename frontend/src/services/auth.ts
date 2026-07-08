import type {
  AuthResponse,
  AuthUser,
  LoginPayload,
  PasswordResetPayload,
  RegisterPayload,
} from "../types/auth";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function parseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => null);
  return new Error(payload?.detail ?? fallback);
}

/** Send a registration email code. */
export async function sendRegisterCode(email: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/register/send-code`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    throw await parseError(response, "验证码发送失败");
  }
}

/** Send a password reset email code. */
export async function sendPasswordResetCode(email: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/password-reset/send-code`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    throw await parseError(response, "验证码发送失败");
  }
}

/** Register and receive the current user through HttpOnly cookies. */
export async function register(payload: RegisterPayload): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, "注册失败");
  }
  return (await response.json()) as AuthResponse;
}

/** Login with email and password. */
export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, "登录失败");
  }
  return (await response.json()) as AuthResponse;
}

/** Reset password with email verification code. */
export async function resetPassword(payload: PasswordResetPayload): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/password-reset`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, "重置密码失败");
  }
}

/** Fetch the current user from the access-token cookie. */
export async function getMe(): Promise<AuthUser | null> {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    credentials: "include",
  });
  if (response.status === 401) return null;
  if (!response.ok) {
    throw await parseError(response, "获取登录状态失败");
  }
  return (await response.json()) as AuthUser;
}

/** Refresh cookies using the refresh-token cookie. */
export async function refreshAuth(): Promise<AuthResponse | null> {
  const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (response.status === 401) return null;
  if (!response.ok) {
    throw await parseError(response, "刷新登录状态失败");
  }
  return (await response.json()) as AuthResponse;
}

/** Logout and clear auth cookies. */
export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    throw await parseError(response, "退出登录失败");
  }
}
