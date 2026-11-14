import { useEffect, useState } from "react";
import { api, ApiError, type Attempt, type Me, type QuestionFull } from "../api";
import { useT } from "../i18n";
import Recorder, { type Recording } from "../Recorder";
import { uploadAnswer } from "../upload";
import { AuthAudio, ErrorBox, haptic, Spinner } from "../ui";

export default function QuestionScreen({ me, id, onAttempt, onPaywall }: {
  me: Me; id: number; onAttempt: (a: Attempt) => void; onPaywall: () => void;
}) {
  const t = useT();
  const [q, setQ] = useState<QuestionFull | null>(null);
  const [error, setError] = useState("");
  const [rec, setRec] = useState<Recording | null>(null);
  const [sending, setSending] = useState(false);
  const [fav, setFav] = useState(false);

  const load = () => {
    setError("");
    api<QuestionFull>(`/questions/${id}`).then(setQ).catch((e) => setError(e.message));
  };
  useEffect(load, [id]);
  useEffect(() => { if (q) setFav(q.favourite); }, [q?.id]); // eslint-disable-line

  const toggleFav = () => {
    if (!q) return;
    const on = !fav;
    haptic("light");
    setFav(on);
    api(`/questions/${q.id}/favourite`, { method: "POST", body: JSON.stringify({ on }) }).catch(() => setFav(!on));
  };

  const submit = async () => {
    if (!rec || !q) return;
    setSending(true);
    setError("");
    try {
      const a = await uploadAnswer(q.id, rec);
      haptic("success");
      onAttempt(a);
    } catch (e) {
      haptic("error");
      if (e instanceof ApiError && e.status === 402) return onPaywall();
      if (e instanceof ApiError && e.status === 429) setError(t("daily_limit"));
      else if (e instanceof ApiError && e.detail === "recording too short") setError(t("too_short"));
      else setError(`${t("error")}: ${(e as Error).message}`);
    } finally {
      setSending(false);
    }
  };

  if (!q && error) return <ErrorBox error={error} onRetry={load} />;
  if (!q) return <Spinner />;
  if (q.locked) {
    return (
      <div className="card promo">
        <p>{t("locked")}</p>
        <button className="btn" onClick={onPaywall}>{t("subscribe")}</button>
      </div>
    );
  }
  return (
    <div>
      <div className="card question-card">
        <div className="row-between">
          <span className="muted small">{t("question")} {q.number}{q.topic ? ` · ${q.topic}` : ""}</span>
          <button className={`star ${fav ? "on" : ""}`} aria-label={t("favourite")} onClick={toggleFav}>{fav ? "★" : "☆"}</button>
        </div>
        <p className="question-text">{q.text}</p>
        {q.question_audio && <AuthAudio id={q.question_audio} label={t("listen_question")} />}
      </div>
      <div className="card">
        <Recorder maxSeconds={me.max_answer_seconds || 180} onReady={setRec} disabled={sending} />
      </div>
      {error && <p className="error-text center-text">{error}</p>}
      <div className="sticky-bottom">
        <button className="btn block" disabled={!rec || sending} onClick={submit}>
          {sending ? t("sending") : t("submit_answer")}
        </button>
      </div>
    </div>
  );
}
