import { useEffect, useMemo, useState } from "react";

import {
  getMe,
  login as loginRequest,
  logout as logoutRequest,
  refreshAuth,
  register as registerRequest,
  resetPassword as resetPasswordRequest,
  sendPasswordResetCode,
  sendRegisterCode,
} from "../../services/auth";
import type { AuthUser, LoginPayload, PasswordResetPayload, RegisterPayload } from "../../types/auth";

/** Browser auth state and actions. Tokens stay in HttpOnly cookies. */
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      setInitializing(true);
      setError("");
      try {
        const current = await getMe();
        if (current) {
          if (!cancelled) setUser(current);
          return;
        }
        const refreshed = await refreshAuth();
        if (!cancelled) setUser(refreshed?.user ?? null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "登录状态恢复失败");
          setUser(null);
        }
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  return useMemo(
    () => ({
      user,
      initializing,
      loading,
      error,
      clearError: () => setError(""),
      sendCode: async (email: string) => {
        setLoading(true);
        setError("");
        try {
          await sendRegisterCode(email);
        } catch (err) {
          const message = err instanceof Error ? err.message : "验证码发送失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
      sendPasswordResetCode: async (email: string) => {
        setLoading(true);
        setError("");
        try {
          await sendPasswordResetCode(email);
        } catch (err) {
          const message = err instanceof Error ? err.message : "验证码发送失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
      register: async (payload: RegisterPayload) => {
        setLoading(true);
        setError("");
        try {
          const response = await registerRequest(payload);
          setUser(response.user);
        } catch (err) {
          const message = err instanceof Error ? err.message : "注册失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
      resetPassword: async (payload: PasswordResetPayload) => {
        setLoading(true);
        setError("");
        try {
          await resetPasswordRequest(payload);
        } catch (err) {
          const message = err instanceof Error ? err.message : "重置密码失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
      login: async (payload: LoginPayload) => {
        setLoading(true);
        setError("");
        try {
          const response = await loginRequest(payload);
          setUser(response.user);
        } catch (err) {
          const message = err instanceof Error ? err.message : "登录失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
      logout: async () => {
        setLoading(true);
        setError("");
        try {
          await logoutRequest();
          setUser(null);
        } catch (err) {
          const message = err instanceof Error ? err.message : "退出登录失败";
          setError(message);
          throw new Error(message);
        } finally {
          setLoading(false);
        }
      },
    }),
    [error, initializing, loading, user],
  );
}

export type AuthState = ReturnType<typeof useAuth>;
