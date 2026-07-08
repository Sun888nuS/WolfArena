/** Safe user payload returned by the backend auth API. */
export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

/** Auth response used by login, register, and refresh endpoints. */
export interface AuthResponse {
  user: AuthUser;
}

/** Registration payload after an email code has been sent. */
export interface RegisterPayload {
  email: string;
  password: string;
  code: string;
  display_name?: string;
}

/** Password login payload. */
export interface LoginPayload {
  email: string;
  password: string;
}

/** Password reset payload after an email code has been sent. */
export interface PasswordResetPayload {
  email: string;
  code: string;
  new_password: string;
}
