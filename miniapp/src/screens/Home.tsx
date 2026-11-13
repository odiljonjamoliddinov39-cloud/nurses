import { useEffect, useState } from "react";
import { api, type Course, type CourseQuestions, type Me } from "../api";
import { fmtDate, pick, useLang, useT } from "../i18n";
import { ErrorBox, haptic, ScoreChip, Section, Spinner } from "../ui";

type Filter = "all" | "new" | "weak" | "fav" | "range";

export default function Home({ me, onOpen, onPaywall, onCourse, onMock, onLearn }: {
  me: Me; onOpen: (questionId: number) => void; onPaywall: () => void; onCourse: (id: number) => void;
  onMock: (courseId: number) => void; onLearn: (courseId: number) => void;
}) {
  const t = useT();
  const lang = useLang();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [data, setData] = useState<CourseQuestions | null>(null);
  const [error, setError] = useState("");
  const [topic, setTopic] = useState<number | "all">("all");
  const [filter, setFilter] = useState<Filter>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [allDone, setAllDone] = useState(false);

  const courseId = courses?.find((c) => c.id === me.course_id)?.id ?? courses?.[0]?.id;

  const load = () => {
    setError("");
    api<Course[]>("/courses").then(setCourses).catch((e) => setError(e.message));
  };
  useEffect(load, []);
  useEffect(() => {
    if (!courseId) return;
    setData(null);
    api<CourseQuestions>(`/courses/${courseId}/questions`).then(setData).catch((e) => setError(e.message));
  }, [courseId]);

  const toggleFav = (id: number, on: boolean) => {
    const set = (v: boolean) => setData((d) => d && { ...d, questions: d.questions.map((x) => (x.id === id ? { ...x, favourite: v } : x)) });
    haptic("light");
    set(on);
    api(`/questions/${id}/favourite`, { method: "POST", body: JSON.stringify({ on }) }).catch(() => set(!on));
  };

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!courses) return <Spinner />;

  const statusLine = me.status === "subscriber" && me.subscription
    ? `${t("status_subscriber")} · ${t("until", { d: fmtDate(me.subscription.ends_at) })}`
    : t(`status_${me.status}` as const);

  return (
    <div>
      <header className="hero">
        <div>
          <div className="muted small">{t("hello")},</div>
          <h1>{me.full_name ?? ""}</h1>
          <span className={`badge st-${me.status}`}>{statusLine}</span>
        </div>
      </header>

      {courses.length === 0 && <div className="card muted">{t("no_courses")}</div>}

      {courses.length > 1 && (
        <Section title={t("choose_course")}>
          <div className="chips-row">
            {courses.map((c) => (
              <button key={c.id} className={`chip-btn ${c.id === courseId ? "active" : ""}`} onClick={() => onCourse(c.id)}>
                {pick(c.name, lang)}
              </button>
            ))}
          </div>
        </Section>
      )}

      {courseId && !data && <Spinner />}
      {data && (() => {
        const answered = data.questions.filter((q) => q.best_score != null);
        const avg = answered.length ? answered.reduce((s, q) => s + (q.best_score ?? 0), 0) / answered.length : null;
        const lo = parseInt(from, 10), hi = parseInt(to, 10);
        const passes = (q: (typeof data.questions)[number]) =>
          filter === "all" ? true
          : filter === "new" ? q.best_score == null
          : filter === "weak" ? q.best_score != null && q.best_score < 3
          : filter === "fav" ? q.favourite
          : (Number.isNaN(lo) || q.number >= lo) && (Number.isNaN(hi) || q.number <= hi);
        const visible = data.questions.filter((q) =>
          (topic === "all" || q.topic_id === topic || (topic === -1 && q.topic_id == null)) && passes(q));
        const hasOpen = data.questions.some((q) => !q.locked);
        const resume = data.questions.find((q) => !q.locked && q.best_score == null);
        const filters: [Filter, string][] = [
          ["all", t("filter_all")], ["new", t("filter_new")], ["weak", t("filter_weak")],
          ["fav", `★ ${t("filter_fav")}`], ["range", t("filter_range")],
        ];
        const hasNoTopic = data.questions.some((q) => q.topic_id == null);
        return (
          <>
            <div className="card course-card">
              <h2>{pick(data.course.name, lang)}</h2>
              <div className="stats">
                <div><b>{answered.length}/{data.questions.length}</b><span>{t("answered")}</span></div>
                <div><b>{avg == null ? "—" : avg.toFixed(1)}</b><span>{t("average")}</span></div>
              </div>
              <div className="progress"><div style={{ width: `${data.questions.length ? (answered.length / data.questions.length) * 100 : 0}%` }} /></div>
            </div>

            {!data.full_access && data.questions.some((q) => q.locked) && (
              <div className="card promo">
                <p>{t("free_hint", { n: me.free_questions })}</p>
                {me.status !== "pending" && (
                  <button className="btn" onClick={onPaywall}>{me.status === "expired" ? t("renew") : t("subscribe")}</button>
                )}
                {me.status === "pending" && <p className="muted small">{t("pending_exists")}</p>}
              </div>
            )}

            {hasOpen && (
              <div className="modes">
                <button className="btn" onClick={() => (resume ? onOpen(resume.id) : setAllDone(true))}>▶ {t("continue_btn")}</button>
                <button className="btn secondary" onClick={() => onMock(data.course.id)}>🎓 {t("mock_exam")}</button>
                <button className="btn secondary" onClick={() => onLearn(data.course.id)}>🎧 {t("learn_mode")}</button>
              </div>
            )}
            {allDone && <p className="muted small center-text">{t("all_done")}</p>}

            {data.questions.length > 0 && (
              <div className="chips-row scroll">
                {filters.map(([k, label]) => (
                  <button key={k} className={`chip-btn ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)}>{label}</button>
                ))}
              </div>
            )}
            {filter === "range" && (
              <div className="range-row">
                <input inputMode="numeric" placeholder={t("range_from")} value={from} onChange={(e) => setFrom(e.target.value.replace(/\D/g, ""))} />
                <span>–</span>
                <input inputMode="numeric" placeholder={t("range_to")} value={to} onChange={(e) => setTo(e.target.value.replace(/\D/g, ""))} />
              </div>
            )}

            {data.topics.length > 0 && (
              <div className="chips-row scroll">
                <button className={`chip-btn ${topic === "all" ? "active" : ""}`} onClick={() => setTopic("all")}>
                  {t("tab_questions")} · {data.questions.length}
                </button>
                {data.topics.map((tp) => (
                  <button key={tp.id} className={`chip-btn ${topic === tp.id ? "active" : ""}`} onClick={() => setTopic(tp.id)}>
                    {tp.name}
                  </button>
                ))}
                {hasNoTopic && (
                  <button className={`chip-btn ${topic === -1 ? "active" : ""}`} onClick={() => setTopic(-1)}>{t("other")}</button>
                )}
              </div>
            )}

            {data.questions.length === 0 && <div className="card muted">{t("no_questions")}</div>}
            {data.questions.length > 0 && visible.length === 0 && <div className="card muted center-text">{t("nothing_here")}</div>}
            <ul className="qlist">
              {visible.map((q) => (
                <li key={q.id} className="qrow">
                  <button className={`qitem ${q.locked ? "locked" : ""}`} onClick={() => (q.locked ? onPaywall() : onOpen(q.id))}>
                    <span className="qnum">{q.number}</span>
                    <span className="qtext">{q.text}</span>
                    {q.locked ? <span className="lock">🔒</span> : <ScoreChip score={q.best_score} />}
                  </button>
                  {!q.locked && (
                    <button className={`star ${q.favourite ? "on" : ""}`} aria-label={t("favourite")}
                      onClick={() => toggleFav(q.id, !q.favourite)}>{q.favourite ? "★" : "☆"}</button>
                  )}
                </li>
              ))}
            </ul>
          </>
        );
      })()}
    </div>
  );
}
