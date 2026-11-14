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

const BOT_USERNAME: string | undefined = import.meta.env.VITE_BOT_USERNAME;

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

function TelegramLoginButton({ onAuth }: { onAuth: (u: Record<string, string | number>) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!BOT_USERNAME || !box.current) return;
    window.onTelegramAuth = onAuth;
    const s = document.createElement("script");
    s.src = "https://telegram.org/js/telegram-widget.js?22";
    s.async = true;
    s.setAttribute("data-telegram-login", BOT_USERNAME);
    s.setAttribute("data-size", "large");
    s.setAttribute("data-request-access", "write");
    s.setAttribute("data-onauth", "onTelegramAuth(user)");
    box.current.replaceChildren(s);
  }, [onAuth]);
  if (!BOT_USERNAME) return null;  // optional: the code sign-in below needs no configuration
  return <div ref={box} className="tg-login" />;
}

const currentPage = () => {
  const id = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.id === id) ? id : "dashboard";
};

/** `#/login?code=ABCD-EFGH` (the bot's one-tap link) -> the code, if present. */
const codeFromLink = () => /login\?code=([A-Za-z0-9-]+)/.exec(window.location.hash)?.[1] ?? null;

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [code, setCode] = useState("");
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
      .catch((e) => setState({ kind: "login", error: e instanceof ApiError ? e.message : `Sign-in failed: ${e.message}` }));
  }, [check]);

  useEffect(() => {
    setUnauthorizedHandler(() => { setToken(null); setState({ kind: "login", error: "Session expired, sign in again." }); });
    const linked = codeFromLink();
    if (linked) { window.history.replaceState(null, "", window.location.pathname); signInWithCode(linked); }  // one-tap link from the bot
    else check();
  }, [check, signInWithCode]);

  const onAuth = useCallback((user: Record<string, string | number>) => {
    setState({ kind: "loading" });
    post<{ token: string }>("/admin/login", user)
      .then(({ token }) => { setToken(token); check(); })
      .catch((e) => setState({
        kind: "login",
        error: e instanceof ApiError && e.status === 403 ? "This Telegram account is not an admin." : `Login failed: ${e.message}`,
      }));
  }, [check]);

  if (state.kind === "loading") return <div className="login"><p className="muted">Loading…</p></div>;
  if (state.kind === "login") {
    return (
      <div className="login">
        <div className="login-card">
          <h1>Admin sign-in</h1>
          {inTelegram() ? (
            <>{state.error && <p className="error-text">{state.error}</p>}<p>Not authorised.</p></>
          ) : (
            <>
              <ol className="steps">
                <li>Open your bot in Telegram and send <code>/admin</code></li>
                <li>Type the code it sends back</li>
              </ol>
              <form onSubmit={(e) => { e.preventDefault(); if (code.trim()) signInWithCode(code.trim()); }}>
                <input className="code-input" value={code} autoFocus autoComplete="off" autoCapitalize="characters" spellCheck={false}
                  placeholder="ABCD-EFGH" maxLength={16} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                <button className="btn" type="submit" disabled={code.trim().length < 8}>Sign in</button>
              </form>
              {state.error && <p className="error-text">{state.error}</p>}
              {BOT_USERNAME && <><div className="muted small or">or</div><TelegramLoginButton onAuth={onAuth} /></>}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="layout">
      <aside className={menu ? "open" : ""}>
        <div className="brand">Oral Exam Trainer<span>Admin</span></div>
        <nav>
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}`} className={page === p.id ? "active" : ""} onClick={() => setMenu(false)}>
              <span>{p.icon}</span>{p.label}
            </a>
          ))}
        </nav>
        <div className="who">
          {state.me.full_name ?? state.me.telegram_id}
          {!inTelegram() && <button className="link" onClick={() => { setToken(null); setState({ kind: "login" }); }}>Sign out</button>}
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
