import { AuthPanel } from "../features/auth/AuthPanel";
import { useAuth } from "../features/auth/useAuth";
import { GamePage } from "../features/game/GamePage";

/** Application root with auth kept independent from gameplay. */
export function App() {
  const auth = useAuth();

  if (auth.initializing) {
    return (
      <main className="auth-page">
        <div className="auth-system-name">WolfArena AI</div>
        <section className="auth-card auth-card-loading">
          <strong>正在恢复登录状态...</strong>
        </section>
      </main>
    );
  }

  if (!auth.user) {
    return <AuthPanel auth={auth} />;
  }

  return <GamePage currentUser={auth.user} onLogout={auth.logout} authLoading={auth.loading} />;
}
