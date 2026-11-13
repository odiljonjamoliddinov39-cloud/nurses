// Every request carries Telegram initData; the backend verifies its signature.
declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export interface TgWebApp {
  initData: string;
  colorScheme?: "light" | "dark";
  ready(): void;
  expand(): void;
  close(): void;
  openTelegramLink?(url: string): void;
  BackButton?: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { notificationOccurred(t: "success" | "error" | "warning"): void; impactOccurred(s: "light" | "medium"): void };
  showAlert?(msg: string): void;
}

export const tg = (): TgWebApp | undefined => window.Telegram?.WebApp;
export const inTelegram = () => Boolean(tg()?.initData);

// Dev: Vite proxies /api to the backend. Production (Vercel): set VITE_API_URL=https://<backend>.
const BASE: string = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Authorization: `tma ${tg()?.initData ?? ""}` };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail ?? detail; } catch { /* plain text */ }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

const blobCache = new Map<number, string>();

/** Protected files (recordings, question audio) need the auth header, so fetch them as blobs. */
export async function fileUrl(id: number): Promise<string> {
  const hit = blobCache.get(id);
  if (hit) return hit;
  const res = await fetch(`${BASE}/files/${id}`, { headers: { Authorization: `tma ${tg()?.initData ?? ""}` } });
  if (!res.ok) throw new ApiError(res.status, "file");
  const url = URL.createObjectURL(await res.blob());
  blobCache.set(id, url);
  return url;
}

export type I18n = { uz?: string; ru?: string; en?: string };

export interface Me {
  id: number; telegram_id: number; full_name: string | null; phone: string | null;
  ui_language: "uz" | "ru" | "en"; course_id: number | null;
  status: "guest" | "pending" | "subscriber" | "expired" | "blocked";
  subscription: { ends_at: string; plan: string | null } | null;
  last_payment: { status: string; reject_reason: string | null; code: string } | null;
  is_admin: boolean; support_contact: string; grading_mode: "self" | "ai";
  free_questions: number; max_answer_seconds: number;
}
export interface Course { id: number; name: I18n; description: I18n | null; questions: number }
export interface QuestionItem {
  id: number; number: number; text: string; topic_id: number | null;
  locked: boolean; free: boolean; best_score: number | null; attempts: number; favourite: boolean;
}
export interface CourseQuestions {
  course: { id: number; name: I18n }; full_access: boolean;
  topics: { id: number; name: string }[]; questions: QuestionItem[];
}
export interface QuestionFull {
  id: number; number: number; course_id: number; text: string; topic: string | null;
  locked: boolean; question_audio: number | null; favourite: boolean;
}
export interface KeyPoint { id: number; text: string; weight: number }
export interface Attempt {
  id: number; state: "recorded" | "transcribed" | "grading" | "graded" | "failed_retry"; created_at: string;
  question: { id: number; number: number; text: string; course_id: number };
  model_answer: string; explanation: string | null; model_audio: number | null;
  key_points: KeyPoint[]; audio: number | null; transcript: string | null;
  score: number | null; auto_score: number | null; manual_score: number | null;
  covered: number[]; wrong: string[]; comment: string | null; what_to_add: string | null; graded_by: string;
}
export interface Plan { id: number; name: string; days: number; price_uzs: number; courses: I18n[] }
export interface Payment {
  id: number; plan: string; amount: number; code: string; status: string;
  reject_reason: string | null; created_at: string;
}

export interface Stats {
  total: number; answered: number; average: number | null; streak: number;
  trend: { date: string; avg: number | null; count: number }[];
  weakest_topics: { topic: string; avg: number; answered: number }[];
}
export interface MockSet {
  questions: { id: number; number: number }[]; total_seconds: number; per_answer_seconds: number;
}
export interface LearnItem {
  id: number; number: number; text: string; topic: string | null; model_answer: string;
  question_audio: number | null; answer_audio: number | null;
}
