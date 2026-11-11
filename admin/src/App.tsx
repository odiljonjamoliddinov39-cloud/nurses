import { useEffect, useState } from "react";
import { api } from "./api";

const MODULES = ["Dashboard", "Payment requests", "Users", "Plans", "Courses",
  "Questions", "Audio", "Settings", "Logs"];

// TODO: Telegram login, then one page per module (see ARCHITECTURE.md section 7).
export default function App() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => { api("/me").then(() => setOk(true)).catch(() => setOk(false)); }, []);
  if (ok === null) return <p>Loading…</p>;
  if (!ok) return <p>Not authorised.</p>;
  return (
    <nav>
      <h1>Admin</h1>
      <ul>{MODULES.map((m) => <li key={m}>{m}</li>)}</ul>
    </nav>
  );
}
