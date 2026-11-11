// Every request carries Telegram initData; the backend verifies its signature.
declare global {
  interface Window {
    Telegram?: { WebApp?: { initData: string; ready(): void; expand(): void } };
  }
}

// Dev: Vite proxies /api to the backend. Production (Vercel): set VITE_API_URL=https://<backend>.
const BASE: string = import.meta.env.VITE_API_URL ?? "/api";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `tma ${window.Telegram?.WebApp?.initData ?? ""}` },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}
