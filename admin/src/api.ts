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

function authHeader(): Record<string, string> {
  const token = getToken();
  if (inTelegram()) return { Authorization: `tma ${window.Telegram!.WebApp!.initData}` };
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = { ...authHeader() };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail ?? detail; } catch { /* plain text */ }
    if (typeof detail !== "string") detail = JSON.stringify(detail);
    if (res.status === 401 && !path.startsWith("/admin/login")) onUnauthorized?.();
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await raw(path, init)).json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

const blobCache = new Map<number, string>();
export async function fileUrl(id: number): Promise<string> {
  const hit = blobCache.get(id);
  if (hit) return hit;
  const url = URL.createObjectURL(await (await raw(`/admin/files/${id}`)).blob());
  blobCache.set(id, url);
  return url;
}

export async function download(path: string, filename: string) {
  const blob = await (await raw(path)).blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

export type I18n = { uz?: string; ru?: string; en?: string };
export const nameOf = (n: I18n | null | undefined) => (n ? n.uz || n.ru || n.en || "" : "");
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString("ru-RU", {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
export const fmtDay = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString("ru-RU") : "—");
export const fmtSum = (n: number) => n.toLocaleString("ru-RU").replace(/,/g, " ");
