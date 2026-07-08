import { useState } from "react";

import type { AuthState } from "./useAuth";

type AuthView = "login" | "register" | "reset";

/** Full-page auth flow before gameplay. */
export function AuthPanel({ auth }: { auth: AuthState }) {
  const [view, setView] = useState<AuthView>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");

  function switchView(nextView: AuthView) {
    setView(nextView);
    setPassword("");
    setConfirmPassword("");
    setCode("");
    setNotice("");
    auth.clearError();
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    if (view === "login") {
      await auth.login({ email, password });
      return;
    }
    if (view === "register") {
      await auth.register({
        email,
        password,
        code,
        display_name: displayName || undefined,
      });
      return;
    }
    if (password !== confirmPassword) {
      setNotice("两次输入的密码不一致");
      return;
    }
    await auth.resetPassword({
      email,
      code,
      new_password: password,
    });
    setNotice("密码已重置，请登录");
    setPassword("");
    setConfirmPassword("");
    setCode("");
    setView("login");
  }

  async function handleSendCode() {
    setNotice("");
    if (view === "reset") {
      await auth.sendPasswordResetCode(email);
    } else {
      await auth.sendCode(email);
    }
    setNotice("验证码已发送，请查收邮箱");
  }

  return (
    <main className="auth-page">
      <div className="auth-system-name">WolfArena AI</div>
      <section className="auth-card" aria-label={titleForView(view)}>
        <h1>{titleForView(view)}</h1>

        <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="邮箱"
            type="email"
            autoComplete="email"
            required
          />

          {view === "register" ? (
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="昵称"
              maxLength={80}
            />
          ) : null}

          {view !== "login" ? (
            <div className="code-row">
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="验证码"
                inputMode="numeric"
                required
              />
              <button
                className="secondary-button"
                onClick={() => void handleSendCode()}
                type="button"
                disabled={auth.loading || !email}
              >
                获取验证码
              </button>
            </div>
          ) : null}

          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={view === "reset" ? "新密码" : "密码"}
            type="password"
            autoComplete={view === "login" ? "current-password" : "new-password"}
            minLength={view === "login" ? 1 : 8}
            required
          />

          {view === "reset" ? (
            <input
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="再次输入密码"
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
            />
          ) : null}

          <button type="submit" disabled={auth.loading}>
            {submitLabelForView(view)}
          </button>
        </form>

        <div className="auth-links">
          {view === "login" ? (
            <>
              <button onClick={() => switchView("reset")} type="button">
                忘记密码
              </button>
              <span>
                没有账户？
                <button onClick={() => switchView("register")} type="button">
                  去注册
                </button>
              </span>
            </>
          ) : null}

          {view === "register" ? (
            <span>
              已有账户？
              <button onClick={() => switchView("login")} type="button">
                去登录
              </button>
            </span>
          ) : null}

          {view === "reset" ? (
            <span>
              想起密码？
              <button onClick={() => switchView("login")} type="button">
                去登录
              </button>
            </span>
          ) : null}
        </div>

        {notice ? <p className="auth-note">{notice}</p> : null}
        {auth.error ? <p className="auth-error">{auth.error}</p> : null}
      </section>
    </main>
  );
}

function titleForView(view: AuthView): string {
  if (view === "register") return "注册";
  if (view === "reset") return "重置密码";
  return "登录";
}

function submitLabelForView(view: AuthView): string {
  if (view === "register") return "注册";
  if (view === "reset") return "确认";
  return "登录";
}
