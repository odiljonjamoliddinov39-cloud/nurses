import { useEffect, useRef, useState } from "react";
import { api, fileUrl, type LearnItem } from "../api";
import { useT } from "../i18n";
import { ErrorBox, haptic, Spinner } from "../ui";

const SPEEDS = [0.75, 1, 1.25, 1.5];
const sourcesOf = (it: LearnItem): number[] => [it.question_audio, it.answer_audio].filter((x): x is number => x != null);

/** Listening playlist: each question followed by its model answer, auto-advancing, adjustable speed. */
export default function Learn({ courseId }: { courseId: number }) {
  const t = useT();
  const [items, setItems] = useState<LearnItem[] | null>(null);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState(0);
  const [stage, setStage] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showText, setShowText] = useState(true);
  const audio = useRef<HTMLAudioElement>(null);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  playingRef.current = playing;
  speedRef.current = speed;

  const load = () => {
    setError("");
    api<{ items: LearnItem[] }>(`/courses/${courseId}/learn`).then((r) => setItems(r.items)).catch((e) => setError(e.message));
  };
  useEffect(load, [courseId]); // eslint-disable-line

  const cur = items?.[idx];
  const srcs = cur ? sourcesOf(cur) : [];

  // Next item that has audio (skipped silently while auto-playing); stop at the end.
  const advance = () => {
    if (!items) return;
    for (let j = idx + 1; j < items.length; j++) {
      if (sourcesOf(items[j]).length) { setIdx(j); setStage(0); return; }
    }
    setPlaying(false);
  };

  // Load the audio for the current item and stage.
  useEffect(() => {
    const a = audio.current;
    if (!a || !cur) return;
    const src = srcs[stage];
    if (src == null) { if (playingRef.current) advance(); return; }
    let alive = true;
    fileUrl(src).then((u) => {
      if (!alive) return;
      a.src = u;
      a.defaultPlaybackRate = speedRef.current;
      a.playbackRate = speedRef.current;
      if (playingRef.current) a.play().catch(() => setPlaying(false));
    }).catch(() => { if (alive && playingRef.current) advance(); });
    return () => { alive = false; };
  }, [items, idx, stage]); // eslint-disable-line

  useEffect(() => {
    const a = audio.current;
    if (a) { a.defaultPlaybackRate = speed; a.playbackRate = speed; }
  }, [speed]);

  const onEnded = () => { if (stage + 1 < srcs.length) setStage(stage + 1); else advance(); };

  const toggle = () => {
    const a = audio.current;
    if (!a || !cur) return;
    haptic("light");
    if (playing) { a.pause(); setPlaying(false); return; }
    setPlaying(true);
    if (!srcs.length) advance();
    else a.play().catch(() => setPlaying(false));
  };
  const go = (delta: number) => {
    if (!items) return;
    setIdx(Math.min(items.length - 1, Math.max(0, idx + delta)));
    setStage(0);
  };
  const cycleSpeed = () => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]);

  // Lock-screen / headset controls ("podcast" mode).
  useEffect(() => {
    if (!cur || !("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({ title: `${cur.number}. ${cur.text}`, artist: t("learn_title") });
    navigator.mediaSession.setActionHandler("play", toggle);
    navigator.mediaSession.setActionHandler("pause", toggle);
    navigator.mediaSession.setActionHandler("nexttrack", () => go(1));
    navigator.mediaSession.setActionHandler("previoustrack", () => go(-1));
  }); // eslint-disable-line

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!items) return <Spinner />;
  if (!items.length || !cur) return <div className="card muted center-text">{t("no_questions")}</div>;

  const hasAnyAudio = items.some((it) => sourcesOf(it).length > 0);
  const isQuestion = cur.question_audio != null && stage === 0;

  return (
    <div>
      <div className="card">
        <h2>🎧 {t("learn_title")}</h2>
        <p className="muted small">{t("learn_hint")}</p>
      </div>
      {!hasAnyAudio && <div className="card warn">{t("learn_no_audio")}</div>}

      <div className="card question-card">
        <div className="muted small">{t("question")} {cur.number}{cur.topic ? ` · ${cur.topic}` : ""}
          {srcs.length > 0 && <span className="badge">{isQuestion ? t("question") : t("model_answer")}</span>}</div>
        <p className="question-text">{cur.text}</p>
        {showText && <p className="pre muted">{cur.model_answer}</p>}
      </div>

      <div className="player">
        <button className="btn secondary" onClick={() => go(-1)} disabled={idx === 0} aria-label="previous">⏮</button>
        <button className="btn play" onClick={toggle} disabled={!hasAnyAudio} aria-label="play">{playing ? "⏸" : "▶"}</button>
        <button className="btn secondary" onClick={() => go(1)} disabled={idx === items.length - 1} aria-label="next">⏭</button>
      </div>
      <div className="player-opts">
        <button className="chip-btn" onClick={cycleSpeed}>{t("learn_speed")}: {speed}×</button>
        <button className={`chip-btn ${showText ? "active" : ""}`} onClick={() => setShowText(!showText)}>{t("learn_text")}</button>
      </div>
      <audio ref={audio} onEnded={onEnded} preload="auto" />

      <div className="section-title"><span>{t("learn_list")}</span><span>{idx + 1} / {items.length}</span></div>
      <ul className="qlist">
        {items.map((it, j) => (
          <li key={it.id}>
            <button className={`qitem ${j === idx ? "current" : ""}`} onClick={() => { setIdx(j); setStage(0); }}>
              <span className="qnum">{it.number}</span>
              <span className="qtext">{it.text}</span>
              {sourcesOf(it).length > 0 && <span className="lock">🔊</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
