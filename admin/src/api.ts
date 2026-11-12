// Inside Telegram the panel sends initData; in a browser it sends the session token
// issued after Telegram Login. The backend verifies both.
declare global {
  interface Window {
    Telegram?: { WebApp?: { initData: string; ready(): void; expand(): void } };
    onTelegramAuth?: (user: Record<string, string | number>) => void;
  }
}

// Dev: Vite proxies /api to the backend. Production (Vercel): set VITE_API_URL=https://<backend>.
const BASE: string = import.meta.env.VITE_API_URL ?? "/api";
const TOKEN_KEY = "admin_session";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: session lasts until reload */ }
}

export const inTelegram = () => Boolean(window.Telegram?.WebApp?.initData);

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const auth = inTelegram() ? `tma ${window.Telegram!.WebApp!.initData}` : token ? `Bearer ${token}` : "";
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers, ...(auth ? { Authorization: auth } : {}) },
  });
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail ?? detail; } catch { /* plain text */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}
