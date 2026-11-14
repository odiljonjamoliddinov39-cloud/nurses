import { useEffect, useState, type ReactNode } from "react";
import { fileUrl } from "./api";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reload = () => {
    setLoading(true); setError("");
    fn().then((d) => setData(d)).catch((e) => setError(e.message)).finally(() => setLoading(false));
  };
  useEffect(reload, deps); // eslint-disable-line
  return { data, error, loading, reload, setData };
}

export function Loading() { return <div className="muted pad">Loading…</div>; }
export function Err({ msg }: { msg: string }) { return msg ? <div className="alert error">{msg}</div> : null; }

export function Page({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <div className="page-head"><h1>{title}</h1><div className="row gap">{actions}</div></div>
      {children}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`}>
        <div className="modal-head"><h2>{title}</h2><button className="icon" onClick={onClose}>✕</button></div>
        {children}
      </div>
    </div>
  );
}

export function AuthImage({ id }: { id: number }) {
  const [src, setSrc] = useState<string | null>(null);
  const [type, setType] = useState("");
  useEffect(() => {
    fileUrl(id).then(async (u) => {
      const b = await fetch(u).then((r) => r.blob());
      setType(b.type); setSrc(u);
    }).catch(() => setSrc(null));
  }, [id]);
  if (!src) return <div className="muted">Loading receipt…</div>;
  if (type === "application/pdf") return <a href={src} target="_blank" rel="noreferrer">Open PDF receipt</a>;
  return <a href={src} target="_blank" rel="noreferrer"><img className="receipt" src={src} alt="receipt" /></a>;
}

export function AuthAudio({ id }: { id: number }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => { fileUrl(id).then(setSrc).catch(() => setSrc(null)); }, [id]);
  return src ? <audio controls src={src} /> : <span className="muted small">…</span>;
}

export function Badge({ value }: { value: string }) {
  return <span className={`badge b-${value}`}>{value}</span>;
}

export function Score({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="muted">—</span>;
  const c = v >= 4 ? "good" : v >= 2.5 ? "mid" : "low";
  return <span className={`score ${c}`}>{v}</span>;
}
