import { useEffect, useState } from "react";
import { api, type Attempt } from "../api";
import { useT } from "../i18n";
import { AuthAudio, ErrorBox, haptic, ScoreRing, Section, Spinner } from "../ui";

const SCORES = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];

export default function AttemptView({ id, initial, onAgain, onNext, onList, compact, nextLabel }: {
  id: number; initial?: Attempt; onAgain: (questionId: number) => void; onNext?: () => void; onList: () => void;
  /** Used inside the mock exam: no "answer again" button. */
  compact?: boolean; nextLabel?: string;
}) {
  const t = useT();
  const [a, setA] = useState<Attempt | null>(initial ?? null);
  const [error, setError] = useState("");
  const [covered, setCovered] = useState<Set<number>>(new Set());
  const [manual, setManual] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => api<Attempt>(`/attempts/${id}`).then(setA).catch((e) => setError(e.message));
  useEffect(() => { if (!initial) load(); }, [id]); // eslint-disable-line

  // AI grading runs in the background: poll until it finishes.
  useEffect(() => {
    if (a?.state !== "grading") return;
    const h = window.setInterval(load, 2500);
    return () => window.clearInterval(h);
  }, [a?.state]); // eslint-disable-line

  const toggle = (kp: number) => setCovered((s) => {
    const n = new Set(s);
    if (n.has(kp)) n.delete(kp); else n.add(kp);
    return n;
  });

  const grade = async () => {
    if (!a) return;
    setSaving(true);
    try {
      const body = a.key_points.length ? { covered: [...covered] } : { score: manual ?? 0 };
      const res = await api<Attempt>(`/attempts/${a.id}/self-grade`, { method: "POST", body: JSON.stringify(body) });
      haptic("success");
      setA(res);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (error && !a) return <ErrorBox error={error} />;
  if (!a) return <Spinner />;

  const modelBlock = (
    <>
      <Section title={t("model_answer")}>
        <div className="card"><p className="pre">{a.model_answer || "—"}</p>
          {a.model_audio && <AuthAudio id={a.model_audio} />}
        </div>
      </Section>
      {a.explanation && <Section title={t("explanation")}><div className="card"><p className="pre">{a.explanation}</p></div></Section>}
    </>
  );

  const questionHead = (
    <div className="card question-card">
      <div className="muted small">{t("question")} {a.question.number}</div>
      <p className="question-text">{a.question.text}</p>
      {a.audio && <AuthAudio id={a.audio} label={t("your_answer")} />}
    </div>
  );

  if (a.state === "grading") {
    return <div>{questionHead}<Spinner label={t("ai_checking")} /></div>;
  }

  if (a.state !== "graded") {
    return (
      <div>
        {questionHead}
        {a.state === "failed_retry" && <div className="card warn">{t("ai_failed")}</div>}
        <div className="card">
          <h3>{t("self_check_title")}</h3>
          <p className="muted small">{t("self_check_hint")}</p>
        </div>
        {modelBlock}
        {a.key_points.length > 0 ? (
          <Section title={t("key_points")}>
            <ul className="checklist">
              {a.key_points.map((k) => (
                <li key={k.id}>
                  <label className={covered.has(k.id) ? "on" : ""}>
                    <input type="checkbox" checked={covered.has(k.id)} onChange={() => toggle(k.id)} />
                    <span>{k.text}</span>
                    {k.weight !== 1 && <span className="muted small">×{k.weight}</span>}
                  </label>
                </li>
              ))}
            </ul>
          </Section>
        ) : (
          <Section title={t("self_score_hint")}>
            <div className="score-picker">
              {SCORES.map((s) => (
                <button key={s} className={`chip-btn ${manual === s ? "active" : ""}`} onClick={() => setManual(s)}>{s}</button>
              ))}
            </div>
          </Section>
        )}
        {error && <p className="error-text center-text">{error}</p>}
        <div className="sticky-bottom">
          <button className="btn block" disabled={saving || (!a.key_points.length && manual == null)} onClick={grade}>
            {t("get_score")}
          </button>
        </div>
      </div>
    );
  }

  const coveredSet = new Set(a.covered);
  return (
    <div>
      <div className="card result-card">
        <ScoreRing score={a.score ?? 0} />
        {a.manual_score != null && <p className="muted small">{t("teacher_score")}: {a.manual_score}/5</p>}
      </div>
      {questionHead}
      {a.key_points.length > 0 && (
        <Section title={t("key_points")}>
          <ul className="points">
            {a.key_points.map((k) => (
              <li key={k.id} className={coveredSet.has(k.id) ? "ok" : "miss"}>
                <span>{coveredSet.has(k.id) ? "✓" : "✗"}</span> {k.text}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {a.wrong.length > 0 && (
        <Section title={t("wrong")}><ul className="points">{a.wrong.map((w, i) => <li key={i} className="miss"><span>!</span> {w}</li>)}</ul></Section>
      )}
      {a.comment && <Section title={t("comment")}><div className="card"><p className="pre">{a.comment}</p></div></Section>}
      {a.what_to_add && <Section title={t("what_to_add")}><div className="card"><p className="pre">{a.what_to_add}</p></div></Section>}
      {a.transcript && <Section title={t("transcript")}><div className="card"><p className="pre muted">{a.transcript}</p></div></Section>}
      {modelBlock}
      <div className="actions">
        {!compact && <button className="btn secondary" onClick={() => onAgain(a.question.id)}>↺ {t("try_again")}</button>}
        {onNext ? <button className="btn" onClick={onNext}>{nextLabel ?? t("next_question")} →</button>
          : <button className="btn" onClick={onList}>{t("to_list")}</button>}
      </div>
    </div>
  );
}
