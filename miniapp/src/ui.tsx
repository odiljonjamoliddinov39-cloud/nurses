import { useEffect, useState, type ReactNode } from "react";
import { fileUrl } from "./api";
import { useT } from "./i18n";

export function Spinner({ label }: { label?: string }) {
  const t = useT();
  return (
    <div className="center muted">
      <div className="spinner" />
      <p>{label ?? t("loading")}</p>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  const t = useT();
  return (
    <div className="card error">
      <p>{error}</p>
      {onRetry && <button className="btn secondary" onClick={onRetry}>{t("retry")}</button>}
    </div>
  );
}

export function Section({ title, children, right }: { title?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="section">
      {title && <div className="section-title"><span>{title}</span>{right}</div>}
      {children}
    </section>
  );
}

/** Plays a protected file (fetched with the auth header). */
export function AuthAudio({ id, label }: { id: number; label?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    fileUrl(id).then((u) => alive && setSrc(u)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [id]);
  if (failed) return null;
  return (
    <div className="audio">
      {label && <div className="audio-label">{label}</div>}
      {src ? <audio controls preload="metadata" src={src} /> : <div className="spinner small" />}
    </div>
  );
}

export function scoreClass(score: number | null | undefined) {
  if (score == null) return "none";
  if (score >= 4) return "good";
  if (score >= 2.5) return "mid";
  return "low";
}

export function ScoreChip({ score }: { score: number | null | undefined }) {
  return <span className={`chip score-${scoreClass(score)}`}>{score == null ? "—" : `${score}/5`}</span>;
}

export function ScoreRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score / 5));
  const r = 52, c = 2 * Math.PI * r;
  return (
    <svg className={`ring score-${scoreClass(score)}`} viewBox="0 0 120 120" width="140" height="140">
      <circle cx="60" cy="60" r={r} className="ring-bg" />
      <circle cx="60" cy="60" r={r} className="ring-fg" strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 60 60)" />
      <text x="60" y="58" textAnchor="middle" className="ring-num">{score}</text>
      <text x="60" y="80" textAnchor="middle" className="ring-den">/ 5</text>
    </svg>
  );
}

export function haptic(kind: "success" | "error" | "light") {
  const h = window.Telegram?.WebApp?.HapticFeedback;
  if (!h) return;
  if (kind === "light") h.impactOccurred("light");
  else h.notificationOccurred(kind);
}
