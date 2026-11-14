import { useState } from "react";
import { api, ApiError, type McqResult, type TestQuestion } from "../api";
import { useT } from "../i18n";
import { haptic, Spinner } from "../ui";

type Phase = "setup" | "loading" | "run" | "result";

/** Multiple-choice test with instant green/red feedback. Results live only in this session. */
export default function TestMode({ courseId, onPaywall, onExit }: { courseId: number; onPaywall: () => void; onExit: () => void }) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>("setup");
  const [count, setCount] = useState(10);
  const [qs, setQs] = useState<TestQuestion[]>([]);
  const [i, setI] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [res, setRes] = useState<McqResult | null>(null);
  const [wrong, setWrong] = useState<TestQuestion[]>([]);
  const [right, setRight] = useState(0);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setError(""); setEmpty(false); setPhase("loading");
    try {
      const r = await api<{ questions: TestQuestion[] }>(`/courses/${courseId}/test?count=${count}`);
      if (!r.questions.length) { setEmpty(true); setPhase("setup"); return; }
      setQs(r.questions); setI(0); setPicked(null); setRes(null); setWrong([]); setRight(0); setPhase("run");
      window.scrollTo(0, 0);
    } catch (e) {
      setError(`${t("error")}: ${(e as Error).message}`);
      setPhase("setup");
    }
  };

  const choose = async (optionId: number) => {
    if (res || busy) return;
    const q = qs[i];
    setBusy(true); setPicked(optionId); setError("");
    try {
      const r = await api<McqResult>(`/questions/${q.id}/mcq-answer`, { method: "POST", body: JSON.stringify({ option_id: optionId }) });
      haptic(r.correct ? "success" : "error");
      setRes(r);
      if (r.correct) setRight((n) => n + 1); else setWrong((w) => [...w, q]);
    } catch (e) {
      setPicked(null);
      if (e instanceof ApiError && e.status === 402) return onPaywall();
      setError(`${t("error")}: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const next = () => {
    if (i + 1 >= qs.length) { setPhase("result"); window.scrollTo(0, 0); return; }
    setI(i + 1); setPicked(null); setRes(null); window.scrollTo(0, 0);
  };

  if (phase === "setup" || phase === "loading") {
    return (
      <div>
        <div className="card">
          <h2>📝 {t("test_mode")}</h2>
          <p className="muted">{t("test_intro")}</p>
          <div className="section-title"><span>{t("mock_count")}</span></div>
          <div className="chips-row">
            {[5, 10, 20].map((n) => (
              <button key={n} className={`chip-btn ${count === n ? "active" : ""}`} onClick={() => setCount(n)}>{n}</button>
            ))}
          </div>
        </div>
        {empty && <div className="card warn">{t("test_none")}</div>}
        {error && <p className="error-text center-text">{error}</p>}
        <div className="sticky-bottom">
          <button className="btn block" disabled={phase === "loading"} onClick={start}>{t("mock_start")}</button>
        </div>
      </div>
    );
  }

  if (phase === "result") {
    return (
      <div>
        <div className="card result-card">
          <h2>{t("test_result")}</h2>
          <div className="big-score">{right}<span>/{qs.length}</span></div>
          <p className="muted">{t("test_score", { c: right, n: qs.length })}</p>
        </div>
        {wrong.length > 0 && (
          <>
            <div className="section-title"><span>{t("test_mistakes")}</span><span>{wrong.length}</span></div>
            <ul className="qlist">
              {wrong.map((q) => (
                <li key={q.id}><div className="qitem"><span className="qnum">{q.number}</span><span className="qtext">{q.text}</span></div></li>
              ))}
            </ul>
          </>
        )}
        <div className="actions">
          <button className="btn secondary" onClick={onExit}>{t("to_list")}</button>
          <button className="btn" onClick={() => setPhase("setup")}>{t("test_retry")}</button>
        </div>
      </div>
    );
  }

  const q = qs[i];
  if (!q) return <Spinner />;
  const last = i + 1 >= qs.length;
  return (
    <div>
      <div className="card mock-bar"><span>{t("question")} {i + 1} / {qs.length}</span><span>✓ {right}</span></div>
      <div className="progress"><div style={{ width: `${(i / qs.length) * 100}%` }} /></div>
      <div className="card question-card"><p className="question-text">{q.text}</p></div>
      <div className="options">
        {q.options.map((o) => {
          const state = !res ? (picked === o.id ? "picked" : "")
            : o.id === res.correct_option_id ? "right" : o.id === picked ? "wrong" : "dim";
          return <button key={o.id} className={`option ${state}`} disabled={!!res || busy} onClick={() => choose(o.id)}>{o.text}</button>;
        })}
      </div>
      {error && <p className="error-text center-text">{error}</p>}
      {res && (
        <div className={`card ${res.correct ? "ok-card" : "warn"}`}>
          <b>{res.correct ? `✓ ${t("test_correct")}` : `✗ ${t("test_wrong")}`}</b>
          {res.explanation && <p className="pre">{res.explanation}</p>}
        </div>
      )}
      {res && (
        <div className="sticky-bottom">
          <button className="btn block" onClick={next}>{last ? t("test_finish") : `${t("mock_next")} →`}</button>
        </div>
      )}
    </div>
  );
}
