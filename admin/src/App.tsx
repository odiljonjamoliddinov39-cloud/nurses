import { LangSwitch, t, tx } from "./i18n";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, inTelegram, post, setToken, setUnauthorizedHandler } from "./api";
import Attempts from "./pages/Attempts";
import Broadcasts from "./pages/Broadcasts";
import Content from "./pages/Content";
import Dashboard from "./pages/Dashboard";
import Logs from "./pages/Logs";
import Payments from "./pages/Payments";
import Plans from "./pages/Plans";
import Promos from "./pages/Promos";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import Users from "./pages/Users";

const PAGES: { id: string; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "📈" },
  { id: "payments", label: "Payment requests", icon: "💳" },
  { id: "users", label: "Users", icon: "👥" },
  { id: "content", label: "Courses & questions", icon: "📚" },
  { id: "plans", label: "Plans", icon: "🏷️" },
  { id: "promos", label: "Promo codes", icon: "🏷️" },
  { id: "attempts", label: "Answers", icon: "🎙️" },
  { id: "broadcasts", label: "Broadcasts", icon: "📣" },
  { id: "reports", label: "Reports", icon: "📊" },
  { id: "settings", label: "Settings", icon: "⚙️" },
  { id: "logs", label: "Logs", icon: "📜" },
];

type Me = { telegram_id: number; full_name: string | null };
type State = { kind: "loading" } | { kind: "login"; error?: string } | { kind: "ok"; me: Me };

const currentPage = () => {
  const id = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.id === id) ? id : "dashboard";
};

/** `#/login?code=ABCD-EFGH` (the bot's one-tap link) -> the code, if present. */
const codeFromLink = () => /login\?code=([A-Za-z0-9-]+)/.exec(window.location.hash)?.[1] ?? null;

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [page, setPage] = useState(currentPage);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    const h = () => setPage(currentPage());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  const go = (id: string) => { window.location.hash = `/${id}`; setMenu(false); };

  const check = useCallback(() => {
    api<Me>("/admin/me")
      .then((me) => setState({ kind: "ok", me }))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setToken(null);
        const error = e instanceof ApiError && e.status === 403 ? "This Telegram account is not an admin." : undefined;
        setState({ kind: "login", error });
      });
  }, []);

  const signInWithCode = useCallback((value: string) => {
    setState({ kind: "loading" });
    post<{ token: string }>("/admin/login-code", { code: value })
      .then(({ token }) => { setToken(token); setCode(""); window.location.hash = "/dashboard"; check(); })
      .catch((e) => setState({ kind: "login", error: e instanceof ApiError ? e.message : `${t("Sign-in failed:")} ${e.message}` }));
  }, [check]);

  const signInWithPassword = useCallback((value: string) => {
    setState({ kind: "loading" });
    post<{ token: string }>("/admin/login-password", { password: value })
      .then(({ token }) => { setToken(token); setPassword(""); window.location.hash = "/dashboard"; check(); })
      .catch((e) => setState({ kind: "login", error: e instanceof ApiError ? e.message : `${t("Sign-in failed:")} ${e.message}` }));
  }, [check]);

  useEffect(() => {
    setUnauthorizedHandler(() => { setToken(null); setState({ kind: "login", error: "Session expired, sign in again." }); });
    const linked = codeFromLink();
    if (linked) { window.history.replaceState(null, "", window.location.pathname); signInWithCode(linked); }  // one-tap link from the bot
    else check();
  }, [check, signInWithCode]);

  if (state.kind === "loading") return <div className="login"><p className="muted">{t("Loading…")}</p></div>;
  if (state.kind === "login") {
    return (
      <div className="login">
        <div className="login-card">
          <LangSwitch className="login-lang" />
          <h1>{t("Admin sign-in")}</h1>
          {inTelegram() ? (
            <>{state.error && <p className="error-text">{t(state.error)}</p>}<p>{t("Not authorised.")}</p></>
          ) : (
            <>
              <form onSubmit={(e) => { e.preventDefault(); if (password) signInWithPassword(password); }}>
                <label className="pw-label">{t("Password")}
                  <input className="pw-input" type="password" value={password} autoFocus autoComplete="current-password"
                    onChange={(e) => setPassword(e.target.value)} />
                </label>
                <button className="btn" type="submit" disabled={!password}>{t("Sign in")}</button>
              </form>
              {state.error && <p className="error-text">{t(state.error)}</p>}
              <p className="muted small hint">{tx("First time, or forgot it? Open your bot in Telegram and send {cmd}: it replies with a new password.", { cmd: <code>/password</code> })}</p>
              <button className="link small" type="button" onClick={() => setShowCode(!showCode)}>
                {showCode ? t("Hide") : t("Sign in with a one-time code from the bot instead")}
              </button>
              {showCode && (
                <form onSubmit={(e) => { e.preventDefault(); if (code.trim()) signInWithCode(code.trim()); }}>
                  <p className="muted small">{tx("Send {cmd} to the bot, then type the code it sends.", { cmd: <code>/admin</code> })}</p>
                  <input className="code-input" value={code} autoComplete="off" autoCapitalize="characters" spellCheck={false}
                    placeholder="ABCD-EFGH" maxLength={16} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                  <button className="btn" type="submit" disabled={code.trim().length < 8}>{t("Sign in with code")}</button>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="layout">
      <aside className={menu ? "open" : ""}>
        <div className="brand">{t("Oral Exam Trainer")}<span>{t("Admin")}</span></div>
        <nav>
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}`} className={page === p.id ? "active" : ""} onClick={() => setMenu(false)}>
              <span>{p.icon}</span>{t(p.label)}
            </a>
          ))}
        </nav>
        <LangSwitch className="side-lang" />
        <div className="who">
          {state.me.full_name ?? state.me.telegram_id}
          {!inTelegram() && <button className="link" onClick={() => { setToken(null); setState({ kind: "login" }); }}>{t("Sign out")}</button>}
        </div>
      </aside>
      <main>
        <button className="burger" onClick={() => setMenu(!menu)}>☰</button>
        {page === "dashboard" && <Dashboard go={go} />}
        {page === "payments" && <Payments />}
        {page === "users" && <Users />}
        {page === "content" && <Content />}
        {page === "plans" && <Plans />}
        {page === "attempts" && <Attempts />}
        {page === "broadcasts" && <Broadcasts />}
        {page === "promos" && <Promos />}
        {page === "reports" && <Reports />}
        {page === "settings" && <Settings />}
        {page === "logs" && <Logs />}
      </main>
    </div>
  );
}
