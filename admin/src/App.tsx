import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, inTelegram, setToken } from "./api";

const MODULES = ["Dashboard", "Payment requests", "Users", "Plans", "Courses",
  "Questions", "Audio", "Settings", "Logs"];
const BOT_USERNAME: string | undefined = import.meta.env.VITE_BOT_USERNAME;

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
  if (!BOT_USERNAME) return <p>VITE_BOT_USERNAME is not set for this deployment.</p>;
  return <div ref={box} />;
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const check = useCallback(() => {
    api<Me>("/admin/me")
      .then((me) => setState({ kind: "ok", me }))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setToken(null);
        const error = e instanceof ApiError && e.status === 403 ? "This Telegram account is not an admin." : undefined;
        setState({ kind: "login", error });
      });
  }, []);

  useEffect(check, [check]);

  const onAuth = useCallback((user: Record<string, string | number>) => {
    setState({ kind: "loading" });
    api<{ token: string }>("/admin/login", { method: "POST", body: JSON.stringify(user) })
      .then(({ token }) => { setToken(token); check(); })
      .catch((e) => setState({
        kind: "login",
        error: e instanceof ApiError && e.status === 403 ? "This Telegram account is not an admin." : `Login failed: ${e.message}`,
      }));
  }, [check]);

  if (state.kind === "loading") return <p>Loading…</p>;
  if (state.kind === "login") {
    return (
      <main style={{ maxWidth: 420, margin: "15vh auto", textAlign: "center", fontFamily: "system-ui" }}>
        <h1>Admin sign-in</h1>
        <p>Sign in with the Telegram account listed as admin.</p>
        {state.error && <p style={{ color: "#c0392b" }}>{state.error}</p>}
        {inTelegram() ? <p>Not authorised.</p> : <TelegramLoginButton onAuth={onAuth} />}
      </main>
    );
  }
  return (
    <nav style={{ fontFamily: "system-ui" }}>
      <h1>Admin</h1>
      <p>Signed in as {state.me.full_name ?? state.me.telegram_id}
        {!inTelegram() && <> · <button onClick={() => { setToken(null); setState({ kind: "login" }); }}>Sign out</button></>}
      </p>
      <ul>{MODULES.map((m) => <li key={m}>{m}</li>)}</ul>
    </nav>
  );
}
