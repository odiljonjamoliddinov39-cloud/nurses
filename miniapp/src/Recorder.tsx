import { useEffect, useRef, useState } from "react";
import { useT } from "./i18n";
import { haptic } from "./ui";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", "audio/aac"];

function pickMime(): string {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export interface Recording { blob: Blob; mime: string; seconds: number }

/** Record up to maxSeconds; shows a preview with "record again" before the parent submits. */
export default function Recorder({ maxSeconds, onReady, disabled }: {
  maxSeconds: number; onReady: (r: Recording | null) => void; disabled?: boolean;
}) {
  const t = useT();
  const [state, setState] = useState<"idle" | "recording" | "done">("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const started = useRef(0);
  const timer = useRef<number | null>(null);

  const cleanup = () => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((tr) => tr.stop());
    stream.current = null;
  };
  useEffect(() => () => { cleanup(); if (preview) URL.revokeObjectURL(preview); }, []); // eslint-disable-line

  const start = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(t("mic_unsupported"));
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError(t("mic_denied"));
      return;
    }
    const mime = pickMime();
    const r = mime ? new MediaRecorder(stream.current, { mimeType: mime }) : new MediaRecorder(stream.current);
    chunks.current = [];
    r.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
    r.onstop = () => {
      const elapsed = (Date.now() - started.current) / 1000;
      cleanup();
      const type = (r.mimeType || mime || "audio/webm").split(";")[0];
      const blob = new Blob(chunks.current, { type });
      if (elapsed < 2 || blob.size < 2000) {
        setError(t("too_short"));
        setState("idle");
        onReady(null);
        return;
      }
      const url = URL.createObjectURL(blob);
      setPreview((old) => { if (old) URL.revokeObjectURL(old); return url; });
      setState("done");
      onReady({ blob, mime: type, seconds: elapsed });
    };
    rec.current = r;
    r.start(1000);
    started.current = Date.now();
    setSeconds(0);
    setState("recording");
    haptic("light");
    timer.current = window.setInterval(() => {
      const s = (Date.now() - started.current) / 1000;
      setSeconds(s);
      if (s >= maxSeconds) stop();
    }, 250);
  };

  const stop = () => {
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
    haptic("light");
  };

  const reset = () => {
    setPreview((old) => { if (old) URL.revokeObjectURL(old); return null; });
    setState("idle");
    setSeconds(0);
    onReady(null);
  };

  return (
    <div className="recorder">
      {state === "idle" && (
        <>
          <button className="mic" onClick={start} disabled={disabled} aria-label="record">
            <svg viewBox="0 0 24 24" width="40" height="40"><path fill="currentColor" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2Z" /></svg>
          </button>
          <p className="muted small center-text">{t("record_hint")}</p>
        </>
      )}
      {state === "recording" && (
        <>
          <button className="mic recording" onClick={stop} aria-label="stop">
            <span className="stop-square" />
          </button>
          <p className="timer"><span className="dot" /> {t("recording")} {fmt(seconds)} / {fmt(maxSeconds)}</p>
          <div className="progress"><div style={{ width: `${Math.min(100, (seconds / maxSeconds) * 100)}%` }} /></div>
        </>
      )}
      {state === "done" && preview && (
        <>
          <audio controls src={preview} />
          <button className="btn link" onClick={reset} disabled={disabled}>↺ {t("rerecord")}</button>
        </>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
