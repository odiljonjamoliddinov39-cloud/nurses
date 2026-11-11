import { useEffect, useState } from "react";
import { api } from "./api";

type Me = { full_name: string | null; status: string };

// TODO (MVP screens): onboarding, home, oral exam start, question, answer (recorder),
// result, my results, profile & subscription, paywall.
export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    api<Me>("/me").then(setMe).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p>Error: {error}</p>;
  if (!me) return <p>Loading…</p>;
  return <h1>Hello, {me.full_name ?? "nurse"} ({me.status})</h1>;
}
