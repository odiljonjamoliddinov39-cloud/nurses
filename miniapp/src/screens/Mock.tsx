import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Attempt, type Me, type MockSet, type QuestionFull } from "../api";
import { useT } from "../i18n";
import Recorder, { type Recording } from "../Recorder";
import { uploadAnswer } from "../upload";
import { AuthAudio, ErrorBox, haptic, ScoreChip, ScoreRing, Spinner } from "../ui";
import AttemptView from "./AttemptView";

type Phase = "setup" | "loading" | "answer" | "check" | "result";

const mmss = (s: number) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.max(0, s) % 60).padStart(2, "0")}`;

/** Mock exam: random questions, one total timer, no hints; self-check afterwards; one combined score. */
export default function Mock({ me, courseId, onPaywall, onExit }: {
  me: Me; courseId: number; onPaywall: () => void; onExit: () => void;
}) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>("setup");
  const [count, setCount] = useState(4);
  const [set, setSet] = useState<MockSet | null>(null);
  const [i, setI] = useState(0);
  const [q, setQ] = useState<QuestionFull | null>(null);
  const [rec, setRec] = useState<Recording | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [left, setLeft] = useState(0);
  const [checkIdx, setCheckIdx] = useState(0);
  const [final, setFinal] = useState<Attempt[] | null>(null);
  const [timeUp, setTimeUp] = useState(false);
  const finishing = useRef(false);

  const start = async () => {
    setError("");
    setPhase("loading");
    try {
      const s = await api<MockSet>(`/courses/${courseId}/mock?count=${count}`);
      finishing.current = false;
      setSet(s); setI(0); setAttempts([]); setFinal(null); setTimeUp(false); setLeft(s.total_seconds);
      setPhase("answer");
    } catch (e) {
      setError(`${t("error")}: ${(e as Error).message}`);
      setPhase("setup");
    }
  };

  // Load the current question.
  useEffect(() => {
    if (phase !== "answer" || !set) return;
    setQ(null); setRec(null);
    api<QuestionFull>(`/questions/${set.questions[i].id}`).then(setQ).catch((e) => setError(e.message));
  }, [phase, i, set]);

  // One timer for the whole exam.
  useEffect(() => {
    if (phase !== "answer") return;
    const h = window.setInterval(() => setLeft((l) => l - 1), 1000);
    return () => window.clearInterval(h);
  }, [phase]);

  const toCheck = (list: Attempt[]) => {
    finishing.current = true;
    setCheckIdx(0);
    setPhase(list.length ? "check" : "result");
    window.scrollTo(0, 0);
  };

  const submit = async (expired = false) => {
    if (!set || finishing.current) return;
    const cur = q && rec ? { q, rec } : null;
    if (!expired && !cur) return;
    if (expired) { finishing.current = true; setTimeUp(true); }
    setSending(true);
    setError("");
    let list = attempts;
    try {
      if (cur) {
        const a = await uploadAnswer(cur.q.id, cur.rec);
        list = [...attempts, a];
        setAttempts(list);
        haptic("success");
      }
      if (expired || i + 1 >= set.questions.length) toCheck(list);
      else setI(i + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) return onPaywall();
      if (expired) return toCheck(list);  // time is up: grade whatever was already sent
      haptic("error");
      if (e instanceof ApiError && e.status === 429) setError(t("daily_limit"));
      else if (e instanceof ApiError && e.detail === "recording too short") setError(t("too_short"));
      else setError(`${t("error")}: ${(e as Error).message}`);
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    if (phase === "answer" && left <= 0 && !finishing.current) void submit(true);
  }, [left, phase]); // eslint-disable-line

  // Final scores come from the server, so AI-graded and teacher-corrected scores are included.
  useEffect(() => {
    if (phase !== "result") return;
    Promise.all(attempts.map((a) => api<Attempt>(`/attempts/${a.id}`))).then(setFinal).catch((e) => setError(e.message));
  }, [phase]); // eslint-disable-line

  if (phase === "setup" || phase === "loading") {
    return (
      <div>
        <div className="card">
          <h2>🎓 {t("mock_exam")}</h2>
          <p className="muted">{t("mock_intro")}</p>
          <div className="section-title"><span>{t("mock_count")}</span></div>
          <div className="chips-row">
            {[3, 4, 5].map((n) => (
              <button key={n} className={`chip-btn ${count === n ? "active" : ""}`} onClick={() => setCount(n)}>{n}</button>
            ))}
          </div>
        </div>
        {error && <p className="error-text center-text">{error}</p>}
        <div className="sticky-bottom">
          <button className="btn block" disabled={phase === "loading"} onClick={start}>{t("mock_start")}</button>
        </div>
      </div>
    );
  }

  if (phase === "answer" && set) {
    const last = i + 1 >= set.questions.length;
    return (
      <div>
        <div className="card mock-bar">
          <span>{t("question")} {i + 1} / {set.questions.length}</span>
          <span className={`timer ${left <= 60 ? "urgent" : ""}`}>⏱ {mmss(left)}</span>
        </div>
        <div className="progress"><div style={{ width: `${(i / set.questions.length) * 100}%` }} /></div>
        {!q && !error && <Spinner />}
        {q && (
          <>
            <div className="card question-card">
              <p className="question-text">{q.text}</p>
              {q.question_audio && <AuthAudio id={q.question_audio} label={t("listen_question")} />}
            </div>
            <div className="card">
              <Recorder key={q.id} maxSeconds={Math.min(me.max_answer_seconds || 180, Math.max(left, 5))} onReady={setRec} disabled={sending} />
            </div>
          </>
        )}
        {error && <p className="error-text center-text">{error}</p>}
        <div className="sticky-bottom">
          <button className="btn block" disabled={!rec || sending} onClick={() => submit(false)}>
            {sending ? t("sending") : last ? t("mock_finish") : `${t("mock_next")} →`}
          </button>
        </div>
      </div>
    );
  }

  if (phase === "check") {
    const a = attempts[checkIdx];
    const lastOne = checkIdx + 1 >= attempts.length;
    return (
      <div>
        {timeUp && <div className="card warn">{t("mock_time_up")}</div>}
        <div className="card">
          <h3>{t("mock_check_title")} · {checkIdx + 1}/{attempts.length}</h3>
          <p className="muted small">{t("mock_check_hint")}</p>
        </div>
        <AttemptView key={a.id} id={a.id} initial={a} compact
          nextLabel={lastOne ? t("mock_result") : t("next_question")}
          onAgain={() => undefined}
          onNext={() => (lastOne ? setPhase("result") : setCheckIdx(checkIdx + 1))}
          onList={() => setPhase("result")} />
      </div>
    );
  }

  // result
  if (error && !final) return <ErrorBox error={error} />;
  if (!final || !set) return attempts.length === 0 ? (
    <div className="card center-text"><p>{t("mock_no_answers")}</p>
      <div className="actions"><button className="btn secondary" onClick={onExit}>{t("to_list")}</button>
        <button className="btn" onClick={() => setPhase("setup")}>{t("mock_retry")}</button></div></div>
  ) : <Spinner />;
  const byQuestion = new Map(final.map((a) => [a.question.id, a]));
  const total = set.questions.reduce((sum, qq) => sum + (byQuestion.get(qq.id)?.score ?? 0), 0);
  const avg = Math.round((total / set.questions.length) * 10) / 10;
  return (
    <div>
      <div className="card result-card">
        <h2>{t("mock_result")}</h2>
        <ScoreRing score={avg} />
        <p className="muted small">{t("mock_total")}</p>
      </div>
      <ul className="qlist">
        {set.questions.map((qq) => {
          const a = byQuestion.get(qq.id);
          return (
            <li key={qq.id}>
              <div className="qitem">
                <span className="qnum">{qq.number}</span>
                <span className="qtext">{a ? a.question.text : <span className="muted">{t("mock_unanswered")}</span>}</span>
                <ScoreChip score={a ? a.score : 0} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="actions">
        <button className="btn secondary" onClick={onExit}>{t("to_list")}</button>
        <button className="btn" onClick={() => setPhase("setup")}>{t("mock_retry")}</button>
      </div>
    </div>
  );
}
